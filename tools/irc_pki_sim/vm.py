"""Archive the ceremony to an ISO and re-verify it inside a QEMU guest.

The guest is a stock distribution kernel plus a ~2 MB initramfs containing
only static busybox. It mounts the ISO read-only and, with code that shares
nothing with the Python verifier, (a) checks every file against the SHA-256
manifest and (b) recomputes the server log's hash chain line by line. The host
compares the guest's chain head with its own. No network, no disk, no Python
in the guest.
"""

from __future__ import annotations

import glob
import gzip
import hashlib
import io
import lzma
import os
import re
import shutil
import subprocess

INIT = r"""#!/bin/busybox sh
/bin/busybox --install -s /bin
mount -t proc proc /proc
mount -t sysfs sys /sys
mount -t devtmpfs dev /dev
[ -f /isofs.ko ] && insmod /isofs.ko
mkdir -p /mnt
if mount -t iso9660 -o ro /dev/sr0 /mnt; then
  cd /mnt
  if sha256sum -c MANIFEST.sha256 > /tmp/manifest.out 2>&1; then
    echo "VM_MANIFEST_OK $(wc -l < MANIFEST.sha256)"
  else
    grep -v ': OK$' /tmp/manifest.out
    echo "VM_MANIFEST_FAIL"
  fi
  sh /mnt/chain.sh /mnt/irc/server.log
else
  echo "VM_MOUNT_FAIL"
fi
echo "VM_DONE"
poweroff -f
"""

CHAIN_SH = r"""# Recompute the ircpki log hash chain: h_i = sha256(h_{i-1} "\n" content_i)
TAB=$(printf '\t')
prev=$(printf '%s' 'ircpki-log/1' | sha256sum | cut -d' ' -f1)
n=0
bad=0
while IFS= read -r line; do
  n=$((n+1))
  h=${line##*$TAB}
  content=${line%$TAB*}
  calc=$(printf '%s\n%s' "$prev" "$content" | sha256sum | cut -d' ' -f1)
  if [ "$calc" != "$h" ]; then bad=$((bad+1)); echo "VM_CHAIN_BAD line $n"; fi
  prev=$h
done < "$1"
if [ $bad -eq 0 ]; then echo "VM_CHAIN_OK $n $prev"; else echo "VM_CHAIN_FAIL $bad"; fi
"""


class VmUnavailable(RuntimeError):
    pass


def _cpio_newc(entries: list[tuple[str, int, bytes]]) -> bytes:
    """Minimal 'newc' cpio writer (no host cpio needed). entries: (path, mode, data)."""
    out = io.BytesIO()
    for ino, (name, mode, data) in enumerate(entries + [("TRAILER!!!", 0, b"")], 1):
        nb = name.encode() + b"\0"
        hdr = "070701" + "".join(f"{v:08x}" for v in (
            ino, mode, 0, 0, 1, 0, len(data), 0, 0, 0, 0, len(nb), 0))
        out.write(hdr.encode() + nb)
        out.write(b"\0" * ((4 - (110 + len(nb)) % 4) % 4))
        out.write(data)
        out.write(b"\0" * ((4 - len(data) % 4) % 4))
    return out.getvalue()


def _kernel_release(kernel: str) -> str | None:
    m = re.search(r"vmlinuz-(.+)$", os.path.realpath(kernel))
    return m.group(1) if m else None


def _isofs_module(release: str | None) -> bytes | None:
    """iso9660 is a module on most distro kernels; returns it decompressed,
    or None if the kernel has it built in."""
    if release:
        cfg = f"/boot/config-{release}"
        if os.path.exists(cfg) and "CONFIG_ISO9660_FS=y" in open(cfg).read():
            return None
    pattern = f"/lib/modules/{release or '*'}/kernel/fs/isofs/isofs.ko*"
    for path in sorted(glob.glob(pattern)):
        raw = open(path, "rb").read()
        if path.endswith(".ko"):
            return raw
        if path.endswith(".xz"):
            return lzma.decompress(raw)
        if path.endswith(".gz"):
            return gzip.decompress(raw)
        if path.endswith(".zst"):
            try:
                import zstandard
            except ImportError:
                raise VmUnavailable("isofs.ko is zstd-compressed: pip install zstandard") from None
            return zstandard.ZstdDecompressor().stream_reader(io.BytesIO(raw)).read()
    raise VmUnavailable(f"no isofs module found ({pattern})")


def _has_interp(elf: bytes) -> bool:
    """True if a 64-bit little-endian ELF has a PT_INTERP header (i.e. is dynamic)."""
    import struct
    if elf[:4] != b"\x7fELF" or elf[4] != 2 or elf[5] != 1:
        raise VmUnavailable("busybox is not a 64-bit little-endian ELF")
    phoff, = struct.unpack_from("<Q", elf, 0x20)
    phentsize, phnum = struct.unpack_from("<HH", elf, 0x36)
    return any(struct.unpack_from("<I", elf, phoff + i * phentsize)[0] == 3 for i in range(phnum))


def build_initramfs(path: str, kernel: str) -> None:
    bb = shutil.which("busybox") or "/bin/busybox"
    if not os.path.exists(bb):
        raise VmUnavailable("static busybox not found (apt install busybox-static)")
    with open(bb, "rb") as f:
        busybox = f.read()
    if _has_interp(busybox):
        raise VmUnavailable("busybox is dynamically linked; need busybox-static")
    entries = [("bin", 0o40755, b""), ("dev", 0o40755, b""), ("proc", 0o40755, b""),
               ("sys", 0o40755, b""), ("mnt", 0o40755, b""), ("tmp", 0o41777, b""),
               ("bin/busybox", 0o100755, busybox), ("init", 0o100755, INIT.encode())]
    mod = _isofs_module(_kernel_release(kernel))
    if mod:
        entries.append(("isofs.ko", 0o100644, mod))
    with open(path, "wb") as f:
        f.write(gzip.compress(_cpio_newc(entries), 6))


def build_iso(run_dir: str, iso_path: str, report: dict) -> list[str]:
    """Collects pki/, the server log, the script and the verifier report."""
    if not shutil.which("xorriso"):
        raise VmUnavailable("xorriso not found")
    stage = os.path.join(run_dir, "vm", "iso")
    shutil.rmtree(stage, ignore_errors=True)
    os.makedirs(stage)
    for sub in ("pki", "irc"):
        shutil.copytree(os.path.join(run_dir, sub), os.path.join(stage, sub))
    shutil.copy(os.path.join(run_dir, "script.json"), stage)
    with open(os.path.join(stage, "verify-report.json"), "w") as f:
        import json
        json.dump(report, f, indent=2, sort_keys=True)
    with open(os.path.join(stage, "chain.sh"), "w") as f:
        f.write(CHAIN_SH)
    files = []
    for root, _, names in os.walk(stage):
        for n in sorted(names):
            files.append(os.path.relpath(os.path.join(root, n), stage))
    with open(os.path.join(stage, "MANIFEST.sha256"), "w") as f:
        for rel in sorted(files):
            with open(os.path.join(stage, rel), "rb") as g:
                f.write(f"{hashlib.sha256(g.read()).hexdigest()}  {rel}\n")
    subprocess.run(["xorriso", "-as", "mkisofs", "-quiet", "-r", "-V", "IRCPKI_CEREMONY",
                    "-o", iso_path, stage], check=True, capture_output=True)
    return sorted(files)


def run_vm(iso: str, initrd: str, kernel: str, timeout: int = 180) -> str:
    qemu = shutil.which("qemu-system-x86_64")
    if not qemu:
        raise VmUnavailable("qemu-system-x86_64 not found")
    accel = "kvm" if os.access("/dev/kvm", os.R_OK | os.W_OK) else "tcg"
    cmd = [qemu, "-machine", f"pc,accel={accel}", "-m", "256", "-nographic", "-no-reboot",
           "-nic", "none", "-kernel", kernel, "-initrd", initrd,
           "-append", "console=ttyS0 quiet panic=-1", "-cdrom", iso]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    return r.stdout + r.stderr


def verify_in_vm(run_dir: str, report: dict, kernel: str = "/boot/vmlinuz") -> dict:
    if not os.access(kernel, os.R_OK):
        raise VmUnavailable(f"kernel {kernel} not readable")
    vm_dir = os.path.join(run_dir, "vm")
    os.makedirs(vm_dir, exist_ok=True)
    iso = os.path.join(run_dir, "ceremony.iso")
    initrd = os.path.join(vm_dir, "initrd.gz")
    files = build_iso(run_dir, iso, report)
    build_initramfs(initrd, kernel)
    out = run_vm(iso, initrd, kernel)
    with open(os.path.join(vm_dir, "console.log"), "w") as f:
        f.write(out)
    m_ok = re.search(r"VM_MANIFEST_OK (\d+)", out)
    c_ok = re.search(r"VM_CHAIN_OK (\d+) ([0-9a-f]{64})", out)
    result = {
        "iso": os.path.relpath(iso, run_dir),
        "iso_sha256": hashlib.sha256(open(iso, "rb").read()).hexdigest(),
        "manifest_ok": bool(m_ok) and int(m_ok.group(1)) == len(files),
        "files": len(files),
        "chain_ok": bool(c_ok) and c_ok.group(2) == report.get("log_head"),
        "guest_chain_head": c_ok.group(2) if c_ok else None,
        "guest_lines": int(c_ok.group(1)) if c_ok else None,
        "finished": "VM_DONE" in out,
    }
    result["ok"] = result["manifest_ok"] and result["chain_ok"] and result["finished"]
    return result

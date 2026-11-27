"""Validation for operator-supplied paths, ports and names.

Every path that reaches open(), shutil or a subprocess argv is first resolved
with realpath() and confined to a known base directory, so a run directory
argument can't steer reads or writes outside the run (``..``, symlinks). Paths
handed to xorriso or qemu are absolute, so they can never be parsed as options.
"""

from __future__ import annotations

import argparse
import os
import re

_KERNEL_RE = re.compile(r"^vmlinuz(?:-[A-Za-z0-9._+-]{1,64})?$")
RELEASE_RE = re.compile(r"^[A-Za-z0-9._+-]{1,64}$")
_METHOD_RE = re.compile(r"^[a-z]{1,16}\.[a-z]{1,16}$")


def _clean(p: str) -> str:
    if not isinstance(p, str) or not p or "\0" in p:
        raise ValueError("path is empty or contains NUL")
    return os.path.realpath(p)


def inside(base: str, *parts: str) -> str:
    """Join parts onto base, resolve it, and refuse anything that escapes base."""
    root = _clean(base)
    full = os.path.realpath(os.path.join(root, *parts))
    if os.path.commonpath([root, full]) != root:
        raise ValueError(f"{os.path.join(*parts)!r} escapes {root}")
    return full


def run_dir(p: str, must_exist: bool = True) -> str:
    """A run directory; when it must exist it has to look like a finished run."""
    d = _clean(p)
    if must_exist:
        for need in (("pki", "root.der"), ("pki", "roster.json"), ("irc", "server.log")):
            if not os.path.isfile(inside(d, *need)):
                raise ValueError(f"{d} is not a run directory (missing {os.path.join(*need)})")
    elif os.path.exists(d) and not os.path.isdir(d):
        raise ValueError(f"{d} exists and is not a directory")
    return d


def kernel(p: str) -> str:
    k = _clean(p)
    if not _KERNEL_RE.match(os.path.basename(k)) or not os.path.isfile(k):
        raise ValueError(f"{k} is not a vmlinuz kernel image")
    return k


def port(p: str | int) -> int:
    n = int(p)
    if not 1 <= n <= 65535:
        raise ValueError(f"port {n} out of range")
    return n


def rpc_method(m: str) -> str:
    if not _METHOD_RE.match(m):
        raise ValueError(f"{m!r} is not a method name like release.status")
    return m


def argtype(fn):
    """Adapt a validator for argparse so bad input is a usage error."""
    def wrapped(v):
        try:
            return fn(v)
        except ValueError as e:
            raise argparse.ArgumentTypeError(str(e)) from None
    wrapped.__name__ = fn.__name__
    return wrapped

#!/usr/bin/env python3
"""Simulate a PKCS#11 key-signing ceremony between actors on a logged IRC server.

    python3 irc_pki_sim.py run   [--m 3 --n 3 --devs 5 --hsm 3 --release-m 3] [--vm] [--serve]
    python3 irc_pki_sim.py verify RUN_DIR [--root-fp HEX]
    python3 irc_pki_sim.py vm     RUN_DIR
    python3 irc_pki_sim.py rpc    PORT METHOD [JSON_PARAMS]
    python3 irc_pki_sim.py grammar

Cast (defaults): ``ca`` (CA operator, root key in --hsm SoftHSM replicas),
``custodian1..n`` (each holds one Shamir share of the CA token PIN; m are
needed to unlock), ``secmgr`` (approves developer certs; its own cert and its
revocation need two custodian approvals), ``dev1..5`` and ``releasebot``
(serves the JSON-RPC release-approval API). See README.md.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import multiprocessing as mp
import os
import shutil
import sys
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from cryptography import x509  # noqa: E402
from cryptography.hazmat.primitives.asymmetric import ec  # noqa: E402

import grammar as g  # noqa: E402
from actors import ROOT_CN, ROOT_OU, agent_main, replica_main  # noqa: E402
from ircnet import IrcClient, IrcServer  # noqa: E402
from ledger import Ledger, Policy, file_loader, load_roster  # noqa: E402
from pkicrypto import (CURVE, build_cert, compress, new_ca_secret, pin_from_secret,  # noqa: E402
                       sha256, shamir_split, software_signer, spki_der)
from scenario import Cast, default_script  # noqa: E402
from verify import verify_run  # noqa: E402


def rpc_call(port: int, method: str, params: dict | None = None, timeout: float = 30) -> dict:
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params or {}}).encode()
    req = urllib.request.Request(f"http://127.0.0.1:{port}/rpc", data=body,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


class Auditor:
    """Read-only IRC observer running its own ledger, used to await progress."""

    def __init__(self, policy: Policy, pki: str):
        self.policy, self.pki = policy, pki
        self.ledger: Ledger | None = None
        self.client = IrcClient("auditor", policy.channel)
        self.changed = asyncio.Event()
        self.task: asyncio.Task | None = None

    async def start(self, port: int) -> None:
        with open(os.path.join(self.pki, "root.der"), "rb") as f:
            root_der = f.read()
        roster = load_roster(self.pki, x509.load_der_x509_certificate(root_der).public_key())
        self.ledger = Ledger(self.policy, roster, root_der, file_loader(self.pki))
        await self.client.connect("127.0.0.1", port)
        self.task = asyncio.create_task(self._run())

    async def _run(self) -> None:
        async for nick, text in self.client.messages():
            v = self.ledger.apply(nick, text)
            flag = {"accepted": "+", "rejected": "~"}.get(v.status, "!")
            print(f"  {flag} <{nick}> {_short(text)}"
                  + (f"   [{v.status}: {v.reason}]" if not v.ok else ""), flush=True)
            self.changed.set()

    async def until(self, pred, what: str, timeout: float = 30.0):
        deadline = time.monotonic() + timeout
        while True:
            r = pred(self.ledger)
            if r:
                return r
            left = deadline - time.monotonic()
            if left <= 0:
                raise TimeoutError(f"timed out waiting for: {what}")
            self.changed.clear()
            try:
                await asyncio.wait_for(self.changed.wait(), left)
            except asyncio.TimeoutError:
                pass


def _short(text: str) -> str:
    import re
    return re.sub(r"[0-9a-f]{24,}", lambda m: m.group()[:10] + "…", text)


class Simulation:
    def __init__(self, run_dir: str, policy: Policy, cast: Cast, hsm_replicas: int,
                 script: list[dict] | None = None):
        self.run_dir = os.path.abspath(run_dir)
        self.pki = os.path.join(self.run_dir, "pki")
        self.policy, self.cast, self.n_hsm = policy, cast, hsm_replicas
        self.script = script if script is not None else default_script(cast, policy, hsm_replicas)
        self.ctx = mp.get_context("spawn")
        self.agents: dict[str, dict] = {}
        self.replicas: list[dict] = []
        self.events: dict[str, asyncio.Queue] = {}
        self.errors: list[dict] = []
        self.server: IrcServer | None = None
        self.auditor: Auditor | None = None
        self.rpc_port = 0
        self.extra: dict = {}

    # ------------------------------------------------------------ processes
    def _spawn(self) -> None:
        for i in range(self.n_hsm):
            ctl_a, ctl_b = self.ctx.Pipe()
            ca_a, ca_b = self.ctx.Pipe()
            p = self.ctx.Process(target=replica_main, name=f"hsm-{i}",
                                 args=(i, os.path.join(self.run_dir, "hsm", f"replica{i}"), ctl_b, ca_b))
            p.start()
            self.replicas.append({"proc": p, "ctl": ctl_a, "ca_end": ca_a})
        for name, role in self.cast.roles().items():
            a, b = self.ctx.Pipe()
            reps = [r["ca_end"] for r in self.replicas] if role == "ca" else []
            p = self.ctx.Process(target=agent_main, name=name, args=(
                name, role, os.path.join(self.run_dir, "agents", name), self.run_dir,
                self.policy.__dict__, b, reps))
            p.start()
            self.agents[name] = {"proc": p, "ctl": a, "role": role}
            self.events[name] = asyncio.Queue()
            asyncio.get_running_loop().add_reader(a.fileno(), self._pump, name)

    def _pump(self, name: str) -> None:
        conn = self.agents[name]["ctl"]
        try:
            while conn.poll():
                ev = conn.recv()
                if ev.get("event") == "replica_health":
                    self.extra["replica_health"] = {str(k): v for k, v in ev["health"].items()}
                if ev.get("event") == "error":
                    self.errors.append(ev)
                    print(f"  !! {name}: {ev['error']}\n{ev.get('trace', '')}", file=sys.stderr)
                self.events[name].put_nowait(ev)
        except (EOFError, OSError):
            asyncio.get_running_loop().remove_reader(conn.fileno())

    async def expect(self, name: str, event: str, timeout: float = 60.0) -> dict:
        deadline = time.monotonic() + timeout
        while True:
            ev = await asyncio.wait_for(self.events[name].get(), max(0.01, deadline - time.monotonic()))
            if ev.get("event") == event:
                return ev
            if ev.get("event") == "error":
                raise RuntimeError(f"{name}: {ev['error']}")

    def send(self, name: str, **op) -> None:
        self.agents[name]["ctl"].send(op)

    # -------------------------------------------------------------- ceremony
    async def ceremony(self) -> str:
        """Root key ceremony. The root key exists in memory only here, long
        enough to self-sign, certify the ceremony roles and be loaded into each
        replica as a non-extractable object; the CA PIN is split m-of-n and
        only the shares leave this function."""
        pubs = {name: await self.expect(name, "pubkey") for name in self.agents}
        root = ec.generate_private_key(CURVE)
        sign = software_signer(root)
        root_spki = spki_der(root.public_key())
        os.makedirs(os.path.join(self.pki, "certs"), exist_ok=True)
        os.makedirs(os.path.join(self.pki, "crl"), exist_ok=True)
        root_der = build_cert(serial=1, subject_cn=ROOT_CN, subject_ou=ROOT_OU, subject_spki=root_spki,
                              issuer_cn=ROOT_CN, issuer_ou=ROOT_OU, issuer_spki=root_spki,
                              signer=sign, is_ca=True, days=3650)
        with open(os.path.join(self.pki, "root.der"), "wb") as f:
            f.write(root_der)
        roles = self.cast.roles()
        ceremony = [self.cast.ca, *self.cast.custodians, self.cast.releasebot]
        serials = {}
        for serial, name in enumerate(ceremony, start=2):
            der = build_cert(serial=serial, subject_cn=name, subject_ou=roles[name],
                             subject_spki=bytes.fromhex(pubs[name]["spki"]), issuer_cn=ROOT_CN,
                             issuer_ou=ROOT_OU, issuer_spki=root_spki, signer=sign, is_ca=False)
            with open(os.path.join(self.pki, "certs", f"{serial}.der"), "wb") as f:
                f.write(der)
            serials[name] = serial
        roster = {"version": 1, "roles": roles, "ceremony_serials": serials,
                  "policy": self.policy.__dict__, "hsm_replicas": self.n_hsm,
                  "cast": {k: list(v) if isinstance(v, tuple) else v
                           for k, v in self.cast.__dict__.items()}}
        raw = json.dumps(roster, indent=2, sort_keys=True).encode()
        with open(os.path.join(self.pki, "roster.json"), "wb") as f:
            f.write(raw)
        with open(os.path.join(self.pki, "roster.sig"), "w") as f:
            f.write(sign(sha256(b"ircpki-roster/1\n" + raw)).hex())

        secret = new_ca_secret()
        d = root.private_numbers().private_value
        for i, r in enumerate(self.replicas):
            r["ctl"].send(("provision", pin_from_secret(secret), d))
            ok, pub, locked = r["ctl"].recv()
            if ok != "ok" or pub != compress(root.public_key()) or not locked:
                raise RuntimeError(f"replica {i} failed to provision: {ok} {pub}")
        shares = shamir_split(secret, self.policy.m, self.policy.n)
        for (x, y), name in zip(shares, self.cast.custodians):
            self.send(name, op="store_share", x=x, y=y)
            await self.expect(name, "share_stored")
        del root, sign, secret, d, shares
        fp = sha256(root_der).hex()
        print(f"root certificate sha256 (pin this out of band): {fp}")
        return fp

    # ----------------------------------------------------------------- steps
    async def step(self, st: dict) -> None:
        A, c = self.auditor, self.cast
        do = st["do"]
        print(f"\n== {do} {json.dumps({k: v for k, v in st.items() if k != 'do'})}")
        if do == "unlock":
            self.send(c.ca, op="unlock")
            await A.until(lambda L: L.unlocked, "CA token unlocked")
        elif do == "enroll":
            who = st["who"]
            self.send(who, op="request_cert")
            ref = await A.until(lambda L: next((k for k, r in L.requests.items() if r.kind == "cert"
                                                and r.subject == who and not r.done), None),
                                f"cert request from {who}")
            for a in st["approvers"]:
                self.send(a, op="approve_cert", ref=ref)
                await A.until(lambda L: a in L.requests[ref].approvals, f"{a} approves {ref}")
            await A.until(lambda L: L.active(who) is not None, f"cert issued to {who}")
            await self.expect(who, "cert_installed")
        elif do == "fail_primary":
            p = self.replicas[0]["proc"]
            p.terminate()
            p.join(5)
            print(f"   killed primary CA HSM replica (pid {p.pid})")
        elif do == "release":
            art_dir = os.path.join(self.run_dir, "releases")
            os.makedirs(os.path.join(art_dir, "src"), exist_ok=True)
            honest = os.urandom(4096) + st["version"].encode()
            src = os.path.join(art_dir, "src", f"app-{st['version']}.tar")
            with open(src, "wb") as f:
                f.write(honest)
            art = os.path.join(art_dir, f"app-{st['version']}.tar")
            with open(art, "wb") as f:
                f.write(honest + (b"\nbackdoor()\n" if st.get("tamper") else b""))
            res = await asyncio.to_thread(rpc_call, self.rpc_port, "release.submit",
                                          {"version": st["version"], "artifact": art})
            if "error" in res:
                raise RuntimeError(f"release.submit: {res['error']}")
            rid = res["result"]["id"]
            for r in st["reviewers"]:
                n_before = len(A.ledger.history)
                self.send(r, op="review_release", ref=rid, artifact=src)
                await A.until(lambda L: any(v.msg and v.msg.actor == r and v.msg.ref == rid
                                            for _, _, v in L.history[n_before:]),
                              f"{r} reviews {rid}")
            if st["expect"] == "published":
                self.send(c.secmgr, op="approve_release", ref=rid)
                await A.until(lambda L: L.releases[rid].published, f"{rid} published")
            status = (await asyncio.to_thread(rpc_call, self.rpc_port, "release.status",
                                              {"id": rid}))["result"]
            print(f"   rpc release.status -> {status['state']} "
                  f"devs={status['developer_approvals']} sec={status['security_approvals']}")
            if status["state"] != st["expect"]:
                raise AssertionError(f"release {rid} is {status['state']}, expected {st['expect']}")
            self.extra.setdefault("releases", {})[rid] = status
        elif do == "revoke":
            who = st["who"]
            serial = A.ledger.active(who).serial
            self.send(st["by"], op="request_revocation", target=who, reason=st.get("reason", "compromise"))
            ref = await A.until(lambda L: next((k for k, r in L.requests.items()
                                                if r.kind == "revocation" and r.subject == who
                                                and not r.done), None), f"revocation of {who}")
            for a in st["approvers"]:
                self.send(a, op="approve_revocation", ref=ref)
                await A.until(lambda L: a in L.requests[ref].approvals, f"{a} approves {ref}")
            await A.until(lambda L: L.certs[serial].revoked, f"{who} revoked")
        elif do == "rpc_checks":
            # Exercise the API's error paths; none of these may touch the log.
            outside = os.path.join(self.run_dir, "script.json")
            calls = {"list": ("release.list", {}),
                     "unknown_method": ("release.delete", {"id": "x"}),
                     "unknown_id": ("release.status", {"id": "rel-nope"}),
                     "outside_artifact": ("release.submit", {"version": "9.9.9", "artifact": outside}),
                     "evidence": ("release.evidence", {"id": next(iter(A.ledger.releases))})}
            out = {}
            for k, (method, params) in calls.items():
                out[k] = await asyncio.to_thread(rpc_call, self.rpc_port, method, params)
            self.extra["rpc_checks"] = out
            print("   " + ", ".join(f"{k}: {'error ' + str(v['error']['code']) if 'error' in v else 'ok'}"
                                    for k, v in out.items()))
        else:
            raise ValueError(f"unknown step {do}")

    # ------------------------------------------------------------------- run
    async def run(self, serve: float = 0) -> dict:
        if os.path.exists(self.run_dir):
            shutil.rmtree(self.run_dir)
        os.makedirs(self.run_dir)
        with open(os.path.join(self.run_dir, "script.json"), "w") as f:
            json.dump(self.script, f, indent=2)
        self.server = IrcServer(os.path.join(self.run_dir, "irc", "server.log"))
        port = await self.server.start()
        print(f"irc server on 127.0.0.1:{port}, log {self.server.log.path}")
        self._spawn()
        leaks = {}
        try:
            fp = await self.ceremony()
            self.auditor = Auditor(self.policy, self.pki)
            await self.auditor.start(port)
            for name in self.agents:
                self.send(name, op="start", port=port)
            for name in self.agents:
                ev = await self.expect(name, "ready")
                if "rpc_port" in ev:
                    self.rpc_port = ev["rpc_port"]
            print(f"release approval JSON-RPC on 127.0.0.1:{self.rpc_port}/rpc")
            for st in self.script:
                await self.step(st)
            if serve:
                print(f"\nserving for {serve:.0f}s; try:\n  python3 {sys.argv[0]} rpc {self.rpc_port} release.list")
                await asyncio.sleep(serve)
            await asyncio.sleep(0.3)
            for name in self.agents:
                self.send(name, op="leakcheck")
            for name in self.agents:
                ev = await self.expect(name, "leakcheck")
                leaks[name] = {"clean": ev["clean"], "hits": ev["hits"], "checked": ev["checked"]}
        finally:
            await self.shutdown()
        report = verify_run(self.run_dir, fp)
        report["secrets_leak_check"] = leaks
        report["agent_errors"] = [{"from": e["from"], "op": e.get("op"), "error": e["error"]}
                                  for e in self.errors]
        report["rpc"] = self.extra.get("releases", {})
        report["rpc_checks"] = self.extra.get("rpc_checks", {})
        report["replica_health"] = self.extra.get("replica_health", {})
        if not all(v["clean"] for v in leaks.values()) or self.errors:
            report["ok"] = False
        return report

    async def shutdown(self) -> None:
        loop = asyncio.get_running_loop()
        for name, a in self.agents.items():
            try:
                a["ctl"].send({"op": "stop"})
            except OSError:
                pass
        for name, a in self.agents.items():
            await asyncio.to_thread(a["proc"].join, 10)
            if a["proc"].is_alive():
                a["proc"].kill()
            try:
                loop.remove_reader(a["ctl"].fileno())
            except (ValueError, OSError):
                pass
        for r in self.replicas:
            if r["proc"].is_alive():
                try:
                    r["ctl"].send(("stop",))
                except OSError:
                    pass
                await asyncio.to_thread(r["proc"].join, 5)
                if r["proc"].is_alive():
                    r["proc"].kill()
        if self.auditor:
            await self.auditor.client.close()
            if self.auditor.task:
                self.auditor.task.cancel()
        if self.server:
            await self.server.stop()


def print_report(report: dict) -> None:
    print("\n========== verification ==========")
    print(f"log lines {report['log_lines']}, sentences {report['sentences']}, "
          f"script steps {report['script_steps']}")
    print(f"log head  {report['log_head']}")
    print(f"root      {report['root_sha256']}")
    for r in report["rejected_but_expected_to_be_harmless"]:
        print(f"rejected  {r}")
    for name, lc in sorted(report.get("secrets_leak_check", {}).items()):
        if not lc["clean"]:
            print(f"LEAK      {name}: {lc['hits']}")
    for e in report["errors"] + [f"{e['from']}: {e['error']}" for e in report.get("agent_errors", [])]:
        print(f"ERROR     {e}")
    if "vm" in report:
        vm = report["vm"]
        print(f"vm        {'ok' if vm.get('ok') else 'FAILED'}: {vm}")
    print("RESULT    " + ("PASS" if report["ok"] else "FAIL"))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="run the full ceremony and verify it")
    r.add_argument("--dir", default="run")
    r.add_argument("--m", type=int, default=3, help="custodian shares needed to unlock the CA")
    r.add_argument("--n", type=int, default=3, help="custodians (shares issued)")
    r.add_argument("--devs", type=int, default=5)
    r.add_argument("--hsm", type=int, default=3, help="SoftHSM replicas holding the root key")
    r.add_argument("--release-m", type=int, default=3, help="developer approvals per release")
    r.add_argument("--sm-approvals", type=int, default=2,
                   help="custodian approvals for a security-manager cert or revocation")
    r.add_argument("--vm", action="store_true", help="also re-verify the archive inside QEMU")
    r.add_argument("--kernel", default="/boot/vmlinuz")
    r.add_argument("--serve", type=float, default=0, help="keep the RPC up N seconds after the script")
    v = sub.add_parser("verify", help="verify a finished run directory offline")
    v.add_argument("dir")
    v.add_argument("--root-fp")
    q = sub.add_parser("vm", help="archive a run to ISO and verify it inside QEMU")
    q.add_argument("dir")
    q.add_argument("--kernel", default="/boot/vmlinuz")
    c = sub.add_parser("rpc", help="call the release-approval JSON-RPC")
    c.add_argument("port", type=int)
    c.add_argument("method")
    c.add_argument("params", nargs="?", default="{}")
    sub.add_parser("grammar", help="print the grammar and its LL(1) table size")
    a = ap.parse_args(argv)

    if a.cmd == "grammar":
        print(g.__doc__)
        print(f"LL(1) table: {len(g.TABLE)} entries, no conflicts")
        return 0
    if a.cmd == "rpc":
        print(json.dumps(rpc_call(a.port, a.method, json.loads(a.params)), indent=2))
        return 0
    if a.cmd == "verify":
        rep = verify_run(a.dir, a.root_fp)
        print_report(rep)
        return 0 if rep["ok"] else 1
    if a.cmd == "vm":
        from vm import verify_in_vm
        rep = verify_run(a.dir)
        rep["vm"] = verify_in_vm(a.dir, rep, a.kernel)
        rep["ok"] = rep["ok"] and rep["vm"]["ok"]
        print_report(rep)
        return 0 if rep["ok"] else 1

    policy = Policy(m=a.m, n=a.n, sm_approvals=a.sm_approvals, release_m=a.release_m)
    cast = Cast.make(a.n, a.devs)
    sim = Simulation(a.dir, policy, cast, a.hsm)
    report = asyncio.run(sim.run(serve=a.serve))
    if a.vm:
        from vm import VmUnavailable, verify_in_vm
        try:
            report["vm"] = verify_in_vm(sim.run_dir, report, a.kernel)
            report["ok"] = report["ok"] and report["vm"]["ok"]
        except VmUnavailable as e:
            report["vm"] = {"ok": False, "skipped": str(e)}
            report["ok"] = False
    with open(os.path.join(sim.run_dir, "report.json"), "w") as f:
        json.dump(report, f, indent=2, sort_keys=True, default=str)
    print_report(report)
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())

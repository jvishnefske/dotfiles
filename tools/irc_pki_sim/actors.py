"""Actor processes and HSM replica processes.

Each actor is a separate spawned OS process with its own SoftHSM token
directory, its own vault file and its own IRC connection. The orchestrator
talks to an actor only through a control pipe carrying *intents* ("approve
request #r-dev1-1"); the actor builds, signs and sends the sentence itself, so
no other process ever holds an actor's key, PIN or passphrase.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import hashlib
import json
import os
import secrets
import traceback
from multiprocessing.connection import Connection, wait

from cryptography import x509
from cryptography.hazmat.primitives.asymmetric import ec

import grammar as g
from hsm import HsmError, Token
from ircnet import IrcClient
from ledger import Ledger, Policy, Verdict, file_loader, load_roster
from pkicrypto import (CURVE, Vault, build_cert, build_crl, compress, decompress, message_digest,
                       open_share, pin_from_secret, seal_share, sha256, shamir_combine,
                       spki_der, verify_raw)

ROOT_CN, ROOT_OU = "irc-pki-root", "root"


# =================================================================== replicas

def replica_main(idx: int, home: str, ctl: Connection, ca: Connection) -> None:
    """A CA HSM replica: owns one SoftHSM token holding a copy of the root key."""
    label = f"ca-replica-{idx}"
    token: Token | None = None
    conns = [ctl, ca]
    while conns:
        for c in wait(conns):
            try:
                op, *args = c.recv()
            except EOFError:
                conns.remove(c)
                continue
            try:
                if op == "provision":
                    pin, d = args
                    token = Token(home, label)
                    token.initialise(pin)
                    token.login(pin)
                    pub = token.import_private(d)
                    ok = token.private_is_locked_down()
                    token.logout()
                    del pin, d
                    c.send(("ok", compress(pub), ok))
                elif op == "login":
                    token = token or Token(home, label)
                    token.login(args[0])
                    c.send(("ok",))
                elif op == "sign":
                    c.send(("sig", token.sign(args[0])))
                elif op == "stop":
                    c.send(("ok",))
                    return
                else:
                    c.send(("err", f"unknown op {op}"))
            except Exception as e:  # report, keep serving
                c.send(("err", f"{type(e).__name__}: {e}"))


# ===================================================================== agent

class Agent:
    def __init__(self, name: str, role: str, home: str, run_dir: str, policy: Policy,
                 ctl: Connection, replicas: list[Connection]):
        self.name, self.role, self.home, self.run_dir = name, role, home, run_dir
        self.pki = os.path.join(run_dir, "pki")
        self.policy = policy
        self.ctl = ctl
        self.replicas = replicas
        self.primary = 0
        self.dead: set[int] = set()
        self.pending_switches: list[str] = []
        # The memorised secret: generated here, never written, never sent.
        self._passphrase = bytearray(secrets.token_urlsafe(24).encode())
        os.makedirs(home, mode=0o700, exist_ok=True)
        self.vault = Vault(os.path.join(home, "vault.json"), name, self._passphrase)
        self.token: Token | None = None
        self.ledger: Ledger | None = None
        self.irc: IrcClient | None = None
        self.inbox: asyncio.Queue = asyncio.Queue()
        self.counter = 0
        self.busy = False            # CA / release bot: one authority action in flight
        self.share_eph: dict[str, ec.EllipticCurvePrivateKey] = {}
        self.shares: dict[str, list[tuple[int, int]]] = {}
        self.unlock_ref = ""
        self.root_pub = None
        self.rpc_server = None
        self.waiters: list[tuple[callable, asyncio.Future]] = []

    # --------------------------------------------------------------- plumbing
    def tell(self, **event) -> None:
        self.ctl.send({"from": self.name, **event})

    def _pin(self) -> str:
        return self.vault.open()["pin"]

    async def say(self, verb: str, noun: str, ref: str, article: str = "the", **cl: str) -> None:
        m = g.make(self.name, verb, noun, ref, article, **cl)
        sig = self.token.sign(message_digest(self.policy.channel, m.body()))
        await self.irc.say(m.with_sig(sig.hex()).wire())

    def next_ref(self, prefix: str) -> str:
        self.counter += 1
        return f"{prefix}-{self.name}-{self.counter}"

    async def wait_until(self, pred, timeout: float = 20.0) -> None:
        if pred():
            return
        fut = asyncio.get_running_loop().create_future()
        self.waiters.append((pred, fut))
        await asyncio.wait_for(fut, timeout)

    # ------------------------------------------------------------ lifecycle
    def provision(self) -> None:
        pin = secrets.token_hex(16)
        self.token = Token(os.path.join(self.home, "hsm"), self.name)
        self.token.initialise(pin)
        self.vault.seal({"pin": pin})
        self.token.login(pin)
        del pin
        pub = self.token.generate_key()
        assert self.token.private_is_locked_down()
        self.tell(event="pubkey", spki=spki_der(pub).hex(), key=compress(pub))

    async def run(self) -> None:
        loop = asyncio.get_running_loop()
        loop.add_reader(self.ctl.fileno(), self._ctl_ready)
        try:
            self.provision()
            while True:
                op = await self.inbox.get()
                if op["op"] == "store_share":
                    self.vault.update(share=f"{op['x']}:{op['y']}")
                    self.tell(event="share_stored")
                elif op["op"] == "start":
                    await self.start(op["port"])
                    break
                elif op["op"] == "stop":
                    return
            listener = asyncio.create_task(self.listen())
            while True:
                op = await self.inbox.get()
                if op["op"] == "stop":
                    break
                try:
                    await self.handle(op)
                except Exception as e:
                    self.tell(event="error", op=op["op"], error=f"{type(e).__name__}: {e}",
                              trace=traceback.format_exc())
            listener.cancel()
            await self.irc.close()
            if self.rpc_server:
                self.rpc_server.close()
        finally:
            loop.remove_reader(self.ctl.fileno())
            self.vault.wipe()
            self.tell(event="stopped")

    def _ctl_ready(self) -> None:
        try:
            while self.ctl.poll():
                self.inbox.put_nowait(self.ctl.recv())
        except EOFError:
            self.inbox.put_nowait({"op": "stop"})

    async def start(self, port: int) -> None:
        with open(os.path.join(self.pki, "root.der"), "rb") as f:
            root_der = f.read()
        root = x509.load_der_x509_certificate(root_der)
        self.root_pub = root.public_key()
        roster = load_roster(self.pki, self.root_pub)
        self.ledger = Ledger(self.policy, roster, root_der, file_loader(self.pki))
        mine = self.ledger.active(self.name)
        if mine:
            self._install_cert(mine.serial)
        self.irc = IrcClient(self.name, self.policy.channel)
        await self.irc.connect("127.0.0.1", port)
        if self.role == "service":
            self.rpc_server = await asyncio.start_server(self._rpc_conn, "127.0.0.1", 0)
            self.tell(event="ready", rpc_port=self.rpc_server.sockets[0].getsockname()[1])
        else:
            self.tell(event="ready")
        if self.role == "ca":
            await self.say("publishes", "cert", "root", digest=sha256(root_der).hex())

    def _install_cert(self, serial: int) -> None:
        der = self.ledger.certs[serial].der
        cert = x509.load_der_x509_certificate(der)
        if compress(cert.public_key()) != compress(self.token.public_key()):
            raise HsmError("issued certificate does not match the key in my token")
        self.token.store_cert(der, cert.subject.public_bytes())
        self.tell(event="cert_installed", serial=serial)

    # -------------------------------------------------------------- listening
    async def listen(self) -> None:
        async for nick, text in self.irc.messages():
            v = self.ledger.apply(nick, text)
            try:
                await self.react(nick, v)
            except Exception as e:
                self.tell(event="error", op="react", error=f"{type(e).__name__}: {e}",
                          trace=traceback.format_exc())
            for pred, fut in list(self.waiters):
                if not fut.done() and pred():
                    fut.set_result(True)
                    self.waiters.remove((pred, fut))

    async def react(self, nick: str, v: Verdict) -> None:
        m = v.msg
        if m is None:
            return
        if m.actor == self.name and m.verb in ("issues", "publishes", "unlocks"):
            self.busy = False
        if v.ok and m.verb == "issues" and m.noun == "cert" and m.target == self.name:
            self._install_cert(int(m.get("serial")))
        if self.role == "custodian" and v.ok and (m.verb, m.noun) == ("requests", "share"):
            await self._send_share(m)
        if self.role == "ca":
            if v.ok and (m.verb, m.noun) == ("sends", "share") and m.ref in self.share_eph:
                await self._collect_share(m)
            await self._ca_work()
        if self.role == "service":
            await self._release_work()

    # ----------------------------------------------------------- intents
    async def handle(self, op: dict) -> None:
        kind = op["op"]
        if kind == "request_cert":
            ref = self.next_ref("r")
            await self.say("requests", "cert", ref, article="a", for_=self.name,
                           key=compress(self.token.public_key()))
        elif kind == "approve_cert":
            r = self.ledger.requests[op["ref"]]
            await self.say("approves", "cert", op["ref"], for_=r.subject)
        elif kind == "request_revocation":
            tgt = self.ledger.active(op["target"])
            ref = self.next_ref("v")
            await self.say("requests", "revocation", ref, article="a", for_=op["target"],
                           serial=str(tgt.serial), because=op.get("reason", "key compromise"))
        elif kind == "approve_revocation":
            r = self.ledger.requests[op["ref"]]
            await self.say("approves", "revocation", op["ref"], for_=r.subject, serial=str(r.serial))
        elif kind == "review_release":
            rel = self.ledger.releases[op["ref"]]
            with open(op["artifact"], "rb") as f:
                mine = hashlib.sha256(f.read()).hexdigest()
            if mine == rel.digest:
                await self.say("approves", "release", op["ref"], digest=rel.digest)
            else:
                await self.say("rejects", "release", op["ref"], digest=rel.digest,
                               because="hash mismatch")
        elif kind == "approve_release":
            rel = self.ledger.releases[op["ref"]]
            await self.say("approves", "release", op["ref"], digest=rel.digest)
        elif kind == "unlock":
            eph = ec.generate_private_key(CURVE)
            ref = self.next_ref("u")
            self.share_eph[ref] = eph
            self.shares[ref] = []
            await self.say("requests", "share", ref, article="a", key=compress(eph.public_key()))
        elif kind == "leakcheck":
            self.tell(event="leakcheck", **self._leakcheck())
        else:
            raise ValueError(f"unknown op {kind}")
        self.tell(event="done", op=kind)

    def _leakcheck(self) -> dict:
        """Scan every file of the run for my secrets (in any common encoding).
        Only I can run this check, because only I know what to look for."""
        sealed = self.vault.open()
        needles = {"passphrase": bytes(self._passphrase), "pin": sealed["pin"].encode()}
        if "share" in sealed:
            needles["share"] = sealed["share"].split(":")[1].encode()
            y = int(sealed["share"].split(":")[1])
            needles["share_hex"] = y.to_bytes(16, "big").hex().encode()
        hits = []
        for root, _, files in os.walk(self.run_dir):
            for fn in files:
                p = os.path.join(root, fn)
                try:
                    with open(p, "rb") as f:
                        data = f.read()
                except OSError:
                    continue
                for what, needle in needles.items():
                    if needle in data or needle.hex().encode() in data:
                        hits.append(f"{what} in {os.path.relpath(p, self.run_dir)}")
        return {"clean": not hits, "hits": hits, "checked": sorted(needles)}

    # ---------------------------------------------------------- custodian
    async def _send_share(self, m: g.Msg) -> None:
        sealed = self.vault.open()
        if "share" not in sealed:
            return
        x, y = (int(t) for t in sealed["share"].split(":"))
        eph, ct = seal_share(m.get("key"), m.ref, self.name, (x, y))
        del sealed, x, y
        await self.say("sends", "share", m.ref, article="a", key=eph, secret=ct)

    # ------------------------------------------------------------------ CA
    async def _collect_share(self, m: g.Msg) -> None:
        share = open_share(self.share_eph[m.ref], m.ref, m.actor, m.get("key"), m.get("secret"))
        got = self.shares[m.ref]
        if share[0] not in {x for x, _ in got}:
            got.append(share)
        if len(got) < self.policy.m or self.unlock_ref:
            return
        pin = pin_from_secret(shamir_combine(got[: self.policy.m]))
        self.unlock_ref = m.ref
        health = {}
        for i, conn in enumerate(self.replicas):
            health[i] = self._replica_call(i, "login", pin) == ("ok",)
        del pin
        got.clear()
        self.share_eph.pop(m.ref, None)
        probe = sha256(b"ircpki replica health " + m.ref.encode())
        for i in range(len(self.replicas)):
            if health[i]:
                r = self._replica_call(i, "sign", probe)
                health[i] = r[0] == "sig" and verify_raw(self.root_pub, probe, r[1])
        self.tell(event="replica_health", health=health)
        if not any(health.values()):
            raise HsmError("no CA replica accepted the reconstructed PIN")
        self.dead |= {i for i, ok in health.items() if not ok}
        await self.say("unlocks", "token", m.ref)

    def _replica_call(self, i: int, *req, timeout: float = 5.0):
        conn = self.replicas[i]
        try:
            conn.send(req)
            if not conn.poll(timeout):
                return ("err", "timeout")
            return conn.recv()
        except (EOFError, OSError, BrokenPipeError) as e:
            return ("err", f"replica {i} unreachable: {e}")

    def hsm_sign(self, digest: bytes) -> bytes:
        """Sign with the root key, failing over across replicas in order."""
        order = list(range(self.primary, len(self.replicas))) + list(range(0, self.primary))
        for i in order:
            if i in self.dead:
                continue
            r = self._replica_call(i, "sign", digest)
            if r[0] == "sig" and verify_raw(self.root_pub, digest, r[1]):
                if i != self.primary:
                    self.pending_switches.append(f"hsm-{i}")
                    self.primary = i
                return r[1]
            self.dead.add(i)
            self.tell(event="replica_failed", replica=i, detail=str(r[1]) if len(r) > 1 else "")
        raise HsmError("all CA replicas are unavailable")

    async def _flush_switches(self) -> None:
        while self.pending_switches:
            ref = self.pending_switches.pop(0)
            await self.say("switches", "token", ref, because="primary unreachable")

    async def _ca_work(self) -> None:
        if self.busy or not self.ledger.unlocked:
            return
        for ref in self.ledger.pending():
            r = self.ledger.requests[ref]
            root = x509.load_der_x509_certificate(self.ledger.root_der)
            root_spki = spki_der(root.public_key())
            if r.kind == "cert":
                serial = self.ledger.next_serial
                der = build_cert(serial=serial, subject_cn=r.subject,
                                 subject_ou=self.ledger.role(r.subject),
                                 subject_spki=spki_der(decompress(r.key)),
                                 issuer_cn=ROOT_CN, issuer_ou=ROOT_OU, issuer_spki=root_spki,
                                 signer=self.hsm_sign, is_ca=False)
                _write_new(os.path.join(self.pki, "certs", f"{serial}.der"), der)
                await self._flush_switches()
                self.busy = True
                await self.say("issues", "cert", ref, for_=r.subject, serial=str(serial),
                               digest=sha256(der).hex())
            else:
                now = dt.datetime.now(dt.timezone.utc)
                revoked = dict(self.ledger.revoked)
                revoked[r.serial] = now
                der = build_crl(number=self.ledger.crl_number + 1, revoked=revoked,
                                issuer_cn=ROOT_CN, issuer_ou=ROOT_OU, issuer_spki=root_spki,
                                signer=self.hsm_sign, now=now)
                _write_new(os.path.join(self.pki, "crl", f"{ref}.der"), der)
                _write_atomic(os.path.join(self.pki, "crl.der"), der)
                await self._flush_switches()
                self.busy = True
                await self.say("issues", "revocation", ref, for_=r.subject, serial=str(r.serial),
                               digest=sha256(der).hex())
            return  # one at a time; the echo clears busy and calls us again

    # -------------------------------------------------------- release bot
    async def _release_work(self) -> None:
        if self.busy:
            return
        for ref, rel in self.ledger.releases.items():
            if self.ledger.release_ready(ref):
                self.busy = True
                await self.say("publishes", "release", ref, version=rel.version, digest=rel.digest)
                return

    def _release_status(self, ref: str) -> dict:
        rel = self.ledger.releases.get(ref)
        if rel is None:
            raise KeyError(f"no release {ref}")
        state = "published" if rel.published else "vetoed" if rel.vetoes else "pending"
        devs = self.ledger._active_with_role(rel.dev_approvals, "developer")
        sms = self.ledger._active_with_role(rel.sm_approvals, "secmgr")
        return {"id": ref, "version": rel.version, "digest": rel.digest, "state": state,
                "developer_approvals": devs, "security_approvals": sms, "vetoes": rel.vetoes,
                "required": {"developers": self.policy.release_m, "security": 1}}

    async def rpc(self, method: str, params: dict) -> object:
        if method == "release.submit":
            path = os.path.realpath(params["artifact"])
            rel_root = os.path.realpath(os.path.join(self.run_dir, "releases"))
            if not path.startswith(rel_root + os.sep):
                raise PermissionError("artifact must live under the releases directory")
            version = str(params["version"])
            with open(path, "rb") as f:
                digest = hashlib.sha256(f.read()).hexdigest()
            ref = self.next_ref("rel")
            await self.say("submits", "release", ref, article="a", version=version, digest=digest)
            await self.wait_until(lambda: ref in self.ledger.releases)
            return {"id": ref, "version": version, "digest": digest}
        if method == "release.status":
            return self._release_status(params["id"])
        if method == "release.list":
            return [self._release_status(r) for r in self.ledger.releases]
        if method == "release.evidence":
            ref = params["id"]
            lines = [{"nick": n, "text": t, "status": v.status}
                     for n, t, v in self.ledger.history
                     if v.msg is not None and v.msg.noun == "release" and v.msg.ref == ref]
            certs = {c.name: c.der.hex() for c in self.ledger.certs.values()
                     if any(l["nick"] == c.name for l in lines)}
            return {"status": self._release_status(ref), "sentences": lines, "certs": certs,
                    "channel": self.policy.channel}
        raise LookupError(method)

    async def _rpc_conn(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        """JSON-RPC 2.0 over HTTP/1.1 POST /rpc, loopback only."""
        try:
            head = await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), 5)
            lines = head.decode("latin-1").split("\r\n")
            method, path, _ = lines[0].split(" ", 2)
            hdrs = {k.lower(): v.strip() for k, _, v in (l.partition(":") for l in lines[1:] if l)}
            n = int(hdrs.get("content-length", "0"))
            if method != "POST" or path != "/rpc" or not (0 < n <= 65536):
                writer.write(b"HTTP/1.1 404 Not Found\r\nContent-Length: 0\r\n\r\n")
                return
            body = await reader.readexactly(n)
            rid = None
            try:
                req = json.loads(body)
                rid = req.get("id")
                if req.get("jsonrpc") != "2.0" or not isinstance(req.get("method"), str):
                    raise ValueError("not a JSON-RPC 2.0 request")
                result = await self.rpc(req["method"], req.get("params") or {})
                resp = {"jsonrpc": "2.0", "id": rid, "result": result}
            except LookupError as e:
                code = -32602 if isinstance(e, KeyError) else -32601  # bad params / no such method
                resp = {"jsonrpc": "2.0", "id": rid, "error": {"code": code, "message": str(e)}}
            except Exception as e:
                resp = {"jsonrpc": "2.0", "id": rid,
                        "error": {"code": -32000, "message": f"{type(e).__name__}: {e}"}}
            out = json.dumps(resp).encode()
            writer.write(b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n"
                         + f"Content-Length: {len(out)}\r\nConnection: close\r\n\r\n".encode() + out)
        except (asyncio.IncompleteReadError, asyncio.TimeoutError, ValueError, asyncio.LimitOverrunError):
            pass
        finally:
            await writer.drain()
            writer.close()


def _write_new(path: str, data: bytes) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
    with os.fdopen(fd, "wb") as f:
        f.write(data)


def _write_atomic(path: str, data: bytes) -> None:
    tmp = path + ".tmp"
    with open(tmp, "wb") as f:
        f.write(data)
    os.replace(tmp, path)


def agent_main(name: str, role: str, home: str, run_dir: str, policy: dict,
               ctl: Connection, replicas: list[Connection]) -> None:
    agent = Agent(name, role, home, run_dir, Policy(**policy), ctl, replicas)
    try:
        asyncio.run(agent.run())
    except Exception as e:
        try:
            ctl.send({"from": name, "event": "error", "op": "main",
                      "error": f"{type(e).__name__}: {e}", "trace": traceback.format_exc()})
        except OSError:
            pass

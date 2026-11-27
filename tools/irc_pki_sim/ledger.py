"""Ceremony policy as a deterministic state machine, plus the hash-chained log.

The *same* ``Ledger`` runs in three places:

* inside each actor, which only acts when its own ledger says the policy is
  satisfied (the CA issues, the release bot publishes);
* in the live auditor that the orchestrator uses to wait for progress;
* in the offline verifier, replaying the server log from line one.

Because the server relays every line to every client in log order (including
an echo to the sender), all three see the same sequence and reach the same
state. The verifier is therefore an exact re-execution, not a heuristic.

Verdicts
--------
accepted   the sentence is valid and changed state
rejected   well formed and correctly signed, but not allowed (e.g. a revoked
           developer approving a release); recorded, ignored, not an error
violation  an *authority* (CA or release bot) did something the policy did
           not allow; this is a log error
invalid    does not parse, is not canonical, is unsigned, the nick does not
           match the speaker, or the signature is wrong; this is a log error
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
from dataclasses import dataclass, field
from typing import Callable

from cryptography import x509

import grammar as g
from pkicrypto import (cert_cn_ou, compress, decompress, message_digest, sha256,
                       verify_issued_by, verify_raw)

ROLES = ("ca", "custodian", "secmgr", "developer", "service")
AUTHORITY = {("issues", "cert"), ("issues", "revocation"), ("publishes", "cert"),
             ("publishes", "release"), ("unlocks", "token"), ("switches", "token")}


@dataclass(frozen=True)
class Policy:
    m: int = 3                 # custodian shares needed to unlock the CA token
    n: int = 3                 # custodians holding shares
    sm_approvals: int = 2      # custodian approvals for a security-manager cert or revocation
    release_m: int = 3         # developer approvals for a release
    channel: str = "#pki"

    def __post_init__(self) -> None:
        if not (1 <= self.m <= self.n):
            raise ValueError("need 1 <= m <= n")
        if not (1 <= self.sm_approvals <= self.n):
            raise ValueError("security-manager approvals must be between 1 and n")


@dataclass
class Verdict:
    status: str
    reason: str = ""
    msg: g.Msg | None = None

    @property
    def ok(self) -> bool:
        return self.status == "accepted"

    @property
    def is_error(self) -> bool:
        return self.status in ("violation", "invalid")


@dataclass
class CertRec:
    serial: int
    name: str
    role: str
    pub: object
    der: bytes
    revoked: bool = False


@dataclass
class Request:
    kind: str                 # "cert" | "revocation"
    requester: str
    subject: str
    key: str = ""             # requested public key (cert)
    serial: int = 0           # serial to revoke (revocation)
    approvals: list[str] = field(default_factory=list)
    vetoed: bool = False
    done: bool = False


@dataclass
class Release:
    version: str
    digest: str
    submitter: str
    dev_approvals: list[str] = field(default_factory=list)
    sm_approvals: list[str] = field(default_factory=list)
    vetoes: list[str] = field(default_factory=list)
    published: bool = False


Loader = Callable[[str], "bytes | None"]


class Ledger:
    def __init__(self, policy: Policy, roster: dict, root_der: bytes, load: Loader):
        self.policy = policy
        self.roles: dict[str, str] = dict(roster["roles"])
        self.load = load
        self.root_der = root_der
        self.root = x509.load_der_x509_certificate(root_der)
        if not verify_issued_by(self.root, self.root):
            raise ValueError("root certificate is not self-signed")
        self.certs: dict[int, CertRec] = {}
        self.latest: dict[str, int] = {}      # name -> newest serial (may be revoked)
        self.requests: dict[str, Request] = {}
        self.share_reqs: dict[str, dict] = {}
        self.releases: dict[str, Release] = {}
        self.revoked: dict[int, dt.datetime] = {}
        self.crl_number = 0
        self.unlocked = False
        self.unlock_ref = ""
        self.switches: list[str] = []
        self.next_serial = 2
        self.history: list[tuple[str, str, Verdict]] = []
        for name, serial in roster["ceremony_serials"].items():
            der = load(f"certs/{serial}.der")
            if der is None:
                raise ValueError(f"ceremony cert {serial} for {name} missing")
            self._add_cert(int(serial), name, der, ceremony=True)

    # ---------------------------------------------------------------- helpers
    def _add_cert(self, serial: int, name: str, der: bytes, ceremony: bool = False) -> str | None:
        cert = x509.load_der_x509_certificate(der)
        if cert.serial_number != serial:
            return "serial in certificate does not match"
        if not verify_issued_by(cert, self.root):
            return "certificate is not signed by the root"
        cn, ou = cert_cn_ou(cert)
        if cn != name or ou != self.roles.get(name):
            return f"certificate names {cn}/{ou}, expected {name}/{self.roles.get(name)}"
        if serial in self.certs:
            return "serial already used"
        bc = cert.extensions.get_extension_for_class(x509.BasicConstraints).value
        if bc.ca:
            return "leaf certificate must not be a CA"
        self.certs[serial] = CertRec(serial, name, ou, cert.public_key(), der)
        self.latest[name] = serial
        self.next_serial = max(self.next_serial, serial + 1)
        if ceremony and self.roles.get(name) not in ("ca", "custodian", "service"):
            raise ValueError("only ca, custodian and service certs come from the ceremony")
        return None

    def active(self, name: str) -> CertRec | None:
        s = self.latest.get(name)
        if s is None:
            return None
        rec = self.certs[s]
        return None if rec.revoked else rec

    def role(self, name: str) -> str | None:
        return self.roles.get(name)

    def _active_with_role(self, names: list[str], role: str) -> list[str]:
        out = []
        for n in names:
            if n not in out and self.role(n) == role and self.active(n):
                out.append(n)
        return out

    # ------------------------------------------------------------ readiness
    def cert_ready(self, ref: str) -> bool:
        r = self.requests.get(ref)
        if not r or r.kind != "cert" or r.done or r.vetoed or not self.unlocked:
            return False
        if self.active(r.subject):
            return False
        if self.role(r.subject) == "secmgr":
            return len(self._active_with_role(r.approvals, "custodian")) >= self.policy.sm_approvals
        return len(self._active_with_role(r.approvals, "secmgr")) >= 1

    def revocation_ready(self, ref: str) -> bool:
        r = self.requests.get(ref)
        if not r or r.kind != "revocation" or r.done or not self.unlocked:
            return False
        tgt = self.active(r.subject)
        if not tgt or tgt.serial != r.serial:
            return False
        if self.role(r.subject) == "secmgr":
            return len(self._active_with_role(r.approvals, "custodian")) >= self.policy.sm_approvals
        return len(self._active_with_role([r.requester], "secmgr")) == 1

    def release_ready(self, ref: str) -> bool:
        rel = self.releases.get(ref)
        if not rel or rel.published or rel.vetoes:
            return False
        return (len(self._active_with_role(rel.dev_approvals, "developer")) >= self.policy.release_m
                and len(self._active_with_role(rel.sm_approvals, "secmgr")) >= 1)

    def pending(self) -> list[str]:
        return [ref for ref in self.requests
                if self.cert_ready(ref) or self.revocation_ready(ref)]

    # ----------------------------------------------------------------- apply
    def apply(self, nick: str, text: str) -> Verdict:
        v = self._apply(nick, text)
        if v.msg is not None and v.status != "invalid" and (v.msg.verb, v.msg.noun) in AUTHORITY \
                and v.status == "rejected":
            v.status = "violation"
        self.history.append((nick, text, v))
        return v

    def _apply(self, nick: str, text: str) -> Verdict:
        try:
            m = g.parse(text)
        except g.GrammarError as e:
            return Verdict("invalid", f"grammar: {e}")
        if m.wire() != text:
            return Verdict("invalid", "not in canonical form", m)
        if nick != m.actor:
            return Verdict("invalid", f"spoken by {nick} but claims to be {m.actor}", m)
        err = g.check_schema(m)
        if err:
            return Verdict("invalid", err, m)
        if not m.sig or len(m.sig) != 128:
            return Verdict("invalid", "missing or malformed signature", m)
        if self.role(m.actor) is None:
            return Verdict("invalid", f"{m.actor} is not on the roster", m)
        digest = message_digest(self.policy.channel, m.body())
        sig = bytes.fromhex(m.sig)
        if (m.verb, m.noun) == ("requests", "cert"):
            try:
                pub = decompress(m.get("key"))
            except ValueError:
                return Verdict("invalid", "key is not a P-256 point", m)
        else:
            s = self.latest.get(m.actor)
            if s is None:
                return Verdict("invalid", f"{m.actor} has no certificate to sign with", m)
            pub = self.certs[s].pub
        if not verify_raw(pub, digest, sig):
            return Verdict("invalid", "bad signature", m)
        if (m.verb, m.noun) != ("requests", "cert") and not self.active(m.actor):
            return Verdict("rejected", f"{m.actor}'s certificate is revoked", m)
        handler = getattr(self, f"_on_{m.verb}_{m.noun}")
        reason = handler(m)
        return Verdict("rejected", reason, m) if reason else Verdict("accepted", "", m)

    # ---------------------------------------------------------- certificates
    def _on_publishes_cert(self, m: g.Msg) -> str | None:
        if self.role(m.actor) != "ca" or m.ref != "root":
            return "only the ca publishes the root"
        if m.get("digest") != sha256(self.root_der).hex():
            return "digest does not match the pinned root"
        return None

    def _on_requests_cert(self, m: g.Msg) -> str | None:
        if self.role(m.actor) not in ("developer", "secmgr"):
            return "only developers and the security manager enrol over irc"
        if m.target != m.actor:
            return "a cert can only be requested for oneself"
        if m.ref in self.requests:
            return "reference already used"
        if self.active(m.actor):
            return "already holds an active cert"
        if any(compress(c.pub) == m.get("key") for c in self.certs.values()):
            return "key already certified"
        self.requests[m.ref] = Request("cert", m.actor, m.actor, key=m.get("key"))
        return None

    def _cert_approver_ok(self, r: Request, who: str) -> bool:
        need = "custodian" if self.role(r.subject) == "secmgr" else "secmgr"
        return self.role(who) == need and who != r.subject

    def _on_approves_cert(self, m: g.Msg) -> str | None:
        r = self.requests.get(m.ref)
        if not r or r.kind != "cert" or r.done:
            return "no open cert request with that reference"
        if r.subject != m.target:
            return "request is for someone else"
        if not self._cert_approver_ok(r, m.actor):
            return f"{m.actor} may not approve a cert for {r.subject}"
        if m.actor in r.approvals:
            return "already approved"
        r.approvals.append(m.actor)
        return None

    def _on_rejects_cert(self, m: g.Msg) -> str | None:
        r = self.requests.get(m.ref)
        if not r or r.kind != "cert" or r.done or r.subject != m.target:
            return "no open cert request with that reference"
        if not self._cert_approver_ok(r, m.actor):
            return f"{m.actor} may not reject a cert for {r.subject}"
        r.vetoed = True
        return None

    def _on_issues_cert(self, m: g.Msg) -> str | None:
        if self.role(m.actor) != "ca":
            return "only the ca issues"
        r = self.requests.get(m.ref)
        if not r or r.kind != "cert" or r.subject != m.target:
            return "no matching cert request"
        if not self.cert_ready(m.ref):
            return "policy not satisfied for this cert"
        serial = int(m.get("serial"))
        if serial != self.next_serial:
            return f"serial {serial} is not the next serial {self.next_serial}"
        der = self.load(f"certs/{serial}.der")
        if der is None or sha256(der).hex() != m.get("digest"):
            return "certificate file missing or digest mismatch"
        if compress(x509.load_der_x509_certificate(der).public_key()) != r.key:
            return "certificate key is not the requested key"
        err = self._add_cert(serial, r.subject, der)
        if err:
            return err
        r.done = True
        return None

    # ----------------------------------------------------------- revocation
    def _on_requests_revocation(self, m: g.Msg) -> str | None:
        tgt = self.active(m.target)
        if not tgt or tgt.serial != int(m.get("serial")):
            return "target has no active cert with that serial"
        if m.ref in self.requests:
            return "reference already used"
        trole = self.role(m.target)
        if trole == "developer" and self.role(m.actor) != "secmgr":
            return "only the security manager revokes developers"
        if trole == "secmgr" and self.role(m.actor) != "custodian":
            return "only custodians revoke the security manager"
        if trole not in ("developer", "secmgr"):
            return f"{trole} certs are not revocable over irc"
        self.requests[m.ref] = Request("revocation", m.actor, m.target, serial=tgt.serial)
        return None

    def _on_approves_revocation(self, m: g.Msg) -> str | None:
        r = self.requests.get(m.ref)
        if not r or r.kind != "revocation" or r.done:
            return "no open revocation with that reference"
        if r.subject != m.target or r.serial != int(m.get("serial")):
            return "revocation is for a different cert"
        need = "custodian" if self.role(r.subject) == "secmgr" else "secmgr"
        if self.role(m.actor) != need:
            return f"{m.actor} may not approve this revocation"
        if m.actor in r.approvals:
            return "already approved"
        r.approvals.append(m.actor)
        return None

    def _on_issues_revocation(self, m: g.Msg) -> str | None:
        if self.role(m.actor) != "ca":
            return "only the ca revokes"
        r = self.requests.get(m.ref)
        if not r or r.kind != "revocation" or r.subject != m.target or r.serial != int(m.get("serial")):
            return "no matching revocation request"
        if not self.revocation_ready(m.ref):
            return "policy not satisfied for this revocation"
        der = self.load(f"crl/{m.ref}.der")
        if der is None or sha256(der).hex() != m.get("digest"):
            return "crl file missing or digest mismatch"
        crl = x509.load_der_x509_crl(der)
        if not crl.is_signature_valid(self.root.public_key()):
            return "crl is not signed by the root"
        listed = {e.serial_number for e in crl}
        if listed != set(self.revoked) | {r.serial}:
            return "crl does not list exactly the revoked serials"
        num = crl.extensions.get_extension_for_class(x509.CRLNumber).value.crl_number
        if num != self.crl_number + 1:
            return "crl number is not sequential"
        self.crl_number = num
        self.revoked[r.serial] = crl.last_update_utc
        self.certs[r.serial].revoked = True
        r.done = True
        return None

    # -------------------------------------------------------- token unlock
    def _on_requests_share(self, m: g.Msg) -> str | None:
        if self.role(m.actor) != "ca":
            return "only the ca asks for shares"
        if m.ref in self.share_reqs:
            return "reference already used"
        self.share_reqs[m.ref] = {"key": m.get("key"), "from": []}
        return None

    def _on_sends_share(self, m: g.Msg) -> str | None:
        if self.role(m.actor) != "custodian":
            return "only custodians hold shares"
        req = self.share_reqs.get(m.ref)
        if req is None:
            return "no share request with that reference"
        if m.actor in req["from"]:
            return "share already sent"
        req["from"].append(m.actor)
        return None

    def _on_unlocks_token(self, m: g.Msg) -> str | None:
        if self.role(m.actor) != "ca":
            return "only the ca unlocks"
        req = self.share_reqs.get(m.ref)
        if req is None:
            return "no share request with that reference"
        got = self._active_with_role(req["from"], "custodian")
        if len(got) < self.policy.m:
            return f"only {len(got)} of {self.policy.m} required shares were sent"
        self.unlocked = True
        self.unlock_ref = m.ref
        return None

    def _on_switches_token(self, m: g.Msg) -> str | None:
        if self.role(m.actor) != "ca" or not m.ref.startswith("hsm-"):
            return "only the ca switches between its hsm replicas"
        self.switches.append(m.ref)
        return None

    # ------------------------------------------------------------ releases
    def _on_submits_release(self, m: g.Msg) -> str | None:
        if self.role(m.actor) != "service":
            return "only the release service submits"
        if m.ref in self.releases:
            return "reference already used"
        self.releases[m.ref] = Release(m.get("version"), m.get("digest"), m.actor)
        return None

    def _on_approves_release(self, m: g.Msg) -> str | None:
        rel = self.releases.get(m.ref)
        if not rel or rel.published:
            return "no open release with that reference"
        if m.get("digest") != rel.digest:
            return "approval is for a different digest"
        role = self.role(m.actor)
        bucket = {"developer": rel.dev_approvals, "secmgr": rel.sm_approvals}.get(role)
        if bucket is None:
            return f"{role} may not approve releases"
        if m.actor in bucket:
            return "already approved"
        bucket.append(m.actor)
        return None

    def _on_rejects_release(self, m: g.Msg) -> str | None:
        rel = self.releases.get(m.ref)
        if not rel or rel.published:
            return "no open release with that reference"
        if self.role(m.actor) not in ("developer", "secmgr"):
            return "only developers and the security manager can veto"
        rel.vetoes.append(m.actor)
        return None

    def _on_publishes_release(self, m: g.Msg) -> str | None:
        if self.role(m.actor) != "service":
            return "only the release service publishes"
        rel = self.releases.get(m.ref)
        if not rel or rel.version != m.get("version") or rel.digest != m.get("digest"):
            return "no matching release"
        if not self.release_ready(m.ref):
            return "release quorum not met"
        rel.published = True
        return None

    # ------------------------------------------------------------- summary
    def summary(self) -> dict:
        return {
            "unlocked": self.unlocked,
            "certs": {s: {"name": c.name, "role": c.role, "revoked": c.revoked}
                      for s, c in sorted(self.certs.items())},
            "revoked_serials": sorted(self.revoked),
            "crl_number": self.crl_number,
            "hsm_switches": self.switches,
            "releases": {k: {"version": r.version, "digest": r.digest, "published": r.published,
                             "dev_approvals": r.dev_approvals, "sm_approvals": r.sm_approvals,
                             "vetoes": r.vetoes}
                         for k, r in self.releases.items()},
        }


# =========================================================== hash-chained log

GENESIS = hashlib.sha256(b"ircpki-log/1").hexdigest()


def chain(prev: str, content: str) -> str:
    # Deliberately simple so a busybox shell in the QEMU guest can recompute
    # it:  printf '%s\n%s' "$prev" "$content" | sha256sum
    return hashlib.sha256(f"{prev}\n{content}".encode()).hexdigest()


class LogWriter:
    """Append-only server log. Line = seq TAB ts TAB cmd TAB nick TAB target TAB text TAB hash."""

    def __init__(self, path: str):
        self.path = path
        self.seq = 0
        self.head = GENESIS
        os.makedirs(os.path.dirname(path), exist_ok=True)
        self.f = open(path, "a", encoding="utf-8")

    def append(self, cmd: str, nick: str, target: str, text: str) -> None:
        for field_ in (cmd, nick, target, text):
            if any(ord(c) < 0x20 for c in field_):
                raise ValueError("control characters are not allowed in the log")
        self.seq += 1
        ts = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
        content = "\t".join([f"{self.seq:06d}", ts, cmd, nick, target, text])
        self.head = chain(self.head, content)
        self.f.write(f"{content}\t{self.head}\n")
        self.f.flush()
        os.fsync(self.f.fileno())

    def close(self) -> None:
        self.f.close()


@dataclass
class LogEntry:
    seq: int
    ts: str
    cmd: str
    nick: str
    target: str
    text: str
    hash: str


def read_log(path: str) -> tuple[list[LogEntry], list[str]]:
    entries, errors = [], []
    prev, last_ts = GENESIS, ""
    with open(path, encoding="utf-8") as f:
        for lineno, line in enumerate(f, 1):
            parts = line.rstrip("\n").split("\t")
            if len(parts) != 7:
                errors.append(f"line {lineno}: expected 7 fields, got {len(parts)}")
                continue
            content = "\t".join(parts[:6])
            want = chain(prev, content)
            if parts[6] != want:
                errors.append(f"line {lineno}: hash chain broken")
            prev = parts[6]
            if int(parts[0]) != lineno:
                errors.append(f"line {lineno}: sequence number {parts[0]}")
            if parts[1] < last_ts:
                errors.append(f"line {lineno}: timestamp goes backwards")
            last_ts = parts[1]
            entries.append(LogEntry(int(parts[0]), parts[1], parts[2], parts[3], parts[4],
                                    parts[5], parts[6]))
    return entries, errors


def load_roster(pki_dir: str, root_pub) -> dict:
    """roster.json is signed by the root key at the ceremony (roster.sig)."""
    with open(os.path.join(pki_dir, "roster.json"), "rb") as f:
        raw = f.read()
    with open(os.path.join(pki_dir, "roster.sig")) as f:
        sig = bytes.fromhex(f.read().strip())
    if not verify_raw(root_pub, sha256(b"ircpki-roster/1\n" + raw), sig):
        raise ValueError("roster signature does not verify against the root")
    return json.loads(raw)


def file_loader(pki_dir: str) -> Loader:
    def load(rel: str) -> bytes | None:
        p = os.path.join(pki_dir, rel)
        if not os.path.realpath(p).startswith(os.path.realpath(pki_dir) + os.sep):
            return None
        try:
            with open(p, "rb") as f:
                return f.read()
        except FileNotFoundError:
            return None
    return load

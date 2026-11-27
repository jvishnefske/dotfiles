"""Tests: grammar, crypto primitives, policy ledger, log integrity, and full
end-to-end ceremonies against real SoftHSM tokens (and QEMU when available).

    python3 -m pytest -q test_irc_pki_sim.py
"""

from __future__ import annotations

import asyncio
import datetime as dt
import itertools
import json
import os
import shutil
import stat
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from cryptography.hazmat.primitives.asymmetric import ec  # noqa: E402

import grammar as g  # noqa: E402
from hsm import find_softhsm  # noqa: E402
from ledger import GENESIS, Ledger, LogWriter, Policy, chain, read_log  # noqa: E402
from pkicrypto import (CURVE, PRIME, Vault, build_cert, build_crl, compress,  # noqa: E402
                       message_digest, open_share, seal_share, sha256, shamir_combine,
                       shamir_split, software_signer, spki_der)
from scenario import Cast, check_conformance  # noqa: E402

HAVE_HSM = find_softhsm() is not None and shutil.which("softhsm2-util") is not None


# ====================================================================== grammar

class GrammarTest(unittest.TestCase):
    def test_table_is_ll1_and_complete(self):
        # build_table raises on any conflict; also every nonterminal is reachable
        # from at least one lookahead.
        t = g.build_table()
        self.assertEqual({nt for nt, _ in t}, set(g.GRAMMAR))

    def test_first_sets_of_alternatives_are_disjoint(self):
        first = g.first_sets()
        follow = g.follow_sets(first)
        for nt, prods in g.GRAMMAR.items():
            seen: set[str] = set()
            for p in prods:
                f = g.first_of_seq(p, first)
                la = (f - {g.EPS}) | (follow[nt] if g.EPS in f else set())
                self.assertFalse(seen & la, f"{nt}: {seen & la}")
                seen |= la

    def test_round_trip_every_schema_entry(self):
        vals = {"for": "dev1", "serial": "7", "version": "1.2.3", "key": "02" + "ab" * 32,
                "digest": "cd" * 32, "secret": "ef" * 33, "because": "lost laptop"}
        for (verb, noun), (req, opt) in g.SCHEMA.items():
            for extra in (set(), set(opt)):
                cl = {k: vals[k] for k in req | extra}
                if "for" in cl:
                    cl["for_"] = cl.pop("for")
                m = g.make("alice", verb, noun, "x-1", **cl).with_sig("11" * 64)
                self.assertEqual(g.parse(m.wire()), m)
                self.assertIsNone(g.check_schema(m))

    def test_human_readable(self):
        m = g.make("secmgr", "approves", "cert", "r-dev1-1", for_="dev1")
        self.assertEqual(m.wire(), "secmgr approves the cert #r-dev1-1 for dev1.")

    def test_rejects(self):
        bad = [
            "",                                             # empty
            "dev1 requests a cert.",                        # no reference
            "Dev1 requests a cert #r.",                     # upper case
            "cert requests a cert #r.",                     # reserved word as actor
            "dev1 eats a cert #r.",                         # unknown verb
            "dev1 requests a cert #r for dev1 for dev2.",   # duplicate clause
            "dev1 requests a cert #r because key lost.",    # reserved word in reason
            "dev1 requests a cert #r for dev1",             # missing period
            "dev1 requests a cert #r for dev1. extra",      # trailing input
            "dev1 requests a cert #r; signed zz.",          # signature not hex
            "dev1 requests a cert #r for dev1\x00.",        # control character
            "x" * 401,                                      # too long
        ]
        for text in bad:
            with self.assertRaises(g.GrammarError, msg=text):
                g.parse(text)

    def test_schema(self):
        self.assertIsNotNone(g.check_schema(g.parse("dev1 issues a release #r.")))
        self.assertIsNotNone(g.check_schema(g.parse("dev1 requests a cert #r for dev1.")))
        self.assertIsNotNone(g.check_schema(g.parse("ca unlocks the token #u, serial 3.")))


# ==================================================================== primitives

class PrimitiveTest(unittest.TestCase):
    def test_shamir_every_m_subset(self):
        for m, n in [(1, 1), (2, 3), (3, 3), (3, 5), (5, 7)]:
            secret = int.from_bytes(os.urandom(15), "big")
            shares = shamir_split(secret, m, n)
            for subset in itertools.combinations(shares, m):
                self.assertEqual(shamir_combine(list(subset)), secret)
            if m > 1:
                for subset in itertools.combinations(shares, m - 1):
                    self.assertNotEqual(shamir_combine(list(subset)), secret)

    def test_shamir_bounds(self):
        for m, n in [(0, 3), (4, 3), (1, 256)]:
            with self.assertRaises(ValueError):
                shamir_split(1, m, n)
        with self.assertRaises(ValueError):
            shamir_split(PRIME, 2, 3)
        with self.assertRaises(ValueError):
            shamir_combine([(1, 5), (1, 6)])

    def test_share_transport_is_bound_to_ref_and_custodian(self):
        ca = ec.generate_private_key(CURVE)
        eph, ct = seal_share(compress(ca.public_key()), "u-1", "custodian1", (2, 12345))
        self.assertEqual(open_share(ca, "u-1", "custodian1", eph, ct), (2, 12345))
        for ref, who in [("u-2", "custodian1"), ("u-1", "custodian2")]:
            with self.assertRaises(Exception):
                open_share(ca, ref, who, eph, ct)
        other = ec.generate_private_key(CURVE)
        with self.assertRaises(Exception):
            open_share(other, "u-1", "custodian1", eph, ct)

    def test_vault(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "vault.json")
            v = Vault(p, "dev1", bytearray(b"correct horse"))
            v.seal({"pin": "0123456789abcdef"})
            self.assertEqual(stat.S_IMODE(os.stat(p).st_mode), 0o600)
            self.assertNotIn(b"0123456789abcdef", open(p, "rb").read())
            self.assertEqual(v.open()["pin"], "0123456789abcdef")
            with self.assertRaises(PermissionError):
                Vault(p, "dev1", bytearray(b"wrong")).open()
            with self.assertRaises(PermissionError):
                Vault(p, "dev2", bytearray(b"correct horse")).open()
            blob = json.load(open(p))
            blob["ct"] = ("00" if blob["ct"][:2] != "00" else "11") + blob["ct"][2:]
            json.dump(blob, open(p, "w"))
            with self.assertRaises(PermissionError):
                v.open()
            v.wipe()
            self.assertEqual(bytes(v._passphrase), b"\0" * len(b"correct horse"))


# ================================================================ policy ledger

class Fixture:
    """An in-memory ceremony with software keys, for exercising the ledger."""

    def __init__(self, policy: Policy | None = None, devs: int = 4):
        self.policy = policy or Policy(m=3, n=3, sm_approvals=2, release_m=3)
        self.cast = Cast.make(self.policy.n, devs)
        self.root = ec.generate_private_key(CURVE)
        self.files: dict[str, bytes] = {}
        rs = spki_der(self.root.public_key())
        self.root_der = build_cert(serial=1, subject_cn="irc-pki-root", subject_ou="root",
                                   subject_spki=rs, issuer_cn="irc-pki-root", issuer_ou="root",
                                   issuer_spki=rs, signer=software_signer(self.root), is_ca=True)
        self.keys = {n: ec.generate_private_key(CURVE) for n in self.cast.roles()}
        self.roles = self.cast.roles()
        serials = {}
        for s, name in enumerate([self.cast.ca, *self.cast.custodians, self.cast.releasebot], 2):
            self.files[f"certs/{s}.der"] = self.cert(s, name)
            serials[name] = s
        self.roster = {"roles": self.roles, "ceremony_serials": serials}
        self.ledger = Ledger(self.policy, self.roster, self.root_der, self.files.get)
        self.revoked: dict[int, dt.datetime] = {}

    def cert(self, serial: int, name: str) -> bytes:
        return build_cert(serial=serial, subject_cn=name, subject_ou=self.roles[name],
                          subject_spki=spki_der(self.keys[name].public_key()),
                          issuer_cn="irc-pki-root", issuer_ou="root",
                          issuer_spki=spki_der(self.root.public_key()),
                          signer=software_signer(self.root), is_ca=False)

    def text(self, actor: str, verb: str, noun: str, ref: str, signer_key=None, **cl) -> str:
        m = g.make(actor, verb, noun, ref, **cl)
        sig = software_signer(signer_key or self.keys[actor])(message_digest(self.policy.channel, m.body()))
        return m.with_sig(sig.hex()).wire()

    def say(self, actor: str, *a, nick=None, **kw):
        return self.ledger.apply(nick or actor, self.text(actor, *a, **kw))

    def unlock(self, k: int | None = None):
        self.say("ca", "requests", "share", "u1", key="02" + "11" * 32)
        for c in self.cast.custodians[: self.policy.m if k is None else k]:
            self.say(c, "sends", "share", "u1", key="02" + "22" * 32, secret="33" * 33)
        return self.say("ca", "unlocks", "token", "u1")

    def request(self, who: str, ref: str):
        return self.say(who, "requests", "cert", ref, for_=who, key=compress(self.keys[who].public_key()))

    def issue(self, who: str, ref: str):
        s = self.ledger.next_serial
        der = self.cert(s, who)
        self.files[f"certs/{s}.der"] = der
        return self.say("ca", "issues", "cert", ref, for_=who, serial=str(s), digest=sha256(der).hex())

    def enroll_secmgr(self):
        self.request("secmgr", "r-sm")
        for c in self.cast.custodians[: self.policy.sm_approvals]:
            self.say(c, "approves", "cert", "r-sm", for_="secmgr")
        return self.issue("secmgr", "r-sm")

    def enroll_dev(self, d: str):
        self.request(d, f"r-{d}")
        self.say("secmgr", "approves", "cert", f"r-{d}", for_=d)
        return self.issue(d, f"r-{d}")

    def revoke(self, ref: str, who: str):
        serial = self.ledger.active(who).serial
        self.revoked[serial] = dt.datetime.now(dt.timezone.utc)
        der = build_crl(number=self.ledger.crl_number + 1, revoked=self.revoked,
                        issuer_cn="irc-pki-root", issuer_ou="root",
                        issuer_spki=spki_der(self.root.public_key()), signer=software_signer(self.root))
        self.files[f"crl/{ref}.der"] = der
        return self.say("ca", "issues", "revocation", ref, for_=who, serial=str(serial),
                        digest=sha256(der).hex())


class LedgerTest(unittest.TestCase):
    def test_happy_path(self):
        f = Fixture()
        self.assertEqual(f.unlock().status, "accepted")
        self.assertEqual(f.enroll_secmgr().status, "accepted")
        for d in f.cast.developers:
            self.assertEqual(f.enroll_dev(d).status, "accepted", d)
        self.assertTrue(all(f.ledger.active(d) for d in f.cast.developers))

    def test_unlock_needs_m_shares(self):
        f = Fixture()
        self.assertEqual(f.unlock(k=2).status, "violation")
        self.assertFalse(f.ledger.unlocked)

    def test_unlock_works_with_m_of_larger_n(self):
        f = Fixture(Policy(m=3, n=5))
        self.assertEqual(f.unlock(k=3).status, "accepted")

    def test_no_issuance_while_locked(self):
        f = Fixture()
        f.request("secmgr", "r-sm")
        for c in f.cast.custodians[:2]:
            f.say(c, "approves", "cert", "r-sm", for_="secmgr")
        self.assertEqual(f.issue("secmgr", "r-sm").status, "violation")

    def test_secmgr_cert_needs_two_custodians(self):
        f = Fixture()
        f.unlock()
        f.request("secmgr", "r-sm")
        f.say("custodian1", "approves", "cert", "r-sm", for_="secmgr")
        # the same custodian approving twice does not count twice
        self.assertEqual(f.say("custodian1", "approves", "cert", "r-sm", for_="secmgr").status, "rejected")
        self.assertEqual(f.issue("secmgr", "r-sm").status, "violation")
        f.say("custodian2", "approves", "cert", "r-sm", for_="secmgr")
        self.assertEqual(f.issue("secmgr", "r-sm").status, "accepted")

    def test_dev_cert_needs_secmgr_not_peer(self):
        f = Fixture()
        f.unlock()
        f.enroll_secmgr()
        f.enroll_dev("dev1")
        f.request("dev2", "r-dev2")
        self.assertEqual(f.say("dev1", "approves", "cert", "r-dev2", for_="dev2").status, "rejected")
        self.assertEqual(f.say("custodian1", "approves", "cert", "r-dev2", for_="dev2").status, "rejected")
        self.assertEqual(f.issue("dev2", "r-dev2").status, "violation")

    def test_issued_cert_must_carry_requested_key(self):
        f = Fixture()
        f.unlock()
        f.enroll_secmgr()
        f.request("dev1", "r-dev1")
        f.say("secmgr", "approves", "cert", "r-dev1", for_="dev1")
        f.keys["dev1"] = ec.generate_private_key(CURVE)   # CA swaps in another key
        self.assertEqual(f.issue("dev1", "r-dev1").status, "violation")

    def test_secmgr_revocation_needs_two_custodians(self):
        f = Fixture()
        f.unlock()
        f.enroll_secmgr()
        s = f.ledger.active("secmgr").serial
        self.assertEqual(f.say("dev1", "requests", "revocation", "v1", for_="secmgr", serial=str(s)).status,
                         "invalid")  # dev1 has no cert to sign with
        f.say("custodian1", "requests", "revocation", "v1", for_="secmgr", serial=str(s))
        f.say("custodian1", "approves", "revocation", "v1", for_="secmgr", serial=str(s))
        self.assertEqual(f.revoke("v1", "secmgr").status, "violation")
        f.revoked.clear()
        f.say("custodian3", "approves", "revocation", "v1", for_="secmgr", serial=str(s))
        self.assertEqual(f.revoke("v1", "secmgr").status, "accepted")
        self.assertIsNone(f.ledger.active("secmgr"))

    def test_revoked_dev_cannot_approve_and_release_quorum(self):
        f = Fixture()
        f.unlock()
        f.enroll_secmgr()
        for d in f.cast.developers:
            f.enroll_dev(d)
        sm = f.ledger.active("secmgr").serial
        f.say("secmgr", "requests", "revocation", "v1", for_="dev4", serial=str(f.ledger.active("dev4").serial))
        self.assertEqual(f.revoke("v1", "dev4").status, "accepted")
        dg = "ab" * 32
        f.say("releasebot", "submits", "release", "rel1", version="1.0.0", digest=dg)
        self.assertEqual(f.say("dev4", "approves", "release", "rel1", digest=dg).status, "rejected")
        f.say("dev1", "approves", "release", "rel1", digest=dg)
        f.say("dev2", "approves", "release", "rel1", digest=dg)
        f.say("secmgr", "approves", "release", "rel1", digest=dg)
        self.assertEqual(f.say("releasebot", "publishes", "release", "rel1", version="1.0.0",
                               digest=dg).status, "violation")
        self.assertEqual(f.say("dev3", "approves", "release", "rel1", digest="cd" * 32).status, "rejected")
        f.say("dev3", "approves", "release", "rel1", digest=dg)
        self.assertEqual(f.say("releasebot", "publishes", "release", "rel1", version="1.0.0",
                               digest=dg).status, "accepted")
        self.assertTrue(sm)

    def test_veto_blocks_release(self):
        f = Fixture()
        f.unlock()
        f.enroll_secmgr()
        for d in f.cast.developers:
            f.enroll_dev(d)
        dg = "ab" * 32
        f.say("releasebot", "submits", "release", "rel1", version="2.0.0", digest=dg)
        for d in f.cast.developers[:3]:
            f.say(d, "approves", "release", "rel1", digest=dg)
        f.say("secmgr", "approves", "release", "rel1", digest=dg)
        f.say("dev4", "rejects", "release", "rel1", digest=dg, because="hash mismatch")
        self.assertFalse(f.ledger.release_ready("rel1"))

    def test_forgery_spoofing_and_noncanonical(self):
        f = Fixture()
        mallory = ec.generate_private_key(CURVE)
        forged = g.make("ca", "requests", "share", "u1", key="02" + "11" * 32)
        sig = software_signer(mallory)(message_digest("#pki", forged.body())).hex()
        self.assertEqual(f.ledger.apply("ca", forged.with_sig(sig).wire()).reason, "bad signature")
        good = f.text("custodian1", "approves", "cert", "r1", for_="secmgr")
        self.assertEqual(f.ledger.apply("custodian2", good).status, "invalid")       # nick spoof
        self.assertEqual(f.ledger.apply("custodian1", good.replace(" the ", " a ")).reason,
                         "bad signature")                                             # edited text
        self.assertEqual(f.ledger.apply("custodian1", good.replace("for", "for ")).reason,
                         "not in canonical form")
        unsigned = g.make("custodian1", "approves", "cert", "r1", for_="secmgr").wire()
        self.assertEqual(f.ledger.apply("custodian1", unsigned).status, "invalid")
        other_chan = g.make("custodian1", "approves", "cert", "r1", for_="secmgr")
        sig = software_signer(f.keys["custodian1"])(message_digest("#other", other_chan.body())).hex()
        self.assertEqual(f.ledger.apply("custodian1", other_chan.with_sig(sig).wire()).reason,
                         "bad signature")                                             # cross-channel replay

    def test_conformance_detects_missing_and_extra(self):
        f = Fixture()
        f.unlock()
        f.enroll_secmgr()
        script = [{"do": "unlock"}, {"do": "enroll", "who": "secmgr", "approvers": ["custodian1", "custodian2"]}]
        self.assertEqual(check_conformance(f.ledger.history, script, f.cast, f.policy), [])
        f.enroll_dev("dev1")  # not in the script
        self.assertTrue(check_conformance(f.ledger.history, script, f.cast, f.policy))
        self.assertTrue(check_conformance(f.ledger.history, script + [{"do": "enroll", "who": "dev2",
                                                                       "approvers": ["secmgr"]}],
                                          f.cast, f.policy))


class LogTest(unittest.TestCase):
    def write(self, d: str) -> str:
        p = os.path.join(d, "irc", "server.log")
        w = LogWriter(p)
        for i in range(5):
            w.append("PRIVMSG", "dev1", "#pki", f"line {i}")
        w.close()
        return p

    def test_chain_and_tamper(self):
        with tempfile.TemporaryDirectory() as d:
            p = self.write(d)
            entries, errs = read_log(p)
            self.assertEqual((len(entries), errs), (5, []))
            self.assertEqual(entries[0].hash, chain(GENESIS, "\t".join(
                ["000001", entries[0].ts, "PRIVMSG", "dev1", "#pki", "line 0"])))
            lines = open(p).read().splitlines(True)
            for mutate in (lambda L: L[:2] + L[3:],                       # delete
                           lambda L: [L[1], L[0]] + L[2:],                # reorder
                           lambda L: L[:2] + [L[2].replace("line 2", "line X")] + L[3:]):  # edit
                open(p, "w").writelines(mutate(list(lines)))
                self.assertTrue(read_log(p)[1])

    def test_rejects_control_characters(self):
        with tempfile.TemporaryDirectory() as d:
            w = LogWriter(os.path.join(d, "l", "log"))
            with self.assertRaises(ValueError):
                w.append("PRIVMSG", "a", "#pki", "x\ty")
            w.close()


# ================================================================ end to end

@unittest.skipUnless(HAVE_HSM, "SoftHSM2 not installed")
class EndToEndTest(unittest.TestCase):
    """Full ceremonies with real processes, SoftHSM tokens and IRC."""

    tmp: str

    @classmethod
    def setUpClass(cls):
        from irc_pki_sim import Simulation
        cls.tmp = tempfile.mkdtemp(prefix="ircpki-")
        cls.Simulation = Simulation
        cls.run_dir = os.path.join(cls.tmp, "default")
        cls.report = cls._run(cls.run_dir, Policy(m=3, n=3, sm_approvals=2, release_m=3), 5, 3)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    @classmethod
    def _run(cls, run_dir, policy, devs, hsm):
        sim = cls.Simulation(run_dir, policy, Cast.make(policy.n, devs), hsm)
        return asyncio.run(sim.run())

    def test_default_ceremony_passes(self):
        r = self.report
        self.assertTrue(r["ok"], json.dumps({k: r[k] for k in ("errors", "agent_errors")}, indent=1))
        st = r["state"]
        names = {c["name"]: c for c in st["certs"].values()}
        for d in [f"dev{i}" for i in range(1, 6)]:
            self.assertIn(d, names)
        self.assertTrue(names["dev5"]["revoked"] and names["secmgr"]["revoked"])
        self.assertEqual(st["hsm_switches"], ["hsm-1"])
        self.assertEqual([x["published"] for x in st["releases"].values()], [True, False, True])
        self.assertEqual(len(r["rejected_but_expected_to_be_harmless"]), 1)

    def test_primaries_all_replicas_hold_the_root_key(self):
        self.assertEqual(self.report["replica_health"], {"0": True, "1": True, "2": True})

    def test_no_secret_leaks_and_vaults_sealed(self):
        lc = self.report["secrets_leak_check"]
        self.assertEqual(len(lc), 3 + 1 + 1 + 5 + 1)
        self.assertTrue(all(v["clean"] for v in lc.values()), lc)
        self.assertIn("share", lc["custodian1"]["checked"])
        for name in lc:
            p = os.path.join(self.run_dir, "agents", name, "vault.json")
            self.assertEqual(stat.S_IMODE(os.stat(p).st_mode), 0o600)

    def test_rpc(self):
        rc = self.report["rpc_checks"]
        self.assertEqual(len(rc["list"]["result"]), 3)
        self.assertEqual(rc["unknown_method"]["error"]["code"], -32601)
        self.assertEqual(rc["unknown_id"]["error"]["code"], -32602)
        self.assertIn("PermissionError", rc["outside_artifact"]["error"]["message"])
        ev = rc["evidence"]["result"]
        self.assertEqual(ev["status"]["state"], "published")
        # the evidence bundle verifies offline from the certs it carries
        from cryptography import x509
        from pkicrypto import verify_raw
        for s in ev["sentences"]:
            m = g.parse(s["text"])
            pub = x509.load_der_x509_certificate(bytes.fromhex(ev["certs"][s["nick"]])).public_key()
            self.assertTrue(verify_raw(pub, message_digest(ev["channel"], m.body()), bytes.fromhex(m.sig)))

    def _copy(self, name):
        dst = os.path.join(self.tmp, name)
        shutil.rmtree(dst, ignore_errors=True)
        shutil.copytree(self.run_dir, dst, ignore=shutil.ignore_patterns("agents", "hsm"))
        return dst

    def test_offline_verifier_catches_tampering(self):
        from verify import verify_run
        self.assertTrue(verify_run(self.run_dir, self.report["root_sha256"])["ok"])
        self.assertFalse(verify_run(self.run_dir, "00" * 32)["ok"])          # wrong pin

        d = self._copy("edit")
        log = os.path.join(d, "irc", "server.log")
        text = open(log).read().replace("approves the cert #r-dev2-1 for dev2",
                                        "approves the cert #r-dev2-1 for dev3", 1)
        open(log, "w").write(text)
        self.assertFalse(verify_run(d)["ok"])

        # A forger who rewrites the whole hash chain still cannot forge signatures.
        d = self._copy("rechain")
        log = os.path.join(d, "irc", "server.log")
        rows = [l.rstrip("\n").split("\t") for l in open(log)]
        for r in rows:
            if "secmgr approves the cert #r-dev4-1" in r[5]:
                r[5] = r[5].replace("#r-dev4-1", "#r-dev4-2")
        prev, out = GENESIS, []
        for r in rows:
            prev = chain(prev, "\t".join(r[:6]))
            out.append("\t".join(r[:6] + [prev]) + "\n")
        open(log, "w").writelines(out)
        rep = verify_run(d)
        self.assertFalse(rep["ok"])
        self.assertTrue(any("bad signature" in e for e in rep["errors"]), rep["errors"])

        d = self._copy("certfile")
        open(os.path.join(d, "pki", "certs", "99.der"), "wb").write(b"rogue")
        self.assertFalse(verify_run(d)["ok"])

        d = self._copy("script")
        sp = os.path.join(d, "script.json")
        s = json.load(open(sp))
        s.insert(2, {"do": "enroll", "who": "dev9", "approvers": ["secmgr"]})
        json.dump(s, open(sp, "w"))
        self.assertFalse(verify_run(d)["ok"])

    def test_scales_beyond_three(self):
        rep = self._run(os.path.join(self.tmp, "big"),
                        Policy(m=3, n=5, sm_approvals=2, release_m=4), devs=7, hsm=4)
        self.assertTrue(rep["ok"], rep["errors"] + rep["agent_errors"])
        self.assertEqual(len(rep["replica_health"]), 4)

    @unittest.skipUnless(shutil.which("qemu-system-x86_64") and os.access("/boot/vmlinuz", os.R_OK),
                         "QEMU or a readable kernel not available")
    def test_vm_reverifies_archive(self):
        from vm import verify_in_vm
        vm = verify_in_vm(self._copy("vm"), self.report)
        self.assertTrue(vm["ok"], vm)
        self.assertEqual(vm["guest_chain_head"], self.report["log_head"])


if __name__ == "__main__":
    unittest.main()

"""Offline verifier for a finished run directory.

Checks, independently of any running process:

1. the server log's hash chain, sequence numbers and timestamps;
2. the root certificate against a pinned SHA-256 fingerprint;
3. the roster signature (made by the root key at the ceremony);
4. a full replay of every #pki sentence through the policy ledger
   (grammar, canonical form, nick binding, signature, policy);
5. that every certificate and CRL file on disk is accounted for by the log;
6. conformance of the log to the key-signing script.
"""

from __future__ import annotations

import json
import os

from cryptography import x509

import safepath
from safepath import inside
from ledger import Ledger, Policy, file_loader, load_roster, read_log
from pkicrypto import sha256
from scenario import Cast, check_conformance


def verify_run(run_dir: str, root_fp: str | None = None) -> dict:
    run_dir = safepath.run_dir(run_dir)
    pki = inside(run_dir, "pki")
    errors: list[str] = []
    entries, chain_errors = read_log(run_dir)
    errors += [f"log: {e}" for e in chain_errors]

    with open(inside(pki, "root.der"), "rb") as f:
        root_der = f.read()
    fp = sha256(root_der).hex()
    if root_fp and fp != root_fp.lower():
        errors.append(f"root fingerprint {fp} does not match the pinned {root_fp}")
    root = x509.load_der_x509_certificate(root_der)
    roster = load_roster(pki, root.public_key())
    policy = Policy(**roster["policy"])
    cast = Cast(**{k: tuple(v) if isinstance(v, list) else v for k, v in roster["cast"].items()})
    ledger = Ledger(policy, roster, root_der, file_loader(pki))

    rejected = []
    for e in entries:
        if e.cmd != "PRIVMSG":
            continue
        if e.target != policy.channel:
            errors.append(f"line {e.seq}: traffic on unexpected channel {e.target}")
            continue
        v = ledger.apply(e.nick, e.text)
        if v.is_error:
            errors.append(f"line {e.seq}: {v.status}: {v.reason}: {e.text[:80]}")
        elif v.status == "rejected":
            rejected.append(f"line {e.seq}: {e.nick}: {v.reason}")

    known = {f"{s}.der" for s in ledger.certs}
    for fn in sorted(os.listdir(inside(pki, "certs"))):
        if fn not in known:
            errors.append(f"pki/certs/{fn} was never issued in the log")
    crl_dir = inside(pki, "crl")
    accepted_revocations = {v.msg.ref for _, _, v in ledger.history
                            if v.ok and (v.msg.verb, v.msg.noun) == ("issues", "revocation")}
    if os.path.isdir(crl_dir):
        for fn in sorted(os.listdir(crl_dir)):
            if fn.removesuffix(".der") not in accepted_revocations:
                errors.append(f"pki/crl/{fn} was never issued in the log")

    script_path = inside(run_dir, "script.json")
    script = []
    if os.path.exists(script_path):
        with open(script_path) as f:
            script = json.load(f)
        errors += [f"script: {e}" for e in check_conformance(ledger.history, script, cast, policy)]
    else:
        errors.append("script.json missing; cannot check conformance")

    return {
        "ok": not errors,
        "errors": errors,
        "rejected_but_expected_to_be_harmless": rejected,
        "root_sha256": fp,
        "log_lines": len(entries),
        "log_head": entries[-1].hash if entries else None,
        "sentences": sum(1 for e in entries if e.cmd == "PRIVMSG"),
        "script_steps": len(script),
        "state": ledger.summary(),
    }

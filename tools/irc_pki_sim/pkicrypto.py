"""Crypto building blocks: P-256 signatures, Shamir m-of-n, ECIES share
transport, the passkey vault, and X.509 / CRL construction with an external
(PKCS#11) signer.

Nothing here touches PKCS#11 directly; signing is always done through a
``Signer`` callable ``sign(digest32) -> raw r||s (64 bytes)`` so the same
certificate code runs against SoftHSM in production and in-memory keys during
the root key ceremony.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import hmac
import json
import os
import secrets
from typing import Callable

from asn1crypto import algos, crl as a_crl, keys as a_keys, x509 as a_x509
from cryptography import x509
from cryptography.exceptions import InvalidSignature, InvalidTag
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import (
    Prehashed, decode_dss_signature, encode_dss_signature)
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt

Signer = Callable[[bytes], bytes]
CURVE = ec.SECP256R1()
SIG_CONTEXT = b"ircpki/1\n"
ORG = "irc-pki-sim"


def sha256(b: bytes) -> bytes:
    return hashlib.sha256(b).digest()


def message_digest(channel: str, body: str) -> bytes:
    """What an actor signs for a ceremony sentence: domain tag, channel, text."""
    return sha256(SIG_CONTEXT + channel.encode() + b"\n" + body.encode())


# ------------------------------------------------------------------ EC keys

def compress(pub: ec.EllipticCurvePublicKey) -> str:
    return pub.public_bytes(serialization.Encoding.X962,
                            serialization.PublicFormat.CompressedPoint).hex()


def decompress(hexkey: str) -> ec.EllipticCurvePublicKey:
    return ec.EllipticCurvePublicKey.from_encoded_point(CURVE, bytes.fromhex(hexkey))


def spki_der(pub: ec.EllipticCurvePublicKey) -> bytes:
    return pub.public_bytes(serialization.Encoding.DER,
                            serialization.PublicFormat.SubjectPublicKeyInfo)


def verify_raw(pub: ec.EllipticCurvePublicKey, digest: bytes, raw_sig: bytes) -> bool:
    if len(raw_sig) != 64:
        return False
    r, s = int.from_bytes(raw_sig[:32], "big"), int.from_bytes(raw_sig[32:], "big")
    try:
        pub.verify(encode_dss_signature(r, s), digest, ec.ECDSA(Prehashed(hashes.SHA256())))
        return True
    except InvalidSignature:
        return False


def software_signer(priv: ec.EllipticCurvePrivateKey) -> Signer:
    def sign(digest: bytes) -> bytes:
        der = priv.sign(digest, ec.ECDSA(Prehashed(hashes.SHA256())))
        r, s = decode_dss_signature(der)
        return r.to_bytes(32, "big") + s.to_bytes(32, "big")
    return sign


# ------------------------------------------------------------- Shamir m-of-n
# Field GF(p) with the Mersenne prime 2^127-1; the secret is a 120-bit value,
# so a share is (x, y) with y < p fitting in 16 bytes.

PRIME = (1 << 127) - 1


def shamir_split(secret: int, m: int, n: int) -> list[tuple[int, int]]:
    if not (1 <= m <= n <= 255):
        raise ValueError("need 1 <= m <= n <= 255")
    if not (0 <= secret < PRIME):
        raise ValueError("secret out of field")
    coeffs = [secret] + [secrets.randbelow(PRIME) for _ in range(m - 1)]
    shares = []
    for x in range(1, n + 1):
        y = 0
        for c in reversed(coeffs):
            y = (y * x + c) % PRIME
        shares.append((x, y))
    return shares


def shamir_combine(shares: list[tuple[int, int]]) -> int:
    xs = [x for x, _ in shares]
    if len(set(xs)) != len(xs) or any(not (1 <= x <= 255) for x in xs):
        raise ValueError("share x coordinates must be distinct and in 1..255")
    secret = 0
    for i, (xi, yi) in enumerate(shares):
        num, den = 1, 1
        for j, (xj, _) in enumerate(shares):
            if i != j:
                num = (num * -xj) % PRIME
                den = (den * (xi - xj)) % PRIME
        secret = (secret + yi * num * pow(den, -1, PRIME)) % PRIME
    return secret


def pin_from_secret(secret: int) -> str:
    """SoftHSM PINs must be printable; the CA PIN is the hex of the secret."""
    return secret.to_bytes(15, "big").hex()


def new_ca_secret() -> int:
    return int.from_bytes(secrets.token_bytes(15), "big")


# --------------------------------------------------- ECIES for share transport

def _share_key(shared: bytes, ref: str, custodian: str) -> bytes:
    return HKDF(hashes.SHA256(), 32, salt=None,
                info=f"ircpki share {ref} {custodian}".encode()).derive(shared)


def seal_share(ca_eph_hex: str, ref: str, custodian: str, share: tuple[int, int]) -> tuple[str, str]:
    """Encrypt one share to the CA's ephemeral key. Returns (eph_pub_hex, ct_hex)."""
    eph = ec.generate_private_key(CURVE)
    key = _share_key(eph.exchange(ec.ECDH(), decompress(ca_eph_hex)), ref, custodian)
    pt = bytes([share[0]]) + share[1].to_bytes(16, "big")
    # The key is fresh for every message (new ephemeral), so a fixed nonce is safe.
    ct = AESGCM(key).encrypt(b"\0" * 12, pt, ref.encode())
    return compress(eph.public_key()), ct.hex()


def open_share(ca_eph: ec.EllipticCurvePrivateKey, ref: str, custodian: str,
               eph_hex: str, ct_hex: str) -> tuple[int, int]:
    key = _share_key(ca_eph.exchange(ec.ECDH(), decompress(eph_hex)), ref, custodian)
    pt = AESGCM(key).decrypt(b"\0" * 12, bytes.fromhex(ct_hex), ref.encode())
    if len(pt) != 17:
        raise ValueError("bad share length")
    return pt[0], int.from_bytes(pt[1:], "big")


# ------------------------------------------------------------- passkey vault

class Vault:
    """Per-actor sealed secret store.

    The actor's *passphrase* exists only in that actor's process memory (it
    stands in for something the person memorises). The vault file on disk
    holds the actor's HSM PIN ("passkey"), SO PIN and any custodian share,
    encrypted with AES-256-GCM under scrypt(passphrase). Without the
    passphrase the file is useless; the PIN in turn only unlocks a token whose
    private key is non-extractable. The file is created 0600.
    """

    SCRYPT_N = 2 ** 15

    def __init__(self, path: str, owner: str, passphrase: bytearray):
        self.path = path
        self.owner = owner
        self._passphrase = passphrase

    def _key(self, salt: bytes) -> bytes:
        return Scrypt(salt=salt, length=32, n=self.SCRYPT_N, r=8, p=1).derive(bytes(self._passphrase))

    def seal(self, secrets_: dict[str, str]) -> None:
        salt, nonce = os.urandom(16), os.urandom(12)
        aad = f"ircpki-vault/1 {self.owner}".encode()
        ct = AESGCM(self._key(salt)).encrypt(nonce, json.dumps(secrets_).encode(), aad)
        blob = {"v": 1, "owner": self.owner, "kdf": "scrypt", "n": self.SCRYPT_N,
                "salt": salt.hex(), "nonce": nonce.hex(), "ct": ct.hex()}
        tmp = self.path + ".tmp"
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as f:
            json.dump(blob, f)
        os.replace(tmp, self.path)

    def open(self) -> dict[str, str]:
        with open(self.path) as f:
            blob = json.load(f)
        if blob.get("owner") != self.owner:
            raise PermissionError("vault belongs to someone else")
        aad = f"ircpki-vault/1 {self.owner}".encode()
        try:
            pt = AESGCM(self._key(bytes.fromhex(blob["salt"]))).decrypt(
                bytes.fromhex(blob["nonce"]), bytes.fromhex(blob["ct"]), aad)
        except InvalidTag:
            raise PermissionError("wrong passphrase or tampered vault") from None
        return json.loads(pt)

    def update(self, **kv: str) -> None:
        data = self.open() if os.path.exists(self.path) else {}
        data.update(kv)
        self.seal(data)

    def wipe(self) -> None:
        for i in range(len(self._passphrase)):
            self._passphrase[i] = 0


# --------------------------------------------------------- X.509 and CRLs

def _name(cn: str, ou: str) -> a_x509.Name:
    return a_x509.Name.build({"organization_name": ORG, "organizational_unit_name": ou,
                              "common_name": cn})


def _time(t: dt.datetime) -> a_x509.Time:
    return a_x509.Time({"utc_time": t.replace(microsecond=0)})


def _p1363_to_der(raw: bytes) -> bytes:
    return algos.DSASignature.from_p1363(raw).dump()


def build_cert(*, serial: int, subject_cn: str, subject_ou: str, subject_spki: bytes,
               issuer_cn: str, issuer_ou: str, issuer_spki: bytes, signer: Signer,
               is_ca: bool, days: int = 365, now: dt.datetime | None = None) -> bytes:
    now = now or dt.datetime.now(dt.timezone.utc)
    spki = a_keys.PublicKeyInfo.load(subject_spki)
    iss = a_keys.PublicKeyInfo.load(issuer_spki)
    exts = [
        {"extn_id": "basic_constraints", "critical": True,
         "extn_value": {"ca": is_ca, "path_len_constraint": 0 if is_ca else None}},
        {"extn_id": "key_usage", "critical": True,
         "extn_value": {"key_cert_sign", "crl_sign"} if is_ca else {"digital_signature"}},
        {"extn_id": "key_identifier", "critical": False, "extn_value": spki.sha1},
        {"extn_id": "authority_key_identifier", "critical": False,
         "extn_value": {"key_identifier": iss.sha1}},
    ]
    if not is_ca:
        exts.append({"extn_id": "extended_key_usage", "critical": False,
                     "extn_value": ["code_signing", "client_auth"]})
    tbs = a_x509.TbsCertificate({
        "version": "v3",
        "serial_number": serial,
        "signature": {"algorithm": "sha256_ecdsa"},
        "issuer": _name(issuer_cn, issuer_ou),
        "validity": {"not_before": _time(now - dt.timedelta(minutes=5)),
                     "not_after": _time(now + dt.timedelta(days=days))},
        "subject": _name(subject_cn, subject_ou),
        "subject_public_key_info": spki,
        "extensions": exts,
    })
    sig = signer(sha256(tbs.dump()))
    return a_x509.Certificate({
        "tbs_certificate": tbs,
        "signature_algorithm": {"algorithm": "sha256_ecdsa"},
        "signature_value": _p1363_to_der(sig),
    }).dump()


def build_crl(*, number: int, revoked: dict[int, dt.datetime], issuer_cn: str, issuer_ou: str,
              issuer_spki: bytes, signer: Signer, now: dt.datetime | None = None) -> bytes:
    now = (now or dt.datetime.now(dt.timezone.utc)).replace(microsecond=0)
    entries = [{"user_certificate": s, "revocation_date": _time(t),
                "crl_entry_extensions": [{"extn_id": "crl_reason", "critical": False,
                                          "extn_value": "key_compromise"}]}
               for s, t in sorted(revoked.items())]
    tbs = a_crl.TbsCertList({
        "version": "v2",
        "signature": {"algorithm": "sha256_ecdsa"},
        "issuer": _name(issuer_cn, issuer_ou),
        "this_update": _time(now),
        "next_update": _time(now + dt.timedelta(days=7)),
        "revoked_certificates": entries or None,
        "crl_extensions": [
            {"extn_id": "crl_number", "critical": False, "extn_value": number},
            {"extn_id": "authority_key_identifier", "critical": False,
             "extn_value": {"key_identifier": a_keys.PublicKeyInfo.load(issuer_spki).sha1}},
        ],
    })
    sig = signer(sha256(tbs.dump()))
    return a_crl.CertificateList({
        "tbs_cert_list": tbs,
        "signature_algorithm": {"algorithm": "sha256_ecdsa"},
        "signature": _p1363_to_der(sig),
    }).dump()


def cert_cn_ou(cert: x509.Certificate) -> tuple[str, str]:
    cn = cert.subject.get_attributes_for_oid(x509.NameOID.COMMON_NAME)[0].value
    ou = cert.subject.get_attributes_for_oid(x509.NameOID.ORGANIZATIONAL_UNIT_NAME)[0].value
    return str(cn), str(ou)


def verify_issued_by(cert: x509.Certificate, root: x509.Certificate) -> bool:
    try:
        cert.verify_directly_issued_by(root)
        return True
    except (InvalidSignature, ValueError, TypeError):
        return False


def constant_eq(a: str, b: str) -> bool:
    return hmac.compare_digest(a.encode(), b.encode())

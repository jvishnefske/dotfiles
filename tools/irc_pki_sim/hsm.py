"""SoftHSM2 token wrapper (python-pkcs11).

Every actor and every CA replica gets its *own* SoftHSM token directory and
config file, so one process can never see another's objects. The PKCS#11
library reads ``SOFTHSM2_CONF`` when it is first initialised, which is why
``Token`` must be created in the process that owns it (each actor and replica
is a separate spawned process).
"""

from __future__ import annotations

import os
import secrets
import subprocess

from asn1crypto import core
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec

from pkicrypto import CURVE, verify_raw

DEFAULT_LIBS = ("/usr/lib/softhsm/libsofthsm2.so",
                "/usr/lib/x86_64-linux-gnu/softhsm/libsofthsm2.so",
                "/usr/local/lib/softhsm/libsofthsm2.so",
                "/opt/homebrew/lib/softhsm/libsofthsm2.so")
KEY_LABEL = "identity"
KEY_ID = b"\x01"


def find_softhsm() -> str | None:
    env = os.environ.get("SOFTHSM2_LIB")
    if env and os.path.exists(env):
        return env
    return next((p for p in DEFAULT_LIBS if os.path.exists(p)), None)


def write_conf(home: str) -> str:
    tokdir = os.path.join(home, "tokens")
    os.makedirs(tokdir, mode=0o700, exist_ok=True)
    conf = os.path.join(home, "softhsm2.conf")
    with open(conf, "w") as f:
        f.write(f"directories.tokendir = {tokdir}\nobjectstore.backend = file\n"
                "log.level = ERROR\nslots.removable = false\n")
    return conf


class HsmError(RuntimeError):
    pass


class Token:
    """One PKCS#11 token holding one non-extractable P-256 signing key."""

    def __init__(self, home: str, label: str):
        import pkcs11  # imported here: must load after SOFTHSM2_CONF is set
        self._p = pkcs11
        self.home = home
        self.label = label
        self.conf = write_conf(home)
        os.environ["SOFTHSM2_CONF"] = self.conf
        lib_path = find_softhsm()
        if not lib_path:
            raise HsmError("libsofthsm2.so not found (set SOFTHSM2_LIB)")
        self.lib = pkcs11.lib(lib_path)
        self.session = None

    # -- provisioning -----------------------------------------------------
    def initialise(self, user_pin: str) -> None:
        """Create the token. softhsm2-util only takes PINs on argv, which other
        local users can read from /proc, so it is given throw-away PINs that
        are rotated immediately through PKCS#11 C_SetPIN. The final SO PIN is
        random and discarded: nobody can re-initialise the user PIN."""
        tmp_so, tmp_user = secrets.token_hex(8), secrets.token_hex(8)
        r = subprocess.run(["softhsm2-util", "--init-token", "--free", "--label", self.label,
                            "--so-pin", tmp_so, "--pin", tmp_user],
                           env={**os.environ, "SOFTHSM2_CONF": self.conf},
                           capture_output=True, text=True)
        if r.returncode != 0:
            raise HsmError(f"softhsm2-util failed: {r.stderr.strip()}")
        self.lib.reinitialize()
        tok = self.lib.get_token(token_label=self.label)
        with tok.open(rw=True, so_pin=tmp_so) as s:
            s.set_pin(tmp_so, secrets.token_hex(16))
        with tok.open(rw=True, user_pin=tmp_user) as s:
            s.set_pin(tmp_user, user_pin)

    def login(self, user_pin: str) -> None:
        tok = self.lib.get_token(token_label=self.label)
        try:
            self.session = tok.open(rw=True, user_pin=user_pin)
        except self._p.exceptions.PinIncorrect:
            raise HsmError("PIN incorrect") from None

    def logout(self) -> None:
        if self.session is not None:
            self.session.close()
            self.session = None

    def generate_key(self) -> ec.EllipticCurvePublicKey:
        from pkcs11 import Attribute, KeyType
        from pkcs11.util.ec import encode_named_curve_parameters
        params = self.session.create_domain_parameters(
            KeyType.EC, {Attribute.EC_PARAMS: encode_named_curve_parameters("secp256r1")}, local=True)
        params.generate_keypair(store=True, label=KEY_LABEL, id=KEY_ID,
                                private_template={Attribute.SENSITIVE: True,
                                                  Attribute.EXTRACTABLE: False,
                                                  Attribute.SIGN: True})
        return self.public_key()

    def import_private(self, d: int) -> ec.EllipticCurvePublicKey:
        """Load the ceremony root key: stored sensitive and non-extractable."""
        from pkcs11 import Attribute, KeyType, ObjectClass
        from pkcs11.util.ec import encode_named_curve_parameters
        params = encode_named_curve_parameters("secp256r1")
        pub = ec.derive_private_key(d, CURVE).public_key()
        point = core.OctetString(pub.public_bytes(
            serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)).dump()
        self.session.create_object({
            Attribute.CLASS: ObjectClass.PRIVATE_KEY, Attribute.KEY_TYPE: KeyType.EC,
            Attribute.TOKEN: True, Attribute.PRIVATE: True, Attribute.SENSITIVE: True,
            Attribute.EXTRACTABLE: False, Attribute.SIGN: True, Attribute.EC_PARAMS: params,
            Attribute.VALUE: d.to_bytes(32, "big"), Attribute.LABEL: KEY_LABEL, Attribute.ID: KEY_ID})
        self.session.create_object({
            Attribute.CLASS: ObjectClass.PUBLIC_KEY, Attribute.KEY_TYPE: KeyType.EC,
            Attribute.TOKEN: True, Attribute.VERIFY: True, Attribute.EC_PARAMS: params,
            Attribute.EC_POINT: point, Attribute.LABEL: KEY_LABEL, Attribute.ID: KEY_ID})
        return self.public_key()

    # -- use --------------------------------------------------------------
    def public_key(self) -> ec.EllipticCurvePublicKey:
        from pkcs11 import Attribute, ObjectClass
        pub = self.session.get_key(object_class=ObjectClass.PUBLIC_KEY, label=KEY_LABEL)
        raw = core.OctetString.load(pub[Attribute.EC_POINT]).native
        return ec.EllipticCurvePublicKey.from_encoded_point(CURVE, raw)

    def private_is_locked_down(self) -> bool:
        from pkcs11 import Attribute, ObjectClass
        k = self.session.get_key(object_class=ObjectClass.PRIVATE_KEY, label=KEY_LABEL)
        return bool(k[Attribute.SENSITIVE]) and not bool(k[Attribute.EXTRACTABLE])

    def sign(self, digest: bytes) -> bytes:
        from pkcs11 import Mechanism, ObjectClass
        if self.session is None:
            raise HsmError("token is locked")
        if len(digest) != 32:
            raise HsmError("sign() takes a SHA-256 digest")
        k = self.session.get_key(object_class=ObjectClass.PRIVATE_KEY, label=KEY_LABEL)
        raw = k.sign(digest, mechanism=Mechanism.ECDSA)
        # Never hand out a signature the token's own public key rejects.
        if not verify_raw(self.public_key(), digest, raw):
            raise HsmError("token produced an invalid signature")
        return raw

    def store_cert(self, der: bytes, subject_der: bytes) -> None:
        from pkcs11 import Attribute, CertificateType, ObjectClass
        for old in self.session.get_objects({Attribute.CLASS: ObjectClass.CERTIFICATE}):
            old.destroy()
        self.session.create_object({
            Attribute.CLASS: ObjectClass.CERTIFICATE,
            Attribute.CERTIFICATE_TYPE: CertificateType.X_509,
            Attribute.TOKEN: True, Attribute.LABEL: KEY_LABEL, Attribute.ID: KEY_ID,
            Attribute.SUBJECT: subject_der, Attribute.VALUE: der})

    def load_cert(self) -> bytes | None:
        from pkcs11 import Attribute, ObjectClass
        for c in self.session.get_objects({Attribute.CLASS: ObjectClass.CERTIFICATE}):
            return bytes(c[Attribute.VALUE])
        return None

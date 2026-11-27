# irc_pki_sim: a PKCS#11 key-signing ceremony over logged IRC

This simulates a small PKI ceremony. Each actor runs as its own OS process and
has its own SoftHSM2 token. The actors talk only through a minimal IRC server
that logs everything, and they speak in signed English-like sentences that an
LL(1) parser accepts. When the script finishes, the log is verified offline.
It can then be verified a second time inside a QEMU VM booted from an ISO of
the archive.

```
python3 irc_pki_sim.py run                 # 3-of-3 custodians, 5 devs, 3 HSM replicas
python3 irc_pki_sim.py run --vm            # ...and re-verify the archive inside QEMU
python3 irc_pki_sim.py run --m 3 --n 5 --devs 7 --hsm 4 --release-m 4
python3 irc_pki_sim.py verify run --root-fp <sha256 printed at the ceremony>
python3 irc_pki_sim.py run --serve 300     # keep the release RPC up afterwards
python3 irc_pki_sim.py rpc <port> release.list
python3 -m pytest -q test_irc_pki_sim.py   # 31 tests, ~15 s
```

Requirements: Python 3.11+, `softhsm2`, and the Python packages `python-pkcs11`,
`asn1crypto` and `cryptography`. The `--vm` option also needs
`qemu-system-x86`, `xorriso`, `busybox-static` and a readable kernel at
`/boot/vmlinuz`. If the kernel's `isofs.ko` is zstd-compressed you also need
the `zstandard` package. On Debian or Ubuntu:

```
apt install softhsm2 qemu-system-x86 xorriso busybox-static linux-image-virtual
pip install python-pkcs11 asn1crypto cryptography zstandard
```

## Cast and policy

| actor | token holds | may |
|---|---|---|
| `ca` | operator key. The **root key is in `--hsm` replica tokens** (separate processes and token dirs) | issue certs and CRLs once the policy allows it |
| `custodian1..n` | own key and one **Shamir share** of the CA token PIN | send a share. **m** shares unlock the CA. Approve the security manager's cert or revocation |
| `secmgr` | own key | approve developer certs, revoke developers, approve releases |
| `dev1..5` | own key | request a cert, review releases (approve or veto) |
| `releasebot` | own key | serve the JSON-RPC, submit and publish releases |

* **Unlocking the CA** takes `m` of `n` custodian shares (default 3 of 3). Each
  share is encrypted (ECIES, P-256 + HKDF + AES-GCM) to a one-time key that
  the CA announces. So the share is carried over IRC and logged, but only the
  CA can read it. The PIN is rebuilt, used to log in to every replica, and
  then dropped. Every replica is health-checked: it signs a probe, and the
  probe is verified against the pinned root.
* **Security-manager cert or revocation** needs approvals from
  `--sm-approvals` distinct custodians (default 2).
* **Developer cert** needs one security-manager approval. A developer's
  revocation is requested by the security manager.
* **Release** needs `--release-m` approvals from active developers
  (default 3) plus the security manager, and no veto. A revoked developer's
  approval is recorded as `rejected` and does not count.
* **Primary HSM failover**: the script kills replica 0 partway through. The
  CA's next signature comes from replica 1, and the CA announces
  `ca switches the token #hsm-1 because primary unreachable.`

Ceremony certificates are real X.509 (P-256/SHA-256), signed inside the
replica token. Each is written to `pki/certs/<serial>.der` and also stored as
a `CKO_CERTIFICATE` next to its key in the owner's token. CRLs go in
`pki/crl/`.

## The passkey only its owner knows

Each actor process makes up its own passphrase. That passphrase stands in for
a memorised secret: it lives only in that process's memory and is never sent,
logged or written. The actor's token PIN (the passkey), along with any
custodian share, is kept in `agents/<name>/vault.json`. That file is mode 0600
and encrypted with AES-256-GCM under `scrypt(passphrase, N=2^15)`. The token's
private key is `SENSITIVE` and not `EXTRACTABLE`. `softhsm2-util` only accepts
PINs on the command line, so a token is created with throw-away PINs, and both
are changed at once through `C_SetPIN`. The final SO PIN is random and thrown
away.

At the end of a run, every actor scans every file in the run for its own
passphrase, PIN and share, raw and hex-encoded. The result goes in
`report.json` under `secrets_leak_check`. Only the actor itself can do this
check, because only it knows what to look for.

Limits: Python cannot reliably wipe memory, and nothing here uses `mlock`. In
a real deployment the passphrase would come from the person, or from a FIDO2
`hmac-secret` authenticator.

## Grammar

```
Message  = IDENT Verb Article Noun REF Clauses Sig "."
Verb     = requests | approves | rejects | issues | submits | publishes | sends | unlocks | switches
Article  = a | an | the | ε
Noun     = cert | revocation | release | share | token
Clauses  = Comma Clause Clauses | ε          Comma = "," | ε
Clause   = for IDENT | serial NUM | version VERSION | with With | because IDENT Words
With     = key HEX | digest HEX | secret HEX       Words = IDENT Words | ε
Sig      = ";" signed HEX | ε
```

Example lines from a run:

```
secmgr requests a cert #r-secmgr-1 for secmgr, with key 02b5e8…; signed 648b….
custodian1 approves the cert #r-secmgr-1 for secmgr; signed fbce….
ca issues the cert #r-secmgr-1 for secmgr, serial 7, with digest 9625…; signed 21bf….
dev1 rejects the release #rel-releasebot-2 with digest 46f6…, because hash mismatch; signed 6c02….
```

The parse table is built from FIRST and FOLLOW sets at import time, and
building it fails on any conflict. The tests also check that the alternatives
for each nonterminal are disjoint. Each signature covers
`"ircpki/1\n" + channel + "\n" + canonical sentence`. The ledger only accepts
the canonical spelling, so the same meaning can't be written two ways, and a
signature can't be replayed on another channel.

## What "verified" means

`verify` replays `irc/server.log` from line 1, with no running processes. It
checks:

1. The hash chain `h_i = sha256(h_{i-1} "\n" line_i)`, the sequence numbers
   and the timestamps.
2. The root certificate against the pinned fingerprint, and the roster
   signature against the root.
3. Every sentence: grammar, canonical form, nick = speaker, signature and
   policy. It uses the same `Ledger` state machine the actors used to decide
   what to do. Since the server relays lines in log order (with echo), that
   replay is exact. Any `invalid` sentence, or any `violation` by an
   authority, fails the run.
4. That every file in `pki/certs` and `pki/crl` is accounted for by the log,
   and that each one's digest, signature, subject, key and CRL contents match.
5. Conformance with `script.json`, the key-signing script the orchestrator
   ran. The expected sentences must appear in order, and the number of
   accepted unlocks, issuances, publications and switches must match exactly.

`vm` puts `pki/`, the log, the script and the report onto an ISO, along with a
SHA-256 manifest. It then boots the host kernel with a busybox-only
initramfs: no network, no Python. The guest checks the manifest and
recomputes the hash chain in `sh`. The host then compares the guest's chain
head with its own.

## Release-approval JSON-RPC

The release bot serves JSON-RPC 2.0 at `POST http://127.0.0.1:<port>/rpc`, on
loopback only.

| method | params | result |
|---|---|---|
| `release.submit` | `version`, `artifact` (a path under `releases/`) | `{id, version, digest}`. The bot posts `submits a release` |
| `release.status` | `id` | `state` (`pending`, `vetoed`, `published`), the approvals, what is still required |
| `release.list` | none | the status of every release |
| `release.evidence` | `id` | the signed sentences and the signers' certs, enough to verify offline |

When the ledger says a release has its quorum, the bot posts `publishes the
release` by itself. Developers approve only if their own rebuild has the same
SHA-256 as the submitted digest. Otherwise they veto with
`because hash mismatch`.

## Files

`grammar.py` is the lexer and LL(1) parser. `pkicrypto.py` covers Shamir,
ECIES, the vault, and X.509/CRL with an external signer. `hsm.py` wraps the
SoftHSM token. `ledger.py` holds the policy state machine and the
hash-chained log. `ircnet.py` is the IRC server and client. `actors.py` has
the actor and replica processes and the RPC. `scenario.py` defines the
key-signing script and the conformance check. `verify.py` is the offline
verifier and `vm.py` the QEMU step. `irc_pki_sim.py` holds the orchestrator,
the ceremony and the CLI.

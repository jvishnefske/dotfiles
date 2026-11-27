"""The key-signing script: what the ceremony is supposed to do, as data.

The orchestrator *executes* the script and the verifier *checks the log
against* it, so they cannot drift apart. Each step expands into an ordered
list of expected sentences; the log must contain them as an ordered
subsequence, and the number of accepted authority actions (unlocks, issues,
publishes) must match the script exactly — nothing extra was signed.
"""

from __future__ import annotations

from dataclasses import dataclass

from ledger import Policy, Verdict


@dataclass(frozen=True)
class Cast:
    custodians: tuple[str, ...]
    developers: tuple[str, ...]
    secmgr: str = "secmgr"
    ca: str = "ca"
    releasebot: str = "releasebot"

    @classmethod
    def make(cls, n_custodians: int, n_devs: int) -> "Cast":
        return cls(tuple(f"custodian{i}" for i in range(1, n_custodians + 1)),
                   tuple(f"dev{i}" for i in range(1, n_devs + 1)))

    def roles(self) -> dict[str, str]:
        r = {self.ca: "ca", self.secmgr: "secmgr", self.releasebot: "service"}
        r.update({c: "custodian" for c in self.custodians})
        r.update({d: "developer" for d in self.developers})
        return r


def default_script(cast: Cast, policy: Policy, hsm_replicas: int) -> list[dict]:
    devs, cust = cast.developers, cast.custodians
    k = policy.release_m
    if len(devs) < k + 1:
        raise ValueError(f"the default script needs at least release_m+1 = {k + 1} developers")
    steps: list[dict] = [{"do": "unlock"},
                         {"do": "enroll", "who": cast.secmgr,
                          "approvers": list(cust[: policy.sm_approvals])}]
    for i, d in enumerate(devs):
        step = {"do": "enroll", "who": d, "approvers": [cast.secmgr]}
        if i == min(2, len(devs) - 1) and hsm_replicas > 1:
            # Kill the primary CA HSM; the next signature must come from a replica.
            steps.append({"do": "fail_primary"})
            step["failover"] = True
        steps.append(step)
    steps += [
        {"do": "release", "version": "1.0.0", "reviewers": list(devs[:k]), "expect": "published"},
        {"do": "release", "version": "1.1.0", "reviewers": [devs[0]], "tamper": True,
         "expect": "vetoed"},
        {"do": "revoke", "who": devs[-1], "by": cast.secmgr, "approvers": [],
         "reason": "lost laptop"},
        # The revoked developer tries to approve; that approval must not count.
        {"do": "release", "version": "1.2.0", "reviewers": [devs[-1]] + list(devs[1:1 + k]),
         "revoked": [devs[-1]], "expect": "published"},
        {"do": "revoke", "who": cast.secmgr, "by": cust[0],
         "approvers": list(cust[: policy.sm_approvals]), "reason": "role change"},
        {"do": "rpc_checks"},
    ]
    return steps


@dataclass(frozen=True)
class Expect:
    actor: str | None
    verb: str
    noun: str
    target: str | None = None
    version: str | None = None
    status: str = "accepted"
    count: int = 1
    bind: bool = False       # this match fixes the reference for the rest of the step
    any_of: tuple[str, ...] = ()
    own_ref: bool = False    # carries its own reference (not the step's bound one)


def expectations(step: dict, cast: Cast, policy: Policy) -> list[Expect]:
    do = step["do"]
    if do == "unlock":
        return [Expect(cast.ca, "requests", "share", bind=True),
                Expect(None, "sends", "share", count=policy.m, any_of=cast.custodians),
                Expect(cast.ca, "unlocks", "token")]
    if do == "enroll":
        who = step["who"]
        switch = [Expect(cast.ca, "switches", "token", own_ref=True)] if step.get("failover") else []
        return ([Expect(who, "requests", "cert", who, bind=True)]
                + [Expect(a, "approves", "cert", who) for a in step["approvers"]]
                + switch + [Expect(cast.ca, "issues", "cert", who)])
    if do in ("fail_primary", "rpc_checks"):
        return []  # observable only through the next enrol step's switch
    if do == "release":
        out = [Expect(cast.releasebot, "submits", "release", version=step["version"], bind=True)]
        if step["expect"] == "vetoed":
            return out + [Expect(r, "rejects", "release") for r in step["reviewers"]]
        out += [Expect(r, "approves", "release",
                       status="rejected" if r in step.get("revoked", []) else "accepted")
                for r in step["reviewers"]]
        return out + [Expect(cast.secmgr, "approves", "release"),
                      Expect(cast.releasebot, "publishes", "release", version=step["version"])]
    if do == "revoke":
        who = step["who"]
        return ([Expect(step["by"], "requests", "revocation", who, bind=True)]
                + [Expect(a, "approves", "revocation", who) for a in step["approvers"]]
                + [Expect(cast.ca, "issues", "revocation", who)])
    raise ValueError(f"unknown step {do}")


COUNTED = (("unlocks", "token"), ("issues", "cert"), ("issues", "revocation"),
           ("publishes", "release"), ("switches", "token"))


def check_conformance(history: list[tuple[str, str, Verdict]], script: list[dict],
                      cast: Cast, policy: Policy) -> list[str]:
    errors: list[str] = []
    events = [(i, v) for i, (_, _, v) in enumerate(history) if v.msg is not None]
    cursor = 0
    expected_counts = {k: 0 for k in COUNTED}
    for sno, step in enumerate(script, 1):
        ref = None
        for e in expectations(step, cast, policy):
            if (e.verb, e.noun) in COUNTED:
                expected_counts[(e.verb, e.noun)] += e.count
            found = 0
            seen_actors: set[str] = set()
            j = cursor
            while j < len(events) and found < e.count:
                _, v = events[j]
                m = v.msg
                ok = (m.verb == e.verb and m.noun == e.noun and v.status == e.status
                      and (e.actor is None or m.actor == e.actor)
                      and (not e.any_of or m.actor in e.any_of)
                      and (e.target is None or m.target == e.target)
                      and (e.version is None or m.get("version") == e.version)
                      and (ref is None or e.bind or e.own_ref or m.ref == ref)
                      and m.actor not in seen_actors)
                if ok:
                    found += 1
                    seen_actors.add(m.actor)
                    if e.bind:
                        ref = m.ref
                j += 1
            if found < e.count:
                who = e.actor or "/".join(e.any_of) or "anyone"
                errors.append(f"step {sno} ({step['do']}): expected {e.count}x "
                              f"'{who} {e.verb} {e.noun}"
                              f"{' for ' + e.target if e.target else ''}' ({e.status}) "
                              f"after event {cursor}, found {found}")
                return errors
            cursor = j
    actual = {k: 0 for k in COUNTED}
    for _, v in events:
        k = (v.msg.verb, v.msg.noun)
        if k in actual and v.ok:
            actual[k] += 1
    for k in COUNTED:
        if actual[k] != expected_counts[k]:
            errors.append(f"script expects {expected_counts[k]} accepted '{k[0]} {k[1]}' "
                          f"but the log has {actual[k]}")
    return errors

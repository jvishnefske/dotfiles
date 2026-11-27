"""Ceremony sentence grammar: lexer, table-driven LL(1) parser, canonical form.

Every ceremony message on IRC is one English-like sentence, for example::

    dev1 requests a cert #r-dev1-1 for dev1, with key 02ab...; signed 9f3c....
    secmgr approves the cert #r-dev1-1 for dev1; signed 77aa....
    ca issues the cert #r-dev1-1 for dev1, serial 7, with digest 5e...; signed ....

Grammar (EBNF; quoted strings are reserved words, UPPER are token classes)::

    Message  = IDENT Verb Article Noun REF Clauses Sig "."
    Verb     = "requests" | "approves" | "rejects" | "issues" | "submits"
             | "publishes" | "sends" | "unlocks" | "switches"
    Article  = "a" | "an" | "the" | (empty)
    Noun     = "cert" | "revocation" | "release" | "share" | "token"
    Clauses  = Comma Clause Clauses | (empty)
    Comma    = "," | (empty)
    Clause   = "for" IDENT | "serial" NUM | "version" VERSION
             | "with" With | "because" IDENT Words
    With     = "key" HEX | "digest" HEX | "secret" HEX
    Words    = IDENT Words | (empty)
    Sig      = ";" "signed" HEX | (empty)

The parse table is built from FIRST/FOLLOW sets at import time and building
it raises if any cell is claimed twice, so "this grammar is LL(1)" is checked
mechanically every time the module loads rather than asserted in a comment.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

VERBS = ("requests", "approves", "rejects", "issues", "submits",
         "publishes", "sends", "unlocks", "switches")
ARTICLES = ("a", "an", "the")
NOUNS = ("cert", "revocation", "release", "share", "token")
CLAUSE_WORDS = ("for", "serial", "version", "with", "because")
WITH_WORDS = ("key", "digest", "secret")
RESERVED = frozenset(VERBS + ARTICLES + NOUNS + CLAUSE_WORDS + WITH_WORDS + ("signed",))

EPS = "ε"
EOF = "$"

# Grammar: nonterminal -> list of productions (tuples of symbols).
# A symbol is a nonterminal name, a token class (IDENT, REF, HEX, NUM,
# VERSION), a punctuation literal, or a reserved word.
GRAMMAR: dict[str, list[tuple[str, ...]]] = {
    "Message": [("IDENT", "Verb", "Article", "Noun", "REF", "Clauses", "Sig", ".")],
    "Verb": [(v,) for v in VERBS],
    "Article": [(a,) for a in ARTICLES] + [()],
    "Noun": [(n,) for n in NOUNS],
    "Clauses": [("Comma", "Clause", "Clauses"), ()],
    "Comma": [(",",), ()],
    "Clause": [("for", "IDENT"), ("serial", "NUM"), ("version", "VERSION"),
               ("with", "With"), ("because", "IDENT", "Words")],
    "With": [("key", "HEX"), ("digest", "HEX"), ("secret", "HEX")],
    "Words": [("IDENT", "Words"), ()],
    "Sig": [(";", "signed", "HEX"), ()],
}
START = "Message"


class GrammarError(ValueError):
    """The message is not a sentence of the ceremony grammar."""


# --------------------------------------------------------------------------- lexer

_TOKEN_RE = re.compile(r"""
    (?P<ws>\s+)
  | (?P<REF>\#[a-z0-9][a-z0-9-]{0,47})
  | (?P<HEX>[0-9a-f]{32,256}(?![0-9a-z]))
  | (?P<VERSION>\d{1,6}(?:\.\d{1,6}){1,3}(?![0-9a-z]))
  | (?P<NUM>\d{1,12}(?![0-9a-z]))
  | (?P<WORD>[a-z][a-z0-9_-]{0,31})
  | (?P<PUNCT>[,;.])
""", re.VERBOSE)


@dataclass(frozen=True)
class Token:
    kind: str   # terminal symbol: IDENT/REF/HEX/NUM/VERSION, a reserved word, punctuation, or $
    value: str
    pos: int


def tokenize(text: str) -> list[Token]:
    if len(text) > 400:
        raise GrammarError("sentence longer than 400 characters")
    out: list[Token] = []
    i = 0
    while i < len(text):
        m = _TOKEN_RE.match(text, i)
        if not m:
            raise GrammarError(f"unexpected character {text[i]!r} at {i}")
        kind = m.lastgroup
        val = m.group()
        if kind == "WORD":
            kind = val if val in RESERVED else "IDENT"
        elif kind == "PUNCT":
            kind = val
        if kind != "ws":
            out.append(Token(kind, val, i))
        i = m.end()
    out.append(Token(EOF, "", len(text)))
    return out


# ----------------------------------------------------------- LL(1) table builder

def _is_nt(sym: str) -> bool:
    return sym in GRAMMAR


def first_sets() -> dict[str, set[str]]:
    first: dict[str, set[str]] = {nt: set() for nt in GRAMMAR}
    changed = True
    while changed:
        changed = False
        for nt, prods in GRAMMAR.items():
            for prod in prods:
                f = first_of_seq(prod, first)
                if not f <= first[nt]:
                    first[nt] |= f
                    changed = True
    return first


def first_of_seq(seq: tuple[str, ...], first: dict[str, set[str]]) -> set[str]:
    out: set[str] = set()
    for sym in seq:
        if not _is_nt(sym):
            out.add(sym)
            return out
        out |= first[sym] - {EPS}
        if EPS not in first[sym]:
            return out
    out.add(EPS)
    return out


def follow_sets(first: dict[str, set[str]]) -> dict[str, set[str]]:
    follow: dict[str, set[str]] = {nt: set() for nt in GRAMMAR}
    follow[START].add(EOF)
    changed = True
    while changed:
        changed = False
        for nt, prods in GRAMMAR.items():
            for prod in prods:
                for i, sym in enumerate(prod):
                    if not _is_nt(sym):
                        continue
                    rest = first_of_seq(prod[i + 1:], first)
                    add = (rest - {EPS}) | (follow[nt] if EPS in rest else set())
                    if not add <= follow[sym]:
                        follow[sym] |= add
                        changed = True
    return follow


def build_table() -> dict[tuple[str, str], tuple[str, ...]]:
    first = first_sets()
    follow = follow_sets(first)
    table: dict[tuple[str, str], tuple[str, ...]] = {}
    for nt, prods in GRAMMAR.items():
        for prod in prods:
            f = first_of_seq(prod, first)
            lookaheads = (f - {EPS}) | (follow[nt] if EPS in f else set())
            for la in lookaheads:
                key = (nt, la)
                if key in table and table[key] != prod:
                    raise AssertionError(f"grammar is not LL(1): conflict at {key}: "
                                         f"{table[key]} vs {prod}")
                table[key] = prod
    return table


TABLE = build_table()


@dataclass
class Node:
    sym: str
    children: list["Node | Token"] = field(default_factory=list)


def parse_tree(text: str) -> Node:
    """Predictive LL(1) parse driven only by TABLE. Raises GrammarError."""
    toks = tokenize(text)
    root = Node(START)
    pos = 0
    # Each stack entry carries the parent node the matched symbol is appended
    # to; the start symbol's "parent" is None, meaning it *is* the root.
    stack: list[tuple[str, Node | None]] = [(EOF, root), (START, None)]
    while stack:
        sym, parent = stack.pop()
        tok = toks[pos]
        if sym == EOF:
            if tok.kind != EOF:
                raise GrammarError(f"trailing input at {tok.pos}: {tok.value!r}")
            break
        if not _is_nt(sym):
            if tok.kind != sym:
                raise GrammarError(f"expected {sym!r} at {tok.pos}, got {tok.value or 'end'!r}")
            parent.children.append(tok)
            pos += 1
            continue
        prod = TABLE.get((sym, tok.kind))
        if prod is None:
            raise GrammarError(f"unexpected {tok.value or 'end'!r} at {tok.pos} while reading {sym}")
        node = root if parent is None else Node(sym)
        if parent is not None:
            parent.children.append(node)
        for s in reversed(prod):
            stack.append((s, node))
    return root


# ---------------------------------------------------------------------- AST

CLAUSE_ORDER = ("for", "serial", "version", "key", "digest", "secret", "because")


@dataclass(frozen=True)
class Msg:
    actor: str
    verb: str
    article: str          # "" when omitted
    noun: str
    ref: str              # without the leading '#'
    clauses: tuple[tuple[str, str], ...]  # canonical order, unique keys
    sig: str = ""         # hex, "" when unsigned

    def get(self, key: str) -> str | None:
        for k, v in self.clauses:
            if k == key:
                return v
        return None

    @property
    def target(self) -> str | None:
        return self.get("for")

    def body(self) -> str:
        """Canonical sentence text without signature and final period."""
        parts = [self.actor, self.verb]
        if self.article:
            parts.append(self.article)
        parts += [self.noun, "#" + self.ref]
        s = " ".join(parts)
        for i, (k, v) in enumerate(self.clauses):
            s += " " if i == 0 else ", "
            s += f"with {k} {v}" if k in WITH_WORDS else f"{k} {v}"
        return s

    def wire(self) -> str:
        return self.body() + (f"; signed {self.sig}" if self.sig else "") + "."

    def with_sig(self, sig: str) -> "Msg":
        return Msg(self.actor, self.verb, self.article, self.noun, self.ref, self.clauses, sig)


def _leaves(n: Node | Token) -> list[Token]:
    if isinstance(n, Token):
        return [n]
    out: list[Token] = []
    for c in n.children:
        out += _leaves(c)
    return out


def _find(n: Node, sym: str) -> list[Node]:
    out = []
    for c in n.children:
        if isinstance(c, Node):
            if c.sym == sym:
                out.append(c)
            out += _find(c, sym)
    return out


def parse(text: str) -> Msg:
    tree = parse_tree(text)
    head = [c for c in tree.children]
    actor = head[0].value
    verb = _leaves(head[1])[0].value
    art_leaves = _leaves(head[2])
    article = art_leaves[0].value if art_leaves else ""
    noun = _leaves(head[3])[0].value
    ref = head[4].value[1:]
    clauses: dict[str, str] = {}
    for cl in _find(tree, "Clause"):
        lv = _leaves(cl)
        kw = lv[0].value
        if kw == "with":
            key, val = lv[1].value, lv[2].value
        elif kw == "because":
            key, val = "because", " ".join(t.value for t in lv[1:])
        else:
            key, val = kw, lv[1].value
        if key in clauses:
            raise GrammarError(f"clause {key!r} given twice")
        clauses[key] = val
    sig_leaves = _leaves(head[6])
    sig = sig_leaves[2].value if sig_leaves else ""
    if actor in RESERVED:
        raise GrammarError("actor name is a reserved word")
    ordered = tuple((k, clauses[k]) for k in CLAUSE_ORDER if k in clauses)
    return Msg(actor, verb, article, noun, ref, ordered, sig)


def make(actor: str, verb: str, noun: str, ref: str, article: str = "the", **clauses: str) -> Msg:
    """Build a canonical message; round-trips through the parser to prove it."""
    if "for_" in clauses:
        clauses["for"] = clauses.pop("for_")
    ordered = tuple((k, str(clauses[k])) for k in CLAUSE_ORDER if k in clauses and clauses[k] is not None)
    unknown = set(clauses) - set(CLAUSE_ORDER)
    if unknown:
        raise GrammarError(f"unknown clauses {unknown}")
    m = Msg(actor, verb, article, noun, ref.lstrip("#"), ordered)
    back = parse(m.wire())
    if back != m:
        raise GrammarError(f"message does not round-trip: {m.wire()!r}")
    return m


# Which clauses each (verb, noun) pair requires and allows. Anything else is
# rejected by the ledger even though it parses.
SCHEMA: dict[tuple[str, str], tuple[frozenset[str], frozenset[str]]] = {}


def _s(verb: str, noun: str, required: str, optional: str = "") -> None:
    SCHEMA[(verb, noun)] = (frozenset(required.split()), frozenset(optional.split()))


_s("requests", "cert", "for key")
_s("approves", "cert", "for")
_s("rejects", "cert", "for", "because")
_s("issues", "cert", "for serial digest")
_s("publishes", "cert", "digest")
_s("requests", "revocation", "for serial", "because")
_s("approves", "revocation", "for serial")
_s("issues", "revocation", "for serial digest")
_s("requests", "share", "key")
_s("sends", "share", "key secret")
_s("unlocks", "token", "")
_s("switches", "token", "", "because")
_s("submits", "release", "version digest")
_s("approves", "release", "digest")
_s("rejects", "release", "digest", "because")
_s("publishes", "release", "version digest")


def check_schema(m: Msg) -> str | None:
    rule = SCHEMA.get((m.verb, m.noun))
    if rule is None:
        return f"'{m.verb} {m.noun}' is not a ceremony action"
    req, opt = rule
    have = {k for k, _ in m.clauses}
    if not req <= have:
        return f"missing clauses {sorted(req - have)}"
    if have - req - opt:
        return f"unexpected clauses {sorted(have - req - opt)}"
    return None

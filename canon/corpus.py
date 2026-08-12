"""
Adversarial differential corpus.

Every case targets one specification question and is built so that two plausible
answers produce different bytes. Cases where all reasonable rulesets agree are
excluded on purpose: they inflate the pass rate and prove nothing.

This is the piece that determines whether the canonicalization test finds
anything. Two implementations agreeing on {"a":1} is not evidence that a
specification is precise; it is evidence that the test was easy.

Each case names the question it probes, so a divergence maps directly to the
line of specification that is missing or ambiguous rather than to a vague
"implementations disagree".
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .ruleset import ABSENT


@dataclass(frozen=True)
class Case:
    id: str
    question: str  # which specification question this probes
    title: str
    value: Any
    note: str = ""
    tags: tuple[str, ...] = field(default_factory=tuple)


Q_ORDER = "key ordering"
Q_UNICODE = "Unicode normalization"
Q_NUMBER = "number representation"
Q_BIGINT = "integer precision"
Q_NULL = "empty vs null vs absent"
Q_ESCAPE = "string escaping"
Q_WS = "whitespace and line endings"
Q_DIGEST = "digest algorithm and encoding"
Q_STRUCT = "structural edge cases"

CORPUS: tuple[Case, ...] = (
    # -- key ordering -------------------------------------------------------
    Case(
        "ORD-01",
        Q_ORDER,
        "BMP private-use vs supplementary key",
        {"\ue000": 1, "\U00010000": 2},
        "The discriminator between UTF-16 and UTF-8 ordering. UTF-16 encodes "
        "U+10000 as surrogates (0xD800..) which sort below U+E000; UTF-8 and "
        "codepoint order put it above. Any spec that says only 'sort the keys' "
        "is ambiguous here.",
        ("high-value",),
    ),
    Case(
        "ORD-02",
        Q_ORDER,
        "ASCII case and digit boundaries",
        {"Z": 1, "a": 2, "A": 3, "0": 4, "_": 5},
        "Agreement expected. Present as a control: a corpus where everything "
        "diverges cannot distinguish a precise spec from a lucky one.",
    ),
    Case(
        "ORD-03",
        Q_ORDER,
        "Keys differing only by combining mark placement",
        {"cafe\u0301": 1, "caf\u00e9": 2},
        "Two keys that are distinct under NONE and collide under NFC. A "
        "normalizing ruleset must reject this document as a duplicate key; a "
        "non-normalizing one emits both. Silent last-wins is the dangerous "
        "outcome and is what the default JSON parser does.",
        ("high-value",),
    ),
    Case(
        "ORD-04",
        Q_ORDER,
        "Empty-string key alongside others",
        {"": 1, "a": 2},
        "Legal JSON, frequently untested.",
    ),
    Case(
        "ORD-05",
        Q_ORDER,
        "Nested objects with independently ordered keys",
        {"b": {"z": 1, "a": 2}, "a": {"y": 3, "b": 4}},
        "Confirms ordering is applied at every depth, not only at the root.",
    ),
    # -- Unicode ------------------------------------------------------------
    Case(
        "UNI-01",
        Q_UNICODE,
        "Decomposed vs precomposed value",
        {"name": "Jose\u0301"},
        "NFC folds this to 'José'; NONE does not. Real names arrive in both "
        "forms depending on the operating system that produced them.",
        ("high-value",),
    ),
    Case(
        "UNI-02",
        Q_UNICODE,
        "Compatibility characters",
        {"id": "\ufb01le", "width": "\uff21\uff22"},
        "NFKC folds the fi ligature and fullwidth letters; NFC does not. A spec "
        "saying 'normalize Unicode' without naming the form is underspecified.",
        ("high-value",),
    ),
    Case(
        "UNI-03",
        Q_UNICODE,
        "Combining marks in non-canonical order",
        {"s": "q\u0307\u0323"},
        "Canonical ordering reorders these; NONE preserves them.",
    ),
    Case(
        "UNI-04",
        Q_UNICODE,
        "Astral plane content",
        {"emoji": "\U0001f9ea\U0001f52c"},
        "Surrogate handling in escaping and in length assumptions.",
    ),
    # -- numbers ------------------------------------------------------------
    Case(
        "NUM-01",
        Q_NUMBER,
        "Integer-valued float",
        {"shots": 1024.0},
        "ES6 emits 1024; a platform float formatter emits 1024.0. This is the "
        "single most likely real-world divergence.",
        ("high-value",),
    ),
    Case(
        "NUM-02",
        Q_NUMBER,
        "Exponential boundary at 1e21",
        {"below": 1e20, "at": 1e21},
        "ES6 switches to exponential at exactly 1e21. Python switches at 1e16.",
        ("high-value",),
    ),
    Case(
        "NUM-03",
        Q_NUMBER,
        "Small-magnitude boundary at 1e-7",
        {"above": 1e-6, "at": 1e-7},
        "ES6 emits 0.000001 then 1e-7. Off-by-one on this boundary is easy to "
        "write and hard to notice.",
        ("high-value",),
    ),
    Case(
        "NUM-04",
        Q_NUMBER,
        "Negative zero",
        {"drift": -0.0},
        "RFC 8785 requires 0. Most formatters emit -0.0. Arises naturally from "
        "any subtraction of equal floats.",
        ("high-value",),
    ),
    Case(
        "NUM-05",
        Q_NUMBER,
        "Repeating binary fraction",
        {"p": 0.1, "q": 0.30000000000000004},
        "Shortest-round-trip behaviour under two formatters.",
    ),
    Case(
        "NUM-06",
        Q_NUMBER,
        "Mixed int and float of equal value",
        {"a": 1, "b": 1.0},
        "Whether the canonical form preserves the int/float distinction at all. "
        "If it does not, two semantically different documents share a digest.",
        ("high-value",),
    ),
    # -- big integers -------------------------------------------------------
    Case(
        "INT-01",
        Q_BIGINT,
        "Boundary of exact IEEE-754 range",
        {"safe": 9007199254740991, "unsafe": 9007199254740993},
        "2**53-1 and 2**53+1. A JavaScript verifier cannot distinguish the "
        "second from 2**53. A Python producer can. Neither is wrong; the "
        "specification has to choose.",
        ("high-value",),
    ),
    Case(
        "INT-02",
        Q_BIGINT,
        "64-bit identifier as a number",
        {"session_id": 18446744073709551615},
        "Common in real payloads and lossy through any float path.",
        ("high-value",),
    ),
    Case(
        "INT-03",
        Q_BIGINT,
        "Same identifier as a string",
        {"session_id": "18446744073709551615"},
        "Control for INT-02. Confirms the string path is lossless, which is why "
        "specs usually require identifiers to be strings.",
    ),
    # -- empty, null, absent ------------------------------------------------
    Case(
        "NUL-01",
        Q_NULL,
        "Null present",
        {"parent_receipt_id": None},
        "The session-1 case in the capability contract: parent is legitimately "
        "null rather than missing.",
        ("high-value",),
    ),
    Case(
        "NUL-02",
        Q_NULL,
        "Key absent",
        {"parent_receipt_id": ABSENT},
        "Must be distinguishable from NUL-01 unless the spec says otherwise. If "
        "these produce identical bytes, a receipt cannot prove which was "
        "declared.",
        ("high-value",),
    ),
    Case(
        "NUL-03",
        Q_NULL,
        "Empty string",
        {"parent_receipt_id": ""},
        "Third member of the triple.",
    ),
    Case(
        "NUL-04",
        Q_NULL,
        "Empty container values",
        {"records": [], "meta": {}},
        "Whether empty containers are preserved or elided.",
    ),
    Case(
        "NUL-05",
        Q_NULL,
        "Nested null inside an array",
        {"defects": [1, None, 3]},
        "Array elements cannot be elided without changing indices, so a "
        "null-eliding ruleset must treat objects and arrays differently.",
    ),
    # -- escaping -----------------------------------------------------------
    Case(
        "ESC-01",
        Q_ESCAPE,
        "Control characters",
        {"log": "a\u0000b\u001fc"},
        "Which escape form: \\u0000 or a short form. Case of the hex digits is "
        "part of the byte sequence.",
        ("high-value",),
    ),
    Case(
        "ESC-02",
        Q_ESCAPE,
        "Characters with short escapes",
        {"s": "tab\there\nnewline\\backslash\"quote"},
        "Short form vs \\u form for the same character.",
        ("high-value",),
    ),
    Case(
        "ESC-03",
        Q_ESCAPE,
        "Forward slash and DEL",
        {"path": "/a/b", "del": "\u007f"},
        "Neither requires escaping; some implementations escape both anyway.",
    ),
    Case(
        "ESC-04",
        Q_ESCAPE,
        "Line and paragraph separators",
        {"s": "a\u2028b\u2029c"},
        "Valid in JSON, invalid in JavaScript source before ES2019. Some "
        "implementations escape them for that reason.",
        ("high-value",),
    ),
    # -- structure ----------------------------------------------------------
    Case(
        "STR-01",
        Q_STRUCT,
        "Deep nesting",
        {"a": {"b": {"c": {"d": {"e": [1, [2, [3]]]}}}}},
        "Indentation and depth handling.",
    ),
    Case(
        "STR-02",
        Q_STRUCT,
        "Array of objects with varying key sets",
        {"runs": [{"b": 1, "a": 2}, {"a": 3}, {}]},
        "Per-element ordering and empty-object handling in sequence.",
    ),
    Case(
        "PKT-01",
        Q_STRUCT,
        "SCQOS universal packet, all 16 declared fields",
        {
            "packet_id": "pkt-0002",
            "system_type": "capability",
            "action": "execute",
            "actor": "qec-syndrome-decode@1.0.0",
            "observer_id": "hudson-forge",
            "source": "sha256:" + "a" * 64,
            "target": "sha256:" + "b" * 64,
            "declared_objective": "decode committed syndrome records",
            "boundary_domain": "offline",
            "cause_id": "pkt-0001",
            "effect_id": "pkt-0003",
            "payload": {
                "session_index": 2,
                "calibration_window_id": "2026-08-06T23:21:59-04:00",
                "shots": 1024.0,
                "logical_error_count": 17,
                "defects_per_round": [3, 0, 5],
            },
            "created_at": "2026-08-09T14:32:07Z",
            "sequence": 2,
            "external_reference": None,
            "external_signature": None,
        },
        "The real target shape. Combines the schema's declared fields with a "
        "float-valued shots count, an integer sequence, and two nullable "
        "external fields. If two faithful readings of the specification disagree "
        "here, they disagree on ordinary production data.",
        ("high-value", "scqos"),
    ),
    Case(
        "PKT-02",
        Q_STRUCT,
        "Same instant, two timestamp encodings",
        {
            "a": {"created_at": "2026-08-09T14:32:07Z"},
            "b": {"created_at": "2026-08-09T14:32:07.000+00:00"},
        },
        "created_at appears in the packet schema with no format rule. Precision "
        "and timezone encoding are unconstrained, so the same instant has more "
        "than one canonical form and therefore more than one digest.",
        ("high-value", "scqos"),
    ),
    Case(
        "PKT-03",
        Q_STRUCT,
        "collection_start: same instant, offset vs Z encoding",
        {
            "a": {"collection_start": "2026-08-07T02:21:59Z"},
            "b": {"collection_start": "2026-08-06T22:21:59-04:00"},
        },
        "Under contract 1.1.0 the admission predicate is a difference between two "
        "collection_start values. These two encode the same instant. If they "
        "canonicalize differently, two byte-distinct states express one temporal "
        "fact, and a substrate comparing declared strings rather than instants "
        "will reach different admission decisions for the same experiment. The "
        "contract pins the format for exactly this reason; the case is retained "
        "to demonstrate what the pinning prevents.",
        ("high-value", "scqos"),
    ),
    Case(
        "STR-03",
        Q_STRUCT,
        "Realistic receipt-shaped document",
        {
            "receipt_version": "1.0.0",
            "decision": "HOLD",
            "session_index": 2,
            "calibration_window_id": "cal-2026-08-07T18:00:00Z",
            "parent_state_digest": "sha256:" + "0" * 64,
            "input_digest": "sha256:" + "1" * 64,
            "predicates": [
                {"id": "I2", "result": "FAIL", "evidence": ["parent.calibration_window_id"]},
                {"id": "I4", "result": "FAIL", "evidence": ["parent.calibration_window_id"]},
                {"id": "I7", "result": "PASS", "evidence": []},
            ],
            "output_digest": None,
            "temporal_window": {"not_before": "2026-08-07T18:00:00Z", "not_after": ABSENT},
        },
        "End-to-end shape combining several questions at once. Closest case to "
        "what an actual receipt will look like.",
        ("high-value",),
    ),
)

BY_ID = {case.id: case for case in CORPUS}


def by_question(question: str) -> tuple[Case, ...]:
    return tuple(c for c in CORPUS if c.question == question)


def high_value() -> tuple[Case, ...]:
    return tuple(c for c in CORPUS if "high-value" in c.tags)


QUESTIONS = (
    Q_ORDER,
    Q_UNICODE,
    Q_NUMBER,
    Q_BIGINT,
    Q_NULL,
    Q_ESCAPE,
    Q_WS,
    Q_DIGEST,
    Q_STRUCT,
)

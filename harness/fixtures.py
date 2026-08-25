"""
Phase 1 fixture construction.

Design decision, recorded because it affects what the study can claim:

  The PARENT is real. The COMPLIANT successor is real. Every VIOLATING
  successor is synthetic, constructed at a controlled offset from the parent.

Both real artifacts are extracted from published QEC-P1 session data
(Zenodo 10.5281/zenodo.22050536): published sessions 11 and 12 on ibm_marrakesh,
separated by 13.74 hours of collection time. That separation is not constructed
— it is what the fair-share queue produced — and it satisfies the contract's
>=12h admission predicate on its own.

So case C01, the primary negative control, is real end to end: real parent, real
successor, real separation, real syndrome data, real decode. The violating cases
are synthetic because no real pair exists at 3h or 11h59m and none should be
manufactured on hardware to create one.

Every synthetic successor is labelled as such in its own artifact and in the
preregistration. No result is reported as though a synthetic session were
collected.

The successors reuse the parent's syndrome records verbatim. That is
intentional. The decode output is then identical across cases, so any
difference in admission outcome is attributable to the declared metadata under
test and to nothing else. Case C10 (replay) is the one place where reused
records are themselves the violation, and it is declared as such.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Session 1 — the real parent.
#
# REPLACE these two values with the committed session-1 artifact before freeze.
# They are the only fixture inputs that must come from collected data; every
# other field below is derived or declared.
#
# PARENT_ARTIFACT_PATH: path to the committed session-1 JSON artifact.
# If absent, the module falls back to PARENT_STUB and marks fixtures
# provisional, so the harness runs end-to-end before the real file is wired in.
# ---------------------------------------------------------------------------

PARENT_ARTIFACT_PATH = Path("fixtures/session-1.json")
REAL_SUCCESSOR_PATH = Path("fixtures/session-2-real.json")

PARENT_STUB: dict[str, Any] = {
    "session_index": 1,
    "backend_id": "ibm_fez",
    "collection_start": "2026-08-07T03:00:00Z",
    "calibration_window_id": "2026-08-06T23:21:59-04:00",
    "calibration_age_hours": 4,
    "calibration_stratum": "fresh",
    "code_distance": 3,
    "rounds": 3,
    "shots": 8,
    "syndrome_records": [
        "000000", "000000", "100000", "010010",
        "000001", "110000", "000000", "001100",
    ],
    "parent_receipt_id": None,
}

TWELVE_HOURS = timedelta(hours=12)


def load_parent() -> tuple[dict, bool]:
    """Return (parent_state, is_real). Falls back to the stub if not yet wired."""
    if PARENT_ARTIFACT_PATH.exists():
        with PARENT_ARTIFACT_PATH.open("rb") as handle:
            return json.loads(handle.read().decode("utf-8")), True
    return dict(PARENT_STUB), False


def load_real_successor() -> dict | None:
    """The collected compliant successor, if wired. None falls back to synthetic."""
    if REAL_SUCCESSOR_PATH.exists():
        with REAL_SUCCESSOR_PATH.open("rb") as handle:
            return json.loads(handle.read().decode("utf-8"))
    return None


def _parse(text: str) -> datetime:
    return datetime.strptime(text, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


def _render(moment: datetime) -> str:
    """RFC 3339, UTC, second precision, literal Z — the format pinned in §3.1."""
    return moment.strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass
class Fixture:
    case_id: str
    title: str
    artifact: dict | None  # None when the case has no input artifact (C18)
    predicted_decision: str  # PERMIT | HOLD | TERMINATE | DETECTED
    predicted_predicates: tuple[str, ...]  # predicted FAILING predicates
    synthetic: bool
    note: str
    requires_substrate: bool = False  # cannot be fixtured offline
    variant_bytes: bytes | None = None
    """A second, semantically identical encoding of the same artifact.

    C05 tests whether two byte-different encodings of one value set produce the
    same decision AND the same state digest. That cannot be expressed by a
    single artifact — the variance lives in the encoding, not the values. The
    harness submits both and compares."""

    declared_digest_override: str | None = None
    """Digest to DECLARE at submission, when it must differ from the real bytes.

    C13's violation lives in the submission, not the artifact: the same bytes
    are sent with a digest computed over something else. A static artifact
    cannot express that, so the mismatch is carried here and applied by the
    harness at submit time."""

    def bytes_(self) -> bytes:
        if self.artifact is None:
            return b""
        return json.dumps(
            self.artifact, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ).encode("utf-8")


def _alternate_encoding(state: dict) -> bytes:
    """Encode the same values with deliberately different bytes.

    Reversed key order, whitespace between tokens, ASCII-escaped non-ASCII.
    Every difference is one a conforming canonicalizer must erase; none changes
    a single value. If a substrate's state digest moves between this and the
    primary encoding, it is hashing what it received rather than what it
    canonicalized.
    """
    reordered = {key: state[key] for key in sorted(state, reverse=True)}
    return json.dumps(
        reordered, indent=1, separators=(" ,", " : "), ensure_ascii=True
    ).encode("utf-8")


def successor(parent: dict, offset: timedelta, **overrides) -> dict:
    """Build a synthetic session 2 at a controlled offset from the parent."""
    state = dict(parent)
    state["session_index"] = parent["session_index"] + 1
    state["collection_start"] = _render(_parse(parent["collection_start"]) + offset)
    state["parent_receipt_id"] = "rcpt-0001"
    state["_synthetic"] = True
    state["_derived_from"] = "session-1 (collected)"
    state.update(overrides)
    return state


def build_phase1(parent: dict) -> list[Fixture]:
    """The eleven phase-1 fixtures, predictions locked per preregistration §5."""
    compliant = TWELVE_HOURS + timedelta(hours=2)      # 14h — comfortably legal
    near_legal = TWELVE_HOURS + timedelta(minutes=1)   # 12h01m
    near_illegal = TWELVE_HOURS - timedelta(minutes=1)  # 11h59m
    inside = timedelta(hours=3)                         # 3h — clear violation

    fixtures: list[Fixture] = []

    # -- negative controls ---------------------------------------------------

    real_successor = load_real_successor()
    fixtures.append(Fixture(
        "C01", "Clean session 2, compliant separation, valid parent",
        real_successor if real_successor is not None else successor(parent, compliant),
        "PERMIT", (),
        synthetic=real_successor is None,
        note="Baseline negative control. A HOLD here falsifies H5 on its own. "
        + (
            "Real end to end: collected parent and collected successor, "
            "separated by the collection times the queue actually produced, "
            "with real syndrome data and a real decode. Nothing about this case "
            "is constructed."
            if real_successor is not None
            else "Synthetic successor — the collected pair is not wired in."
        ),
    ))

    benign = successor(parent, compliant)
    benign["_operator_note"] = "second run of the evening"
    fixtures.append(Fixture(
        "C02", "Benign perturbation of a non-material field",
        benign,
        "PERMIT", (), True,
        "An added field the contract never declares material. Must not affect "
        "admission. Distinguishes a gate that evaluates declared predicates "
        "from one that reacts to any change in input bytes.",
    ))

    c05_state = successor(parent, compliant)
    fixtures.append(Fixture(
        "C05", "Serialization variance pair, identical semantics",
        c05_state,
        "PERMIT", (), True,
        note="Submitted twice with differing byte encodings of the same value "
        "set: reversed key order, whitespace between tokens, and non-ASCII "
        "escaping. Both must yield the same decision AND the same state digest. "
        "This is the canonicalization test (H4) and a negative control at once. "
        "If the two encodings produce different state digests, the substrate is "
        "hashing submitted bytes rather than canonical bytes.",
        variant_bytes=_alternate_encoding(c05_state),
    ))

    stale = successor(parent, compliant, calibration_stratum="stale",
                      calibration_age_hours=83)
    fixtures.append(Fixture(
        "C24", "Stale calibration stratum, compliant separation",
        stale,
        "PERMIT", (), True,
        "Over-reach control. calibration_stratum and calibration_age_hours are "
        "declared and receipt-bound but explicitly NOT admission predicates "
        "(contract §5.1.2). A HOLD means gating on a field the contract did not "
        "make material — a failure mode no violation case can surface. The 83h "
        "value is the real observed freeze duration, not an invented figure.",
    ))

    # -- the governing invariant ---------------------------------------------

    fixtures.append(Fixture(
        "C06", "Session 2 collected 3h after session 1",
        successor(parent, inside),
        "HOLD", ("I2", "I1"), True,
        "The headline case. Locally valid in every respect — schema validates, "
        "digest resolves, decode completes, output well-formed. Illegal only in "
        "relation to its predecessor. A per-execution gate that does not retain "
        "session 1 will PERMIT.",
    ))

    fixtures.append(Fixture(
        "C22", "Near-boundary violation: 11h59m",
        successor(parent, near_illegal),
        "HOLD", ("I2", "I1"), True,
        "Matched pair with C23. Differs from it by two minutes of declared time "
        "and nothing else.",
    ))

    fixtures.append(Fixture(
        "C23", "Near-boundary compliance: 12h01m",
        successor(parent, near_legal),
        "PERMIT", (), True,
        "The other half of the pair. A gate that HOLDs on both C22 and C23 is "
        "not evaluating the predicate, only reacting to input shape; one that "
        "PERMITs both is not evaluating it either. Only a correct split shows "
        "the substrate computes the capability's rule.",
    ))

    orphan = successor(parent, compliant, parent_receipt_id="rcpt-does-not-exist")
    fixtures.append(Fixture(
        "C07", "Declared parent absent from governance state",
        orphan,
        "HOLD", ("I2",), True,
        "SC-Engineering stated that missing required ancestry is HOLD, never "
        "PERMIT-by-default. Directly tests that commitment. Default-permit on "
        "missing history is the most common failure in lineage systems.",
    ))

    # -- reference -----------------------------------------------------------

    tampered = successor(parent, compliant)
    fixtures.append(Fixture(
        "C13", "Declared input digest does not match actual bytes",
        tampered,
        "HOLD", ("I6",), True,
        note="Submitted with a digest computed over different bytes than those "
        "sent. Cheapest check in the matrix; a substrate failing this fails "
        "everything downstream, since every other digest claim rests on the "
        "same mechanism.",
        declared_digest_override="f" * 64,
    ))

    # -- cases that cannot be fixtured offline -------------------------------

    fixtures.append(Fixture(
        "C09", "Two executions submitted concurrently against one parent",
        successor(parent, compliant),
        "PERMIT×1, HOLD×1", ("I2",), True,
        "Requires two simultaneous submissions against the live substrate. The "
        "artifact is identical for both; the race is the test. SC-Engineering "
        "stated admission is serialized per lineage and the loser must "
        "re-evaluate against the new present state. Exactly one may acquire "
        "successor authority.",
        requires_substrate=True,
    ))

    fixtures.append(Fixture(
        "C18", "Consequence emitted with no admission request",
        None,
        "DETECTED", ("I5",), False,
        "No input artifact: the capability writes its declared output without "
        "requesting admission at all. Tests H2 — whether a capability inside the "
        "boundary possesses an alternate execution lane. If undetected, "
        "governance is cooperative rather than mediating, which is a legitimate "
        "scope but not the one currently claimed.",
        requires_substrate=True,
    ))

    return fixtures


def write_fixtures(destination: Path) -> tuple[list[Fixture], bool]:
    """Materialize fixtures to disk and return them with the parent's realness."""
    parent, is_real = load_parent()
    fixtures = build_phase1(parent)
    destination.mkdir(parents=True, exist_ok=True)

    manifest = {
        "protocol_version": "1.1.0",
        "parent_source": "collected session-1 artifact" if is_real else "STUB — not yet wired",
        "parent_is_real": is_real,
        "parent_collection_start": parent["collection_start"],
        "cases": [],
    }

    for fixture in fixtures:
        entry = {
            "case_id": fixture.case_id,
            "title": fixture.title,
            "predicted_decision": fixture.predicted_decision,
            "predicted_failing_predicates": list(fixture.predicted_predicates),
            "synthetic_successor": fixture.synthetic,
            "requires_live_substrate": fixture.requires_substrate,
            "declared_digest_override": fixture.declared_digest_override,
            "has_encoding_variant": fixture.variant_bytes is not None,
            "note": fixture.note,
        }
        if fixture.artifact is not None:
            path = destination / f"{fixture.case_id}.json"
            raw = fixture.bytes_()
            path.write_bytes(raw)
            entry["artifact"] = path.name
            entry["artifact_bytes"] = len(raw)
        manifest["cases"].append(entry)

    (destination / "MANIFEST.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return fixtures, is_real

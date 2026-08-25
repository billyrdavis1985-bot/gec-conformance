"""
Extract capability input artifacts from published QEC-P1 session data.

Source: github.com/billyrdavis1985-bot/IRMB_QEC-P1_DriftAware_RepetitionCode
        Zenodo concept DOI 10.5281/zenodo.22050536

This turns collected experimental sessions into the input artifact the frozen
contract declares. Every field is derived from the published run files; nothing
is invented. Where a convention has to be chosen, it is stated here rather than
left implicit, because the resulting bytes are hashed and the choice becomes
part of the artifact's identity.

DECLARED CONVENTIONS
--------------------
1. Circuit selection. The encoded arm under the archive policy with the |1>
   preparation: "P_archive|ENC_PASSIVE|1". Chosen because it is present in every
   session, uses the same patch across sessions, and is the arm the study's own
   analysis treats as canonical. Fixed for all sessions; not selected per-session.

2. Syndrome field layout. Published outcomes have the form "DDD AA AA AA":
   three data bits followed by three whitespace-separated 2-bit ancilla groups,
   one per round. The syndrome record is the three ancilla groups concatenated in
   published order, left to right, giving rounds x (distance-1) = 6 bits. Data
   bits are discarded: the capability decodes syndromes, not logical outcomes.

3. Round order. Groups are taken in published left-to-right order and NOT
   reversed. Qiskit's little-endian register convention means this may place the
   final round first. That does not matter for conformance: the decode table is
   total over all 2^6 patterns, the ordering is applied identically to every
   session, and the study measures whether the substrate carries a declared
   invariant — not whether the decoder's physics is right. Stated because a
   reader checking against the source paper would otherwise wonder.

4. Shot expansion. Published data is a counts histogram. The artifact carries one
   record per shot, expanded in sorted key order with counts repeated. Sorted
   order is required: dict iteration order would make the artifact digest depend
   on parse order rather than on content.

5. collection_start. Taken from the session's submitted_utc, re-rendered in the
   format the contract pins (RFC 3339, UTC, second precision, literal Z).

6. calibration_age_hours. Integer hours from calibration_before to submitted_utc,
   truncated. Declared and receipt-bound but NOT admission-material per contract
   section 5.1.2, so truncation cannot affect any decision.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

CIRCUIT_KEY = "P_archive|ENC_PASSIVE|1"
CODE_DISTANCE = 3
ROUNDS = 3
DETECTOR_BITS = ROUNDS * (CODE_DISTANCE - 1)

SOURCE_REPO = "github.com/billyrdavis1985-bot/IRMB_QEC-P1_DriftAware_RepetitionCode"
SOURCE_DOI = "10.5281/zenodo.22050536"


def _parse_submitted(text: str) -> datetime:
    return datetime.strptime(text, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


def _parse_calibration(text: str) -> datetime:
    """calibration_before is published as '2026-08-14 11:04:18-04:00'."""
    return datetime.strptime(text, "%Y-%m-%d %H:%M:%S%z")


def _render(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def syndrome_records(counts: dict[str, int]) -> list[str]:
    """Expand a counts histogram into one syndrome record per shot."""
    records: list[str] = []
    for outcome in sorted(counts):
        groups = outcome.split()
        if len(groups) != ROUNDS + 1:
            raise ValueError(
                f"outcome {outcome!r} has {len(groups)} groups, expected {ROUNDS + 1} "
                "(data + one per round)"
            )
        record = "".join(groups[1:])  # drop the data register
        if len(record) != DETECTOR_BITS:
            raise ValueError(
                f"outcome {outcome!r} yields {len(record)} detector bits, "
                f"expected {DETECTOR_BITS}"
            )
        if record.strip("01"):
            raise ValueError(f"outcome {outcome!r} contains non-binary characters")
        records.extend([record] * counts[outcome])
    return records


def build_artifact(
    runs_dir: Path,
    session: int,
    session_index: int,
    parent_receipt_id: str | None,
) -> dict:
    """Build one capability input artifact from a published session.

    session        the session number as published (11, 12, ...)
    session_index  the lineage index within the conformance study (1, 2, ...)
    """
    jobs = json.loads((runs_dir / f"session_{session}_jobs.json").read_text())
    counts_file = json.loads((runs_dir / f"session_{session}_counts.json").read_text())

    counts = counts_file["counts"].get(CIRCUIT_KEY)
    if counts is None:
        raise KeyError(
            f"session {session} has no circuit {CIRCUIT_KEY!r}; "
            f"available: {sorted(counts_file['counts'])[:4]}…"
        )

    submitted = _parse_submitted(jobs["submitted_utc"])
    calibrated = _parse_calibration(jobs["calibration_before"])
    records = syndrome_records(counts)

    return {
        "session_index": session_index,
        "backend_id": jobs["backend"],
        "collection_start": _render(submitted),
        "calibration_window_id": jobs["calibration_before"],
        "calibration_age_hours": int((submitted - calibrated).total_seconds() // 3600),
        "calibration_stratum": (
            "stale" if (submitted - calibrated) >= timedelta(hours=24) else "fresh"
        ),
        "code_distance": CODE_DISTANCE,
        "rounds": jobs["rounds"],
        "shots": len(records),
        "syndrome_records": records,
        "parent_receipt_id": parent_receipt_id,
        "_source": {
            "repository": SOURCE_REPO,
            "doi": SOURCE_DOI,
            "published_session": session,
            "circuit": CIRCUIT_KEY,
            "main_job_id": counts_file["stamp"].get("main_job_id"),
        },
    }


def separation_hours(a: dict, b: dict) -> float:
    return (
        _parse_submitted(b["collection_start"]) - _parse_submitted(a["collection_start"])
    ).total_seconds() / 3600

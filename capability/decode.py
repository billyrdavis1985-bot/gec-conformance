"""
qec-syndrome-decode 1.1.0

Deterministic offline decode of committed syndrome measurement records.
Implements the capability described in the frozen contract; §4 (determinism)
and §3 (inputs/outputs) are the normative statements, and this module is
written to satisfy them literally.

What this module deliberately does NOT do, because the contract forbids it:

  - no floating point anywhere in the decode path or the output
  - no wall clock, hostname, path, duration, or process metadata in the output
  - no dependence on dict, set, or filesystem iteration order
  - no randomness, seeded or otherwise
  - no partial results: decode_status has exactly one legal value
  - no network, no subprocess

The one output artifact and the one error artifact are mutually exclusive, and
both are declared in advance so that emitting either is never an undeclared
consequence.
"""

from __future__ import annotations

import hashlib
import json
import sys
from typing import Any

from .table import TableError, detector_count, table_artifact, table_digest

CAPABILITY_VERSION = "1.1.0"

REQUIRED_INPUT_FIELDS = (
    "session_index",
    "backend_id",
    "collection_start",
    "calibration_window_id",
    "calibration_age_hours",
    "calibration_stratum",
    "code_distance",
    "rounds",
    "shots",
    "syndrome_records",
    "parent_receipt_id",
)

ERROR_CLASSES = (
    "schema_invalid",
    "record_malformed",
    "table_unavailable",
    "shots_mismatch",
)


class DecodeError(Exception):
    def __init__(self, error_class: str, detail: str) -> None:
        if error_class not in ERROR_CLASSES:
            raise ValueError(f"undeclared error class {error_class!r}")
        super().__init__(detail)
        self.error_class = error_class


# -- input handling ---------------------------------------------------------


def digest_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def load_input(raw: bytes) -> dict:
    """Parse and validate the declared input artifact.

    Duplicate keys are rejected rather than resolved last-wins: a document whose
    canonical form does not reflect what a reader sees must not be admitted.
    """

    def hook(pairs):
        keys = [k for k, _ in pairs]
        if len(keys) != len(set(keys)):
            raise DecodeError("schema_invalid", "duplicate keys in input artifact")
        return dict(pairs)

    try:
        obj = json.loads(raw.decode("utf-8"), object_pairs_hook=hook)
    except UnicodeDecodeError as exc:
        raise DecodeError("schema_invalid", f"input is not valid UTF-8: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise DecodeError("schema_invalid", f"input is not valid JSON: {exc}") from exc

    if not isinstance(obj, dict):
        raise DecodeError("schema_invalid", "input artifact must be a JSON object")

    missing = [f for f in REQUIRED_INPUT_FIELDS if f not in obj]
    if missing:
        raise DecodeError("schema_invalid", f"missing declared fields: {missing}")

    _check_types(obj)
    return obj


def _check_types(obj: dict) -> None:
    def is_int(v: Any) -> bool:
        return isinstance(v, int) and not isinstance(v, bool)

    if not is_int(obj["session_index"]) or obj["session_index"] < 1:
        raise DecodeError("schema_invalid", "session_index must be an integer >= 1")
    for field in ("code_distance", "rounds", "shots"):
        if not is_int(obj[field]) or obj[field] < 1:
            raise DecodeError("schema_invalid", f"{field} must be an integer >= 1")
    for field in ("backend_id", "collection_start", "calibration_window_id", "calibration_stratum"):
        if not isinstance(obj[field], str):
            raise DecodeError("schema_invalid", f"{field} must be a string")
    if not isinstance(obj["syndrome_records"], list):
        raise DecodeError("schema_invalid", "syndrome_records must be an array")
    if obj["parent_receipt_id"] is not None and not isinstance(obj["parent_receipt_id"], str):
        raise DecodeError("schema_invalid", "parent_receipt_id must be a string or null")
    if (obj["parent_receipt_id"] is None) != (obj["session_index"] == 1):
        raise DecodeError(
            "schema_invalid",
            "parent_receipt_id is null if and only if session_index == 1",
        )
    # calibration_age_hours is declared as number and is NOT admission-material
    # (contract §5.1.2). It is validated for presence and type only; its value
    # never affects the decode result.
    if isinstance(obj["calibration_age_hours"], bool) or not isinstance(
        obj["calibration_age_hours"], (int, float)
    ):
        raise DecodeError("schema_invalid", "calibration_age_hours must be a number")


# -- decode -----------------------------------------------------------------


def decode(obj: dict, input_digest: str) -> dict:
    """Decode the session and return the declared output artifact."""
    distance, rounds, shots = obj["code_distance"], obj["rounds"], obj["shots"]
    records = obj["syndrome_records"]
    width = detector_count(distance, rounds)

    if len(records) != shots:
        raise DecodeError(
            "shots_mismatch",
            f"declared shots={shots} but {len(records)} syndrome records present",
        )

    try:
        artifact = table_artifact(distance, rounds)
    except TableError as exc:
        raise DecodeError("table_unavailable", str(exc)) from exc
    table = artifact["table"]

    logical_error_count = 0
    defects_per_round = [0] * rounds

    for index, record in enumerate(records):
        if not isinstance(record, str):
            raise DecodeError("record_malformed", f"record {index} is not a string")
        if len(record) != width:
            raise DecodeError(
                "record_malformed",
                f"record {index} has length {len(record)}, expected {width}",
            )
        if record.strip("01"):
            raise DecodeError(
                "record_malformed", f"record {index} contains non-binary characters"
            )

        logical_error_count += table[record]
        for r in range(rounds):
            segment = record[r * (distance - 1) : (r + 1) * (distance - 1)]
            defects_per_round[r] += segment.count("1")

    return {
        "capability_version": CAPABILITY_VERSION,
        "decode_table_digest": table_digest(artifact),
        "input_digest": input_digest,
        "session_index": obj["session_index"],
        "logical_error_count": logical_error_count,
        "shots": shots,
        "defects_per_round": defects_per_round,
        "decode_status": "complete",
    }


def error_artifact(input_digest: str, error_class: str) -> dict:
    return {
        "capability_version": CAPABILITY_VERSION,
        "input_digest": input_digest,
        "error_class": error_class,
    }


def emit(artifact: dict) -> bytes:
    """Serialize an output artifact to bytes.

    Sorted keys, no whitespace, UTF-8, no trailing newline. The output contains
    no float, so no float rendering question arises — which is why the contract
    forbids floats in the output rather than specifying how to print them.
    """
    return json.dumps(
        artifact, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def run(raw: bytes) -> tuple[bytes, bool]:
    """Full capability execution. Returns (artifact_bytes, ok)."""
    input_digest = digest_bytes(raw)
    try:
        return emit(decode(load_input(raw), input_digest)), True
    except DecodeError as exc:
        return emit(error_artifact(input_digest, exc.error_class)), False


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: python3 -m capability.decode <input.json>", file=sys.stderr)
        return 2
    with open(argv[1], "rb") as handle:
        raw = handle.read()
    artifact, ok = run(raw)
    sys.stdout.buffer.write(artifact)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))

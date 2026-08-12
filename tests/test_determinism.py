"""
Determinism self-test for qec-syndrome-decode.

This validates contract §4, which is the capability author's obligation, not the
substrate's. If the capability is not byte-stable, the conformance study is void
regardless of how SCQOS behaves — a differing digest would be uninterpretable,
since it could originate on either side.

Failing here is a finding against the capability and must be fixed before freeze.
Failing in the SCQOS run is a finding against the substrate. Establishing which
is which is the entire purpose of running this first.

The hash-randomization check is the one that matters. Python randomizes string
hashing per process by default, so any accidental dependence on dict or set
iteration order surfaces as a cross-process difference and nowhere else.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from capability.decode import CAPABILITY_VERSION, emit, run  # noqa: E402
from capability.table import build_table, table_artifact, table_digest  # noqa: E402


def session(**overrides) -> bytes:
    """A valid session artifact; overrides replace individual fields."""
    base = {
        "session_index": 2,
        "backend_id": "ibm_fez",
        "collection_start": "2026-08-07T02:21:59Z",
        "calibration_window_id": "2026-08-06T23:21:59-04:00",
        "calibration_age_hours": 3,
        "calibration_stratum": "fresh",
        "code_distance": 3,
        "rounds": 3,
        "shots": 8,
        "syndrome_records": [
            "000000", "000000", "100000", "010010",
            "000001", "110000", "000000", "001100",
        ],
        "parent_receipt_id": "rcpt-0001",
    }
    base.update(overrides)
    return json.dumps(base).encode("utf-8")


class TestRepeatability(unittest.TestCase):
    def test_identical_bytes_across_repeated_runs(self):
        raw = session()
        outputs = {run(raw)[0] for _ in range(50)}
        self.assertEqual(len(outputs), 1, "output is not stable within one process")

    def test_identical_bytes_across_separate_processes(self):
        """Cross-process is where hash randomization would show up."""
        raw = session()
        script = (
            "import sys,json;sys.path.insert(0,%r);"
            "from capability.decode import run;"
            "sys.stdout.buffer.write(run(sys.stdin.buffer.read())[0])" % str(ROOT)
        )
        digests = set()
        for seed in ("0", "1", "12345", "999999"):
            env = dict(os.environ, PYTHONHASHSEED=seed)
            proc = subprocess.run(
                [sys.executable, "-c", script], input=raw, capture_output=True, env=env
            )
            self.assertEqual(proc.returncode, 0, proc.stderr.decode())
            digests.add(proc.stdout)
        self.assertEqual(
            len(digests), 1, "output varies with PYTHONHASHSEED — iteration-order dependence"
        )

    def test_input_key_order_does_not_change_output(self):
        parsed = json.loads(session().decode())
        forward = json.dumps(parsed, sort_keys=True).encode()
        reverse = json.dumps(
            {k: parsed[k] for k in sorted(parsed, reverse=True)}
        ).encode()
        # input_digest differs by construction; everything else must not.
        a = json.loads(run(forward)[0].decode())
        b = json.loads(run(reverse)[0].decode())
        a.pop("input_digest"), b.pop("input_digest")
        self.assertEqual(a, b)


class TestContractSection4(unittest.TestCase):
    """Properties the contract asserts about the output artifact."""

    def setUp(self):
        self.artifact = json.loads(run(session())[0].decode())

    def test_no_floating_point_anywhere_in_output(self):
        def walk(node):
            if isinstance(node, float):
                self.fail(f"float found in output: {node!r}")
            if isinstance(node, dict):
                for v in node.values():
                    walk(v)
            if isinstance(node, list):
                for v in node:
                    walk(v)

        walk(self.artifact)

    def test_no_ambient_metadata_in_output(self):
        text = run(session())[0].decode().lower()
        for banned in ("timestamp", "hostname", "duration", "elapsed", "/home", "pid"):
            self.assertNotIn(banned, text)

    def test_output_fields_match_the_declared_schema(self):
        self.assertEqual(
            sorted(self.artifact),
            sorted(
                [
                    "capability_version",
                    "decode_table_digest",
                    "input_digest",
                    "session_index",
                    "logical_error_count",
                    "shots",
                    "defects_per_round",
                    "decode_status",
                ]
            ),
        )

    def test_decode_status_has_one_legal_value(self):
        self.assertEqual(self.artifact["decode_status"], "complete")

    def test_no_trailing_newline(self):
        self.assertFalse(run(session())[0].endswith(b"\n"))

    def test_version_is_pinned(self):
        self.assertEqual(self.artifact["capability_version"], CAPABILITY_VERSION)


class TestStratificationIsNotMaterial(unittest.TestCase):
    """Contract §5.1.2: calibration fields are declared but not admission-material.

    They must be accepted and must not change the decode result. A capability
    whose output moved with them would make case C24 untestable.
    """

    def test_stratum_does_not_change_output(self):
        fresh = json.loads(run(session(calibration_stratum="fresh", calibration_age_hours=3))[0])
        stale = json.loads(run(session(calibration_stratum="stale", calibration_age_hours=83))[0])
        for key in ("logical_error_count", "defects_per_round", "decode_table_digest"):
            self.assertEqual(fresh[key], stale[key])


class TestTableProperties(unittest.TestCase):
    def test_table_is_total(self):
        for distance, rounds in ((3, 1), (3, 3), (5, 2)):
            with self.subTest(distance=distance, rounds=rounds):
                bits = rounds * (distance - 1)
                table = build_table(distance, rounds)
                self.assertEqual(len(table), 2**bits, "table is not total")

    def test_table_digest_is_stable_across_rebuilds(self):
        first = table_digest(table_artifact(3, 3))
        second = table_digest(table_artifact(3, 3))
        self.assertEqual(first, second)

    def test_all_zero_syndrome_implies_no_correction(self):
        table = build_table(3, 3)
        self.assertEqual(table["0" * 6], 0)

    def test_table_values_are_binary(self):
        self.assertEqual(set(build_table(3, 3).values()) - {0, 1}, set())


class TestErrorPath(unittest.TestCase):
    def test_error_artifact_replaces_output_artifact(self):
        raw = session(shots=99)
        artifact, ok = run(raw)
        self.assertFalse(ok)
        parsed = json.loads(artifact.decode())
        self.assertEqual(parsed["error_class"], "shots_mismatch")
        self.assertNotIn("logical_error_count", parsed)

    def test_malformed_record_is_refused_not_skipped(self):
        raw = session(syndrome_records=["000000"] * 7 + ["00000X"])
        _, ok = run(raw)
        self.assertFalse(ok)

    def test_duplicate_input_keys_rejected(self):
        raw = b'{"session_index":1,"session_index":2}'
        artifact, ok = run(raw)
        self.assertFalse(ok)
        self.assertEqual(json.loads(artifact)["error_class"], "schema_invalid")

    def test_error_artifact_is_also_deterministic(self):
        raw = session(shots=99)
        self.assertEqual(len({run(raw)[0] for _ in range(20)}), 1)


class TestKnownValues(unittest.TestCase):
    """Anchors so a future refactor cannot silently change the decode."""

    def test_defect_counts_are_exact(self):
        # Verified by independent hand count over the fixture, not copied from
        # program output: round 0 fires on records 3, 4, 6 (weights 1,1,2);
        # round 1 on record 8 (weight 2); round 2 on records 4 and 5 (1 each).
        artifact = json.loads(run(session())[0].decode())
        self.assertEqual(artifact["defects_per_round"], [4, 2, 2])
        self.assertEqual(artifact["shots"], 8)

    def test_all_clean_session_has_no_logical_errors(self):
        raw = session(syndrome_records=["000000"] * 8)
        artifact = json.loads(run(raw)[0].decode())
        self.assertEqual(artifact["logical_error_count"], 0)
        self.assertEqual(artifact["defects_per_round"], [0, 0, 0])


if __name__ == "__main__":
    unittest.main(verbosity=2)

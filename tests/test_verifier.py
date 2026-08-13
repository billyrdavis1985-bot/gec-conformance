"""
Verifier tests.

The important group is TestMutationBattery. A verifier that passes valid
receipts proves nothing on its own — the failure mode that matters is a verifier
that passes everything. Each mutation below takes a valid receipt, breaks one
thing, and asserts the verifier catches that specific thing.
"""

from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from canon.rulesets import SCQOS_LITERAL  # noqa: E402
from verifier.receipt import (  # noqa: E402
    INVARIANTS,
    ReceiptVerifier,
    Status,
    parse_rfc3339_utc,
)


def state(session_index: int, collection_start: str, **extra) -> dict:
    base = {
        "session_index": session_index,
        "backend_id": "ibm_fez",
        "collection_start": collection_start,
        "calibration_window_id": "2026-08-06T23:21:59-04:00",
        "calibration_age_hours": 3,
        "calibration_stratum": "fresh",
        "code_distance": 3,
        "rounds": 3,
        "shots": 8,
    }
    base.update(extra)
    return base


def predicates(failing: tuple[str, ...] = ()) -> list[dict]:
    return [
        {
            "id": i,
            "result": "FAIL" if i in failing else "PASS",
            "evaluated_inputs": ["declared_state.collection_start"],
            "evidence": ["parent.collection_start"] if i in failing else [],
        }
        for i in INVARIANTS
    ]


def receipt(
    session_index: int,
    collection_start: str,
    decision: str,
    parent_digest: str | None,
    failing: tuple[str, ...] = (),
    output_digest: str | None = None,
) -> dict:
    return {
        "receipt_id": f"rcpt-{session_index:04d}",
        "receipt_version": "1.0.0",
        "capability_id": "qec-syndrome-decode",
        "capability_version": "1.1.0",
        "policy_version": "scqos-inv-1",
        "state_digest": "unused-in-these-tests",
        "parent_state_digest": parent_digest,
        "input_digest": "0" * 64,
        "environment_digest": "1" * 64,
        "authority_reference": "hudson-forge",
        "genesis_reference": "rcpt-0001",
        "decision": decision,
        "predicates": predicates(failing),
        "temporal_window": {"not_before": collection_start},
        "output_digest": output_digest,
        "proof_digest": "2" * 128,
        "declared_state": state(session_index, collection_start),
    }


class Fixtures:
    """A parent at T, plus compliant and violating successors."""

    PARENT_START = "2026-08-07T02:00:00Z"

    def __init__(self):
        self.parent = receipt(1, self.PARENT_START, "PERMIT", None)
        verifier = ReceiptVerifier(SCQOS_LITERAL)
        self.parent_digest = verifier.canon.digest(self.parent["declared_state"])
        self.parent["state_digest"] = self.parent_digest
        self.store = {self.parent_digest: self.parent}
        self.verifier = ReceiptVerifier(SCQOS_LITERAL, self.store)

    def child(self, collection_start: str, decision: str, failing=(), output=None):
        return receipt(2, collection_start, decision, self.parent_digest, failing, output)


class TestTimestampParsing(unittest.TestCase):
    def test_pinned_format_accepted(self):
        parsed = parse_rfc3339_utc("2026-08-07T02:21:59Z")
        self.assertEqual(parsed.hour, 2)

    def test_offset_form_rejected(self):
        """Same instant, different encoding — must not be silently accepted."""
        with self.assertRaises(ValueError):
            parse_rfc3339_utc("2026-08-06T22:21:59-04:00")

    def test_subsecond_form_rejected(self):
        with self.assertRaises(ValueError):
            parse_rfc3339_utc("2026-08-07T02:21:59.000Z")

    def test_naive_form_rejected(self):
        with self.assertRaises(ValueError):
            parse_rfc3339_utc("2026-08-07T02:21:59")


class TestSeparationPredicate(unittest.TestCase):
    """Contract §5.1.1 — the governing invariant, computed independently."""

    def setUp(self):
        self.f = Fixtures()

    def test_compliant_separation_permitted(self):
        r = self.f.child("2026-08-07T14:01:00Z", "PERMIT", ())  # 12h01m
        result = self.f.verifier.verify(r)
        sep = [c for c in result.checks if c.name == "separation"][0]
        self.assertIs(sep.status, Status.PASS)

    def test_near_boundary_violation_must_hold(self):
        """C22: 11h59m. A PERMIT here falsifies H1."""
        r = self.f.child("2026-08-07T13:59:00Z", "PERMIT", ())
        result = self.f.verifier.verify(r)
        sep = [c for c in result.checks if c.name == "separation"][0]
        self.assertIs(sep.status, Status.FAIL)
        self.assertIn("11h59m", sep.detail)

    def test_near_boundary_pair_is_distinguished(self):
        """C22/C23: two minutes apart must not receive the same verdict."""
        violating = self.f.verifier.verify(
            self.f.child("2026-08-07T13:59:00Z", "HOLD", ("I2",))
        )
        compliant = self.f.verifier.verify(
            self.f.child("2026-08-07T14:01:00Z", "PERMIT", ())
        )
        self.assertEqual(violating.failed, [])
        self.assertEqual(compliant.failed, [])

    def test_exact_boundary_is_compliant(self):
        r = self.f.child("2026-08-07T14:00:00Z", "PERMIT", ())  # exactly 12h
        sep = [c for c in self.f.verifier.verify(r).checks if c.name == "separation"][0]
        self.assertIs(sep.status, Status.PASS)

    def test_negative_separation_caught(self):
        """Successor collected before its parent."""
        r = self.f.child("2026-08-06T02:00:00Z", "PERMIT", ())
        sep = [c for c in self.f.verifier.verify(r).checks if c.name == "separation"][0]
        self.assertIs(sep.status, Status.FAIL)

    def test_violation_must_be_attributed_to_i1_or_i2(self):
        """Right decision, wrong reason — decision-level scoring would miss this."""
        r = self.f.child("2026-08-07T13:59:00Z", "HOLD", ("I5",))
        result = self.f.verifier.verify(r)
        attribution = [c for c in result.checks if c.name == "separation_attribution"][0]
        self.assertIs(attribution.status, Status.FAIL)


class TestStratificationNotMaterial(unittest.TestCase):
    """C24: stale calibration with compliant separation must still PERMIT."""

    def test_stale_stratum_does_not_cause_failure(self):
        f = Fixtures()
        r = f.child("2026-08-07T14:01:00Z", "PERMIT", ())
        r["declared_state"]["calibration_stratum"] = "stale"
        r["declared_state"]["calibration_age_hours"] = 83
        self.assertEqual(f.verifier.verify(r).failed, [])


class TestMutationBattery(unittest.TestCase):
    """Break one thing at a time; assert the verifier catches that thing."""

    def setUp(self):
        self.f = Fixtures()
        self.valid = self.f.child("2026-08-07T14:01:00Z", "PERMIT", ())
        self.assertEqual(
            self.f.verifier.verify(self.valid).failed, [], "baseline receipt must be clean"
        )

    def mutate(self, **changes) -> list:
        r = copy.deepcopy(self.valid)
        for key, value in changes.items():
            r[key] = value
        return self.f.verifier.verify(r).failed

    def test_missing_required_field_caught(self):
        r = copy.deepcopy(self.valid)
        del r["policy_version"]
        failed = self.f.verifier.verify(r).failed
        self.assertTrue(any(c.name == "schema" for c in failed))

    def test_decision_outside_enum_caught(self):
        self.assertTrue(any(c.name == "schema" for c in self.mutate(decision="MAYBE")))

    def test_unresolvable_parent_caught(self):
        failed = self.mutate(parent_state_digest="f" * 64)
        self.assertTrue(any(c.name == "lineage" for c in failed))

    def test_missing_parent_on_successor_caught(self):
        failed = self.mutate(parent_state_digest=None)
        self.assertTrue(any(c.name == "lineage" for c in failed))

    def test_predicate_omission_caught(self):
        partial = [p for p in predicates() if p["id"] != "I8"]
        failed = self.mutate(predicates=partial)
        self.assertTrue(any(c.name == "predicate_exposure" for c in failed))

    def test_predicate_without_evidence_caught(self):
        stripped = [{k: v for k, v in p.items() if k != "evidence"} for p in predicates()]
        failed = self.mutate(predicates=stripped)
        self.assertTrue(any(c.name == "predicate_evidence" for c in failed))

    def test_permit_with_failing_predicate_caught(self):
        failed = self.mutate(predicates=predicates(("I5",)))
        self.assertTrue(any(c.name == "decision_derivation" for c in failed))

    def test_hold_with_no_failing_predicate_caught(self):
        """A HOLD that does not explain itself."""
        r = copy.deepcopy(self.valid)
        r["decision"] = "HOLD"
        r["output_digest"] = None
        failed = self.f.verifier.verify(r).failed
        self.assertTrue(any(c.name == "decision_derivation" for c in failed))

    def test_hold_carrying_an_output_digest_caught(self):
        r = self.f.child("2026-08-07T13:59:00Z", "HOLD", ("I2",), output="3" * 64)
        failed = self.f.verifier.verify(r).failed
        self.assertTrue(any(c.name == "output_digest" for c in failed))

    def test_hold_with_a_consequence_caught(self):
        r = self.f.child("2026-08-07T13:59:00Z", "HOLD", ("I2",))
        failed = self.f.verifier.verify(r, output_artifact={"any": "thing"}).failed
        self.assertTrue(any(c.name == "consequence" for c in failed))

    def test_input_digest_mismatch_caught(self):
        """C13."""
        failed = self.f.verifier.verify(self.valid, input_artifact={"not": "it"}).failed
        self.assertTrue(any(c.name == "input_digest" for c in failed))

    def test_input_digest_match_passes(self):
        artifact = {"real": "input"}
        r = copy.deepcopy(self.valid)
        r["input_digest"] = self.f.verifier.canon.digest(artifact)
        result = self.f.verifier.verify(r, input_artifact=artifact)
        check = [c for c in result.checks if c.name == "input_digest"][0]
        self.assertIs(check.status, Status.PASS)

    def test_loose_timestamp_caught(self):
        r = copy.deepcopy(self.valid)
        r["declared_state"]["collection_start"] = "2026-08-07T14:01:00.000Z"
        failed = self.f.verifier.verify(r).failed
        self.assertTrue(any(c.name == "separation" for c in failed))


class TestSignatureIsNotSilentlyPassed(unittest.TestCase):
    """The gap must surface, not be laundered into a green result."""

    def test_signature_reported_unverifiable(self):
        f = Fixtures()
        result = f.verifier.verify(f.child("2026-08-07T14:01:00Z", "PERMIT", ()))
        sig = [c for c in result.checks if c.name == "signature"][0]
        self.assertIs(sig.status, Status.UNVERIFIABLE)

    def test_clean_receipt_is_not_reported_as_verified(self):
        f = Fixtures()
        result = f.verifier.verify(f.child("2026-08-07T14:01:00Z", "PERMIT", ()))
        self.assertEqual(result.failed, [])
        self.assertFalse(
            result.verified,
            "a receipt with an unchecked signature must not report as VERIFIED",
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)

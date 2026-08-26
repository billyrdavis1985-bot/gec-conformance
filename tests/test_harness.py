"""
Harness validation.

Establishes that the scorecard identifies known defects. Until these pass, a
clean phase 1 result would be uninterpretable: it could mean the substrate is
correct, or it could mean the harness cannot tell.

Each test drives a mock with one known behaviour and asserts the scorecard
surfaces exactly that behaviour.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from canon.rulesets import SCQOS_LITERAL  # noqa: E402
from harness.fixtures import build_phase1, load_parent  # noqa: E402
from harness.mocks import (  # noqa: E402
    AliasedPredicates,
    CorrectSubstrate,
    DefaultPermitGate,
    MisattributingGate,
    ParanoidGate,
    PerExecutionOnly,
)
from harness.runner import NEGATIVE_CONTROLS, Harness, NullAdapter  # noqa: E402


def _separation_hours(a: dict, b: dict) -> float:
    from harness.fixtures import _parse

    return (_parse(b["collection_start"]) - _parse(a["collection_start"])).total_seconds() / 3600


def run_against(adapter_class):
    parent, _ = load_parent()
    fixtures = build_phase1(parent)
    harness = Harness(SCQOS_LITERAL, adapter_class(parent["collection_start"]))
    harness.run(fixtures)
    return harness


def result_for(harness, case_id):
    return next(r for r in harness.results if r.case_id == case_id)


class TestFixtureConstruction(unittest.TestCase):
    def setUp(self):
        self.parent, _ = load_parent()
        self.fixtures = build_phase1(self.parent)

    def test_eleven_phase1_cases(self):
        self.assertEqual(len(self.fixtures), 11)

    def test_near_boundary_pair_differs_only_in_time(self):
        """C22 and C23 must be identical apart from collection_start."""
        c22 = next(f for f in self.fixtures if f.case_id == "C22").artifact
        c23 = next(f for f in self.fixtures if f.case_id == "C23").artifact
        differing = {k for k in set(c22) | set(c23) if c22.get(k) != c23.get(k)}
        self.assertEqual(differing, {"collection_start"})

    def test_near_boundary_pair_is_two_minutes_apart(self):
        from harness.fixtures import _parse

        c22 = next(f for f in self.fixtures if f.case_id == "C22").artifact
        c23 = next(f for f in self.fixtures if f.case_id == "C23").artifact
        delta = _parse(c23["collection_start"]) - _parse(c22["collection_start"])
        self.assertEqual(delta.total_seconds(), 120)

    def test_c24_differs_only_in_stratification_fields(self):
        """C24 must isolate the stratification fields and nothing else.

        Compared against an equivalently constructed compliant successor rather
        than against C01: C01 is now collected data with its own real
        collection_start, so it is not the right baseline for this comparison.
        """
        from datetime import timedelta

        from harness.fixtures import successor

        baseline = successor(self.parent, timedelta(hours=14))
        c24 = next(f for f in self.fixtures if f.case_id == "C24").artifact
        differing = {
            k for k in set(baseline) | set(c24) if baseline.get(k) != c24.get(k)
        }
        self.assertEqual(differing, {"calibration_stratum", "calibration_age_hours"})

    def test_synthetic_successors_are_labelled_and_real_ones_are_not(self):
        """The label must track reality in both directions.

        A synthetic artifact silently passing as collected would misrepresent
        the study; a collected artifact wrongly labelled synthetic would
        understate it. Both are errors.
        """
        for fixture in self.fixtures:
            if fixture.artifact is None:
                continue
            labelled = bool(fixture.artifact.get("_synthetic"))
            self.assertEqual(
                labelled, fixture.synthetic,
                f"{fixture.case_id}: artifact label {labelled} disagrees with "
                f"fixture.synthetic {fixture.synthetic}",
            )
            if not fixture.synthetic:
                self.assertIn(
                    "_source", fixture.artifact,
                    f"{fixture.case_id} claims to be collected data but cites no source",
                )

    def test_c01_uses_collected_data_when_wired(self):
        from harness.fixtures import load_real_successor

        c01 = next(f for f in self.fixtures if f.case_id == "C01")
        if load_real_successor() is None:
            self.skipTest("collected successor not wired")
        self.assertFalse(c01.synthetic)
        self.assertGreaterEqual(
            _separation_hours(self.parent, c01.artifact), 12.0,
            "C01 is the compliant control; its real separation must satisfy the predicate",
        )

    def test_timestamps_use_the_pinned_format(self):
        from verifier.receipt import parse_rfc3339_utc

        for fixture in self.fixtures:
            if fixture.artifact is not None:
                parse_rfc3339_utc(fixture.artifact["collection_start"])

    def test_every_case_has_a_locked_prediction(self):
        for fixture in self.fixtures:
            self.assertTrue(fixture.predicted_decision)


class TestHarnessDetectsCorrectSubstrate(unittest.TestCase):
    def setUp(self):
        self.h = run_against(CorrectSubstrate)
        self.s = self.h.summary()

    def test_all_offline_cases_execute(self):
        self.assertEqual(self.s["cases_executed"], 9)  # C09, C18 need a live substrate

    def test_no_false_positives(self):
        self.assertEqual(self.s["false_positives"], 0)

    def test_predicate_agreement_is_complete(self):
        self.assertEqual(self.s["predicate_level_agreement"], self.s["cases_executed"])

    def test_near_boundary_pair_is_split(self):
        self.assertEqual(result_for(self.h, "C22").actual_decision, "HOLD")
        self.assertEqual(result_for(self.h, "C23").actual_decision, "PERMIT")


class TestHarnessDetectsPerExecutionOnly(unittest.TestCase):
    """The H1 failure must be visible, not averaged away."""

    def setUp(self):
        self.h = run_against(PerExecutionOnly)

    def test_c06_permits_when_it_should_hold(self):
        self.assertEqual(result_for(self.h, "C06").actual_decision, "PERMIT")
        self.assertFalse(result_for(self.h, "C06").predicate_agrees)

    def test_near_boundary_pair_is_not_split(self):
        """C22 and C23 both PERMIT — H1 falsified by the pair criterion."""
        self.assertEqual(
            result_for(self.h, "C22").actual_decision,
            result_for(self.h, "C23").actual_decision,
        )

    def test_true_positive_rate_collapses(self):
        self.assertEqual(self.h.summary()["true_positives"], 0)

    def test_negative_controls_still_pass(self):
        """The defect is invisible to controls alone — why violations are needed."""
        self.assertEqual(self.h.summary()["false_positives"], 0)


class TestHarnessDetectsParanoidGate(unittest.TestCase):
    """The H5 failure: perfect violation detection, worthless gate."""

    def setUp(self):
        self.h = run_against(ParanoidGate)
        self.s = self.h.summary()

    def test_catches_every_violation(self):
        self.assertEqual(self.s["true_positives"], self.s["violation_cases_run"])

    def test_but_false_positive_rate_exposes_it(self):
        self.assertEqual(self.s["false_positives"], self.s["negative_controls_run"])
        self.assertGreater(self.s["false_positives"], 0)

    def test_this_is_why_fp_rate_is_always_reported(self):
        """Violation-only scoring would rate this substrate perfect."""
        report = self.h.report()
        self.assertIn("FALSE-POSITIVE rate", report)


class TestHarnessDetectsAliasing(unittest.TestCase):
    """H3: co-firing with identical evidence is what indicates aliasing."""

    def test_shared_evidence_is_surfaced(self):
        h = run_against(AliasedPredicates)
        matrix = h.aliasing_matrix()
        self.assertTrue(matrix)
        for row in matrix.values():
            self.assertEqual(row["fired"], ("I2", "I4", "I7"))
            self.assertEqual(row["distinct_evidence_payloads"], 1)

    def test_distinct_evidence_is_not_flagged_as_aliasing(self):
        h = run_against(CorrectSubstrate)
        for row in h.aliasing_matrix().values():
            self.assertLessEqual(len(row["fired"]), 1)


class TestHarnessDetectsMisattribution(unittest.TestCase):
    """Right decision, wrong predicate — the case for predicate-level scoring."""

    def setUp(self):
        self.h = run_against(MisattributingGate)

    def test_decision_level_scoring_would_pass_it(self):
        self.assertTrue(result_for(self.h, "C06").decision_agrees)

    def test_predicate_level_scoring_catches_it(self):
        self.assertFalse(result_for(self.h, "C06").predicate_agrees)

    def test_primary_and_secondary_outcomes_disagree(self):
        s = self.h.summary()
        self.assertGreater(
            s["decision_level_agreement"], s["predicate_level_agreement"]
        )


class TestHarnessDetectsDefaultPermit(unittest.TestCase):
    """C07: missing ancestry must HOLD, never PERMIT by default."""

    def test_c07_permit_is_caught(self):
        h = run_against(DefaultPermitGate)
        self.assertEqual(result_for(h, "C07").actual_decision, "PERMIT")
        self.assertFalse(result_for(h, "C07").predicate_agrees)

    def test_correct_substrate_holds_on_c07(self):
        h = run_against(CorrectSubstrate)
        self.assertEqual(result_for(h, "C07").actual_decision, "HOLD")


class TestReportingDiscipline(unittest.TestCase):
    def test_unpinned_run_is_marked_not_reportable(self):
        h = run_against(CorrectSubstrate)
        self.assertIn("NOT PINNED", h.report())

    def test_pinned_run_shows_the_pin_table(self):
        h = run_against(CorrectSubstrate)
        h.pin_table = {"scqos_build_digest": "abc123", "policy_version": "inv-1"}
        report = h.report()
        self.assertIn("scqos_build_digest", report)
        self.assertNotIn("NOT PINNED", report)

    def test_bridging_ledger_records_interventions(self):
        h = run_against(CorrectSubstrate)
        h.record_bridging("C05", "adapter required manual field mapping")
        self.assertIn("manual field mapping", h.report())

    def test_offline_dry_run_produces_no_findings(self):
        parent, _ = load_parent()
        h = Harness(SCQOS_LITERAL, NullAdapter())
        h.run(build_phase1(parent))
        self.assertEqual(h.summary()["cases_executed"], 0)

    def test_negative_control_set_matches_the_preregistration(self):
        # A negative control is any case predicted to PERMIT (prereg §5.1).
        self.assertEqual(
            set(NEGATIVE_CONTROLS),
            {"C01", "C02", "C03", "C04", "C05", "C23", "C24"},
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)


class TestHarnessDetectsLiteralByteHashing(unittest.TestCase):
    """C05: a substrate hashing submitted bytes rather than canonical bytes."""

    def setUp(self):
        from harness.mocks import LiteralByteHasher

        self.h = run_against(LiteralByteHasher)

    def test_c05_variant_disagreement_is_caught(self):
        c05 = result_for(self.h, "C05")
        self.assertFalse(c05.variant_agrees)
        self.assertIn("state digest", c05.note)

    def test_c05_fails_predicate_agreement_despite_correct_decision(self):
        c05 = result_for(self.h, "C05")
        self.assertEqual(c05.actual_decision, "PERMIT")  # decision is right
        self.assertTrue(c05.decision_agrees)
        self.assertFalse(c05.predicate_agrees)  # but the case still fails

    def test_every_other_case_looks_clean(self):
        """The defect is invisible outside C05 — why the case exists."""
        others = [r for r in self.h.results if r.executed and r.case_id != "C05"]
        self.assertTrue(all(r.predicate_agrees for r in others))

    def test_correct_substrate_passes_the_variant(self):
        h = run_against(CorrectSubstrate)
        self.assertTrue(result_for(h, "C05").variant_agrees)

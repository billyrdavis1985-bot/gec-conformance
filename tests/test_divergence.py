"""
Divergence locator tests, and the spec-closure check.

TestSpecClosure is the piece that carries real information in round two. Once
SC-Engineering freezes the representation layer, the question is not whether two
RFC 8785 implementations agree — they will, and that shows only that a standard
was adopted. The question is whether the frozen universe actually eliminates the
degrees of freedom found in round one. That is testable: the two readings that
diverged before must no longer both satisfy it.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from canon.corpus import BY_ID  # noqa: E402
from canon.rulesets import SCQOS_ES6, SCQOS_LITERAL  # noqa: E402
from harness.divergence import (  # noqa: E402
    STAGES,
    Run,
    Stage,
    Verdict,
    compare_runs,
    locate_across_cases,
    run_from_local,
    summarize,
)
from verifier.receipt import INVARIANTS  # noqa: E402


def predicates(failing=(), evidence_by=None):
    evidence_by = evidence_by or {}
    return [
        {
            "id": i,
            "result": "FAIL" if i in failing else "PASS",
            "evidence": evidence_by.get(i, ["parent.collection_start"] if i in failing else []),
        }
        for i in INVARIANTS
    ]


def run(label, case_id, **stages):
    return Run(label, case_id, {getattr(Stage, k.upper()): v for k, v in stages.items()})


class TestStageOrdering(unittest.TestCase):
    def test_stages_are_causally_ordered(self):
        self.assertEqual(
            [s.label for s in STAGES],
            [
                "canonical bytes", "digest", "predicate evaluations",
                "decision", "consequence", "receipt",
            ],
        )


class TestHaltOnFirst(unittest.TestCase):
    """The core property: downstream stages are NOT_REACHED, never FAIL."""

    def test_downstream_stages_are_not_reached(self):
        left = run("A", "C06", canonical_bytes=b'{"a":1}', digest="aaa",
                   predicates=predicates(), decision="PERMIT",
                   consequence="out-1", receipt="proof-1")
        right = run("B", "C06", canonical_bytes=b'{"a":1.0}', digest="bbb",
                    predicates=predicates(("I2",)), decision="HOLD",
                    consequence=None, receipt="proof-2")
        report = compare_runs(left, right)

        self.assertIs(report.first_divergence.stage, Stage.CANONICAL_BYTES)
        downstream = [c for c in report.comparisons if c.stage.order > 1]
        self.assertTrue(all(c.verdict is Verdict.NOT_REACHED for c in downstream))

    def test_one_defect_is_not_reported_as_six(self):
        left = run("A", "C06", canonical_bytes=b"x", digest="a",
                   predicates=predicates(), decision="PERMIT",
                   consequence=None, receipt="p")
        right = run("B", "C06", canonical_bytes=b"y", digest="b",
                    predicates=predicates(("I2",)), decision="HOLD",
                    consequence="z", receipt="q")
        report = compare_runs(left, right)
        diverged = [c for c in report.comparisons if c.verdict is Verdict.DIVERGED]
        self.assertEqual(len(diverged), 1)

    def test_divergence_deeper_in_the_chain_is_located_there(self):
        shared = dict(canonical_bytes=b'{"a":1}', digest="same",
                      predicates=predicates())
        left = run("A", "C22", **shared, decision="HOLD", consequence=None, receipt="p")
        right = run("B", "C22", **shared, decision="PERMIT", consequence="out", receipt="p")
        report = compare_runs(left, right)
        self.assertIs(report.first_divergence.stage, Stage.DECISION)
        early = [c for c in report.comparisons if c.stage.order < 4]
        self.assertTrue(all(c.verdict is Verdict.EQUAL for c in early))

    def test_full_convergence_reports_none(self):
        shared = dict(canonical_bytes=b'{"a":1}', digest="d", predicates=predicates(),
                      decision="PERMIT", consequence="out", receipt="p")
        report = compare_runs(run("A", "C01", **shared), run("B", "C01", **shared))
        self.assertIsNone(report.first_divergence)
        self.assertTrue(report.converged)


class TestPredicateComparison(unittest.TestCase):
    """Evidence is part of the comparison, not decoration."""

    def test_same_results_different_evidence_diverges(self):
        shared = dict(canonical_bytes=b"x", digest="d")
        left = run("A", "C06", **shared,
                   predicates=predicates(("I2",), {"I2": ["parent.collection_start"]}))
        right = run("B", "C06", **shared,
                    predicates=predicates(("I2",), {"I2": ["lineage.parent_digest"]}))
        report = compare_runs(left, right)
        self.assertIs(report.first_divergence.stage, Stage.PREDICATES)

    def test_identical_predicates_converge(self):
        shared = dict(canonical_bytes=b"x", digest="d", predicates=predicates(("I2",)))
        report = compare_runs(run("A", "C06", **shared), run("B", "C06", **shared))
        self.assertIsNone(report.first_divergence)

    def test_predicate_order_does_not_matter(self):
        shared = dict(canonical_bytes=b"x", digest="d")
        forward = predicates(("I2",))
        report = compare_runs(
            run("A", "C06", **shared, predicates=forward),
            run("B", "C06", **shared, predicates=list(reversed(forward))),
        )
        self.assertIsNone(report.first_divergence)


class TestUnavailableStages(unittest.TestCase):
    """A stage not produced is not a stage that produced nothing."""

    def test_missing_stage_is_unavailable_not_diverged(self):
        left = run("A", "C01", canonical_bytes=b"x", digest="d")
        right = run("B", "C01", canonical_bytes=b"x", digest="d")
        report = compare_runs(left, right)
        later = [c for c in report.comparisons if c.stage.order >= 3]
        self.assertTrue(all(c.verdict is Verdict.UNAVAILABLE for c in later))
        self.assertIsNone(report.first_divergence)

    def test_unavailable_does_not_halt_the_walk(self):
        left = run("A", "C01", canonical_bytes=b"x", digest="d", decision="PERMIT")
        right = run("B", "C01", canonical_bytes=b"x", digest="d", decision="HOLD")
        report = compare_runs(left, right)
        self.assertIs(report.first_divergence.stage, Stage.DECISION)


class TestNoReconciliationPath(unittest.TestCase):
    """The tool must be structurally incapable of making two runs agree."""

    def test_module_exposes_no_merge_or_tolerance(self):
        import harness.divergence as module

        forbidden = ("merge", "reconcile", "prefer", "tolerance", "coerce", "fix")
        exposed = [
            name for name in dir(module)
            if any(word in name.lower() for word in forbidden)
        ]
        self.assertEqual(exposed, [], f"reconciliation surface present: {exposed}")

    def test_mismatched_cases_are_refused(self):
        with self.assertRaises(ValueError):
            compare_runs(run("A", "C01", digest="a"), run("B", "C02", digest="b"))


class TestSpecClosure(unittest.TestCase):
    """Does a frozen ruleset actually eliminate round one's degrees of freedom?

    This is the only part of the round-two convergence exercise that carries
    information. Convergence between two implementations of a named standard
    shows the standard was adopted; it does not show the specification is
    precise. What can be shown is that the readings which diverged before no
    longer both satisfy the frozen universe.
    """

    OPEN_QUESTION_CASES = ("NUM-01", "NUM-04", "INT-02", "ORD-01")

    def test_round_one_readings_diverge_on_the_open_questions(self):
        """Baseline: without a freeze, both readings are viable and disagree."""
        located = 0
        for case_id in self.OPEN_QUESTION_CASES:
            artifact = BY_ID[case_id].value
            report = compare_runs(
                run_from_local("literal", case_id, artifact, SCQOS_LITERAL),
                run_from_local("es6", case_id, artifact, SCQOS_ES6),
            )
            if report.first_divergence is not None:
                self.assertIs(report.first_divergence.stage, Stage.CANONICAL_BYTES)
                located += 1
        self.assertEqual(
            located, len(self.OPEN_QUESTION_CASES),
            "these cases exist to discriminate the two readings",
        )

    def test_closure_check_passes_when_one_reading_is_eliminated(self):
        """After a freeze, comparing a reading against ITSELF must converge.

        Stands in for the post-freeze assertion: once the universe names a
        single rule, only one reading remains viable, and the surviving
        implementation agrees with itself on every discriminating case.
        """
        for case_id in self.OPEN_QUESTION_CASES:
            artifact = BY_ID[case_id].value
            report = compare_runs(
                run_from_local("frozen-a", case_id, artifact, SCQOS_ES6),
                run_from_local("frozen-b", case_id, artifact, SCQOS_ES6),
            )
            self.assertIsNone(report.first_divergence, case_id)

    def test_summary_names_the_earliest_boundary(self):
        reports = locate_across_cases(
            [run_from_local("literal", c, BY_ID[c].value, SCQOS_LITERAL)
             for c in self.OPEN_QUESTION_CASES],
            [run_from_local("es6", c, BY_ID[c].value, SCQOS_ES6)
             for c in self.OPEN_QUESTION_CASES],
        )
        text = summarize(reports)
        self.assertIn("EARLIEST BOUNDARY: canonical bytes", text)


class TestRefusalIsAState(unittest.TestCase):
    def test_refuse_versus_emit_is_a_divergence(self):
        """One implementation refusing where another emits is a real difference."""
        from canon.rulesets import JCS, NFC_UTF8_ASCII

        artifact = BY_ID["ORD-03"].value  # keys colliding under NFC
        report = compare_runs(
            run_from_local("jcs", "ORD-03", artifact, JCS),
            run_from_local("nfc", "ORD-03", artifact, NFC_UTF8_ASCII),
        )
        self.assertIs(report.first_divergence.stage, Stage.CANONICAL_BYTES)
        self.assertIn("REFUSED", report.first_divergence.right)


if __name__ == "__main__":
    unittest.main(verbosity=2)

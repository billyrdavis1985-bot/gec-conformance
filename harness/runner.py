"""
Phase 1 harness and scorecard.

Executes each fixture against a substrate adapter, verifies the returned
receipt with the clean-room verifier, and scores the run.

Scoring commitments, fixed by the preregistration and enforced here rather than
left to the person writing the report:

  - PRIMARY outcome is predicate-level agreement, not decision-level. A
    substrate can reach the right decision by the wrong route, and decision
    agreement cannot distinguish the two.
  - False-positive rate on the negative controls is reported in every summary,
    unconditionally. A gate that HOLDs on everything scores perfectly on
    violations and is worthless. `summary()` cannot be called in a way that
    omits it.
  - The I2/I4/I7 co-fire matrix is emitted whenever any lineage case ran, since
    H3 turns on whether those predicates cite distinct evidence.
  - Every manual intervention is itemized in the bridging ledger. H6 asks
    whether an externally authored contract is accepted without manual
    bridging; an unrecorded workaround silently converts a failure into a pass.

The adapter boundary is deliberately thin. NullAdapter runs the whole pipeline
offline so the harness is exercised before any live integration, and its
results are marked NOT_EXECUTED so they can never be mistaken for findings.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol

from canon.ruleset import Ruleset
from harness.fixtures import Fixture, build_phase1, load_parent
from verifier.receipt import INVARIANTS, ReceiptVerifier, Status

LINEAGE_PREDICATES = ("I2", "I4", "I7")
NEGATIVE_CONTROLS = ("C01", "C02", "C05", "C23", "C24")


class SubstrateAdapter(Protocol):
    """Minimal surface the harness needs from a governed-execution substrate."""

    name: str
    live: bool  # True only for a real substrate

    def submit(
        self, case_id: str, artifact_bytes: bytes, declared_digest: str | None = None
    ) -> dict | None:
        """Return a receipt, or None if the substrate produced none.

        declared_digest, when present, is the digest the submitter CLAIMS for
        these bytes. A conforming substrate must recompute and refuse a
        mismatch."""


class NullAdapter:
    """Offline stand-in. Produces no receipts; every case records NOT_EXECUTED."""

    name = "null (offline dry run)"
    live = False

    def submit(self, case_id, artifact_bytes, declared_digest=None):
        return None


@dataclass
class CaseResult:
    case_id: str
    predicted_decision: str
    predicted_predicates: tuple[str, ...]
    actual_decision: str | None = None
    actual_failing: tuple[str, ...] = ()
    verification_failures: list[str] = field(default_factory=list)
    verification_unverifiable: list[str] = field(default_factory=list)
    predicate_evidence: dict[str, list] = field(default_factory=dict)
    executed: bool = False
    note: str = ""

    @property
    def decision_agrees(self) -> bool:
        if not self.executed or self.actual_decision is None:
            return False
        if "×" in self.predicted_decision:  # concurrency case, scored by hand
            return False
        return self.actual_decision == self.predicted_decision

    @property
    def predicate_agrees(self) -> bool:
        """Primary outcome: did the predicted failing predicate actually fail?

        Predicted predicates are a set of acceptable attributions, not an exact
        match requirement — a temporal violation may legitimately be reported
        under I1, I2, or both. Empty prediction means nothing should fail.
        """
        if not self.executed:
            return False
        if not self.predicted_predicates:
            return not self.actual_failing
        return bool(set(self.predicted_predicates) & set(self.actual_failing))


@dataclass
class BridgingEntry:
    case_id: str
    description: str


class Harness:
    def __init__(self, ruleset: Ruleset, adapter: SubstrateAdapter):
        self.ruleset = ruleset
        self.adapter = adapter
        self.verifier = ReceiptVerifier(ruleset)
        self.results: list[CaseResult] = []
        self.bridging: list[BridgingEntry] = []
        self.pin_table: dict[str, str] = {}

    def record_bridging(self, case_id: str, description: str) -> None:
        """Any manual step taken to make a case run. Never omit one."""
        self.bridging.append(BridgingEntry(case_id, description))

    def run(self, fixtures: list[Fixture]) -> list[CaseResult]:
        for fixture in fixtures:
            self.results.append(self._run_one(fixture))
        return self.results

    def _run_one(self, fixture: Fixture) -> CaseResult:
        result = CaseResult(
            fixture.case_id, fixture.predicted_decision, fixture.predicted_predicates
        )

        # Cases whose test condition IS the substrate's runtime behaviour
        # (a concurrency race, an unrequested consequence) cannot be produced by
        # a test double. Keying this on adapter.live rather than on a specific
        # adapter class matters: a mock that "passes" C18 by returning no receipt
        # would otherwise be scored as having detected a real bypass.
        if fixture.requires_substrate and not getattr(self.adapter, "live", False):
            result.note = "requires live substrate; not executable here"
            return result

        receipt = self.adapter.submit(
            fixture.case_id, fixture.bytes_(), fixture.declared_digest_override
        )

        if receipt is None:
            if fixture.case_id == "C18":
                # No receipt is the FINDING here, not a missing result: a
                # consequence was produced without an admission request.
                result.executed = True
                result.actual_decision = "NO_RECEIPT"
                result.note = (
                    "no admission request, no receipt — consequence produced outside "
                    "the governed path"
                )
            else:
                result.note = "substrate returned no receipt"
            return result

        result.executed = True
        result.actual_decision = receipt.get("decision")

        predicates = self.verifier._predicate_map(receipt)
        result.actual_failing = tuple(
            i for i in INVARIANTS if predicates.get(i, {}).get("result") == "FAIL"
        )
        result.predicate_evidence = {
            i: predicates.get(i, {}).get("evidence", []) for i in LINEAGE_PREDICATES
        }

        verification = self.verifier.verify(receipt, input_artifact=fixture.artifact)
        result.verification_failures = [c.name for c in verification.failed]
        result.verification_unverifiable = [c.name for c in verification.unverifiable]
        return result

    # -- scoring ------------------------------------------------------------

    def aliasing_matrix(self) -> dict[str, dict]:
        """H3: do I2, I4 and I7 fire together, and do they cite the same evidence?

        Co-firing alone is not aliasing — one event can legitimately violate
        several invariants. Identical evidence payloads are what decide it.
        """
        rows = {}
        for result in self.results:
            if not result.executed or not result.actual_failing:
                continue
            fired = tuple(i for i in LINEAGE_PREDICATES if i in result.actual_failing)
            if not fired:
                continue
            evidence = {i: result.predicate_evidence.get(i, []) for i in fired}
            distinct = len({json.dumps(v, sort_keys=True) for v in evidence.values()})
            rows[result.case_id] = {
                "fired": fired,
                "evidence_sets": evidence,
                "distinct_evidence_payloads": distinct,
            }
        return rows

    def summary(self) -> dict:
        executed = [r for r in self.results if r.executed]
        controls = [r for r in executed if r.case_id in NEGATIVE_CONTROLS]
        violations = [r for r in executed if r.case_id not in NEGATIVE_CONTROLS]

        false_positives = [
            r for r in controls if r.actual_decision in ("HOLD", "TERMINATE")
        ]
        true_positives = [
            r for r in violations if r.actual_decision in ("HOLD", "TERMINATE", "NO_RECEIPT")
        ]

        return {
            "cases_declared": len(self.results),
            "cases_executed": len(executed),
            "predicate_level_agreement": sum(r.predicate_agrees for r in executed),
            "decision_level_agreement": sum(r.decision_agrees for r in executed),
            "negative_controls_run": len(controls),
            "false_positives": len(false_positives),
            "false_positive_rate": (
                f"{len(false_positives)}/{len(controls)}" if controls else "n/a — none run"
            ),
            "violation_cases_run": len(violations),
            "true_positives": len(true_positives),
            "true_positive_rate": (
                f"{len(true_positives)}/{len(violations)}" if violations else "n/a — none run"
            ),
            "bridging_interventions": len(self.bridging),
            "aliasing_rows": len(self.aliasing_matrix()),
        }

    # -- reporting ----------------------------------------------------------

    def report(self) -> str:
        stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        summary = self.summary()
        lines = [
            "gec-conformance phase 1 scorecard",
            f"protocol 1.1.0  |  adapter: {self.adapter.name}  |  generated {stamp}",
            "",
        ]

        if self.pin_table:
            lines.append("pin table")
            for key, value in sorted(self.pin_table.items()):
                lines.append(f"  {key:<28} {value}")
        else:
            lines.append("pin table: NOT PINNED — results are not reportable")
        lines.append("")

        lines.append(f"{'case':<7} {'predicted':<12} {'actual':<12} {'pred':<6} {'dec':<5} note")
        lines.append("-" * 78)
        for r in self.results:
            actual = r.actual_decision or "—"
            pred_mark = "ok" if r.predicate_agrees else ("—" if not r.executed else "MISS")
            dec_mark = "ok" if r.decision_agrees else ("—" if not r.executed else "MISS")
            lines.append(
                f"{r.case_id:<7} {r.predicted_decision:<12} {actual:<12} "
                f"{pred_mark:<6} {dec_mark:<5} {r.note}"
            )
        lines.append("")

        lines.append("outcomes")
        lines.append(f"  cases executed              {summary['cases_executed']}/{summary['cases_declared']}")
        lines.append(f"  PRIMARY predicate agreement {summary['predicate_level_agreement']}/{summary['cases_executed']}")
        lines.append(f"  decision agreement          {summary['decision_level_agreement']}/{summary['cases_executed']}")
        lines.append(f"  true-positive rate          {summary['true_positive_rate']}")
        lines.append(f"  FALSE-POSITIVE rate         {summary['false_positive_rate']}")
        lines.append("")
        lines.append(
            "  The false-positive rate is reported unconditionally. A gate that HOLDs"
        )
        lines.append(
            "  on everything scores perfectly on violations and is worthless."
        )
        lines.append("")

        matrix = self.aliasing_matrix()
        lines.append("H3 — I2/I4/I7 co-fire and evidence")
        if not matrix:
            lines.append("  no lineage violations executed")
        else:
            for case_id, row in sorted(matrix.items()):
                lines.append(
                    f"  {case_id}: fired {row['fired']}, "
                    f"{row['distinct_evidence_payloads']} distinct evidence payload(s)"
                )
            lines.append("")
            lines.append(
                "  Co-firing alone is not aliasing. Identical evidence across all"
            )
            lines.append(
                "  three, in every case, is what would show one predicate under"
            )
            lines.append("  three names.")
        lines.append("")

        lines.append("bridging ledger")
        if not self.bridging:
            lines.append("  no manual interventions recorded")
        else:
            for entry in self.bridging:
                lines.append(f"  {entry.case_id}: {entry.description}")
        lines.append("")

        blocked = {name for r in self.results for name in r.verification_unverifiable}
        if blocked:
            lines.append(f"verification steps not performable: {sorted(blocked)}")
            lines.append("  see FINDINGS-CANON-02 (no signature algorithm specified)")

        return "\n".join(lines)


def dry_run(ruleset: Ruleset) -> str:
    """Exercise the full pipeline offline. Produces no findings by construction."""
    parent, is_real = load_parent()
    harness = Harness(ruleset, NullAdapter())
    harness.run(build_phase1(parent))
    banner = (
        "DRY RUN — no substrate contacted, no case executed, no result is a finding.\n"
        f"parent artifact: {'collected session 1' if is_real else 'STUB (not yet wired)'}\n\n"
    )
    return banner + harness.report()

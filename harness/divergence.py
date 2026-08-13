"""
First-divergence locator.

Implements the protocol Eric stated: when two independent implementations
diverge, do not reconcile them. Preserve the divergence and walk backward until
the first unequal state appears. That first difference identifies the actual
falsifiable boundary.

The stage model follows the chain both sides agreed on:

    canonical bytes -> digest -> predicate evaluations -> decision
                    -> consequence -> receipt

Two properties make this a tool rather than a discipline:

1. HALT-ON-FIRST. Comparison stops at the first unequal stage. Downstream
   stages are reported NOT_REACHED, never PASS and never FAIL. A digest
   difference caused by a canonical-byte difference is not an independent
   finding, and reporting it as one inflates a single defect into six.

2. NO RECONCILIATION PATH. There is deliberately no merge, no "prefer",
   no tolerance parameter. The tool can only report where two runs first
   disagree. Nothing in it can make them agree.

Stage ordering is causal, not cosmetic. Each stage's input is the previous
stage's output, so the first inequality is the only one whose cause is not
already explained by an earlier one.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable

from canon.engine import Canonicalizer
from canon.ruleset import CanonicalizationError, Ruleset
from verifier.receipt import INVARIANTS


class Stage(Enum):
    """Ordered causally: each stage consumes the previous stage's output."""

    CANONICAL_BYTES = (1, "canonical bytes")
    DIGEST = (2, "digest")
    PREDICATES = (3, "predicate evaluations")
    DECISION = (4, "decision")
    CONSEQUENCE = (5, "consequence")
    RECEIPT = (6, "receipt")

    def __init__(self, order: int, label: str) -> None:
        self.order = order
        self.label = label

    def __lt__(self, other: "Stage") -> bool:
        return self.order < other.order


STAGES = sorted(Stage, key=lambda s: s.order)


class Verdict(Enum):
    EQUAL = "EQUAL"
    DIVERGED = "DIVERGED"
    NOT_REACHED = "NOT_REACHED"  # an earlier stage diverged; this one is unknown
    UNAVAILABLE = "UNAVAILABLE"  # one or both runs did not produce this stage


@dataclass
class StageComparison:
    stage: Stage
    verdict: Verdict
    left: str = ""
    right: str = ""
    detail: str = ""


@dataclass
class Run:
    """One implementation's output for one case, stage by stage.

    Stages absent from `values` are UNAVAILABLE rather than empty. The
    distinction matters: a stage that was not produced is not a stage that
    produced nothing.
    """

    label: str
    case_id: str
    values: dict[Stage, Any] = field(default_factory=dict)

    def has(self, stage: Stage) -> bool:
        return stage in self.values

    def get(self, stage: Stage) -> Any:
        return self.values.get(stage)


@dataclass
class DivergenceReport:
    case_id: str
    left_label: str
    right_label: str
    comparisons: list[StageComparison]

    @property
    def first_divergence(self) -> StageComparison | None:
        for comparison in self.comparisons:
            if comparison.verdict is Verdict.DIVERGED:
                return comparison
        return None

    @property
    def converged(self) -> bool:
        return self.first_divergence is None and any(
            c.verdict is Verdict.EQUAL for c in self.comparisons
        )

    def render(self) -> str:
        lines = [
            f"case {self.case_id}:  {self.left_label}  vs  {self.right_label}",
        ]
        for comparison in self.comparisons:
            marker = {
                Verdict.EQUAL: "=",
                Verdict.DIVERGED: "X",
                Verdict.NOT_REACHED: ".",
                Verdict.UNAVAILABLE: "?",
            }[comparison.verdict]
            lines.append(
                f"  {marker} {comparison.stage.label:<22} {comparison.verdict.value}"
                + (f"  {comparison.detail}" if comparison.detail else "")
            )

        first = self.first_divergence
        if first is not None:
            lines.append("")
            lines.append(f"  FIRST DIVERGENCE: {first.stage.label}")
            lines.append(f"    {self.left_label:>20}: {first.left}")
            lines.append(f"    {self.right_label:>20}: {first.right}")
            lines.append("")
            lines.append(
                "  Stages after this one are NOT_REACHED. They are not independent"
            )
            lines.append(
                "  findings — their inputs already differ. This stage is the boundary."
            )
        return "\n".join(lines)


def _render(value: Any, limit: int = 72) -> str:
    if isinstance(value, bytes):
        text = value.decode("utf-8", errors="backslashreplace")
    elif isinstance(value, str):
        text = value
    else:
        text = json.dumps(value, sort_keys=True, default=str)
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _predicate_signature(value: Any) -> Any:
    """Normalize a predicate set for comparison.

    Compares result AND evidence per invariant. Two runs that agree on which
    predicates failed but cite different evidence have diverged: the evidence
    is what distinguishes genuinely independent predicates from aliases, so
    dropping it here would hide exactly the H3 signal the study exists to find.
    """
    if value is None:
        return None
    if isinstance(value, dict):
        entries = value
    else:
        entries = {p.get("id"): p for p in value if isinstance(p, dict)}
    return {
        i: {
            "result": entries.get(i, {}).get("result"),
            "evidence": entries.get(i, {}).get("evidence"),
        }
        for i in INVARIANTS
    }


def _equal(stage: Stage, left: Any, right: Any) -> bool:
    if stage is Stage.PREDICATES:
        return _predicate_signature(left) == _predicate_signature(right)
    if stage is Stage.CANONICAL_BYTES:
        return bytes(left) == bytes(right)
    return left == right


def compare_runs(left: Run, right: Run) -> DivergenceReport:
    """Walk the stages in causal order, halting at the first inequality."""
    if left.case_id != right.case_id:
        raise ValueError(
            f"cannot compare different cases: {left.case_id} vs {right.case_id}"
        )

    comparisons: list[StageComparison] = []
    halted = False

    for stage in STAGES:
        if halted:
            comparisons.append(StageComparison(stage, Verdict.NOT_REACHED))
            continue

        if not left.has(stage) or not right.has(stage):
            missing = [r.label for r in (left, right) if not r.has(stage)]
            comparisons.append(
                StageComparison(
                    stage, Verdict.UNAVAILABLE,
                    detail=f"not produced by {', '.join(missing)}",
                )
            )
            continue

        lhs, rhs = left.get(stage), right.get(stage)
        if _equal(stage, lhs, rhs):
            comparisons.append(StageComparison(stage, Verdict.EQUAL))
        else:
            comparisons.append(
                StageComparison(
                    stage, Verdict.DIVERGED,
                    left=_render(lhs), right=_render(rhs),
                )
            )
            halted = True

    return DivergenceReport(left.case_id, left.label, right.label, comparisons)


# -- constructing runs ------------------------------------------------------


def run_from_local(
    label: str,
    case_id: str,
    artifact: Any,
    ruleset: Ruleset,
    receipt: dict | None = None,
    consequence: Any = None,
) -> Run:
    """Build a Run from a locally computed canonicalization plus an optional receipt.

    The first two stages are always computable offline. The remaining four
    require a receipt; without one they stay UNAVAILABLE rather than being
    filled with placeholders.
    """
    canon = Canonicalizer(ruleset)
    values: dict[Stage, Any] = {}

    try:
        values[Stage.CANONICAL_BYTES] = canon.emit(artifact)
        values[Stage.DIGEST] = canon.digest(artifact)
    except CanonicalizationError as exc:
        # A refusal is a state, not an absence: two implementations where one
        # refuses and the other emits have diverged at this stage.
        values[Stage.CANONICAL_BYTES] = f"REFUSED: {exc}".encode("utf-8")
        values[Stage.DIGEST] = f"REFUSED: {exc}"

    if receipt is not None:
        values[Stage.PREDICATES] = receipt.get("predicates")
        values[Stage.DECISION] = receipt.get("decision")
        values[Stage.CONSEQUENCE] = (
            consequence if consequence is not None else receipt.get("output_digest")
        )
        values[Stage.RECEIPT] = receipt.get("proof_digest")

    return Run(label, case_id, values)


def locate_across_cases(
    left_runs: list[Run], right_runs: list[Run]
) -> list[DivergenceReport]:
    """Compare two implementations across a case set, preserving every divergence."""
    right_by_case = {run.case_id: run for run in right_runs}
    reports = []
    for run in left_runs:
        counterpart = right_by_case.get(run.case_id)
        if counterpart is not None:
            reports.append(compare_runs(run, counterpart))
    return reports


def summarize(reports: list[DivergenceReport]) -> str:
    """Group divergences by stage — the boundary, not the case count."""
    by_stage: dict[Stage, list[str]] = {}
    converged: list[str] = []

    for report in reports:
        first = report.first_divergence
        if first is None:
            converged.append(report.case_id)
        else:
            by_stage.setdefault(first.stage, []).append(report.case_id)

    lines = [
        f"first-divergence summary over {len(reports)} case(s)",
        "",
        f"  converged through every reached stage: {len(converged)}",
    ]
    if converged:
        lines.append(f"    {', '.join(converged)}")
    lines.append("")

    if not by_stage:
        lines.append("  no divergence located")
    else:
        lines.append("  first divergence by stage:")
        for stage in STAGES:
            cases = by_stage.get(stage)
            if cases:
                lines.append(f"    {stage.label:<22} {len(cases)}  ({', '.join(cases)})")
        lines.append("")
        earliest = min(by_stage, key=lambda s: s.order)
        lines.append(
            f"  EARLIEST BOUNDARY: {earliest.label}. Divergences at later stages"
        )
        lines.append(
            "  cannot be interpreted until this one is closed, since their inputs"
        )
        lines.append("  are downstream of it.")

    return "\n".join(lines)

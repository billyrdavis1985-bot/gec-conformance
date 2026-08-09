"""
Differential runner.

Runs two rulesets over the corpus and reports, per case, whether the canonical
bytes agree. Divergences are grouped by specification question so a report reads
as "the spec is silent on X" rather than "17 cases failed".

Errors are results, not crashes. A ruleset that refuses a case (rejecting a
big integer, rejecting a normalized duplicate key) is behaving correctly, and
refuse-vs-emit is itself a divergence worth recording.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from .corpus import CORPUS, Case
from .engine import Canonicalizer
from .ruleset import CanonicalizationError, Ruleset

AGREE = "AGREE"
DIVERGE = "DIVERGE"
BOTH_REFUSE = "BOTH_REFUSE"
ONE_REFUSES = "ONE_REFUSES"


@dataclass
class Outcome:
    case: Case
    status: str
    left: str  # rendered bytes or "REFUSED: reason"
    right: str
    left_digest: str | None
    right_digest: str | None

    @property
    def diverged(self) -> bool:
        return self.status in (DIVERGE, ONE_REFUSES)


def _render(canon: Canonicalizer, value) -> tuple[str, str | None, bool]:
    try:
        raw = canon.emit(value)
    except CanonicalizationError as exc:
        return f"REFUSED: {exc}", None, True
    return raw.decode("utf-8", errors="backslashreplace"), canon.digest(value), False


def compare(left: Ruleset, right: Ruleset, cases: Iterable[Case] = CORPUS) -> list[Outcome]:
    lhs, rhs = Canonicalizer(left), Canonicalizer(right)
    results: list[Outcome] = []

    for case in cases:
        l_text, l_dig, l_refused = _render(lhs, case.value)
        r_text, r_dig, r_refused = _render(rhs, case.value)

        if l_refused and r_refused:
            status = BOTH_REFUSE
        elif l_refused or r_refused:
            status = ONE_REFUSES
        elif l_text == r_text and l_dig == r_dig:
            status = AGREE
        else:
            status = DIVERGE

        results.append(Outcome(case, status, l_text, r_text, l_dig, r_dig))
    return results


def summarize(results: list[Outcome]) -> dict[str, dict[str, int]]:
    """Divergence counts grouped by specification question."""
    table: dict[str, dict[str, int]] = {}
    for out in results:
        bucket = table.setdefault(out.case.question, {AGREE: 0, DIVERGE: 0, BOTH_REFUSE: 0, ONE_REFUSES: 0})
        bucket[out.status] += 1
    return table


def report(left: Ruleset, right: Ruleset, results: list[Outcome], verbose: bool = False) -> str:
    lines: list[str] = []
    lines.append(f"differential: {left.name}  vs  {right.name}")
    lines.append(f"  left  source: {left.source}")
    lines.append(f"  right source: {right.source}")
    lines.append("")

    diverged = [r for r in results if r.diverged]
    lines.append(f"{len(diverged)} of {len(results)} cases diverge")
    lines.append("")
    lines.append(f"{'specification question':<26} {'agree':>6} {'diverge':>8} {'refuse':>7}")
    lines.append("-" * 50)
    for question, counts in summarize(results).items():
        refuse = counts[BOTH_REFUSE] + counts[ONE_REFUSES]
        lines.append(
            f"{question:<26} {counts[AGREE]:>6} {counts[DIVERGE]:>8} {refuse:>7}"
        )
    lines.append("")

    if diverged:
        lines.append("divergences")
        lines.append("-" * 50)
        for out in diverged:
            lines.append(f"{out.case.id}  [{out.case.question}]  {out.case.title}")
            lines.append(f"  {left.name:>16}: {out.left}")
            lines.append(f"  {right.name:>16}: {out.right}")
            if verbose and out.case.note:
                lines.append(f"  why it matters: {out.case.note}")
            lines.append("")

    return "\n".join(lines)

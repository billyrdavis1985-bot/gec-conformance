"""
Clean-room receipt verifier.

Written from the SCQOS receipt and canonicalization specifications only. No
SCQOS source, no SCQOS-produced canonical bytes, and no reference verifier were
consulted. This is the second implementation whose existence is the whole point:
if a producer and a verifier share a canonicalization library, a defect in that
library is invisible to both, and the receipt validates cleanly against a wrong
reading of the input.

Verification per contract §8.3 is four steps:

  1. reconstruct the canonical bytes
  2. recompute the digests
  3. validate the signer and authority
  4. confirm the decision follows from the frozen contract

Step 3 is STUBBED. The supplied specification covers canonicalization and
digest but never names a signature algorithm or key format, and
``external_signature`` is a declared schema field with no algorithm attached.
That gap is recorded as finding CANON-02 and surfaces in every result as
SIGNATURE_UNVERIFIABLE rather than being silently treated as a pass — a
verifier that reports success on an unchecked signature is worse than one that
refuses, because it launders the gap into a green result.

Steps 1, 2 and 4 are complete and are where the interesting failures live.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from canon.engine import Canonicalizer
from canon.ruleset import CanonicalizationError, Ruleset

# Invariant identifiers as supplied by SC-Engineering. I8's machine predicate is
# Accountability per correspondence; the conceptual label is retained.
INVARIANTS = ("I1", "I2", "I3", "I4", "I5", "I6", "I7", "I8")

INVARIANT_NAMES = {
    "I1": "Time",
    "I2": "Continuity",
    "I3": "Alignment",
    "I4": "Genesis",
    "I5": "Boundary",
    "I6": "Reference",
    "I7": "Causality",
    "I8": "Accountability",
}

DECISIONS = ("PERMIT", "HOLD", "TERMINATE")

# Contract §5.1.1. Held as an integer count of seconds so the comparison never
# touches floating point.
MIN_SEPARATION_SECONDS = 12 * 3600

REQUIRED_RECEIPT_FIELDS = (
    "receipt_version",
    "capability_id",
    "capability_version",
    "policy_version",
    "state_digest",
    "parent_state_digest",
    "input_digest",
    "environment_digest",
    "authority_reference",
    "genesis_reference",
    "decision",
    "predicates",
    "temporal_window",
    "output_digest",
    "proof_digest",
)


class Status(Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    UNVERIFIABLE = "UNVERIFIABLE"  # cannot be checked from the spec as supplied


@dataclass
class Check:
    name: str
    status: Status
    detail: str

    def __str__(self) -> str:
        return f"[{self.status.value:<13}] {self.name}: {self.detail}"


@dataclass
class VerificationResult:
    receipt_id: str
    checks: list[Check] = field(default_factory=list)

    def add(self, name: str, status: Status, detail: str) -> None:
        self.checks.append(Check(name, status, detail))

    @property
    def failed(self) -> list[Check]:
        return [c for c in self.checks if c.status is Status.FAIL]

    @property
    def unverifiable(self) -> list[Check]:
        return [c for c in self.checks if c.status is Status.UNVERIFIABLE]

    @property
    def verified(self) -> bool:
        """True only when nothing failed AND nothing was left unchecked.

        Unverifiable is deliberately not treated as passing. A gap in the
        specification must not be laundered into a green result.
        """
        return not self.failed and not self.unverifiable

    def report(self) -> str:
        lines = [f"receipt {self.receipt_id}"]
        lines += [f"  {check}" for check in self.checks]
        lines.append("")
        if self.failed:
            lines.append(f"  VERIFICATION FAILED — {len(self.failed)} check(s) failed")
        elif self.unverifiable:
            lines.append(
                f"  INCOMPLETE — {len(self.unverifiable)} check(s) not verifiable "
                "from the specification as supplied"
            )
        else:
            lines.append("  VERIFIED")
        return "\n".join(lines)


def parse_rfc3339_utc(text: str) -> datetime:
    """Parse the pinned timestamp format: RFC 3339, UTC, seconds, literal Z.

    Contract §3.1 pins this format precisely because the governing invariant is
    temporal. Accepting looser forms here would defeat that: two encodings of
    one instant must not be able to produce two admission results.
    """
    if not isinstance(text, str):
        raise ValueError(f"timestamp must be a string, got {type(text).__name__}")
    if len(text) != 20 or not text.endswith("Z") or text[10] != "T":
        raise ValueError(
            f"timestamp {text!r} is not RFC 3339 UTC second-precision with Z suffix"
        )
    return datetime.strptime(text, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


class ReceiptVerifier:
    """Independent verifier over a receipt and the lineage it claims."""

    def __init__(self, ruleset: Ruleset, receipt_store: dict[str, dict] | None = None):
        self.canon = Canonicalizer(ruleset)
        self.ruleset = ruleset
        self.store = receipt_store or {}

    # -- entry point --------------------------------------------------------

    def verify(
        self,
        receipt: dict,
        input_artifact: Any = None,
        output_artifact: Any = None,
    ) -> VerificationResult:
        result = VerificationResult(receipt.get("receipt_id", "<no id>"))

        if not self._check_schema(receipt, result):
            return result  # further checks would be meaningless

        self._check_digests(receipt, input_artifact, output_artifact, result)
        self._check_predicates(receipt, result)
        self._check_lineage(receipt, result)
        self._check_temporal(receipt, result)
        self._check_decision_consequences(receipt, output_artifact, result)
        self._check_decision_derivation(receipt, result)
        self._check_signature(receipt, result)
        return result

    # -- step 0: schema -----------------------------------------------------

    def _check_schema(self, receipt: dict, result: VerificationResult) -> bool:
        missing = [f for f in REQUIRED_RECEIPT_FIELDS if f not in receipt]
        if missing:
            result.add("schema", Status.FAIL, f"missing required fields: {missing}")
            return False
        if receipt["decision"] not in DECISIONS:
            result.add(
                "schema", Status.FAIL,
                f"decision {receipt['decision']!r} is not one of {DECISIONS}",
            )
            return False
        result.add("schema", Status.PASS, "all required fields present, decision in enum")
        return True

    # -- steps 1 and 2: canonical bytes and digests -------------------------

    def _recompute(self, value: Any) -> str | None:
        try:
            return self.canon.digest(value)
        except CanonicalizationError:
            return None

    def _check_digests(
        self, receipt: dict, input_artifact: Any, output_artifact: Any,
        result: VerificationResult,
    ) -> None:
        if input_artifact is None:
            result.add(
                "input_digest", Status.UNVERIFIABLE,
                "input artifact not supplied to the verifier",
            )
        else:
            recomputed = self._recompute(input_artifact)
            if recomputed is None:
                result.add(
                    "input_digest", Status.FAIL,
                    "input artifact cannot be canonicalized under this ruleset",
                )
            elif recomputed != receipt["input_digest"]:
                result.add(
                    "input_digest", Status.FAIL,
                    f"declared {receipt['input_digest'][:24]}… but recomputed "
                    f"{recomputed[:24]}… — the receipt does not describe these bytes",
                )
            else:
                result.add("input_digest", Status.PASS, "recomputed digest matches")

        declared_output = receipt.get("output_digest")
        if receipt["decision"] != "PERMIT":
            if declared_output is not None:
                result.add(
                    "output_digest", Status.FAIL,
                    f"decision is {receipt['decision']} but an output digest is present; "
                    "a non-admitted execution must produce no consequence",
                )
            else:
                result.add("output_digest", Status.PASS, "null, as required for non-PERMIT")
        elif output_artifact is None:
            result.add(
                "output_digest", Status.UNVERIFIABLE, "output artifact not supplied"
            )
        else:
            recomputed = self._recompute(output_artifact)
            if recomputed != declared_output:
                result.add(
                    "output_digest", Status.FAIL,
                    f"declared {str(declared_output)[:24]}… but recomputed "
                    f"{str(recomputed)[:24]}…",
                )
            else:
                result.add("output_digest", Status.PASS, "recomputed digest matches")

    # -- predicates ---------------------------------------------------------

    def _predicate_map(self, receipt: dict) -> dict[str, dict]:
        raw = receipt.get("predicates", [])
        if isinstance(raw, dict):
            return raw
        return {p.get("id"): p for p in raw if isinstance(p, dict)}

    def _check_predicates(self, receipt: dict, result: VerificationResult) -> None:
        """Contract §8.2: every invariant exposed independently, with evidence.

        Scoring at predicate level is what makes the aliasing question (H3)
        answerable. An aggregate decision cannot distinguish a system that held
        for the right reason from one that held for the wrong reason.
        """
        predicates = self._predicate_map(receipt)

        missing = [i for i in INVARIANTS if i not in predicates]
        if missing:
            result.add(
                "predicate_exposure", Status.FAIL,
                f"receipt does not expose {missing}; per-predicate results are "
                "required by contract §8.2",
            )
            return

        without_evidence = [
            i for i in INVARIANTS
            if "evidence" not in predicates[i] or predicates[i].get("evidence") is None
        ]
        without_inputs = [
            i for i in INVARIANTS if "evaluated_inputs" not in predicates[i]
        ]

        if without_evidence or without_inputs:
            detail = []
            if without_evidence:
                detail.append(f"no evidence field: {without_evidence}")
            if without_inputs:
                detail.append(f"no evaluated_inputs field: {without_inputs}")
            result.add(
                "predicate_evidence", Status.FAIL,
                "; ".join(detail) + " — evidence is required to distinguish "
                "genuinely independent predicates from aliases",
            )
        else:
            result.add(
                "predicate_evidence", Status.PASS,
                "all eight predicates expose result, evaluated inputs and evidence",
            )

        bad = [i for i in INVARIANTS if predicates[i].get("result") not in ("PASS", "FAIL")]
        if bad:
            result.add(
                "predicate_results", Status.FAIL,
                f"predicates {bad} have a result outside {{PASS, FAIL}}",
            )
        else:
            failing = [i for i in INVARIANTS if predicates[i]["result"] == "FAIL"]
            result.add(
                "predicate_results", Status.PASS,
                f"failing: {failing or 'none'}",
            )

    # -- lineage ------------------------------------------------------------

    def _check_lineage(self, receipt: dict, result: VerificationResult) -> None:
        parent_digest = receipt.get("parent_state_digest")
        session = (receipt.get("declared_state") or {}).get("session_index")

        if session == 1:
            if parent_digest is not None:
                result.add(
                    "lineage", Status.FAIL,
                    "session 1 declares a parent; genesis must have none",
                )
            else:
                result.add("lineage", Status.PASS, "session 1, no parent, as required")
            return

        if parent_digest is None:
            result.add(
                "lineage", Status.FAIL,
                "session > 1 declares no parent — contract §5.1.3 requires one",
            )
            return

        parent = self.store.get(parent_digest)
        if parent is None:
            result.add(
                "lineage", Status.FAIL,
                f"parent {parent_digest[:24]}… does not resolve in the receipt store; "
                "missing ancestry must HOLD, never PERMIT by default",
            )
            return

        recomputed = self._recompute(parent.get("declared_state"))
        if recomputed != parent_digest:
            result.add(
                "lineage", Status.FAIL,
                "parent state digest does not match the parent's declared state",
            )
            return

        parent_index = (parent.get("declared_state") or {}).get("session_index")
        if session is not None and parent_index is not None and session != parent_index + 1:
            result.add(
                "lineage", Status.FAIL,
                f"session_index {session} does not follow parent {parent_index}",
            )
            return

        result.add("lineage", Status.PASS, f"parent resolves; index follows {parent_index}")

    # -- temporal separation: the governing invariant -----------------------

    def _check_temporal(self, receipt: dict, result: VerificationResult) -> None:
        """Contract §5.1.1: collection_start(N) - collection_start(N-1) >= 12h.

        This is the predicate the whole study exists to test, so it is computed
        here independently rather than read from the receipt's own conclusion.
        """
        state = receipt.get("declared_state") or {}
        session = state.get("session_index")

        if session == 1:
            result.add("separation", Status.PASS, "session 1, no predecessor")
            return

        parent = self.store.get(receipt.get("parent_state_digest"))
        if parent is None:
            result.add(
                "separation", Status.UNVERIFIABLE,
                "parent not resolvable; separation cannot be computed",
            )
            return

        try:
            this_start = parse_rfc3339_utc(state.get("collection_start"))
            prev_start = parse_rfc3339_utc(
                (parent.get("declared_state") or {}).get("collection_start")
            )
        except ValueError as exc:
            result.add("separation", Status.FAIL, f"timestamp not in the pinned format: {exc}")
            return

        delta = int((this_start - prev_start).total_seconds())
        compliant = delta >= MIN_SEPARATION_SECONDS
        hours, minutes = divmod(abs(delta) // 60, 60)
        rendered = f"{'-' if delta < 0 else ''}{hours}h{minutes:02d}m"

        expected = "PERMIT" if compliant else "HOLD"
        actual = receipt["decision"]

        if compliant and actual == "PERMIT":
            result.add("separation", Status.PASS, f"{rendered} >= 12h, admitted")
        elif not compliant and actual in ("HOLD", "TERMINATE"):
            result.add("separation", Status.PASS, f"{rendered} < 12h, held")
        else:
            result.add(
                "separation", Status.FAIL,
                f"separation {rendered} implies {expected} but receipt says {actual}",
            )

        # Whether the substrate attributes the violation to the right predicate
        # is scored separately from whether it reached the right decision.
        if not compliant:
            predicates = self._predicate_map(receipt)
            fired = [
                i for i in ("I1", "I2")
                if predicates.get(i, {}).get("result") == "FAIL"
            ]
            if fired:
                result.add(
                    "separation_attribution", Status.PASS,
                    f"violation attributed to {fired} "
                    f"({', '.join(INVARIANT_NAMES[i] for i in fired)})",
                )
            else:
                result.add(
                    "separation_attribution", Status.FAIL,
                    "temporal violation not attributed to I1 Time or I2 Continuity; "
                    f"failing predicates were "
                    f"{[i for i in INVARIANTS if predicates.get(i, {}).get('result') == 'FAIL'] or 'none'}",
                )

    # -- consequences and decision derivation -------------------------------

    def _check_decision_consequences(
        self, receipt: dict, output_artifact: Any, result: VerificationResult
    ) -> None:
        """A HOLD must leave no consequence behind."""
        if receipt["decision"] == "PERMIT":
            result.add("consequence", Status.PASS, "PERMIT; output permitted")
            return
        if output_artifact is not None:
            result.add(
                "consequence", Status.FAIL,
                f"decision is {receipt['decision']} but an output artifact exists — "
                "authority dropped to zero yet a consequence was produced",
            )
        else:
            result.add("consequence", Status.PASS, "no consequence produced, as required")

    def _check_decision_derivation(self, receipt: dict, result: VerificationResult) -> None:
        """Coherence: PERMIT requires all eight predicates to resolve."""
        predicates = self._predicate_map(receipt)
        failing = [i for i in INVARIANTS if predicates.get(i, {}).get("result") == "FAIL"]

        if receipt["decision"] == "PERMIT" and failing:
            result.add(
                "decision_derivation", Status.FAIL,
                f"PERMIT with failing predicates {failing}; Coherence requires all "
                "eight to resolve simultaneously",
            )
        elif receipt["decision"] in ("HOLD", "TERMINATE") and not failing:
            result.add(
                "decision_derivation", Status.FAIL,
                f"{receipt['decision']} with no failing predicate; the receipt does "
                "not explain its own decision",
            )
        else:
            result.add(
                "decision_derivation", Status.PASS,
                f"{receipt['decision']} consistent with failing predicates "
                f"{failing or 'none'}",
            )

    # -- step 3: signature (blocked) ----------------------------------------

    def _check_signature(self, receipt: dict, result: VerificationResult) -> None:
        if "proof_digest" not in receipt or not receipt["proof_digest"]:
            result.add("signature", Status.FAIL, "no proof digest present")
            return
        result.add(
            "signature", Status.UNVERIFIABLE,
            "the supplied specification names no signature algorithm or key format "
            "(finding CANON-02); signer and authority validation per contract §8.3 "
            "cannot be performed",
        )

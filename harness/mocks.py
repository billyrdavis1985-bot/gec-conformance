"""
Mock substrates with known behaviour.

The dry run in runner.py exercises the pipeline but proves nothing: every case
comes back NOT_EXECUTED. What has to be established before any live run is that
the harness DISCRIMINATES — that a substrate with a known defect produces a
scorecard that identifies that defect, and a correct one does not.

Each mock below implements one behaviour the study is designed to detect:

  CorrectSubstrate     computes the separation predicate properly
  PerExecutionOnly     evaluates each execution in isolation (the H1 failure)
  ParanoidGate         HOLDs on everything (the H5 failure)
  AliasedPredicates    correct decisions, but I2/I4/I7 share one evidence set
  MisattributingGate   right decision, wrong predicate blamed
  DefaultPermitGate    permits when ancestry is missing

These are test doubles for validating the instrument. They are never used in a
reported run, and no output from them is a finding about SCQOS.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone

from verifier.receipt import INVARIANTS, MIN_SEPARATION_SECONDS

PARENT_DIGEST = "parent-digest-fixture"


def _digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _parse(text: str) -> datetime:
    return datetime.strptime(text, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


def _predicates(failing: tuple[str, ...], evidence_by: dict | None = None) -> list[dict]:
    evidence_by = evidence_by or {}
    return [
        {
            "id": i,
            "result": "FAIL" if i in failing else "PASS",
            "evaluated_inputs": ["declared_state.collection_start"],
            "evidence": evidence_by.get(i, ["parent.collection_start"] if i in failing else []),
        }
        for i in INVARIANTS
    ]


def _receipt(case_id: str, state: dict, decision: str, predicates: list[dict],
             input_digest: str = "0" * 64) -> dict:
    return {
        "receipt_id": f"rcpt-{case_id}",
        "receipt_version": "1.0.0",
        "capability_id": "qec-syndrome-decode",
        "capability_version": "1.1.0",
        "policy_version": "mock",
        "state_digest": f"state-{case_id}",
        "parent_state_digest": PARENT_DIGEST if state.get("session_index", 1) > 1 else None,
        "input_digest": input_digest,
        "environment_digest": "1" * 64,
        "authority_reference": "hudson-forge",
        "genesis_reference": "rcpt-0001",
        "decision": decision,
        "predicates": predicates,
        "temporal_window": {"not_before": state.get("collection_start")},
        "output_digest": ("2" * 64) if decision == "PERMIT" else None,
        "proof_digest": "3" * 128,
        "declared_state": state,
    }


class _Base:
    """Shared plumbing: parse the artifact and know the parent's start time."""

    name = "mock"
    live = False  # a test double is never a substrate; see runner._run_one

    def __init__(self, parent_start: str):
        self.parent_start = _parse(parent_start)

    def _state(self, artifact_bytes: bytes) -> dict | None:
        if not artifact_bytes:
            return None
        return json.loads(artifact_bytes.decode("utf-8"))

    def _separation_ok(self, state: dict) -> bool:
        delta = (_parse(state["collection_start"]) - self.parent_start).total_seconds()
        return int(delta) >= MIN_SEPARATION_SECONDS

    def _ancestry_ok(self, state: dict) -> bool:
        return state.get("parent_receipt_id") == "rcpt-0001"


class CorrectSubstrate(_Base):
    """Evaluates the capability's declared predicate across executions."""

    name = "mock: correct"

    def submit(self, case_id, artifact_bytes, declared_digest=None):
        state = self._state(artifact_bytes)
        if state is None:
            return None
        actual = _digest(artifact_bytes)
        if declared_digest is not None and declared_digest != actual:
            return _receipt(case_id, state, "HOLD",
                            _predicates(("I6",),
                                        {"I6": ["declared input_digest", "recomputed digest"]}),
                            input_digest=declared_digest)
        if not self._ancestry_ok(state):
            return _receipt(case_id, state, "HOLD",
                            _predicates(("I2",), {"I2": ["parent_receipt_id unresolved"]}))
        if not self._separation_ok(state):
            return _receipt(case_id, state, "HOLD",
                            _predicates(("I1", "I2"),
                                        {"I1": ["temporal_window", "parent.collection_start"],
                                         "I2": ["lineage.parent_state_digest"]}))
        return _receipt(case_id, state, "PERMIT", _predicates(()))


class PerExecutionOnly(_Base):
    """The H1 failure: each execution judged in isolation, parent forgotten."""

    name = "mock: per-execution only"

    def submit(self, case_id, artifact_bytes, declared_digest=None):
        state = self._state(artifact_bytes)
        if state is None:
            return None
        # Every within-execution check passes, so everything is admitted.
        return _receipt(case_id, state, "PERMIT", _predicates(()))


class ParanoidGate(_Base):
    """The H5 failure: HOLDs on everything. Perfect on violations, useless."""

    name = "mock: paranoid (holds everything)"

    def submit(self, case_id, artifact_bytes, declared_digest=None):
        state = self._state(artifact_bytes)
        if state is None:
            return None
        return _receipt(case_id, state, "HOLD", _predicates(("I2",)))


class AliasedPredicates(_Base):
    """Correct decisions, but I2/I4/I7 are one predicate under three names."""

    name = "mock: aliased I2/I4/I7"

    def submit(self, case_id, artifact_bytes, declared_digest=None):
        state = self._state(artifact_bytes)
        if state is None:
            return None
        if self._ancestry_ok(state) and self._separation_ok(state):
            return _receipt(case_id, state, "PERMIT", _predicates(()))
        shared = ["lineage.parent_state_digest"]
        return _receipt(case_id, state, "HOLD",
                        _predicates(("I2", "I4", "I7"),
                                    {"I2": shared, "I4": shared, "I7": shared}))


class MisattributingGate(_Base):
    """Right decision, wrong reason — invisible to decision-level scoring."""

    name = "mock: misattributing"

    def submit(self, case_id, artifact_bytes, declared_digest=None):
        state = self._state(artifact_bytes)
        if state is None:
            return None
        if self._ancestry_ok(state) and self._separation_ok(state):
            return _receipt(case_id, state, "PERMIT", _predicates(()))
        return _receipt(case_id, state, "HOLD",
                        _predicates(("I5",), {"I5": ["boundary.resource_ceiling"]}))


class DefaultPermitGate(_Base):
    """Permits when ancestry cannot be resolved — the C07 failure."""

    name = "mock: default-permit on missing ancestry"

    def submit(self, case_id, artifact_bytes, declared_digest=None):
        state = self._state(artifact_bytes)
        if state is None:
            return None
        if not self._ancestry_ok(state):
            return _receipt(case_id, state, "PERMIT", _predicates(()))
        if not self._separation_ok(state):
            return _receipt(case_id, state, "HOLD", _predicates(("I1", "I2")))
        return _receipt(case_id, state, "PERMIT", _predicates(()))

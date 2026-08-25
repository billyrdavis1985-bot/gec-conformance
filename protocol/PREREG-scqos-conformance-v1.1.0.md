# Preregistration — Independent Conformance Test of a Governed-Execution Substrate

**protocol_id:** `gec-conformance`
**protocol_version:** `1.1.0`
**subject system:** SCQOS (SC-Engineering)
**capability under contract:** `qec-syndrome-decode v1.1.0`, contract digest recorded at freeze
**author:** Billy R. Davis Jr., Hudson Forge Technologies LLC
**status:** REGISTERED PRIOR TO EXECUTION — no case, prediction, or criterion below may be
edited after registration; changes are appended as dated deviations (§9)
**registration venue:** OSF (DOI recorded on registration)

---

## Revision note — 1.0.0 to 1.1.0

Tracks contract 1.1.0, in which the governing invariant became a minimum temporal
separation between sessions rather than a calibration-window-identity rule (contract
§5.1.1 records why). Neither version was registered and no case was executed, so nothing
is invalidated.

Case changes: C06 restated in terms of separation. Three cases added — C22 (near-boundary
violation), C23 (near-boundary compliance), C24 (stratification field must not trigger
HOLD). Declared set is now 24 cases; phase 1 grows from 8 to 11. The near-boundary pair
and the over-reach control were not constructible under the previous predicate, which is
part of why the new one is a better test article.

---

## 0. What this protocol is

A preregistered conformance protocol for systems that claim to govern execution by admitting
or holding state transitions against declared invariants. It is written to be reusable against
any such system. SCQOS is the first subject.

The design follows a controlled-corruption pattern: an independently authored capability is
executed through the substrate under a frozen contract, benign perturbations and deliberate
violations are injected, and the substrate's decision **and its stated reason** are compared
against predictions locked before execution.

**Why predictions are locked first.** Both parties want a particular outcome. Post-hoc
reasoning about whether a HOLD was "for the right reason" is unfalsifiable and both of us
would do it in good faith. Locking the predicted decision *and the predicted failing
predicate* removes that degree of freedom from both sides.

---

## 1. Object under test — pinning requirement

The subject system is under active development. Results are meaningless unless the object is
pinned. Before the first execution, the following are recorded and frozen:

| Item | Recorded value |
|---|---|
| SCQOS build digest | _(at execution)_ |
| Invariant-set / policy version | _(at execution)_ |
| Adapter stub version + digest | _(at execution)_ |
| Receipt schema version | _(at execution)_ |
| Canonicalization spec document digest | _(at execution)_ |
| Capability contract digest | _(from contract §11)_ |
| Decode table digest | _(from contract §11)_ |

If any pinned item changes mid-study, every completed case is either re-run against the new
pin or reported separately under the old pin. Silently mixing pins is treated as a failed
study, not a deviation.

---

## 2. Independence declarations

Recorded before execution so the independence claim is auditable rather than asserted:

1. The capability, contract, canonicalizer, verifier, and harness were authored without access
   to SCQOS source code.
2. The clean-room canonicalizer and receipt verifier were written **from the specification
   document alone**, whose digest is pinned in §1. Confirmed by commit history predating any
   access to SCQOS implementation.
3. The capability is not tuned to pass. Per SC-Engineering's explicit instruction, no change
   is made to the capability, contract, or inputs for the purpose of producing a PERMIT.
4. Where a case fails for reasons of unimplemented functionality rather than design, it is
   reported as such. "Not built yet" and "designed wrong" are different findings and are not
   merged.

---

## 3. Claims under test

Stated as SC-Engineering stated them, so the result is measured against the actual claim.

**H1 — Cross-execution continuity.** SCQOS carries Continuity across executions, not as an
isolated pre-execution check. A state that is locally valid but illegal only in relation to
its predecessor must HOLD — and a state that is compliant by two minutes must not.

**H2 — Mediating enforcement.** SCQOS is out-of-process mediating, not advisory. A capability
inside the governed boundary possesses no alternate execution lane; an undeclared consequence
is a governance violation.

> Noted for the record: the claim as stated was that SCQOS is *intended to be* mediating.
> H2 tests the running system, and a negative result may indicate an unimplemented mechanism
> rather than a rejected design. §2.4 applies.

**H3 — Predicate independence.** I1–I8 are eight invariants, not fewer wearing eight names.
Specifically, I2 Continuity, I4 Genesis, and I7 Causality are operationally distinct.

**H4 — Verification independence.** The receipt is independently verifiable: canonicalization
is specified precisely enough that a clean-room implementation produces byte-identical output.

> **Interpretation limit, recorded before execution.** If the frozen specification names a
> published standard (RFC 8785, RFC 7493, RFC 3339, RFC 8032), agreement between two
> implementations of that standard is **weak evidence**: it shows a standard was adopted, not
> that the specification is precise. Bespoke rules are where divergence is informative. A
> post-freeze convergence result must not be reported as though it were the same finding as
> convergence against bespoke rules.
>
> A second consequence: any rebuild after round one is **not clean-room in the round-one
> sense**. The implementer retains the prior implementation and knowledge of which readings
> were chosen at each open point. The informative test after a freeze is therefore not
> "do two implementations agree" but **"does the frozen universe eliminate the specific
> degrees of freedom found in round one"** — asserted by the spec-closure check, which
> requires that the two round-one readings can no longer both satisfy it.
>
> Convergence is also not correctness. Agreement through the chain proves agreement on
> representation; it does not show the governance model is right. C22 and C23 could converge
> on every byte and both be permitted. The case matrix remains the substantive test.

**H5 — Selectivity.** The gate discriminates. It does not achieve its violation-detection rate
by holding broadly.

**H6 — Socket generality.** An externally authored contract is accepted without manual
bridging by either party.

---

## 4. Primary and secondary outcomes

**Primary — predicate-level agreement.** For each case: does the observed failing predicate
match the predicted failing predicate? Decision-level agreement is secondary, because a system
can reach the right decision by the wrong route and decision-level scoring cannot tell.

**Secondary:**

- Decision-level confusion matrix (PERMIT / HOLD / TERMINATE × predicted).
- **False-positive rate on negative controls.** Reported alongside true-positive rate in every
  summary, without exception. A gate that HOLDs on everything scores perfectly on violations
  and is worthless; any report omitting the FP rate is incomplete.
- **Aliasing co-fire matrix.** Across all lineage-violation cases, the joint firing pattern of
  I2 / I4 / I7, together with their evaluated inputs and evidence payloads.
- Bridging ledger: every manual intervention required to make the integration work, itemized.
- Byte-level agreement between clean-room and SCQOS canonicalization.

---

## 5. Case matrix — 21 cases, predictions locked

Predicted decision and predicted failing predicate are fixed at registration. Phase 1 cases
are marked ●; the remainder are declared here and deferred, so that the executed subset cannot
be read as post-hoc selection.

### 5.1 Negative controls — must PERMIT (5)

| ID | Case | Predicted | Predicate |
|---|---|---|---|
| ● C01 | Clean session 2: new calibration window, valid parent, matching digests | PERMIT | none fail |
| ● C02 | Benign perturbation: an irrelevant, non-material metadata field altered | PERMIT | none fail |
| C03 | Non-semantic reordering of fields in the declared input | PERMIT | none fail |
| C04 | Session 3 following a session 2 that was HELD and legitimately requalified | PERMIT | none fail |
| ● C05 | Serialization variance pair: identical semantics, differing byte encoding | PERMIT both, **identical decision and identical digest** | none fail |
| ● C24 | `calibration_stratum` = "stale", separation compliant | PERMIT | none fail |

C24 is an over-reach control. `calibration_age_hours` and `calibration_stratum` are
declared in the contract and bound by the receipt but are explicitly **not** admission
predicates (contract §5.1.2). A HOLD here means the substrate is gating on a field the
contract did not make material — a failure mode distinct from missing a real violation,
and one that no violation-detection case can surface.

C05 is simultaneously the canonicalization test (H4) and a negative control (H5).

### 5.2 Continuity and lineage (7)

| ID | Case | Predicted | Predicate |
|---|---|---|---|
| ● C06 | Session 2 collected 3h after session 1, well inside the 12h minimum | HOLD | I2 and/or I1 |
| ● C07 | Declared parent receipt absent from governance state | HOLD | I2 |
| C08 | Session 2 submitted claiming fresh genesis, no parent declared | HOLD | I4 |
| ● C09 | Two executions submitted concurrently against the same parent | exactly one PERMIT, one HOLD-or-re-evaluate | I2 (+I1) |
| C10 | Session 1's contract and inputs replayed as session 2 | HOLD | I2, I6 |
| C11 | Fabricated ancestry: a self-asserted session-1 record claimed as parent | HOLD | I4, I6 |
| C12 | Content-address collision: byte-identical declared state as a distinct session | HOLD | I2, I6 |
| ● C22 | Near-boundary violation: separation of 11h59m | HOLD | I2 and/or I1 |
| ● C23 | Near-boundary compliance: separation of 12h01m, otherwise identical to C22 | PERMIT | none fail |

C22 and C23 are a matched pair differing by two minutes of declared time. They are the
sharpest instrument in the matrix: a gate that HOLDs on both is not evaluating the
predicate, only reacting to the shape of the input, and a gate that PERMITs both is not
evaluating it either. Only a correct split on this pair demonstrates that the substrate
computes the capability's rule rather than pattern-matching a violation.

Both target I2 Continuity and I1 Time jointly, since the predicate is temporal. Which
predicate the receipt reports as failing is scored, not assumed — see H3.

C11 tests a surface introduced by the answer to blocker 2. Lineage state being persistent and
content-addressed protects retrieved records from tampering; it says nothing about what may be
*asserted at write time*. If a capability can populate its own ancestry, continuity is only as
strong as the initial authority check.

C12 probes whether session identity is content-derived or independently assigned. If
content-derived, a legitimate identical re-run and a replay are indistinguishable.

### 5.3 Reference and alignment (4)

| ID | Case | Predicted | Predicate |
|---|---|---|---|
| ● C13 | Declared input digest does not match actual input bytes | HOLD | I6 |
| C14 | Contract version incremented mid-execution | HOLD | I3, I6 |
| C15 | Decode table substitution: table X declared, table Y executed | HOLD | I3, I6 |
| C16 | Retry re-parenting: after losing C09, is the loser silently re-parented to the winner's state? | HOLD, or PERMIT only with the new parent explicitly declared and re-admitted | I3 |

C16 follows from the answer to blocker 3. "The other must re-evaluate against the new present
state" means the loser retries rather than fails. If it then succeeds as a successor of a
lineage it never declared, execution has drifted from what was authorized — an Alignment
failure, not a Continuity one.

### 5.4 Boundary and enforcement (3)

| ID | Case | Predicted | Predicate |
|---|---|---|---|
| ● C18 | Consequence emitted with no admission request at all | detected; HOLD or TERMINATE | enforcement, I5 |
| C17 | Capability writes a second artifact outside declared outputs | HOLD or TERMINATE | I5 |
| C19 | Declared resource ceiling exceeded (wall clock or memory per contract §5.2) | HOLD or TERMINATE | I5 |

C18 is the load-bearing test for H2 and is the cheapest case in the matrix. If an undeclared
consequence emitted without requesting admission goes undetected, then "no alternate execution
lane" does not hold in the running system, and every downstream claim about provable
boundaries is conditional on capability cooperation. That is a legitimate scope for a
governance system — it is not the scope currently claimed.

### 5.5 Time and accountability (2)

| ID | Case | Predicted | Predicate |
|---|---|---|---|
| C20 | Admission presented outside its declared validity window | HOLD | I1 |
| C21 | Authority resolves and is unrevoked; withdrawal channel unreachable | HOLD | I8 / Accountability |

C21 tests the distinction SC-Engineering accepted: authority must remain attributable,
challengeable, and **withdrawable**, not merely cryptographically present. A PERMIT here means
the predicate checks key presence. This is a scope finding about the trust model rather than a
defect claim, and is reported that way.

### 5.6 Declared but out of scope

The signed-discontinuity escape — an authority declaring an authorized discontinuity to clear
a HOLD — is **not tested**, and the reason is recorded here rather than omitted. The answer to
blocker 4 makes it legitimate by design, so a PERMIT would not be a finding. What it
establishes is a scope boundary worth stating in SCQOS documentation: **SC constrains
capabilities, not authorities.** Holders of authority can lawfully clear a HOLD; software
inside the boundary cannot. That is a common and defensible trust model. It is narrower than
the surrounding language implies.

---

## 6. Phase structure

**Phase 1 (11 cases):** C01, C02, C05, C06, C07, C09, C13, C18, C22, C23, C24.

Chosen for coverage of every hypothesis at least once, and for cost. C09 and C18 were promoted
from the deferred set after the answers to blockers 1 and 3 made them directly falsifiable.
C22/C23 and C24 enter with contract 1.1.0 and are cheap: they reuse the C06 fixture with
one field altered.

**Phase 2 (14 cases):** the remainder, executed on the same pin or on a newly recorded pin per §1.

Phase 1 results are published whether or not phase 2 occurs. Phase 2 is not a condition of
reporting.

---

## 7. Falsification criteria

Fixed in advance. Each is a single-case criterion; no aggregate score can rescue a failed one.

| Claim | Falsified if |
|---|---|
| H1 | C06 returns PERMIT, **or** C22 and C23 receive the same decision |
| H2 | C18 goes undetected, or C17/C19 produce their consequence before any HOLD |
| H3 | I2, I4 and I7 co-fire on 100% of C06–C12 with substantively identical evidence payloads |
| H4 | Clean-room and SCQOS canonicalization disagree on any byte in C05 |
| H5 | Any negative control (C01–C05) returns HOLD |
| H6 | The contract requires manual bridging by either party to be accepted |

**H3 note.** Co-firing alone is not proof of aliasing; a single event can legitimately violate
several invariants. The evidence payloads are what decide it. If I2, I4 and I7 always fire
together *and* always cite the same evaluated inputs, they are one predicate under three
names. If they cite different evidence, they are distinct and the criticism is withdrawn.

---

## 8. Execution and reporting protocol

1. Register this document; record the DOI.
2. Pin every item in §1; publish the pin table.
3. Execute phase 1 in the order listed. No case is re-run to obtain a different result; every
   run is recorded, including infrastructure failures.
4. Verify every receipt with both verifiers; record byte-level agreement.
5. Report the predicate-level matrix, the decision-level matrix, the false-positive rate, the
   aliasing co-fire matrix, and the bridging ledger.
6. Publish regardless of outcome. Negative results are published in the same venue, at the same
   length, on the same timeline as positive ones.

**Non-repair rule.** Defects in the subject system encountered during execution are logged as
findings and not fixed by the author. Diagnosing SCQOS is outside the declared scope of this
work, and repairing it mid-study would destroy the independence claim in §2.

---

## 9. Deviations

Any departure from this protocol is appended below with date, description, and reason, before
the affected result is reported. Deviations are not edits: no line above is altered.

_(none at registration)_

**D-1 — 2026-08-25 — Stage B parent and successor sourced from published QEC-P1 sessions.**

At registration the fixture parent was a labelled stub, and Stage B of the freeze was
recorded PROVISIONAL. Stage B is now FROZEN against collected data.

The parent is published session 11 and the compliant successor is published session 12,
both on ibm_marrakesh, from the QEC-P1 study (Zenodo concept DOI 10.5281/zenodo.22050536).
Their collection times are separated by 13.74 hours — a real separation produced by queue
scheduling, not constructed — which satisfies the contract's ≥12h admission predicate
without adjustment.

Consequence for the case set: C01, the primary negative control, is now real end to end —
collected parent, collected successor, real separation, real syndrome data, real decode.
The violating cases (C06 at 3h, C22 at 11h59m) remain synthetic successors constructed
from the collected parent, because no collected pair exists at those separations and none
should be manufactured on hardware to create one. Every synthetic artifact is labelled in
its own bytes and asserted by test.

Two properties of the source data are recorded because they bound what the conformance
study can claim, and neither affects it. First, both sessions ran under one frozen
calibration cycle, so the calibration window identifier is identical across them; this is
why C24's stratification values are set explicitly rather than derived. Second, an earlier
pilot session on a different backend is not pooled with this series and is not used here.

No hypothesis, case, prediction, or falsification criterion is altered by this entry.

---

## 10. Publication

- Preregistration: OSF, with DOI, prior to execution.
- Protocol, harness, canonicalizer, verifier: author's repository under the author's license.
- Results: published in full, positive or negative, per the terms of record in contract §12.

The protocol is intended to be reusable against any system claiming governed execution. SCQOS
is its first subject, and its value does not depend on the outcome of that first test.

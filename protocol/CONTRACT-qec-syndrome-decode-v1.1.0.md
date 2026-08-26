# Capability Execution Contract

**capability_id:** `qec-syndrome-decode`
**capability_version:** `1.1.0`
**contract_version:** `1.1.0`
**contract_status:** FROZEN — see §11; no field may change without a version increment
**supersedes:** `1.0.0` (unfrozen, unpublished, never executed against)
**author:** Billy R. Davis Jr., Hudson Forge Technologies LLC
**authored_independently_of:** SC-Engineering / SCQOS
**date_frozen:** 2026-08-25T21:44:34Z
**contract_digest:** `b7b90b9c42de057c6abbbb911f97d1d2dbc5108be51297d71b509a7ed5d2d17f`

---

## Revision note — 1.0.0 to 1.1.0

The governing invariant in §5.1 changed from a calibration-window-identity rule to a
minimum temporal separation between sessions, with the calibration fields demoted to
declared-but-not-admitted stratification. §3.1 gains `collection_start`,
`calibration_age_hours`, and `calibration_stratum`, and pins a timestamp format.

Version 1.0.0 was never frozen, never registered, and no execution was performed against
it. This revision therefore invalidates nothing. It is recorded rather than silently
applied because the reason for the change — that a published calibration timestamp is a
weak proxy for hardware state — is itself relevant to what the substrate is being asked
to enforce. See §5.1.1.

---

## 0. Purpose and standing of this document

This contract is authored outside SC-Engineering and frozen before integration. It exists to
test a specific claim: that an independently created capability can plug into the SCQOS
governed substrate without rewriting its core, and that SCQOS enforces the capability's own
declared invariants across executions rather than only its internal ones.

Two consequences follow, and both are deliberate:

1. **The shape of this contract was not designed by SC-Engineering.** If the adapter cannot
   accept it without manual bridging, that is a finding about the socket, not a defect in this
   document. Required changes must be recorded as adapter findings, not as silent edits here.
2. **The governing invariant under test (§5.1) belongs to the capability, not to SCQOS.**
   It is a methodological rule from the QEC-P1 experimental protocol — a minimum temporal
   separation between collection sessions. SCQOS is being asked to carry a rule it did not
   author, across executions it does not own, using a predicate that spans two of its own
   invariants. That is the substance of the test.

This document is the sole normative description of the capability. Where it disagrees with
any conversation, message, or later summary, this document governs.

---

## 1. Capability identity

| Field | Value |
|---|---|
| `capability_id` | `qec-syndrome-decode` |
| `capability_version` | `1.1.0` |
| `implementation_digest` | SHA-256 of the frozen source tree tarball (§11) |
| `decode_table_digest` | SHA-256 of the canonical decode table artifact |
| `runtime` | Python 3.11, standard library only |
| `determinism_class` | STRICT (§4) |
| `owner` | Hudson Forge Technologies LLC |
| `license` | capability source and decode table remain the property of the author |

---

## 2. Governing intent

Decode syndrome measurement records from a completed distance-`d` repetition-code experiment
into logical error counts, deterministically and offline, such that the decode result is
reproducible byte-for-byte by any party holding the input artifact and the decode table.

The capability performs **no quantum execution**. It reads already-committed measurement
records. This is a deliberate design choice: a live quantum job is non-reproducible by
construction, and the reproduction criterion under test requires that identical declared
inputs yield identical evidence.

Intent is fixed for the lifetime of `contract_version 1.0.0`. Any execution whose observed
behavior is not fully described by this section constitutes drift and is expected to be
refused under I3 Alignment.

---

## 3. Inputs and outputs

### 3.1 Declared input

Exactly one input artifact, referenced by content digest. No other input of any kind is
declared, including environment variables, configuration files, clocks, and network responses.

```yaml
input:
  artifact_id: qec_session_record
  reference: content_digest            # SHA-256, resolved canonically
  media_type: application/json
  count: 1                             # exactly one; not "at least one"
  schema:
    session_index:          integer    # 1-based, monotonic within lineage
    backend_id:             string     # e.g. "ibm_fez"
    collection_start:       string     # RFC 3339, UTC, second precision, "Z" suffix
    calibration_window_id:  string     # published calibration timestamp at collection time
    calibration_age_hours:  number     # collection_start minus calibration_window_id, hours
    calibration_stratum:    string     # "fresh" | "stale", derived per §5.1.2
    code_distance:          integer
    rounds:                 integer
    shots:                  integer
    syndrome_records:       array[string]   # fixed-width bitstrings, length = rounds*(d-1)
    parent_receipt_id:      string|null     # null permitted only for session_index == 1
```

`collection_start` is **material** to admission and carries the separation predicate.
`calibration_window_id` and `calibration_age_hours` are material to stratification but
**not** to admission. See §5.1 for why the two are separated.

`collection_start` format is fixed here because the invariant is temporal: two encodings
of the same instant must not produce two different admission results. RFC 3339, UTC,
second precision, literal `Z`. No offset forms, no sub-second digits.

### 3.2 Declared output

Exactly one output artifact. Not "one or more."

```yaml
output:
  artifact_id: qec_decode_summary
  media_type: application/json
  count: 1
  schema:
    capability_version:     string
    decode_table_digest:    string
    input_digest:           string
    session_index:          integer
    logical_error_count:    integer
    shots:                  integer
    defects_per_round:      array[integer]
    decode_status:          string     # "complete" only; no partial results
```

The output contains **no timestamp, no hostname, no path, no duration, and no floating-point
value.** This is required for the determinism guarantee in §4 and is not negotiable within
this contract version.

### 3.3 Declared error artifact

On internal failure the capability emits one error artifact instead of the output artifact.
It is declared in advance so that its emission is not itself an undeclared consequence.

```yaml
error_output:
  artifact_id: qec_decode_error
  media_type: application/json
  count: 0..1                          # mutually exclusive with qec_decode_summary
  schema:
    capability_version: string
    input_digest:       string
    error_class:        string         # enumerated set, fixed at freeze
```

---

## 4. Determinism guarantees

The capability is **STRICT** deterministic. Given identical input bytes and an identical
decode table, it produces identical output bytes on any conforming runtime.

- No random number generation, seeded or otherwise.
- Integer arithmetic only. No floating point anywhere in the decode path or the output.
- No dependence on dictionary, set, or filesystem iteration order.
- No locale, timezone, or encoding dependence; all I/O is UTF-8, all sorting is bytewise.
- No wall-clock, monotonic clock, or process metadata reaches the output.
- Decode is a fixed lookup table keyed by syndrome pattern, pinned by `decode_table_digest`.
  Table lookup is total: every possible syndrome pattern has an entry. There is no fallback
  branch, and therefore no untested path.

**Verification obligation.** Any party may re-run the capability against the input artifact
and compare `qec_decode_summary` byte-for-byte. Divergence falsifies this section and is a
finding against the capability, not against SCQOS.

---

## 5. Boundaries

### 5.1 Lineage boundary — the invariant under test

#### 5.1.1 The admission predicate

For any execution with `session_index = N` where `N > 1`:

```
REQUIRED: collection_start(N) - collection_start(N-1) >= 12 hours
```

Computed over instants, not calendar fields. Both operands are the `collection_start`
values declared in the respective admitted states.

**Rationale.** Sessions collected too close together are not statistically independent:
they share hardware conditions, and treating them as independent replicates is
pseudoreplication. The consequence is methodological, not cosmetic — the experiment
produces a wrong number that looks like a right number.

**Why a temporal separation and not a calibration-window change.** An earlier revision of
this contract used `calibration_window_id(N) != calibration_window_id(N-1)`. That
predicate was superseded, and the reason is recorded here rather than quietly dropped,
because it bears on what the substrate is being asked to enforce.

The published calibration timestamp turned out to be a weak proxy for hardware state. The
device under study is a Heron r2 processor running continuous mitigation: it self-adjusts
while its published metadata stays fixed. During collection, an observed freeze held the
published timestamp constant for roughly 83 hours across multiple backends — well beyond
the 60.6-hour maximum in an archive of 707 hourly snapshots whose median gap is 1.2 hours.
The vendor separately documents that a failed benchmarking run may be reported as an
error value of exactly 1.0, meaning *undefined* rather than *catastrophic*.

So a window-ID change is neither necessary nor sufficient for independence. Elapsed time
is the weaker but honest proxy, and it is the one the replication unit now rests on.

**Why this makes a better test article.** Three properties, each of which the previous
predicate lacked:

1. It engages **two** invariants jointly. The predicate is temporal, so I1 Time is
   implicated alongside I2 Continuity. If the receipt attributes a violation to only one,
   that is informative about predicate separation (see preregistration H3).
2. It cannot be satisfied by editing a field. An opaque window ID is whatever the
   declaring party says it is; a timestamp is checkable against the receipt's own
   temporal window and against the parent's declared value.
3. It admits a **near-boundary** case. A separation of 11h59m is a violation and 12h01m
   is not, from otherwise identical inputs. A gate that HOLDs on both is not evaluating
   the predicate, merely reacting to the shape of the input.

**Why this is the test.** The violating execution is *locally valid*. Session N in
isolation satisfies every within-execution check: its input digest resolves, its schema
validates, its decode completes, its output is well-formed. It is illegal only in relation
to session N-1.

A per-execution admission gate that does not retain session N-1 will PERMIT. SCQOS claims
to carry Continuity across the lifecycle rather than performing an isolated pre-execution
check. Under that claim, the required decision is **HOLD**.

#### 5.1.2 Stratification fields — declared, not admitted

```
calibration_stratum := "stale" if calibration_age_hours >= 24 else "fresh"
```

`calibration_age_hours` and `calibration_stratum` are carried in the input artifact and
bound by the receipt, but they are **not** admission predicates. No value of either
causes HOLD.

They are declared for a reason that matters to this test: they establish that a field can
be *material to the experiment* without being *material to admission*. A substrate that
holds on a stratification field is over-reaching; one that fails to bind it in the receipt
is under-recording. Both are findings, and neither is visible unless the distinction is
declared in advance.

Any sensitivity analysis over these strata belongs to the experimental protocol, not to
this contract, and is out of scope for the conformance study.

#### 5.1.3 Additional lineage requirements

```
REQUIRED: parent_receipt_id resolves to an admitted receipt of the same capability_id
REQUIRED: session_index(N) == session_index(parent) + 1
REQUIRED: backend_id(N) == backend_id(parent)
REQUIRED: parent_receipt_id is null if and only if session_index == 1
```

### 5.2 Resource boundary

```yaml
boundaries:
  filesystem_read:   [declared input artifact by digest]
  filesystem_write:  [declared output artifact path, exactly once]
  network:           none                  # no egress, no ingress, no DNS
  subprocess:        none
  wall_clock_max:    60s
  memory_max:        512MiB
  concurrency:       1                     # single execution per lineage at a time
```

Anything not enumerated here is undeclared. Per SC-Engineering's stated model, an undeclared
consequence is a governance violation, and the capability possesses no alternate execution
lane. §5.2 is the surface on which that claim is tested.

### 5.3 Authority boundary

Execution authority is scoped to a single admitted state. It does not extend to the successor
session, and it is not renewed by the completion of this execution. Session N+1 requires its
own admission and its own receipt.

---

## 6. Expected consequence

A single admitted execution produces exactly:

1. one `qec_decode_summary` artifact (or one `qec_decode_error` artifact), and
2. one verifiable receipt binding the input digest, the output digest, and the parent receipt.

Nothing else. No cache is populated, no index is updated, no notification is emitted, no
state outside the declared output is mutated. If any additional consequence is observed, the
boundary claim in §5.2 has failed regardless of what the receipt says.

---

## 7. Failure behavior

| Condition | Required behavior |
|---|---|
| HOLD at admission | No execution. No output artifact. No partial write. Receipt records HOLD and the failing predicate(s). |
| HOLD mid-execution | Execution authority drops to zero at the transition boundary. No further consequence. Last coherent state and evidence preserved. |
| Internal capability error | One `qec_decode_error` artifact, no `qec_decode_summary`. |
| Post-HOLD | No silent resume. Requalification requires a new governance event producing a new receipt, or TERMINATE. |
| Ambiguity | HOLD. The capability declares no permissive default anywhere. |

**Partial output is never valid.** `decode_status` has exactly one legal value.

---

## 8. Admission and receipt requirements

### 8.1 Admission

The capability requests admission at the governed transition boundary before any declared
consequence. It does not proceed on timeout, on error, or on an unparseable response. Absence
of a decision is treated as HOLD.

### 8.2 Receipt requirements

Per SC-Engineering's stated minimum, plus one addition agreed in correspondence:

`receipt_version`, execution/capability identity, invariant-set/policy version, current and
parent state digests, canonical input/environment/reference digests, authority/genesis
reference, `decision ∈ {PERMIT, HOLD, TERMINATE}`, timestamp and temporal window,
output/consequence digest, final proof digest and signature.

**Addition — per-predicate exposure.** The receipt must expose each of I1–I8 independently,
each carrying: the predicate result, the evaluated inputs, and the evidence relied upon.
An aggregate decision alone is insufficient for this test. Scoring is at predicate level
(see the preregistration, §H3), because a system can reach the correct decision by the wrong
route, and decision-level agreement cannot distinguish the two.

### 8.3 Independent verification

Verification means: reconstruct the canonical bytes, recompute the digests, validate the
signer and authority, and confirm that the decision follows from this frozen contract.

The verifier used in this study is **written clean-room from the SCQOS receipt and
canonicalization specification, without reading SCQOS source.** The hash of the specification
document it was written from is recorded in the preregistration. If the clean-room verifier
and the SCQOS verifier disagree on any byte, the receipt is not independently verifiable and
the canonicalization rules are underspecified.

**Open specification items required before freeze of the adapter stub** — each of these must
be pinned or a clean-room implementation cannot exist:

- object key ordering rule
- Unicode normalization form
- integer vs. string encoding for numeric fields
- floating-point representation, if any field admits one
- timestamp precision and timezone encoding
- empty value vs. absent key
- line ending and trailing newline treatment
- digest algorithm, encoding (hex vs. base64), and case

---

## 9. Reproducibility instructions

Reproduction of the **governance experiment**, per the narrowed criterion agreed in
correspondence: identical declared inputs, policy version, and canonicalization must yield the
same admissibility logic, decision semantics, and independently verifiable evidence. The
reproducer does not need SC-Engineering, the author, or any live quantum device.

0. Note that admission depends on `collection_start` values in two artifacts (this
   session and its parent). A reproducer must obtain both, or the parent's receipt.
1. Obtain the input artifact by digest.
2. Obtain the capability source tree and decode table by digest; verify both.
3. Run the capability offline; confirm `qec_decode_summary` matches byte-for-byte.
4. Obtain the receipt; verify it using an independently written verifier.
5. Confirm the recorded decision follows from this contract and the pinned invariant-set version.

Success criterion, as stated by SC-Engineering: a second engineer completes steps 1–5 from
the contract and evidence alone, with no manual bridging by either party.

---

## 10. Scope limits — what this contract does not claim

Stated so that neither party over-reads the result later:

- It does not claim the capability is correct as physics. It claims the decode is deterministic.
- It does not claim a fresh quantum run would be admitted. Governance replay operates over
  recorded evidence.
- It does not test SCQOS against a malicious *operator*, only a misbehaving *capability*.
  Authority-level escape is examined separately (preregistration case C21) and is a question
  about the trust model, not a defect claim.
- It does not certify SCQOS for any production, safety, or compliance use.

---

## 11. Freeze procedure

At freeze, the following are computed and recorded, and this document becomes immutable:

```
implementation_digest = SHA-256(capability source tree tarball, reproducible build flags)
decode_table_digest   = SHA-256(canonical decode table artifact)
contract_digest       = SHA-256(canonical bytes of this document, §11 digest lines blanked)
```

Canonicalization of this document for digest purposes: UTF-8, LF line endings, single
trailing newline, no trailing whitespace on any line.

Any change to any field after freeze requires `contract_version 1.0.1` or higher and
invalidates every result obtained under `1.0.0`. Results are reported against the contract
digest, never against "the contract."

---

## 12. Terms of record

- Capability source, decode table, experimental data, canonicalizer, verifier, and test
  harness remain the property of the author.
- Adapter, execution contract, and resulting receipt/proof artifacts may be used by
  SC-Engineering.
- The author retains the right to publish findings, positive or negative.

_(Agreed in correspondence between B. Davis and E. Robles, August 2026.)_

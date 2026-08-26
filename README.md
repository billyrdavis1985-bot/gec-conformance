# gec-conformance

**A preregistered conformance protocol for governed-execution claims.**

[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.22103548.svg)](https://doi.org/10.5281/zenodo.22103548)
OSF preregistration: [10.17605/OSF.IO/XNC43](https://doi.org/10.17605/OSF.IO/XNC43) · License: MIT

Systems that claim to govern execution — admitting or holding state transitions
against declared invariants — are hard to evaluate honestly. Both the evaluator
and the system's authors have an interest in the outcome, and both can reason
after the fact about whether a decision was made *for the right reason*.

This protocol removes that freedom. An independently authored capability runs
through the substrate under a contract frozen and hashed in advance. Benign
perturbations and deliberate violations are injected. The substrate's decision
**and its stated reason** are compared against predictions locked before
execution and registered publicly.

Two scoring commitments follow from that, and both are enforced in code rather
than left to the person writing the report:

- **Predicate-level agreement is primary.** A system can reach the correct
  decision by the wrong route; decision agreement cannot tell the difference.
  A mock substrate that blames the wrong invariant scores 8/9 on decisions and
  5/9 on predicates.
- **False-positive rate is reported unconditionally.** A gate that holds on
  everything catches every violation and is worthless. `summary()` cannot be
  called in a way that omits it.

The subject of the first application is SCQOS (SC-Engineering). The governing
invariant under test belongs to the *capability*, not the substrate: a minimum
temporal separation between experimental collection sessions, drawn from a
quantum error-correction protocol. The substrate is asked to carry a rule it did
not author, across executions it does not own.

The protocol is reusable against any system making governed-execution claims.
Its value does not depend on the outcome of that first application.

## Status

Two specification-boundary findings are recorded and accepted by the subject
system's author: [CANON-01](FINDINGS-CANON-01.md) (the specification admitted
multiple faithful implementations — 9 of 33 corpus cases diverged between two
honest readings) and [CANON-02](FINDINGS-CANON-02.md) (no signature algorithm or
key format specified, so one of four verification steps cannot be performed).

Both freeze stages are complete. Execution is pending the subject system's
frozen representation layer, signature profile, adapter contract, and pin table.

---

## Why the canonicalizer exists

A receipt asserts `input_digest = abc123…`. Verifying that independently means
hashing the input yourself and comparing. But hashing needs bytes, and the same
structured value has many valid byte representations. Canonicalization is the
rule that collapses structure to exactly one byte sequence.

The failure this rig detects: **if a producer and a verifier share a
canonicalization library, a defect in it is invisible.** Both sides make the
same mistake, the digests match, the receipt validates cleanly against a wrong
reading of the input, and nothing inside the system can notice. Only a second
implementation — written from the specification rather than from the code — can
find it.

That is why the specification, not the reference implementation, is what gets
requested, and why the implementation is committed and hashed before any
comparison. A disagreement is only a finding if it was reached without looking.

## Architecture

    capability/        qec-syndrome-decode 1.1.0 — deterministic offline decode
      table.py         total decode table, exhaustive matching, integer weights
      decode.py        the capability itself
    verifier/
      receipt.py       clean-room receipt verifier (signature step blocked)
    harness/
      fixtures.py      phase 1 fixtures — real parent, synthetic successors
      runner.py        execution and scorecard
      mocks.py         substrates with known defects, for validating the harness
      divergence.py    first-divergence locator — halts at the first unequal stage
    canon/
      ruleset.py       decisions as explicit configuration — no defaults anywhere
      numbers.py       ES6 Number::toString (ECMA-262 6.1.6.1.20)
      engine.py        rule-agnostic serializer + strict JSON parser
      rulesets/        concrete rulesets: JCS baseline + bespoke variants
      corpus.py        adversarial differential corpus
      differ.py        runner, grouped by specification question

The engine holds **no canonicalization policy**. A canonicalizer written
directly against one specification cannot test that specification, because its
assumptions and the spec's are the same object. Separating engine from ruleset
makes an incoming specification a config file rather than a rewrite, and makes
differential comparison possible at all.

`Ruleset` has no default values. An unstated rule is the exact failure mode this
tool exists to detect, so the tool must not silently supply one of its own.
Where a source specification is silent, record it in `assumed_fields` — the gap
is a finding, not something to decide on their behalf.

## The eight specification questions

Every field on `Ruleset` corresponds to a question a canonicalization spec must
answer. Silence on any one of them means two competent implementations can
diverge without either being wrong:

| Question | Field | Discriminating case |
|---|---|---|
| Key ordering | `key_order` | ORD-01 — UTF-16 surrogates sort below U+E000, UTF-8 above |
| Unicode normalization | `unicode_form` | UNI-01, UNI-02 — decomposed forms, compatibility characters |
| Number representation | `number_format` | NUM-01, NUM-02, NUM-04 — integer floats, 1e21 boundary, negative zero |
| Integer precision | `bigint_policy` | INT-01, INT-02 — values beyond 2^53 |
| Empty / null / absent | `absent_null` | NUL-01…03 — the three-way distinction JSON cannot express |
| String escaping | `string_escaping` | ESC-01, ESC-02, ESC-04 | 
| Whitespace and line endings | `line_ending`, `indent`, `trailing_newline` | any case, under `pretty_sorted` |
| Digest algorithm and encoding | `digest_algorithm`, `digest_encoding` | identical bytes, different digest string |

## The corpus

30 cases, each targeting one question, each built so two plausible answers
produce different bytes. Cases where every reasonable ruleset agrees are
excluded on purpose: they inflate the pass rate and prove nothing.

`test_high_value_cases_actually_diverge_somewhere` enforces this — a case tagged
high-value that no ruleset pair distinguishes is a mislabelled case and fails
the build.

## Usage

    python3 -m unittest discover -s tests     # 158 tests
    python3 -m unittest tests.test_rfc8785_vectors -v   # official RFC vectors
    python3 cli.py rulesets                   # every ruleset and its decisions
    python3 cli.py corpus --high-value        # the discriminating cases
    python3 cli.py diff jcs nfc_utf8_ascii -v # differential run
    echo '{"b":1,"a":2}' | python3 cli.py emit jcs --stdin

Exit code 1 from `diff` means at least one divergence, so it works in CI.

## Reading a result

Against a specification that names a standard, agreement is expected and is
**weak evidence**: it shows they picked a standard, not that their spec is
precise. Bespoke rules are where divergence is likely and where each one is a
real interoperability defect. This distinction is recorded in the
preregistration under H4 so that a pass cannot be over-claimed after the fact.

A divergence maps to the specification question that produced it, so the finding
reads as "the spec is silent on Unicode normalization form" rather than "17
cases failed."

## Known properties, recorded rather than hidden

- **NUM-06**: `1` and `1.0` share a canonical form under RFC 8785. Two
  semantically different documents therefore share a digest. This is a property
  of the standard, not a defect here, and it is tested explicitly.
- `bigint_policy=IEEE754_COERCE` is this implementation's reading of RFC 8785's
  ES6 number model. A spec that means something else must say so.
- The strict parser rejects duplicate keys rather than taking last-wins. The
  standard library parser silently discards them *before* canonicalization can
  see them, so a default-parser verifier cannot detect a producer that exploited
  the ambiguity.

## Baseline validation

The JCS ruleset passes RFC 8785's own published vectors: all 24 finite Appendix B
number samples, both non-finite refusals, the Section 3.2.3 UTF-16 property
sorting test, and the Section 3.2.4 byte-exact end-to-end example. A deliberately
broken renderer using the platform float repr fails 10 of the 24, so the harness
discriminates rather than passing vacuously.

This matters for attribution: a divergence found against a subject specification
can be charged to that specification rather than to a defect in the baseline.

## Harness validation

The scorecard is validated against six mock substrates with known behaviour,
because a clean phase 1 result is uninterpretable unless the instrument is known
to discriminate. Each defect produces a distinguishable signature:

| Mock | Predicate | Decision | TP | FP |
|---|---|---|---|---|
| correct | 9/9 | 9/9 | 4/4 | 0/5 |
| per-execution only (H1 failure) | 5/9 | 5/9 | 0/4 | 0/5 |
| paranoid, holds everything (H5) | 3/9 | 4/9 | 4/4 | 5/5 |
| misattributing (right decision, wrong predicate) | 5/9 | 8/9 | 3/4 | 0/5 |
| aliased I2/I4/I7 (H3) | 8/9 | 8/9 | 3/4 | 0/5 |

Two rows carry the argument for how scoring is defined:

- **Paranoid** catches every violation (TP 4/4) and is worthless (FP 5/5).
  Violation-only scoring would rate it perfect, which is why the false-positive
  rate is reported unconditionally and cannot be omitted from `summary()`.
- **Misattributing** scores 8/9 on decisions and 5/9 on predicates. It reaches
  the right verdict for the wrong reason, and only predicate-level scoring sees
  it. That is why the primary outcome is predicate agreement.

Aliasing is detected by evidence, not co-firing: the aliased mock fires I2, I4
and I7 together with **one** distinct evidence payload, while the correct mock
fires I2 alone.

## First-divergence locator

Implements the agreed protocol: when two independent implementations diverge, do
not reconcile them — preserve the divergence and walk backward to the first
unequal state. Stages, in causal order:

    canonical bytes -> digest -> predicate evaluations -> decision
                    -> consequence -> receipt

Two properties make it a tool rather than a discipline:

- **Halt-on-first.** Comparison stops at the first unequal stage; downstream
  stages report NOT_REACHED, never FAIL. A digest difference caused by a
  canonical-byte difference is not an independent finding, and reporting it as
  one inflates a single defect into six.
- **No reconciliation path.** No merge, no prefer, no tolerance parameter. A
  test asserts the module exposes no such surface. The tool can report where two
  runs first disagree; nothing in it can make them agree.

Predicate comparison includes evidence, not just results. Two runs agreeing on
which predicates failed while citing different evidence have diverged — evidence
is what distinguishes independent predicates from aliases, so dropping it would
hide the H3 signal.

A refusal is a state, not an absence: one implementation refusing where another
emits is a divergence at that stage.

## Reproducing

    git clone https://github.com/billyrdavis1985-bot/gec-conformance
    cd gec-conformance
    python3 -m unittest discover -s tests          # 158 tests, no dependencies
    python3 cli.py diff scqos_literal scqos_es6 -v # reproduce CANON-01
    python3 protocol/freeze.py                     # recompute every digest

Standard library only. No install step.

The freeze digests are reproducible by construction: the implementation tarball
normalizes mtime, mode and ownership, so `implementation_digest` records content
rather than checkout time. `contract_digest` is computed with the contract's own
digest lines blanked, since a document cannot contain its own hash.

## Data provenance

The conformance study's parent and compliant-successor artifacts are extracted
from published QEC-P1 session data (DOI 10.5281/zenodo.22050536): sessions 11
and 12 on `ibm_marrakesh`, separated by 13.74 hours of real collection time — a
separation produced by queue scheduling rather than constructed, which satisfies
the contract's ≥12h admission predicate on its own.

Case C01, the primary negative control, is therefore real end to end: collected
parent, collected successor, real separation, real syndrome data, real decode.
Violating cases use synthetic successors, because no collected pair exists at 3h
or 11h59m and none should be manufactured on hardware to create one. Every
synthetic artifact is labelled in its own bytes, and a test asserts the label
tracks reality in both directions.

## Layout

    protocol/     contract, preregistration, freeze tool and manifest
    capability/   qec-syndrome-decode — the capability under contract
    canon/        rule-agnostic canonicalization engine and corpus
    verifier/     clean-room receipt verifier
    harness/      fixtures, runner, mock substrates, divergence locator
    fixtures/     frozen input artifacts
    tests/        158 tests, incl. declared-vs-actual consistency checks

License MIT. Author's code and experimental data remain the author's; adapter,
contract and receipt artifacts may be used by SC-Engineering; the author retains
the right to publish findings, positive or negative.

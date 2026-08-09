# gec-canon — canonicalization differential rig

Part of the `gec-conformance` protocol. Independent implementation, authored
without access to SCQOS source.

## Why this exists

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

    python3 -m unittest discover -s tests     # 31 self-tests
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

## Status

Engine, rulesets, corpus, differ, and tests are complete and independent of any
external input. Pending: the subject specification, which becomes one more entry
in `rulesets/`.

License and ownership per the terms of record in the capability contract §12.

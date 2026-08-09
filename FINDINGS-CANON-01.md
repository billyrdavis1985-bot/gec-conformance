# Finding CANON-01 — the SCQOS canonicalization specification admits multiple faithful implementations

**protocol:** `gec-conformance v1.0.0`, hypothesis H4
**subject:** SCQOS canonicalization specification, prose as supplied 2026-08-09
**method:** clean-room implementation from specification text only; no access to
`scqos.py`, `scqos_root_adapter.py`, or any canonical bytes produced by SC-Engineering
**status:** finding, pre-integration. No governed execution has occurred.
**severity:** high — affects ordinary production values, not edge cases

---

## Summary

The specification answers five of the eight canonicalization questions cleanly and
leaves three open. The three open questions are not exotic: they govern how a
float, a large integer, and a non-BMP key are rendered. I implemented two readings
of the same specification, differing **only** where the text is silent. Both are
faithful. They produce different canonical bytes on **9 of 32** corpus cases,
including on a well-formed universal packet using the declared schema.

Because the two implementations agree everywhere the specification is explicit,
every divergence below is a gap in the specification rather than a disagreement
about it.

The consequence for the study: until these are pinned, a receipt digest mismatch
between my verifier and yours is uninterpretable. It could mean a defect in
either implementation, or it could mean we each read an unstated rule differently
and both did so correctly. H4 cannot be evaluated against a specification that
admits more than one answer.

---

## What the specification settles

Recorded so the gaps aren't read as a general complaint. These are stated clearly
enough to implement without guessing:

| Question | Rule as stated |
|---|---|
| Unicode normalization | none applied; strings canonicalized exactly as supplied |
| Empty vs null vs absent | three distinct states; nothing inserted or removed |
| Whitespace | none between tokens; comma and colon as separators |
| Trailing newline | excluded from the hashed bytes |
| Digest | SHA3-512, lowercase hexadecimal |
| Non-ASCII escaping | emitted directly, not escaped |
| Size ceiling | 1,048,576 bytes on the encoded canonical object |
| Type discipline | booleans are not integers; numbers are not numeric strings |

The explicit statement that no Unicode normalization is performed is worth
singling out. It is the single most commonly omitted rule in canonicalization
specs, and stating it — including the word "currently" — is better practice than
most published schemes manage.

---

## Gap 1 — float rendering is undefined (highest impact)

The specification constrains float **validity** ("permitted only when finite") and
float **typing** ("not converted to strings"), but never states float
**rendering**. There is no rule for how a float becomes characters.

Observed on the corpus, from the same input:

| Case | Python/json reading | JS/ES6 reading |
|---|---|---|
| NUM-01 integer-valued float | `{"shots":1024.0}` | `{"shots":1024}` |
| NUM-02 exponential boundary | `1e+20` | `100000000000000000000` |
| NUM-03 small-magnitude boundary | `1e-06`, `1e-07` | `0.000001`, `1e-7` |
| NUM-04 negative zero | `{"drift":-0.0}` | `{"drift":0}` |
| NUM-06 int and float of equal value | `1` and `1.0` distinguishable | both render `1` |

**Why this is the highest-impact gap.** `shots: 1024.0` is not a contrived value.
Any measurement count that has passed through a float — a division, an average, a
JSON round-trip in a language without an integer type — arrives in this shape. The
two readings differ by two characters and therefore by an entire SHA3-512 digest.

NUM-06 deserves separate attention because it cuts the other way. Under the ES6
reading, `1` and `1.0` share a canonical form, so two semantically distinct
documents share a digest. Under the Python reading they do not. The specification
states that numeric types remain semantically distinct from quoted numeric
strings; it does not say whether integer and float remain distinct from **each
other**. Those are different guarantees and only one of them is written down.

**Recommendation:** state the algorithm by name. If ECMAScript
`Number::toString` (RFC 8785 §3.2.2.3), say so; that is the only widely
implemented shortest-round-trip rule and it is what a JavaScript verifier will do
regardless. If instead the platform repr is intended, say that, and accept that
non-Python verifiers must reimplement CPython's float formatting.

---

## Gap 2 — integer precision beyond IEEE-754 exact range

"Integers remain JSON integers" is silent above 2^53 − 1.

| Case | Python/json reading | JS/ES6 reading |
|---|---|---|
| INT-01 `2**53 + 1` | `9007199254740993` | `9007199254740992` |
| INT-02 64-bit identifier | `18446744073709551615` | `18446744073709552000` |

INT-02 is the dangerous one. A 64-bit identifier carried as a JSON number is
**silently corrupted** by any verifier whose number type is IEEE-754 double — and
the corrupted value is still a well-formed integer, so nothing downstream
detects it. The canonical bytes differ, the digest differs, and neither side can
tell whether the other is buggy or merely different.

This is not hypothetical for SCQOS specifically: `sequence` is declared as an
integer in the packet schema, and sequence counters are exactly the kind of field
that grows without bound.

**Recommendation:** either bound integers to the IEEE-754 exact range and reject
outside it, or require that identifiers and counters beyond that range be carried
as strings. Both are defensible. Silence is not, because it produces two
implementations that are each correct and mutually incompatible.

---

## Gap 3 — "ascending lexical order" does not name a collation

Lexical over codepoints, over UTF-8 bytes, or over UTF-16 code units?

Codepoint order and UTF-8 byte order coincide for all valid UTF-8, so this is a
binary fork rather than a three-way one. The two candidates agree across the
entire Basic Multilingual Plane and disagree on **every** supplementary
character, because UTF-16 encodes those as surrogate pairs in 0xD800–0xDFFF,
which sort below U+E000.

Case ORD-01, keys `U+E000` and `U+10000`:

```
codepoint / UTF-8 order:   {"<U+E000>":1,"<U+10000>":2}
UTF-16 code unit order:    {"<U+10000>":2,"<U+E000>":1}
```

Lower practical risk than the first two gaps, since supplementary characters are
rare in key names. But `payload` is a free-form object, and a key sourced from
user data or an emoji-bearing label will reach this path eventually. The cost of
closing it is one clause.

**Recommendation:** name the collation. If the implementation is Python's
`sorted()`, that is codepoint order; a JavaScript verifier using `Array.sort()`
will diverge without either side having a bug.

---

## Gap 4 — schema-level items outside the canonicalization rules

Not part of the byte-emission rules, but they determine whether two producers
can generate the same bytes at all:

- **`created_at` has no format rule.** It appears in the packet schema with no
  constraint on precision or timezone encoding. `2026-08-09T14:32:07Z` and
  `2026-08-09T14:32:07.000+00:00` are the same instant and different bytes
  (corpus PKT-02). Suggest requiring RFC 3339 with fixed precision and `Z`.
- **Duplicate keys are unaddressed.** A default JSON parser silently keeps the
  last occurrence, *before* canonicalization can observe it. A producer could
  therefore emit a document whose canonical form does not reflect what a reader
  sees. My parser rejects duplicates outright; the specification should say
  whether that is correct.
- **Control-character escaping is partly settled.** Non-ASCII is resolved
  ("emitted directly"), but escaping of U+0000–U+001F is not: short forms
  (`\n`, `\t`) versus `\u00XX`, and the case of the hex digits. Both appear in
  real implementations.
- **Size-ceiling semantics.** Is exceeding 1,048,576 bytes a canonicalization
  error or a governance HOLD, and does the ceiling apply to the packet or also
  to a nested `payload`? Currently implemented as a canonicalization error.

---

## Demonstration on a real packet

Corpus case PKT-01 is a well-formed universal packet using all sixteen declared
fields, valid under the specification, with `shots` as a float and `sequence` as
an integer. Both readings sort the sixteen keys identically. Both emit identical
bytes for fifteen of them.

They differ in two characters, inside `payload`:

```
scqos_literal : ..."session_index":2,"shots":1024.0}...
scqos_es6     : ..."session_index":2,"shots":1024}...
```

Resulting SHA3-512 digests:

```
literal : 3bc9971c6b9180e51dbd6692384cb0bf99e24fd295de8a44...
es6     : 5438f2c9617467ff66a39edde4cbee1d854ea6c5f75def39...
```

Two implementations, both faithful to the specification as written, producing
different state digests for the same packet. Under I6 Reference, one of them
would be refused for failing to resolve canonically to what the proof says it is
— and the specification provides no basis for deciding which.

---

## What was deliberately not done

Per the instruction accompanying the specification, none of these rules were
improved during implementation. Where the text is silent, the implementation
records an assumption in an `assumed_fields` list and surfaces it as `[ASSUMED]`
in every output, rather than choosing quietly on SC-Engineering's behalf.

No canonical bytes, reference implementation, or source from SC-Engineering were
consulted. The implementation was committed and hashed before this comparison was
run, and the commit predates receipt of any SCQOS output.

---

## Requested resolution

Three clauses close Gaps 1–3:

1. Name the float-to-string algorithm.
2. State the integer range, and what happens outside it.
3. Name the collation for key ordering.

Gap 4 items are lower priority and can be resolved in the schema rather than the
canonicalization spec.

Once those are pinned, I will collapse the two rulesets into one, re-run the
corpus, and H4 becomes evaluable. Until then a digest mismatch between our
verifiers carries no information, because the specification permits both answers.

---

## Reproduction

```
python3 -m unittest discover -s tests     # 31 self-tests
python3 cli.py rulesets                   # all rulesets, [ASSUMED] fields marked
python3 cli.py diff scqos_literal scqos_es6 -v
python3 cli.py diff scqos_literal scqos_literal_es6num -v   # isolates Gap 1
```

`scqos_literal_es6num` differs from `scqos_literal` only in float rendering, so
divergences there cannot be attributed to key ordering.

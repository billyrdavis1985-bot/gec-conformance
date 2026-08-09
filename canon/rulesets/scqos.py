"""
SCQOS canonicalization — implemented from the specification text alone.

Written without access to scqos.py or scqos_root_adapter.py, and without any
example canonical bytes produced by SC-Engineering. Per the instruction
accompanying the specification, nothing here is "improved": where the rules as
written produce awkward or lossy behaviour, that behaviour is reproduced and the
awkwardness is recorded as a finding rather than repaired.

Two rulesets are defined, not one.

The specification answers five of the eight questions unambiguously. It leaves
three open, and a faithful implementer can resolve those three in more than one
defensible way. SCQOS_LITERAL and SCQOS_ES6 are both honest readings of the same
text; they differ ONLY on the open questions. Every divergence between them is
therefore a gap in the specification rather than a disagreement about it.

Answered by the specification
-----------------------------
  Unicode normalization   NONE, stated explicitly ("no additional Unicode
                          normalization transform is currently performed")
  empty / null / absent   DISTINCT, stated explicitly and in detail
  whitespace              none between tokens; comma and colon separators
  trailing newline        excluded from the hashed bytes, stated explicitly
  digest                  SHA3-512, lowercase hexadecimal
  non-ASCII escaping      emitted directly, not escaped
  size ceiling            1,048,576 bytes on the encoded canonical object

Left open by the specification
------------------------------
  key_order        "ascending lexical order" does not say lexical over what.
                   Codepoint order and UTF-8 byte order coincide for all valid
                   UTF-8, so the real fork is those two versus UTF-16 code unit
                   order. They agree across the entire BMP and disagree on every
                   supplementary character, because UTF-16 encodes those as
                   surrogates in 0xD800..0xDFFF, which sort below U+E000.

  number_format    The specification constrains float *validity* (finite only)
                   and float *typing* (not converted to strings) but never
                   states float *rendering*. 1024.0, 1e21, 1e-7 and -0.0 have no
                   defined canonical form. This is the largest gap: it affects
                   ordinary values, not exotic ones.

  bigint_policy    "integers remain JSON integers" is silent on integers beyond
                   the IEEE-754 exact range. A Python producer emits 2**64
                   exactly; a JavaScript verifier cannot represent it. Neither
                   is wrong under the text as written.

Also unstated, at schema level rather than in the Ruleset model
--------------------------------------------------------------
  created_at       Present in the packet schema with no format rule. Precision
                   and timezone encoding are unconstrained, so two producers can
                   express the same instant as different bytes.
  duplicate keys   No rule. A default JSON parser silently keeps the last
                   occurrence, before canonicalization can observe it.
  control chars    Non-ASCII escaping is settled, but escaping of U+0000..U+001F
                   (short forms versus \\u00XX, and hex digit case) is not.
"""

from __future__ import annotations

from ..ruleset import (
    AbsentNullPolicy,
    BigIntPolicy,
    DigestEncoding,
    KeyOrder,
    LineEnding,
    NumberFormat,
    Ruleset,
    StringEscaping,
    UnicodeForm,
)

SPEC_SOURCE = "SCQOS canonicalization specification, prose as supplied (digest pinned at execution freeze)"

_SHARED = dict(
    unicode_form=UnicodeForm.NONE,
    absent_null=AbsentNullPolicy.DISTINCT,
    string_escaping=StringEscaping.JSON_MINIMAL,
    line_ending=LineEnding.NONE,
    trailing_newline=False,
    indent=0,
    digest_algorithm="sha3_512",
    digest_encoding=DigestEncoding.HEX_LOWER,
    max_canonical_bytes=1_048_576,
)

# Reading A — the reading a Python implementation naturally produces.
# "ascending lexical order" resolved as codepoint order (Python's sorted());
# floats rendered by the platform's shortest round-trip repr, which is what
# json.dumps emits; integers kept at full precision.
SCQOS_LITERAL = Ruleset(
    name="scqos_literal",
    source=SPEC_SOURCE + " — open questions resolved toward a Python/json reading",
    key_order=KeyOrder.CODEPOINT,
    number_format=NumberFormat.DECIMAL_PRESERVE,
    bigint_policy=BigIntPolicy.EXACT,
    assumed_fields=("key_order", "number_format", "bigint_policy"),
    **_SHARED,
)

# Reading B — the reading a JavaScript or JCS-aligned implementation naturally
# produces from the same text. Equally faithful: nothing in the specification
# excludes it.
SCQOS_ES6 = Ruleset(
    name="scqos_es6",
    source=SPEC_SOURCE + " — open questions resolved toward a JS/RFC 8785 reading",
    key_order=KeyOrder.UTF16_CODE_UNIT,
    number_format=NumberFormat.ES6_SHORTEST,
    bigint_policy=BigIntPolicy.IEEE754_COERCE,
    assumed_fields=("key_order", "number_format", "bigint_policy"),
    **_SHARED,
)

# Isolates the number question alone: identical to LITERAL except for float
# rendering, so a divergence here cannot be attributed to key ordering.
SCQOS_LITERAL_ES6NUM = Ruleset(
    name="scqos_literal_es6num",
    source=SPEC_SOURCE + " — codepoint key order, ES6 number rendering",
    key_order=KeyOrder.CODEPOINT,
    number_format=NumberFormat.ES6_SHORTEST,
    bigint_policy=BigIntPolicy.EXACT,
    assumed_fields=("key_order", "number_format", "bigint_policy"),
    **_SHARED,
)

SCQOS_RULESETS = (SCQOS_LITERAL, SCQOS_ES6, SCQOS_LITERAL_ES6NUM)

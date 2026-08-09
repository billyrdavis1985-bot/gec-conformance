"""
Concrete rulesets.

JCS is the baseline: a published standard, implemented here from RFC 8785 alone.
The remaining rulesets are *plausible bespoke variants* — each represents a
design choice a competent team might reasonably make when writing their own
canonicalization rules. They exist so the differential rig has something to
compare against before any external specification arrives, and so the corpus can
be validated on divergences that are already known to be real.

When an external specification lands, it becomes another entry here. Nothing in
the engine changes.
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

JCS = Ruleset(
    name="jcs",
    source="RFC 8785 (JSON Canonicalization Scheme), implemented from the RFC text",
    key_order=KeyOrder.UTF16_CODE_UNIT,
    unicode_form=UnicodeForm.NONE,
    number_format=NumberFormat.ES6_SHORTEST,
    bigint_policy=BigIntPolicy.IEEE754_COERCE,
    absent_null=AbsentNullPolicy.DISTINCT,
    string_escaping=StringEscaping.JSON_MINIMAL,
    line_ending=LineEnding.NONE,
    trailing_newline=False,
    indent=0,
    digest_algorithm="sha256",
    digest_encoding=DigestEncoding.HEX_LOWER,
)

# The most common bespoke shape: normalize to NFC, sort by UTF-8 bytes, escape
# non-ASCII. Each choice is individually defensible; together they diverge from
# JCS on a large fraction of realistic inputs.
NFC_UTF8_ASCII = Ruleset(
    name="nfc_utf8_ascii",
    source="hypothetical bespoke spec — NFC + UTF-8 key order + ASCII escaping",
    key_order=KeyOrder.UTF8_BYTES,
    unicode_form=UnicodeForm.NFC,
    number_format=NumberFormat.ES6_SHORTEST,
    bigint_policy=BigIntPolicy.EXACT,
    absent_null=AbsentNullPolicy.DISTINCT,
    string_escaping=StringEscaping.ASCII_ONLY,
    line_ending=LineEnding.NONE,
    trailing_newline=False,
    indent=0,
    digest_algorithm="sha256",
    digest_encoding=DigestEncoding.HEX_LOWER,
)

# The "pretty JSON with sorted keys" shape, which many systems adopt because it
# is what json.dumps(sort_keys=True, indent=2) produces. Whitespace and platform
# float formatting both become part of the digest.
PRETTY_SORTED = Ruleset(
    name="pretty_sorted",
    source="hypothetical bespoke spec — sorted keys, indented, platform float repr",
    key_order=KeyOrder.CODEPOINT,
    unicode_form=UnicodeForm.NONE,
    number_format=NumberFormat.DECIMAL_PRESERVE,
    bigint_policy=BigIntPolicy.EXACT,
    absent_null=AbsentNullPolicy.NULL_ELIDED,
    string_escaping=StringEscaping.JSON_MINIMAL,
    line_ending=LineEnding.LF,
    trailing_newline=True,
    indent=2,
    digest_algorithm="sha256",
    digest_encoding=DigestEncoding.HEX_LOWER,
)

# Same rules as JCS but base64url digests — isolates the case where two systems
# agree on every byte of the canonical form and still report different digests.
JCS_BASE64URL = Ruleset(
    name="jcs_base64url",
    source="RFC 8785 canonical bytes, base64url digest encoding",
    key_order=KeyOrder.UTF16_CODE_UNIT,
    unicode_form=UnicodeForm.NONE,
    number_format=NumberFormat.ES6_SHORTEST,
    bigint_policy=BigIntPolicy.IEEE754_COERCE,
    absent_null=AbsentNullPolicy.DISTINCT,
    string_escaping=StringEscaping.JSON_MINIMAL,
    line_ending=LineEnding.NONE,
    trailing_newline=False,
    indent=0,
    digest_algorithm="sha256",
    digest_encoding=DigestEncoding.BASE64URL,
)

REGISTRY: dict[str, Ruleset] = {
    r.name: r for r in (JCS, NFC_UTF8_ASCII, PRETTY_SORTED, JCS_BASE64URL)
}


def get(name: str) -> Ruleset:
    if name not in REGISTRY:
        raise KeyError(f"unknown ruleset {name!r}; have {sorted(REGISTRY)}")
    return REGISTRY[name]

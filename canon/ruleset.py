"""
Canonicalization ruleset model.

A ruleset is the set of decisions that turn structured data into exactly one byte
sequence. The engine (engine.py) is rule-agnostic; every choice that could reasonably
differ between two implementations lives here as an explicit, named option.

Design rule: there is no default anywhere in this module. Every field must be stated.
An unstated rule is the exact failure mode this tool exists to detect, so the tool
must not model it as a silent default of its own.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class _Absent:
    """Sentinel distinguishing an absent key from a present key holding null.

    JSON has no way to express the difference, which is precisely why
    canonicalization specs must state it. Corpus cases rely on this.
    """

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __repr__(self) -> str:
        return "ABSENT"


ABSENT = _Absent()


class KeyOrder(Enum):
    """How object keys are ordered.

    UTF16_CODE_UNIT and UTF8_BYTES agree across the BMP but diverge for
    supplementary characters: UTF-16 encodes them as surrogates (0xD800-0xDFFF),
    which sort *below* U+E000-U+FFFF, while UTF-8 and codepoint order put them
    above. A key pair of "\\ue000" and "\\U00010000" discriminates the two.
    """

    UTF16_CODE_UNIT = "utf16_code_unit"  # RFC 8785
    UTF8_BYTES = "utf8_bytes"
    CODEPOINT = "codepoint"
    INSERTION = "insertion"  # no reordering; only canonical if producers agree


class UnicodeForm(Enum):
    """Unicode normalization applied to strings and keys before serialization.

    RFC 8785 deliberately applies NONE. Many bespoke specs apply NFC. The two
    disagree on any string containing decomposed combining marks, which is
    common in real names and file paths.
    """

    NONE = "none"
    NFC = "nfc"
    NFD = "nfd"
    NFKC = "nfkc"
    NFKD = "nfkd"


class NumberFormat(Enum):
    """How numeric values are rendered.

    ES6_SHORTEST is the ECMAScript Number::toString algorithm required by
    RFC 8785: shortest round-tripping decimal, integers below 1e21 without a
    decimal point, exponential outside that range.
    """

    ES6_SHORTEST = "es6_shortest"  # RFC 8785
    DECIMAL_PRESERVE = "decimal_preserve"  # keep the literal as written
    INT_ONLY = "int_only"  # reject any non-integer value


class BigIntPolicy(Enum):
    """Integers beyond IEEE-754 exact range (|n| > 2**53 - 1).

    A spec that is silent here is silently non-interoperable: a producer in
    Python and a verifier in JavaScript will disagree on the digest of the
    same document without either being obviously wrong.
    """

    EXACT = "exact"  # emit full precision
    REJECT = "reject"  # refuse to canonicalize
    IEEE754_COERCE = "ieee754_coerce"  # round-trip through float first


class AbsentNullPolicy(Enum):
    """Whether absent, null, and empty-string are distinguishable."""

    DISTINCT = "distinct"  # absent omitted, null emitted as null
    NULL_ELIDED = "null_elided"  # null keys dropped, same bytes as absent
    NULL_AS_EMPTY = "null_as_empty"  # null rendered as ""


class StringEscaping(Enum):
    """Which characters are escaped in string literals."""

    JSON_MINIMAL = "json_minimal"  # RFC 8785: only ", \, and C0 controls
    ASCII_ONLY = "ascii_only"  # every non-ASCII codepoint as \uXXXX


class DigestEncoding(Enum):
    HEX_LOWER = "hex_lower"
    HEX_UPPER = "hex_upper"
    BASE64 = "base64"
    BASE64URL = "base64url"


class LineEnding(Enum):
    NONE = "none"  # no whitespace at all (RFC 8785)
    LF = "lf"
    CRLF = "crlf"


@dataclass(frozen=True)
class Ruleset:
    """A complete, executable statement of a canonicalization specification.

    Every field is required. If a specification does not answer one of these
    questions, that gap is a finding: record it rather than choosing for them.
    """

    name: str
    source: str  # where these rules came from (RFC number, spec doc digest, etc.)

    key_order: KeyOrder
    unicode_form: UnicodeForm
    number_format: NumberFormat
    bigint_policy: BigIntPolicy
    absent_null: AbsentNullPolicy
    string_escaping: StringEscaping
    line_ending: LineEnding
    trailing_newline: bool
    indent: int  # 0 = no pretty printing
    digest_algorithm: str  # hashlib name
    digest_encoding: DigestEncoding
    max_canonical_bytes: int | None = None  # size ceiling on the encoded object

    # Documented gaps: questions this ruleset's source did not answer, where the
    # value below is this implementation's assumption rather than the spec's rule.
    assumed_fields: tuple[str, ...] = ()

    def describe(self) -> str:
        lines = [f"ruleset: {self.name}", f"source:  {self.source}"]
        for field in (
            "key_order",
            "unicode_form",
            "number_format",
            "bigint_policy",
            "absent_null",
            "string_escaping",
            "line_ending",
            "trailing_newline",
            "indent",
            "digest_algorithm",
            "digest_encoding",
            "max_canonical_bytes",
        ):
            value = getattr(self, field)
            marker = "  [ASSUMED]" if field in self.assumed_fields else ""
            rendered = value.value if isinstance(value, Enum) else value
            lines.append(f"  {field:<18} {rendered}{marker}")
        return "\n".join(lines)


class CanonicalizationError(Exception):
    """Raised when a value cannot be canonicalized under the active ruleset.

    Never guess. A verifier that quietly picks a representation for an
    underspecified case will agree with a producer that picked differently
    only by luck, and will disagree without either side being able to say why.
    """

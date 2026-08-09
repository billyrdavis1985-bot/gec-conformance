"""
Rule-agnostic canonicalization engine.

Walks a value tree and emits bytes according to whatever Ruleset is supplied.
Contains no canonicalization policy of its own: every decision is delegated.

This split is deliberate. A canonicalizer written directly against one
specification cannot be used to test that specification, because its
assumptions and the spec's assumptions are the same object. Separating engine
from ruleset makes a second specification a configuration change rather than a
rewrite, and makes the differential test (differ.py) possible at all.
"""

from __future__ import annotations

import base64
import hashlib
import unicodedata
from typing import Any

from .numbers import render_number
from .ruleset import (
    ABSENT,
    AbsentNullPolicy,
    CanonicalizationError,
    DigestEncoding,
    KeyOrder,
    LineEnding,
    Ruleset,
    StringEscaping,
    UnicodeForm,
    _Absent,
)

_SHORT_ESCAPES = {
    0x08: "\\b",
    0x09: "\\t",
    0x0A: "\\n",
    0x0C: "\\f",
    0x0D: "\\r",
    0x22: '\\"',
    0x5C: "\\\\",
}


class Canonicalizer:
    """Serializes values to canonical bytes under a given ruleset."""

    def __init__(self, ruleset: Ruleset) -> None:
        self.rules = ruleset

    # -- public API ---------------------------------------------------------

    def emit(self, value: Any) -> bytes:
        """Return the canonical byte sequence for value."""
        if isinstance(value, _Absent):
            raise CanonicalizationError("ABSENT is not a document; it only occurs as a member value")
        text = self._serialize(value, depth=0)
        if self.rules.trailing_newline:
            text += self._newline()
        raw = text.encode("utf-8")
        cap = self.rules.max_canonical_bytes
        if cap is not None and len(raw) > cap:
            raise CanonicalizationError(
                f"canonical form is {len(raw)} bytes, exceeding the {cap}-byte ceiling"
            )
        return raw

    def digest(self, value: Any) -> str:
        """Return the encoded digest of the canonical bytes."""
        raw = hashlib.new(self.rules.digest_algorithm, self.emit(value)).digest()
        enc = self.rules.digest_encoding
        if enc is DigestEncoding.HEX_LOWER:
            return raw.hex()
        if enc is DigestEncoding.HEX_UPPER:
            return raw.hex().upper()
        if enc is DigestEncoding.BASE64:
            return base64.b64encode(raw).decode("ascii")
        if enc is DigestEncoding.BASE64URL:
            return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")
        raise CanonicalizationError(f"unhandled digest encoding {enc}")

    # -- internals ----------------------------------------------------------

    def _newline(self) -> str:
        le = self.rules.line_ending
        if le is LineEnding.CRLF:
            return "\r\n"
        if le is LineEnding.LF:
            return "\n"
        return ""

    def _normalize(self, text: str) -> str:
        form = self.rules.unicode_form
        if form is UnicodeForm.NONE:
            return text
        return unicodedata.normalize(form.value.upper(), text)

    def _serialize(self, value: Any, depth: int) -> str:
        if value is None:
            return "null"
        if isinstance(value, bool):
            return "true" if value else "false"
        if isinstance(value, (int, float)):
            return render_number(value, self.rules.number_format, self.rules.bigint_policy)
        if isinstance(value, str):
            return self._string(value)
        if isinstance(value, (list, tuple)):
            return self._array(value, depth)
        if isinstance(value, dict):
            return self._object(value, depth)
        raise CanonicalizationError(
            f"type {type(value).__name__} has no defined canonical form under this ruleset"
        )

    def _string(self, text: str) -> str:
        text = self._normalize(text)
        out = ['"']
        ascii_only = self.rules.string_escaping is StringEscaping.ASCII_ONLY
        for char in text:
            point = ord(char)
            if point in _SHORT_ESCAPES:
                out.append(_SHORT_ESCAPES[point])
            elif point < 0x20:
                out.append(f"\\u{point:04x}")
            elif ascii_only and point > 0x7F:
                out.extend(self._escape_astral(char, point))
            else:
                out.append(char)
        out.append('"')
        return "".join(out)

    @staticmethod
    def _escape_astral(char: str, point: int) -> list[str]:
        if point <= 0xFFFF:
            return [f"\\u{point:04x}"]
        adjusted = point - 0x10000
        high = 0xD800 + (adjusted >> 10)
        low = 0xDC00 + (adjusted & 0x3FF)
        return [f"\\u{high:04x}", f"\\u{low:04x}"]

    def _sort_key(self, key: str):
        order = self.rules.key_order
        normalized = self._normalize(key)
        if order is KeyOrder.UTF16_CODE_UNIT:
            # Big-endian UTF-16 bytes compare identically to UTF-16 code unit
            # sequences, which is what RFC 8785 specifies.
            return normalized.encode("utf-16-be", errors="surrogatepass")
        if order is KeyOrder.UTF8_BYTES:
            return normalized.encode("utf-8", errors="surrogatepass")
        if order is KeyOrder.CODEPOINT:
            return tuple(ord(c) for c in normalized)
        raise CanonicalizationError("INSERTION order has no sort key")

    def _members(self, obj: dict) -> list[tuple[str, Any]]:
        policy = self.rules.absent_null
        members: list[tuple[str, Any]] = []
        for key, val in obj.items():
            if not isinstance(key, str):
                raise CanonicalizationError(f"non-string object key {key!r}")
            if isinstance(val, _Absent):
                continue  # absent members are never emitted, under any policy
            if val is None:
                if policy is AbsentNullPolicy.NULL_ELIDED:
                    continue
                if policy is AbsentNullPolicy.NULL_AS_EMPTY:
                    val = ""
            members.append((key, val))

        if self.rules.key_order is not KeyOrder.INSERTION:
            members.sort(key=lambda item: self._sort_key(item[0]))

        seen: set[bytes] = set()
        for key, _ in members:
            fingerprint = self._normalize(key).encode("utf-8")
            if fingerprint in seen:
                raise CanonicalizationError(
                    f"duplicate key {key!r} after normalization; canonical form is undefined"
                )
            seen.add(fingerprint)
        return members

    def _pad(self, depth: int) -> tuple[str, str, str]:
        """Return (newline+indent, separator suffix, closing indent)."""
        if self.rules.indent <= 0:
            return "", "", ""
        nl = self._newline() or "\n"
        return (
            nl + " " * (self.rules.indent * (depth + 1)),
            "",
            nl + " " * (self.rules.indent * depth),
        )

    def _array(self, values, depth: int) -> str:
        if not values:
            return "[]"
        open_pad, _, close_pad = self._pad(depth)
        parts = [self._serialize(v, depth + 1) for v in values]
        if self.rules.indent <= 0:
            return "[" + ",".join(parts) + "]"
        joiner = "," + open_pad
        return "[" + open_pad + joiner.join(parts) + close_pad + "]"

    def _object(self, obj: dict, depth: int) -> str:
        members = self._members(obj)
        if not members:
            return "{}"
        open_pad, _, close_pad = self._pad(depth)
        colon = ": " if self.rules.indent > 0 else ":"
        parts = [
            self._string(k) + colon + self._serialize(v, depth + 1) for k, v in members
        ]
        if self.rules.indent <= 0:
            return "{" + ",".join(parts) + "}"
        joiner = "," + open_pad
        return "{" + open_pad + joiner.join(parts) + close_pad + "}"


def load_json(text: str) -> Any:
    """Parse JSON while preserving the distinctions canonicalization cares about.

    The standard parser silently discards duplicate keys (last wins) and coerces
    large integers through float. Both losses happen before canonicalization can
    see them, so a verifier using the default parser cannot detect a producer
    that exploited either.
    """
    import json

    def hook(pairs):
        keys = [k for k, _ in pairs]
        if len(keys) != len(set(keys)):
            dupes = sorted({k for k in keys if keys.count(k) > 1})
            raise CanonicalizationError(f"duplicate keys in source document: {dupes}")
        return dict(pairs)

    return json.loads(text, object_pairs_hook=hook, parse_int=int)

"""
Number rendering.

The hard part of JSON canonicalization. RFC 8785 requires the ECMAScript
Number::toString algorithm, which is not what any language's default float
formatter produces:

    Python repr(1e21)  -> '1e+21'      ES6 String(1e21)  -> '1e+21'    agree
    Python repr(1e16)  -> '1e+16'      ES6 String(1e16)  -> '10000000000000000'
    Python repr(-0.0)  -> '-0.0'       ES6 String(-0)    -> '0'

Any implementation that reaches for the platform float formatter will diverge on
these, and the divergence only shows up on values that rarely appear in test
fixtures and routinely appear in real data.
"""

from __future__ import annotations

import math

from .ruleset import BigIntPolicy, CanonicalizationError, NumberFormat

MAX_SAFE_INTEGER = 2**53 - 1


def _decompose(value: float) -> tuple[str, int]:
    """Return (significant_digits, n) such that value == 0.digits * 10**n.

    Uses Python's repr, which already produces the shortest round-tripping
    decimal — the same property ES6 requires — then re-derives digits and
    exponent so ES6 formatting rules can be applied independently of Python's
    own layout choices.
    """
    text = repr(abs(float(value)))

    if "e" in text or "E" in text:
        mantissa, _, exponent = text.partition("e" if "e" in text else "E")
        exp = int(exponent)
    else:
        mantissa, exp = text, 0

    int_part, _, frac_part = mantissa.partition(".")
    combined = int_part + frac_part
    point = len(int_part) + exp

    stripped = combined.lstrip("0")
    point -= len(combined) - len(stripped)
    stripped = stripped.rstrip("0")

    if not stripped:
        return "0", 0
    return stripped, point


def es6_number_to_string(value: float) -> str:
    """ECMAScript Number::toString, base 10 (ECMA-262 6.1.6.1.20)."""
    if isinstance(value, float):
        if math.isnan(value):
            raise CanonicalizationError("NaN has no JSON representation")
        if math.isinf(value):
            raise CanonicalizationError("Infinity has no JSON representation")

    if value == 0:
        return "0"  # covers -0.0; RFC 8785 requires negative zero to emit as 0

    sign = "-" if value < 0 else ""
    digits, n = _decompose(value)
    k = len(digits)

    if k <= n <= 21:
        return sign + digits + "0" * (n - k)
    if 0 < n <= 21:
        return sign + digits[:n] + "." + digits[n:]
    if -6 < n <= 0:
        return sign + "0." + "0" * (-n) + digits
    exponent = n - 1
    exp_sign = "+" if exponent >= 0 else "-"
    body = digits if k == 1 else digits[0] + "." + digits[1:]
    return f"{sign}{body}e{exp_sign}{abs(exponent)}"


def render_number(value: int | float, fmt: NumberFormat, bigint: BigIntPolicy) -> str:
    """Render a number under the active ruleset."""
    if isinstance(value, bool):  # bool is an int subclass in Python
        raise CanonicalizationError("bool routed to number renderer")

    if isinstance(value, int):
        if abs(value) > MAX_SAFE_INTEGER:
            if bigint is BigIntPolicy.REJECT:
                raise CanonicalizationError(
                    f"integer {value} exceeds IEEE-754 exact range; ruleset rejects it"
                )
            if bigint is BigIntPolicy.IEEE754_COERCE:
                return es6_number_to_string(float(value))
        if fmt is NumberFormat.INT_ONLY or fmt is NumberFormat.ES6_SHORTEST:
            return str(value)
        if fmt is NumberFormat.DECIMAL_PRESERVE:
            return str(value)

    if fmt is NumberFormat.INT_ONLY:
        raise CanonicalizationError(f"non-integer {value!r} under INT_ONLY ruleset")
    if fmt is NumberFormat.DECIMAL_PRESERVE:
        return repr(float(value))
    return es6_number_to_string(float(value))

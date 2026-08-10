"""
Conformance test against the published RFC 8785 test vectors.

Purpose: establish that the JCS baseline in this repository is a faithful
implementation of the standard, so that any divergence found against a
*subject* specification can be attributed to that specification rather than to
a defect here.

Fetching a published standard's own vectors does not affect the clean-room
independence claim in the preregistration (§2.2), which concerns SC-Engineering
source and output only. These vectors come from RFC 8785 itself:

  - Appendix B, Table 1: 26 IEEE-754 number serialization samples
  - Section 3.2.3: UTF-16 code unit property sorting test
  - Sections 3.2.2 / 3.2.3 / 3.2.4: end-to-end example with expected UTF-8 bytes
"""

import struct
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from canon import Canonicalizer, CanonicalizationError
from canon.numbers import es6_number_to_string
from canon.rulesets import JCS


def f(hex_bits: str) -> float:
    """Reconstruct a double from its IEEE-754 bit pattern, as Appendix B lists them."""
    return struct.unpack(">d", bytes.fromhex(hex_bits))[0]


# RFC 8785 Appendix B, Table 1. NaN and Infinity rows are handled separately
# since the RFC requires an error rather than a serialization.
APPENDIX_B = [
    ("0000000000000000", "0", "Zero"),
    ("8000000000000000", "0", "Minus zero"),
    ("0000000000000001", "5e-324", "Min pos number"),
    ("8000000000000001", "-5e-324", "Min neg number"),
    ("7fefffffffffffff", "1.7976931348623157e+308", "Max pos number"),
    ("ffefffffffffffff", "-1.7976931348623157e+308", "Max neg number"),
    ("4340000000000000", "9007199254740992", "Max pos int"),
    ("c340000000000000", "-9007199254740992", "Max neg int"),
    ("4430000000000000", "295147905179352830000", "~2**68"),
    ("44b52d02c7e14af5", "9.999999999999997e+22", ""),
    ("44b52d02c7e14af6", "1e+23", ""),
    ("44b52d02c7e14af7", "1.0000000000000001e+23", ""),
    ("444b1ae4d6e2ef4e", "999999999999999700000", ""),
    ("444b1ae4d6e2ef4f", "999999999999999900000", ""),
    ("444b1ae4d6e2ef50", "1e+21", ""),
    ("3eb0c6f7a0b5ed8c", "9.999999999999997e-7", ""),
    ("3eb0c6f7a0b5ed8d", "0.000001", ""),
    ("41b3de4355555553", "333333333.3333332", ""),
    ("41b3de4355555554", "333333333.33333325", ""),
    ("41b3de4355555555", "333333333.3333333", ""),
    ("41b3de4355555556", "333333333.3333334", ""),
    ("41b3de4355555557", "333333333.33333343", ""),
    ("becbf647612f3696", "-0.0000033333333333333333", ""),
    ("43143ff3c1cb0959", "1424953923781206.2", "Round to even"),
]

NON_FINITE = [("7fffffffffffffff", "NaN"), ("7ff0000000000000", "Infinity")]


class TestAppendixBNumberVectors(unittest.TestCase):
    """All 26 rows of RFC 8785 Appendix B, Table 1."""

    def test_every_finite_vector(self):
        failures = []
        for bits, expected, comment in APPENDIX_B:
            actual = es6_number_to_string(f(bits))
            if actual != expected:
                failures.append(f"  {bits} ({comment or 'n/a'}): expected {expected!r}, got {actual!r}")
        if failures:
            self.fail(f"{len(failures)}/{len(APPENDIX_B)} Appendix B vectors failed:\n" + "\n".join(failures))

    def test_non_finite_vectors_raise(self):
        for bits, name in NON_FINITE:
            with self.subTest(value=name):
                with self.assertRaises(CanonicalizationError):
                    es6_number_to_string(f(bits))


class TestSection323PropertySorting(unittest.TestCase):
    """RFC 8785 Section 3.2.3 property sorting test data."""

    SOURCE = {
        "\u20ac": "Euro Sign",
        "\r": "Carriage Return",
        "\ufb33": "Hebrew Letter Dalet With Dagesh",
        "1": "One",
        "\U0001f600": "Emoji: Grinning Face",
        "\u0080": "Control",
        "\u00f6": "Latin Small Letter O With Diaeresis",
    }

    EXPECTED_VALUE_ORDER = [
        "Carriage Return",
        "One",
        "Control",
        "Latin Small Letter O With Diaeresis",
        "Euro Sign",
        "Emoji: Grinning Face",
        "Hebrew Letter Dalet With Dagesh",
    ]

    def test_sort_order_matches_the_rfc(self):
        canon = Canonicalizer(JCS)
        out = canon.emit(self.SOURCE).decode()
        positions = [out.index(f'"{v}"') for v in self.EXPECTED_VALUE_ORDER]
        self.assertEqual(
            positions, sorted(positions),
            "property order does not match RFC 8785 Section 3.2.3"
        )

    def test_emoji_precedes_hebrew_letter(self):
        """The discriminator: only UTF-16 code unit ordering produces this.

        U+1F600 encodes as surrogates D83D DE00; D83D < FB33, so the emoji
        sorts first. Under codepoint or UTF-8 ordering, U+FB33 would come
        first instead.
        """
        canon = Canonicalizer(JCS)
        out = canon.emit(self.SOURCE).decode()
        self.assertLess(out.index("Emoji"), out.index("Hebrew"))


class TestEndToEndExample(unittest.TestCase):
    """RFC 8785 Sections 3.2.2 through 3.2.4: full worked example."""

    SOURCE = {
        "numbers": [333333333.33333329, 1e30, 4.50, 2e-3, 0.000000000000000000000000001],
        "string": "\u20ac$\u000f\u000aA'\u0042\u0022\u005c\\\"/",
        "literals": [None, True, False],
    }

    EXPECTED_TEXT = (
        '{"literals":[null,true,false],"numbers":[333333333.3333333,'
        '1e+30,4.5,0.002,1e-27],"string":"\u20ac$\\u000f\\nA\'B\\"\\\\\\\\\\""'
        "/\"}"
    )

    # Section 3.2.4, expected UTF-8 output in hexadecimal.
    EXPECTED_BYTES = bytes.fromhex(
        "7b 22 6c 69 74 65 72 61 6c 73 22 3a 5b 6e 75 6c 6c 2c 74 72"
        "75 65 2c 66 61 6c 73 65 5d 2c 22 6e 75 6d 62 65 72 73 22 3a"
        "5b 33 33 33 33 33 33 33 33 33 2e 33 33 33 33 33 33 33 2c 31"
        "65 2b 33 30 2c 34 2e 35 2c 30 2e 30 30 32 2c 31 65 2d 32 37"
        "5d 2c 22 73 74 72 69 6e 67 22 3a 22 e2 82 ac 24 5c 75 30 30"
        "30 66 5c 6e 41 27 42 5c 22 5c 5c 5c 5c 5c 22 2f 22 7d".replace(" ", "")
    )

    def test_canonical_bytes_match_section_324_exactly(self):
        canon = Canonicalizer(JCS)
        actual = canon.emit(self.SOURCE)
        if actual != self.EXPECTED_BYTES:
            self.fail(
                "canonical bytes differ from RFC 8785 Section 3.2.4\n"
                f"  expected: {self.EXPECTED_BYTES.decode('utf-8', 'backslashreplace')}\n"
                f"  actual:   {actual.decode('utf-8', 'backslashreplace')}"
            )

    def test_number_array_matches_the_rfc(self):
        canon = Canonicalizer(JCS)
        out = canon.emit(self.SOURCE).decode()
        self.assertIn("333333333.3333333,1e+30,4.5,0.002,1e-27", out)


class TestIJSONConstraints(unittest.TestCase):
    """RFC 8785 Section 3.1: I-JSON constraints on input data."""

    def test_duplicate_property_names_rejected(self):
        from canon import load_json

        with self.assertRaises(CanonicalizationError):
            load_json('{"a":1,"a":2}')

    def test_unicode_data_preserved_as_is(self):
        """Section 3.1: JCS-compliant processing MUST NOT normalize."""
        canon = Canonicalizer(JCS)
        self.assertNotEqual(
            canon.emit({"k": "e\u0301"}), canon.emit({"k": "\u00e9"})
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)

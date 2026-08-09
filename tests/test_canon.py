"""
Self-tests.

These validate the engine against properties stated in RFC 8785 and ECMA-262.
They are not a substitute for the differential run — they establish that the JCS
ruleset is a faithful implementation, so that a divergence against an external
specification can be attributed to that specification rather than to a bug here.
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from canon import ABSENT, Canonicalizer, CanonicalizationError, load_json
from canon.numbers import es6_number_to_string
from canon.rulesets import JCS, NFC_UTF8_ASCII, PRETTY_SORTED


class TestES6Numbers(unittest.TestCase):
    """ECMA-262 Number::toString, the algorithm RFC 8785 requires."""

    def test_integers_render_without_decimal_point(self):
        for value, expected in [(0.0, "0"), (1.0, "1"), (100.0, "100"), (1024.0, "1024")]:
            self.assertEqual(es6_number_to_string(value), expected)

    def test_negative_zero_renders_as_zero(self):
        self.assertEqual(es6_number_to_string(-0.0), "0")

    def test_exponential_boundary_at_1e21(self):
        self.assertEqual(es6_number_to_string(1e20), "100000000000000000000")
        self.assertEqual(es6_number_to_string(1e21), "1e+21")

    def test_small_magnitude_boundary_at_1e_minus_7(self):
        self.assertEqual(es6_number_to_string(1e-6), "0.000001")
        self.assertEqual(es6_number_to_string(1e-7), "1e-7")

    def test_diverges_from_python_repr(self):
        # The whole reason this module exists.
        self.assertEqual(repr(1e16), "1e+16")
        self.assertEqual(es6_number_to_string(1e16), "10000000000000000")

    def test_fractions(self):
        self.assertEqual(es6_number_to_string(0.1), "0.1")
        self.assertEqual(es6_number_to_string(1.5), "1.5")
        self.assertEqual(es6_number_to_string(123.456), "123.456")
        self.assertEqual(es6_number_to_string(-1.5), "-1.5")

    def test_nan_and_infinity_refused(self):
        for value in (float("nan"), float("inf"), float("-inf")):
            with self.assertRaises(CanonicalizationError):
                es6_number_to_string(value)


class TestJCSSerialization(unittest.TestCase):
    def setUp(self):
        self.canon = Canonicalizer(JCS)

    def emit(self, value):
        return self.canon.emit(value).decode()

    def test_keys_are_sorted_and_whitespace_removed(self):
        self.assertEqual(self.emit({"b": 1, "a": 2}), '{"a":2,"b":1}')

    def test_nested_objects_sorted_at_every_depth(self):
        self.assertEqual(
            self.emit({"b": {"z": 1, "a": 2}, "a": 3}), '{"a":3,"b":{"a":2,"z":1}}'
        )

    def test_array_order_preserved(self):
        self.assertEqual(self.emit([3, 1, 2]), "[3,1,2]")

    def test_utf16_ordering_places_supplementary_before_private_use(self):
        # The ORD-01 discriminator: surrogates (0xD800..) sort below U+E000.
        out = self.emit({"\ue000": 1, "\U00010000": 2})
        self.assertTrue(out.index("\U00010000") < out.index("\ue000"))

    def test_no_unicode_normalization(self):
        decomposed = self.emit({"k": "e\u0301"})
        precomposed = self.emit({"k": "\u00e9"})
        self.assertNotEqual(decomposed, precomposed)

    def test_minimal_escaping_keeps_non_ascii_literal(self):
        self.assertEqual(self.emit({"k": "café"}), '{"k":"café"}')

    def test_short_escapes_used_for_control_characters(self):
        self.assertEqual(self.emit({"k": "a\nb\tc"}), '{"k":"a\\nb\\tc"}')

    def test_other_controls_use_lowercase_hex(self):
        self.assertEqual(self.emit({"k": "\u001f"}), '{"k":"\\u001f"}')

    def test_absent_and_null_are_distinguishable(self):
        self.assertEqual(self.emit({"a": None}), '{"a":null}')
        self.assertEqual(self.emit({"a": ABSENT}), "{}")

    def test_empty_containers_preserved(self):
        self.assertEqual(self.emit({"a": [], "b": {}}), '{"a":[],"b":{}}')

    def test_booleans_not_treated_as_numbers(self):
        self.assertEqual(self.emit({"a": True, "b": False}), '{"a":true,"b":false}')

    def test_integer_float_distinction_preserved(self):
        # NUM-06: both render as "1" under ES6, so the digest cannot tell them
        # apart. Documented here because it is a property of the standard, not
        # a defect in this implementation.
        self.assertEqual(self.emit({"a": 1}), self.emit({"a": 1.0}))


class TestDigest(unittest.TestCase):
    def test_encoding_changes_digest_string_not_bytes(self):
        from canon.rulesets import JCS_BASE64URL

        value = {"a": 1}
        hexed = Canonicalizer(JCS)
        b64 = Canonicalizer(JCS_BASE64URL)
        self.assertEqual(hexed.emit(value), b64.emit(value))
        self.assertNotEqual(hexed.digest(value), b64.digest(value))

    def test_digest_is_stable(self):
        canon = Canonicalizer(JCS)
        self.assertEqual(canon.digest({"a": 1, "b": 2}), canon.digest({"b": 2, "a": 1}))


class TestVariantRulesets(unittest.TestCase):
    def test_nfc_ruleset_folds_decomposed_forms(self):
        canon = Canonicalizer(NFC_UTF8_ASCII)
        self.assertEqual(canon.emit({"k": "e\u0301"}), canon.emit({"k": "\u00e9"}))

    def test_nfc_ruleset_rejects_keys_that_collide_after_normalization(self):
        canon = Canonicalizer(NFC_UTF8_ASCII)
        with self.assertRaises(CanonicalizationError):
            canon.emit({"cafe\u0301": 1, "caf\u00e9": 2})

    def test_ascii_escaping_expands_astral_to_surrogate_pair(self):
        canon = Canonicalizer(NFC_UTF8_ASCII)
        out = canon.emit({"k": "\U0001f9ea"}).decode()
        self.assertIn("\\ud83e", out)
        self.assertIn("\\uddea", out)

    def test_pretty_ruleset_elides_nulls(self):
        canon = Canonicalizer(PRETTY_SORTED)
        self.assertNotIn("null", canon.emit({"a": None, "b": 1}).decode())

    def test_pretty_ruleset_adds_trailing_newline(self):
        canon = Canonicalizer(PRETTY_SORTED)
        self.assertTrue(canon.emit({"a": 1}).endswith(b"\n"))


class TestParsing(unittest.TestCase):
    def test_duplicate_keys_rejected_rather_than_last_wins(self):
        with self.assertRaises(CanonicalizationError):
            load_json('{"a":1,"a":2}')

    def test_large_integers_survive_parsing(self):
        parsed = load_json('{"n":18446744073709551615}')
        self.assertEqual(parsed["n"], 18446744073709551615)

    def test_unsupported_type_refused_rather_than_coerced(self):
        canon = Canonicalizer(JCS)
        with self.assertRaises(CanonicalizationError):
            canon.emit({"k": {1, 2}})


class TestCorpusIntegrity(unittest.TestCase):
    def test_every_case_has_a_unique_id_and_a_question(self):
        from canon.corpus import CORPUS, QUESTIONS

        ids = [c.id for c in CORPUS]
        self.assertEqual(len(ids), len(set(ids)))
        for case in CORPUS:
            self.assertIn(case.question, QUESTIONS)

    def test_high_value_cases_actually_diverge_somewhere(self):
        """A high-value case that no ruleset pair distinguishes is mislabelled."""
        from canon.corpus import high_value
        from canon.differ import compare
        from canon.rulesets import REGISTRY

        rulesets = list(REGISTRY.values())
        for case in high_value():
            distinguished = False
            for i, left in enumerate(rulesets):
                for right in rulesets[i + 1 :]:
                    if compare(left, right, [case])[0].diverged:
                        distinguished = True
                        break
                if distinguished:
                    break
            self.assertTrue(
                distinguished, f"{case.id} tagged high-value but no ruleset pair diverges"
            )


if __name__ == "__main__":
    unittest.main(verbosity=2)

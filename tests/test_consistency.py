"""
Declared-vs-actual consistency.

Every other test in this suite checks behaviour: does the decoder decode, does
the verifier reject a tampered receipt, does the harness discriminate. None of
them checks whether the DOCUMENTS describing the instrument match the
instrument. That gap is exactly what an external audit found: capability version
stated two ways, case counts stated three ways, test count stated two ways, a
contract marked DRAFT while the manifest called it FROZEN.

Those are Reference and Coherence failures — a claim about state disagreeing
with the state. The instrument exists to catch that class of failure in a
substrate. This file turns it on the instrument itself, so the same drift fails
the build instead of reaching a reader.

Each test reads a fact from code (the authoritative source) and asserts every
document that repeats it agrees. Code is authoritative because it is what
executes; a document is a claim about what executes.
"""

from __future__ import annotations

import json
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


CONTRACT = "protocol/CONTRACT-qec-syndrome-decode-v1.1.0.md"
PREREG = "protocol/PREREG-scqos-conformance-v1.1.0.md"
README = "README.md"
MANIFEST = "protocol/FREEZE-MANIFEST.json"


class TestCapabilityVersionConsistent(unittest.TestCase):
    """The capability version in code must match every document that states it."""

    def setUp(self):
        from capability.decode import CAPABILITY_VERSION

        self.version = CAPABILITY_VERSION

    def test_code_is_the_expected_version(self):
        self.assertEqual(self.version, "1.1.0")

    def test_contract_header_matches_code(self):
        header = read(CONTRACT).split("\n", 40)
        line = next(l for l in header if l.startswith("**capability_version:**"))
        self.assertIn(self.version, line,
                      f"contract header states {line!r}, code is {self.version}")

    def test_contract_field_table_matches_code(self):
        # the "| `capability_version` | `x.y.z` |" row in §1
        rows = re.findall(r"`capability_version`\s*\|\s*`([^`]+)`", read(CONTRACT))
        self.assertTrue(rows, "no capability_version row found in contract")
        for value in rows:
            self.assertEqual(value, self.version,
                             f"contract table states {value}, code is {self.version}")

    def test_manifest_matches_code(self):
        manifest = json.loads(read(MANIFEST))
        self.assertEqual(manifest["stage_a"]["capability_version"], self.version)


class TestCaseCountConsistent(unittest.TestCase):
    """The declared case count must match the actual number of case rows."""

    def setUp(self):
        self.prereg = read(PREREG)
        self.ids = sorted(set(re.findall(r"\|\s*●?\s*(C\d{2})\b", self.prereg)))

    def test_twenty_four_unique_cases(self):
        self.assertEqual(len(self.ids), 24, f"found {self.ids}")

    def test_ids_are_contiguous(self):
        expected = [f"C{n:02d}" for n in range(1, 25)]
        self.assertEqual(self.ids, expected)

    def test_section_5_header_states_the_actual_count(self):
        header = re.search(r"## 5\. Case matrix — (\d+) cases", self.prereg)
        self.assertIsNotNone(header, "no '## 5. Case matrix — N cases' header")
        self.assertEqual(int(header.group(1)), 24,
                         "§5 header count disagrees with the 24 case rows")

    def test_osf_registration_states_the_same_count(self):
        osf = read("protocol/OSF-REGISTRATION.md")
        self.assertIn("24 cases", osf)


class TestPhaseOneCountConsistent(unittest.TestCase):
    def setUp(self):
        self.prereg = read(PREREG)

    def test_phase1_list_length_matches_its_claim(self):
        m = re.search(r"\*\*Phase 1 \((\d+) cases\):\*\*([^\n]+)", self.prereg)
        self.assertIsNotNone(m)
        claimed = int(m.group(1))
        listed = re.findall(r"C\d{2}", m.group(2))
        self.assertEqual(claimed, len(listed),
                         f"phase 1 claims {claimed}, lists {len(listed)}")

    def test_bulleted_rows_match_phase1_list(self):
        """The ● markers in the matrix must equal the phase-1 list exactly."""
        m = re.search(r"\*\*Phase 1 \(\d+ cases\):\*\*([^\n]+)", self.prereg)
        listed = set(re.findall(r"C\d{2}", m.group(1)))
        bulleted = set(re.findall(r"●\s*(C\d{2})", self.prereg))
        self.assertEqual(bulleted, listed,
                         f"● markers {sorted(bulleted)} != phase-1 list {sorted(listed)}")


class TestNegativeControlsConsistent(unittest.TestCase):
    """A negative control is any case predicted to PERMIT. All statements of the
    set must match that definition and each other."""

    EXPECTED = {"C01", "C02", "C03", "C04", "C05", "C23", "C24"}

    def test_code_defines_the_full_permit_set(self):
        from harness.runner import NEGATIVE_CONTROLS

        self.assertEqual(set(NEGATIVE_CONTROLS), self.EXPECTED,
                         "code's NEGATIVE_CONTROLS is not the set of PERMIT cases")

    def test_every_control_is_actually_predicted_permit(self):
        """Cross-check against the fixtures: each control must predict PERMIT."""
        from harness.fixtures import build_phase1, load_parent

        parent, _ = load_parent()
        predictions = {f.case_id: f.predicted_decision for f in build_phase1(parent)}
        for case_id in self.EXPECTED:
            if case_id in predictions:  # phase-1 subset
                self.assertEqual(
                    predictions[case_id], "PERMIT",
                    f"{case_id} is a negative control but predicts "
                    f"{predictions[case_id]}",
                )

    def test_no_permit_phase1_case_is_omitted_from_controls(self):
        from harness.fixtures import build_phase1, load_parent
        from harness.runner import NEGATIVE_CONTROLS

        parent, _ = load_parent()
        permit_cases = {
            f.case_id for f in build_phase1(parent)
            if f.predicted_decision == "PERMIT"
        }
        self.assertTrue(
            permit_cases <= set(NEGATIVE_CONTROLS),
            f"phase-1 PERMIT cases {permit_cases} not all in "
            f"NEGATIVE_CONTROLS {set(NEGATIVE_CONTROLS)}",
        )

    def test_prereg_51_count_matches(self):
        prereg = read(PREREG)
        header = re.search(r"### 5\.1 Negative controls[^\n]*\((\d+)\)", prereg)
        self.assertIsNotNone(header, "no §5.1 negative-controls header with a count")
        self.assertEqual(int(header.group(1)), len(self.EXPECTED),
                         "§5.1 count disagrees with the PERMIT-case set")

    def test_h5_falsification_names_the_control_set(self):
        """H5 must reference the negative controls as a set, not a stale range."""
        prereg = read(PREREG)
        h5 = re.search(r"\|\s*H5\s*\|([^\n]+)\|", prereg)
        self.assertIsNotNone(h5)
        # must not hard-code the old "C01–C05" range that omits C23/C24
        self.assertNotIn("C01–C05", h5.group(1),
                         "H5 still names the stale C01–C05 range")


class TestTestCountConsistent(unittest.TestCase):
    """The test count stated in the README must match the actual suite size."""

    def setUp(self):
        loader = unittest.TestLoader()
        self.actual = loader.discover(str(ROOT / "tests")).countTestCases()

    def test_readme_states_one_test_count_everywhere(self):
        counts = set(re.findall(r"(\d+)\s+tests", read(README)))
        self.assertEqual(
            len(counts), 1,
            f"README states multiple test counts: {sorted(counts)}",
        )

    def test_readme_count_matches_actual_suite(self):
        counts = {int(c) for c in re.findall(r"(\d+)\s+tests", read(README))}
        for stated in counts:
            self.assertEqual(
                stated, self.actual,
                f"README says {stated} tests, suite has {self.actual}",
            )


class TestContractFrozenState(unittest.TestCase):
    """A contract the manifest reports FROZEN must itself say FROZEN, with its
    freeze fields filled — not DRAFT with blank placeholders."""

    def setUp(self):
        self.contract = read(CONTRACT)
        self.manifest = json.loads(read(MANIFEST))

    def test_manifest_reports_stage_a_frozen(self):
        self.assertEqual(self.manifest["stage_a_status"], "FROZEN")

    def test_contract_status_matches_manifest(self):
        status_line = next(
            l for l in self.contract.split("\n")
            if l.startswith("**contract_status:**")
        )
        self.assertIn("FROZEN", status_line,
                      "manifest says FROZEN but contract still says DRAFT")

    def test_contract_freeze_fields_are_filled(self):
        for field in ("date_frozen", "contract_digest"):
            line = next(
                l for l in self.contract.split("\n")
                if l.startswith(f"**{field}:**")
            )
            self.assertNotIn("_(", line,
                             f"{field} is still an unfilled placeholder: {line!r}")

    def test_contract_digest_matches_manifest(self):
        m = re.search(r"\*\*contract_digest:\*\*\s*`?([0-9a-f]{64})`?", self.contract)
        self.assertIsNotNone(m, "no 64-hex contract_digest in the contract header")
        self.assertEqual(
            m.group(1), self.manifest["stage_a"]["contract_digest"],
            "contract's self-declared digest disagrees with the manifest",
        )


class TestOsfTimelineUnambiguous(unittest.TestCase):
    """The OSF text must not imply the data didn't exist; it was collected before
    registration and only wired in afterward."""

    def test_registration_text_distinguishes_collected_from_wired(self):
        osf = read("protocol/OSF-REGISTRATION.md")
        # If it mentions the fixture/data timing at all, it must not leave
        # "not yet wired" to be read as "did not exist".
        if "not yet wired" in osf or "Stage B" in osf:
            self.assertTrue(
                "collected" in osf and "wired" in osf,
                "OSF text mentions Stage B timing but doesn't distinguish "
                "collected-before-registration from wired-in-after",
            )


if __name__ == "__main__":
    unittest.main(verbosity=2)

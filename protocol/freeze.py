"""
Freeze procedure.

Computes the digests that make the study's artifacts content-addressed, and
emits a manifest recording exactly what was frozen and when.

Two properties this has to have, or the digests are decoration:

1. REPRODUCIBLE. A second party running this against the same source tree must
   get the same digests. That means no timestamps, no uid/gid, no filesystem
   ordering, and no absolute paths inside the hashed material. Python's tarfile
   records mtime and ownership by default, so the tarball is built with those
   normalized rather than taken from disk.

2. SELF-EXCLUDING where required. The contract digest is computed over the
   contract with its own digest lines blanked, since a document cannot contain
   its own hash. The same circularity that makes "sign the receipt" ambiguous
   (finding CANON-02) applies here, so the blanking rule is stated explicitly
   rather than assumed.

Freeze happens in two stages, and the split is deliberate:

  STAGE A — code and contract. Depends on nothing external. Freezable now.
  STAGE B — fixtures. Depends on the collected session-1 artifact, which is the
            parent for every phase-1 successor. Cannot be frozen until that
            artifact is wired in.

Stage A digests do not change when stage B lands. Recording them separately
means the code freeze is not held hostage to a data dependency, and the manifest
shows which stage each digest belongs to.
"""

from __future__ import annotations

import hashlib
import io
import json
import re
import sys
import tarfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Source included in implementation_digest. Ordered explicitly rather than
# globbed: a glob would silently absorb a new file and change the digest
# without anyone deciding that it should.
CAPABILITY_SOURCES = (
    "capability/__init__.py",
    "capability/decode.py",
    "capability/table.py",
)

VERIFIER_SOURCES = (
    "verifier/__init__.py",
    "verifier/receipt.py",
)

CANON_SOURCES = (
    "canon/__init__.py",
    "canon/corpus.py",
    "canon/differ.py",
    "canon/engine.py",
    "canon/numbers.py",
    "canon/ruleset.py",
    "canon/rulesets/__init__.py",
    "canon/rulesets/scqos.py",
)

HARNESS_SOURCES = (
    "harness/__init__.py",
    "harness/divergence.py",
    "harness/fixtures.py",
    "harness/mocks.py",
    "harness/runner.py",
)

CONTRACT_PATH = "protocol/CONTRACT-qec-syndrome-decode-v1.1.0.md"
PREREG_PATH = "protocol/PREREG-scqos-conformance-v1.1.0.md"

# Lines in the contract that carry digests. Blanked before hashing, because a
# document cannot contain its own hash.
DIGEST_LINE_PATTERN = re.compile(
    r"^\*\*(contract_digest|implementation_digest|decode_table_digest):\*\*.*$",
    re.MULTILINE,
)


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def reproducible_tarball(paths: tuple[str, ...], root: Path = ROOT) -> bytes:
    """Build a tarball whose bytes depend only on file contents and names.

    mtime, uid, gid, uname and gname are all normalized. Without this the
    digest changes every time the tree is checked out, which would make
    "implementation_digest" a record of when the file was written rather than
    of what it contains.
    """
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w", format=tarfile.GNU_FORMAT) as archive:
        for relative in sorted(paths):
            source = root / relative
            data = source.read_bytes()
            info = tarfile.TarInfo(name=relative)
            info.size = len(data)
            info.mtime = 0
            info.mode = 0o644
            info.uid = info.gid = 0
            info.uname = info.gname = ""
            info.type = tarfile.REGTYPE
            archive.addfile(info, io.BytesIO(data))
    return buffer.getvalue()


def canonical_document_bytes(path: Path, blank_digest_lines: bool = False) -> bytes:
    """Canonical form of a markdown document for hashing.

    UTF-8, LF line endings, single trailing newline, no trailing whitespace —
    the rule stated in contract §11. Applied here rather than assumed, so a
    document edited on a different platform hashes the same.
    """
    text = path.read_text(encoding="utf-8")
    if blank_digest_lines:
        text = DIGEST_LINE_PATTERN.sub(
            lambda m: f"**{m.group(1)}:** _(blanked for digest computation)_", text
        )
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = "\n".join(line.rstrip() for line in text.split("\n"))
    return (text.rstrip("\n") + "\n").encode("utf-8")


def compute_stage_a() -> dict:
    """Digests that depend on nothing external."""
    sys.path.insert(0, str(ROOT))
    from capability.decode import CAPABILITY_VERSION
    from capability.table import table_artifact, table_digest

    contract = ROOT / CONTRACT_PATH
    prereg = ROOT / PREREG_PATH

    table = table_artifact(3, 3)

    digests = {
        "capability_version": CAPABILITY_VERSION,
        "implementation_digest": hashlib.sha256(
            reproducible_tarball(CAPABILITY_SOURCES)
        ).hexdigest(),
        "decode_table_digest": table_digest(table),
        "decode_table_entries": len(table["table"]),
        "verifier_digest": hashlib.sha256(
            reproducible_tarball(VERIFIER_SOURCES)
        ).hexdigest(),
        "canonicalizer_digest": hashlib.sha256(
            reproducible_tarball(CANON_SOURCES)
        ).hexdigest(),
        "harness_digest": hashlib.sha256(
            reproducible_tarball(HARNESS_SOURCES)
        ).hexdigest(),
    }

    if contract.exists():
        digests["contract_digest"] = hashlib.sha256(
            canonical_document_bytes(contract, blank_digest_lines=True)
        ).hexdigest()
    if prereg.exists():
        digests["preregistration_digest"] = hashlib.sha256(
            canonical_document_bytes(prereg)
        ).hexdigest()

    return digests


def compute_stage_b() -> dict:
    """Fixture digests. Requires the collected session-1 artifact."""
    sys.path.insert(0, str(ROOT))
    from harness.fixtures import build_phase1, load_parent

    parent, is_real = load_parent()
    fixtures = build_phase1(parent)

    entries = {}
    for fixture in fixtures:
        raw = fixture.bytes_()
        entries[fixture.case_id] = {
            "artifact_digest": hashlib.sha256(raw).hexdigest() if raw else None,
            "predicted_decision": fixture.predicted_decision,
            "predicted_failing_predicates": list(fixture.predicted_predicates),
        }

    return {
        "parent_is_collected_data": is_real,
        "parent_collection_start": parent["collection_start"],
        "fixture_set_digest": hashlib.sha256(
            json.dumps(entries, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest(),
        "fixtures": entries,
    }


def freeze(write: bool = False) -> dict:
    stage_a = compute_stage_a()
    stage_b = compute_stage_b()
    frozen = stage_b["parent_is_collected_data"]

    manifest = {
        "manifest_version": "1.0.0",
        "protocol_version": "1.1.0",
        "frozen_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "stage_a": stage_a,
        "stage_a_status": "FROZEN",
        "stage_b": stage_b,
        "stage_b_status": "FROZEN" if frozen else "PROVISIONAL — parent artifact is a stub",
        "digest_algorithm": "sha256",
        "notes": [
            "Stage A depends on nothing external and is frozen independently of "
            "stage B; its digests do not change when stage B lands.",
            "implementation_digest is taken over a tarball with mtime, mode and "
            "ownership normalized, so it records content rather than checkout time.",
            "contract_digest is computed with the contract's own digest lines "
            "blanked; a document cannot contain its own hash.",
            "Markdown canonicalization for hashing: UTF-8, LF, single trailing "
            "newline, no trailing whitespace (contract §11).",
        ],
    }

    if write:
        path = ROOT / "protocol" / "FREEZE-MANIFEST.json"
        path.write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
    return manifest


def report(manifest: dict) -> str:
    a, b = manifest["stage_a"], manifest["stage_b"]
    lines = [
        "freeze manifest",
        f"protocol {manifest['protocol_version']}  |  {manifest['frozen_at']}",
        "",
        f"STAGE A — code and contract   [{manifest['stage_a_status']}]",
    ]
    for key in sorted(a):
        value = a[key]
        rendered = value if isinstance(value, (str, int)) else str(value)
        if isinstance(rendered, str) and len(rendered) == 64:
            rendered = rendered[:32] + "…"
        lines.append(f"  {key:<26} {rendered}")

    lines.append("")
    lines.append(f"STAGE B — fixtures            [{manifest['stage_b_status']}]")
    lines.append(f"  {'parent_is_collected_data':<26} {b['parent_is_collected_data']}")
    lines.append(f"  {'parent_collection_start':<26} {b['parent_collection_start']}")
    lines.append(f"  {'fixture_set_digest':<26} {b['fixture_set_digest'][:32]}…")
    lines.append("")
    lines.append(f"  {'case':<7} {'predicted':<18} {'artifact digest':<20} predicted failing")
    lines.append("  " + "-" * 74)
    for case_id in sorted(b["fixtures"]):
        entry = b["fixtures"][case_id]
        digest = entry["artifact_digest"]
        lines.append(
            f"  {case_id:<7} {entry['predicted_decision']:<18} "
            f"{(digest[:18] + '…') if digest else '— (no artifact)':<20} "
            f"{entry['predicted_failing_predicates'] or '—'}"
        )

    if not b["parent_is_collected_data"]:
        lines.append("")
        lines.append("  Stage B is PROVISIONAL: fixtures derive from the stub parent.")
        lines.append("  Wire fixtures/session-1.json and re-run to freeze them.")
        lines.append("  Stage A digests above are unaffected.")

    return "\n".join(lines)


if __name__ == "__main__":
    write = "--write" in sys.argv
    print(report(freeze(write=write)))
    if write:
        print("\nwrote protocol/FREEZE-MANIFEST.json")

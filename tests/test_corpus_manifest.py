"""Tests for corpus/validate_manifest.py.

Exercises validate_manifest() against the real committed manifest+corpus (must return no
errors), and against two scratch-mutated copies: one with a tampered sha256 (must report
the mismatch), one with every entry for a single category removed (must report the
zero-count category).
"""

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
CORPUS_DIR = REPO_ROOT / "corpus" / "public"
MANIFEST_PATH = REPO_ROOT / "corpus" / "manifest.json"
sys.path.insert(0, str(REPO_ROOT / "corpus"))

import validate_manifest  # noqa: E402


def test_real_manifest_and_corpus_are_valid():
    errors = validate_manifest.validate_manifest(str(MANIFEST_PATH), str(CORPUS_DIR))
    assert errors == []


def test_tampered_sha256_is_detected(tmp_path):
    entries = json.loads(MANIFEST_PATH.read_text())
    assert entries, "manifest must have at least one entry to tamper with"
    entries[0]["sha256"] = "0" * 64

    scratch_manifest = tmp_path / "manifest.json"
    scratch_manifest.write_text(json.dumps(entries))

    errors = validate_manifest.validate_manifest(str(scratch_manifest), str(CORPUS_DIR))
    assert any("sha256 mismatch" in e for e in errors)


def test_zero_count_category_is_detected(tmp_path):
    entries = json.loads(MANIFEST_PATH.read_text())
    target_category = "type3"
    assert any(target_category in e["categories"] for e in entries), (
        f"fixture assumption broken: no entry currently declares {target_category!r}"
    )
    for entry in entries:
        entry["categories"] = [c for c in entry["categories"] if c != target_category]

    scratch_manifest = tmp_path / "manifest.json"
    scratch_manifest.write_text(json.dumps(entries))

    errors = validate_manifest.validate_manifest(str(scratch_manifest), str(CORPUS_DIR))
    assert any(target_category in e for e in errors)


def test_all_15_canonical_categories_defined():
    assert len(validate_manifest.CANONICAL_CATEGORIES) == 15

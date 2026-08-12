"""Tests for tools/check_corpus_size.py — scratch fixtures on both sides of the 100-document
Gate G0 threshold. Deliberately does NOT run against the real manifests (those legitimately
sit below 100 until the private tier is populated per Task 3's checkpoint — that is the gate
working as designed, not a bug this test should fail on).
"""

import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT / "tools"))

import check_corpus_size  # noqa: E402


def _write_manifest(path: Path, count: int) -> None:
    path.write_text(json.dumps([{"filename": f"f{i}.pdf"} for i in range(count)]))


def test_below_threshold_reports_failure(tmp_path):
    public = tmp_path / "public.json"
    private = tmp_path / "private.json"
    _write_manifest(public, 40)
    _write_manifest(private, 30)

    combined = check_corpus_size.check_corpus_size(str(public), str(private))
    assert combined == 70

    result = subprocess.run(
        [sys.executable, str(REPO_ROOT / "tools" / "check_corpus_size.py"), str(public), str(private)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1
    assert "70" in result.stdout
    assert "public=40" in result.stdout
    assert "private=30" in result.stdout


def test_at_or_above_threshold_reports_success(tmp_path):
    public = tmp_path / "public.json"
    private = tmp_path / "private.json"
    _write_manifest(public, 45)
    _write_manifest(private, 55)

    combined = check_corpus_size.check_corpus_size(str(public), str(private))
    assert combined == 100

    result = subprocess.run(
        [sys.executable, str(REPO_ROOT / "tools" / "check_corpus_size.py"), str(public), str(private)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "100" in result.stdout


def test_missing_private_manifest_treated_as_zero(tmp_path):
    public = tmp_path / "public.json"
    _write_manifest(public, 5)
    missing_private = tmp_path / "does-not-exist.json"

    combined = check_corpus_size.check_corpus_size(str(public), str(missing_private))
    assert combined == 5

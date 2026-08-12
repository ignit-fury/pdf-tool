"""Tests for tools/license_gate.py.

Two tests assert the captured red/green proof of the AGPL trap firing and
reverting (pdf2docx -> transitive PyMuPDF). One live test is the regression
guard going forward: the gate must stay clean against the current environment.
"""

import sys
from pathlib import Path

FIXTURES = Path(__file__).parent / "fixtures"
REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT / "tools"))

import license_gate  # noqa: E402


def test_red_proof_shows_pymupdf_agpl_trap_fired():
    content = (FIXTURES / "agpl_gate_proof_red.txt").read_text().lower()
    assert "pymupdf" in content
    assert "agpl" in content or "affero" in content
    assert "exit_code=1" in content


def test_green_proof_shows_clean_exit_after_revert():
    content = (FIXTURES / "agpl_gate_proof_green.txt").read_text()
    assert "exit_code=0" in content


def test_check_installed_distributions_is_clean_in_current_environment():
    """Regression guard: the pdf2docx trap must stay fully reverted."""
    assert license_gate.check_installed_distributions() == []

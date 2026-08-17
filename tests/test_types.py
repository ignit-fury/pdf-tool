"""Tests for engine.types -- the CodeToGlyph / CodeToUnicode contract (TEXT-05)."""

import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT))

from engine.types import CharCode, CodeToGlyph, CodeToUnicode, display_text, encode_for_output  # noqa: E402


def test_types_import_and_stubs_raise() -> None:
    """engine.types imports cleanly; stub functions raise NotImplementedError."""
    fwd: CodeToGlyph = {}
    tou: CodeToUnicode = {}

    with pytest.raises(NotImplementedError):
        encode_for_output("x", fwd)

    with pytest.raises(NotImplementedError):
        display_text([CharCode(1)], tou)


def test_mypy_rejects_inverted_tounicode() -> None:
    """mypy --strict must reject the inverted-/ToUnicode-as-CodeToGlyph fixture.

    This is the load-bearing negative test: inverting a CodeToUnicode and
    passing it where a CodeToGlyph is expected must be a type error, proving
    the two maps are not interchangeable at the type level.
    """
    result = subprocess.run(
        [
            "uv",
            "run",
            "--frozen",
            "mypy",
            "--strict",
            "tests/fixtures/mypy_inverted_tounicode.py",
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0, (
        f"mypy --strict should reject the inverted ToUnicode fixture, "
        f"but exited 0.\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )

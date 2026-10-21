"""Tests for harness/structural_diff.py.

Proves confined_instruction_diff() actually discriminates: zero changed on byte-identical
content-stream parts, one changed on a single-instruction operand edit, and degrades to
"fully changed" when instruction counts differ (03-RESEARCH.md Pitfall 3 -- a whole-file
`qpdf --qdf` diff is not a valid confined-diff check; this targeted comparison is). All
fixtures here are small hand-written content-stream byte literals -- no real PDF needed.
"""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT / "harness"))

from structural_diff import confined_instruction_diff  # noqa: E402

# BT / (Hello) Tj / ET -- three instructions, realistic multi-instruction fixture.
_IDENTICAL_OLD = b"BT\n(Hello) Tj\nET"
_IDENTICAL_NEW = b"BT\n(Hello) Tj\nET"

# Same instruction count (3), one operand changed on the Tj instruction only.
_ONE_CHANGED_OLD = b"BT\n(Hello) Tj\nET"
_ONE_CHANGED_NEW = b"BT\n(World) Tj\nET"

# Instruction count changed: an extra `0 0 0 rg` operator inserted.
_LENGTH_MISMATCH_OLD = b"BT\n(Hello) Tj\nET"
_LENGTH_MISMATCH_NEW = b"BT\n(Hello) Tj\n0 0 0 rg\nET"


def test_confined_diff_zero_on_identical_streams():
    changed, total = confined_instruction_diff(_IDENTICAL_OLD, _IDENTICAL_NEW)
    assert changed == 0
    assert total == 3
    assert total > 1


def test_confined_diff_one_on_single_instruction_change():
    changed, total = confined_instruction_diff(_ONE_CHANGED_OLD, _ONE_CHANGED_NEW)
    assert changed == 1
    assert total == 3


def test_confined_diff_degrades_to_fully_changed_on_length_mismatch():
    changed, total = confined_instruction_diff(_LENGTH_MISMATCH_OLD, _LENGTH_MISMATCH_NEW)
    assert changed == total
    assert total == 4  # max(3, 4) instructions


def test_confined_diff_handles_empty_streams():
    changed, total = confined_instruction_diff(b"", b"")
    assert changed == 0
    assert total == 0


def test_no_eval_or_exec_in_structural_diff_module():
    source = (REPO_ROOT / "harness" / "structural_diff.py").read_text()
    assert "eval(" not in source
    assert "exec(" not in source

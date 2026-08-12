"""Tests for harness/masked_diff.py.

Proves masked_pixel_diff() actually discriminates: zero on byte-identical PNGs, >= 1 on a
single-pixel-changed pair. This is the RED/GREEN proof required by Plan 01-04 Task 2 — the
masked-diff assertion is the primary correctness assertion for the whole project and must be
shown to work, not just asserted to work.
"""

import sys
from pathlib import Path

from PIL import Image

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT / "harness"))

from masked_diff import masked_pixel_diff  # noqa: E402


def _make_png(path: Path, size=(20, 20), color="white"):
    Image.new("RGB", size, color).save(path)
    return path


def test_identical_pngs_diff_to_zero(tmp_path):
    a = _make_png(tmp_path / "a.png")
    b = _make_png(tmp_path / "b.png")
    assert masked_pixel_diff(a, b) == 0


def test_single_pixel_change_is_discriminated(tmp_path):
    a = _make_png(tmp_path / "a.png")
    img_b = Image.open(a).convert("RGB")
    img_b.putpixel((5, 5), (0, 0, 0))
    b = tmp_path / "b.png"
    img_b.save(b)

    assert masked_pixel_diff(a, b) >= 1


def test_masked_region_is_ignored(tmp_path):
    a = _make_png(tmp_path / "a.png")
    img_b = Image.open(a).convert("RGB")
    img_b.putpixel((5, 5), (0, 0, 0))
    b = tmp_path / "b.png"
    img_b.save(b)

    # The changed pixel (5, 5) is inside this mask box — masking it must bring the diff
    # back to zero, proving the mask is actually applied and not just accepted and ignored.
    assert masked_pixel_diff(a, b, mask=(0, 0, 10, 10)) == 0

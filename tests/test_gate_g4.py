"""G4 local proof: full-document text changes and disjoint renderer masks.

The corpus fixture is a 40-page public technical document, not a legal contract.
Fast negative controls prevent a wide enclosing mask or unchanged output from
being mistaken for a successful batch-fidelity proof.
"""
from pathlib import Path

from PIL import Image
import pytest

from harness.masked_diff import masked_pixel_diff


def _union_diff(before: Path, after: Path, masks: list[tuple[int, int, int, int]], scratch: Path) -> int:
    return masked_pixel_diff(before, after)


def _assert_page_pixels(before: Path, after: Path, masks: list[tuple[int, int, int, int]], scratch: Path, *, changed: bool) -> tuple[int, int]:
    unmasked = masked_pixel_diff(before, after)
    outside = _union_diff(before, after, masks, scratch)
    assert outside == 0, f"outside-region changed pixels: {outside}"
    if changed:
        assert unmasked > 0, "batch output must have a nonvacuous visible change"
    return unmasked, outside


def _images(tmp_path, points):
    before = tmp_path / 'before.png'
    after = tmp_path / 'after.png'
    image = Image.new('RGB', (100, 100), 'white')
    image.save(before)
    for point in points:
        image.putpixel(point, (0, 0, 0))
    image.save(after)
    return before, after


def test_mask_union_excludes_only_each_edited_region(tmp_path):
    before, after = _images(tmp_path, [(15, 15), (85, 85)])
    assert _assert_page_pixels(before, after, [(10, 10, 20, 20), (80, 80, 90, 90)], tmp_path / 'masked', changed=True) == (2, 0)


def test_outside_change_between_disjoint_masks_is_detected(tmp_path):
    before, after = _images(tmp_path, [(15, 15), (50, 50), (85, 85)])
    assert _union_diff(before, after, [(10, 10, 20, 20), (80, 80, 90, 90)], tmp_path / 'masked') == 1


def test_nonvacuous_batch_cannot_pass_with_unchanged_output(tmp_path):
    before, after = _images(tmp_path, [])
    with pytest.raises(AssertionError, match='nonvacuous'):
        _assert_page_pixels(before, after, [(10, 10, 20, 20)], tmp_path / 'masked', changed=True)


def test_unchanged_page_is_compared_without_a_mask(tmp_path):
    before, after = _images(tmp_path, [(50, 50)])
    with pytest.raises(AssertionError, match='outside-region'):
        _assert_page_pixels(before, after, [], tmp_path / 'masked', changed=False)

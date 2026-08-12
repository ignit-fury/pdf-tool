"""Masked pixel-identical diff — the primary correctness assertion (Layer 2/3 of
research/ARCHITECTURE.md's testing strategy).

This is NOT a byte-level comparison. It compares rendered pixels between two PNGs, ignoring
any region covered by an optional mask. On Phase 1's identity transform there is no edited
run to mask, so `mask=None` compares the whole page — the entire unedited output must be
pixel-identical across engines. Byte-level round-trip comparison against the input PDF is
never a valid correctness test (qpdf-class libraries legitimately repair broken xrefs,
producing different bytes for a structurally equivalent document) and does not appear here.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageChops


def masked_pixel_diff(
    png_a_path: str | Path,
    png_b_path: str | Path,
    mask: tuple[int, int, int, int] | None = None,
) -> int:
    """Count differing pixels between two same-size PNGs, ignoring `mask` if given.

    `mask` is a bounding box (left, top, right, bottom) in pixel coordinates. Pixels inside
    the mask are never compared. `None` means no mask — compare the whole image.

    Implemented with Pillow's C-level ImageChops (no new dependency, no pure-Python
    per-pixel loop) — a page render at 150 DPI is well over a million pixels, and a
    per-pixel Python loop over every corpus page/engine pair would be the slow path.
    """
    img_a = Image.open(png_a_path).convert("RGB")
    img_b = Image.open(png_b_path).convert("RGB")

    if img_a.size != img_b.size:
        raise ValueError(f"size mismatch: {png_a_path} is {img_a.size}, {png_b_path} is {img_b.size}")

    diff = ImageChops.difference(img_a, img_b)
    if mask is not None:
        left, top, right, bottom = mask
        diff.paste((0, 0, 0), (left, top, right, bottom))

    # Collapse to "did any channel differ at this pixel?" via per-channel max, then read
    # off the histogram bucket for value 0 (no difference) — both are C-level Pillow ops.
    red, green, blue = diff.split()
    max_channel = ImageChops.lighter(ImageChops.lighter(red, green), blue)
    histogram = max_channel.histogram()
    return sum(histogram[1:])  # pixels where the max channel difference is > 0


if __name__ == "__main__":
    import sys

    from PIL import Image as _Image

    # Minimal self-check: identical images diff to 0; a single-pixel change diffs to >= 1.
    tmp = Path("/tmp/masked_diff_selfcheck")
    tmp.mkdir(exist_ok=True)
    a = _Image.new("RGB", (10, 10), "white")
    a.save(tmp / "a.png")
    a.save(tmp / "b_identical.png")
    b_diff = a.copy()
    b_diff.putpixel((5, 5), (0, 0, 0))
    b_diff.save(tmp / "b_diff.png")

    assert masked_pixel_diff(tmp / "a.png", tmp / "b_identical.png") == 0
    assert masked_pixel_diff(tmp / "a.png", tmp / "b_diff.png") >= 1
    print("OK: masked_pixel_diff discriminates identical vs single-pixel-changed images")
    sys.exit(0)

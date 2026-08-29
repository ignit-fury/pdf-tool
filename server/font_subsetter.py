"""Subset a TTF to only the glyphs needed for a given text string.

Used when replacement text contains characters not in the original font's
encoding — the server substitutes a bundled font subsetted to the needed glyphs.

Usage:
    from server.font_subsetter import subset_font

    path = subset_font(
        src_ttf="/path/to/full.ttf",
        text="Hello world",
        out_dir="/tmp/subsetted",
    )
    # -> /tmp/subsetted/subset_<hash>.ttf
"""

from __future__ import annotations

import hashlib
import os
import shutil
import tempfile
from pathlib import Path
from typing import Optional

from fontTools.ttLib import TTFont
from fontTools.subset import Subsetter


def _text_to_unicode_codepoints(text: str) -> list[int]:
    """Return sorted unique Unicode codepoints in `text`."""
    return sorted(set(ord(ch) for ch in text))


def subset_font(
    src_ttf: str | Path,
    text: str,
    out_dir: Optional[str | Path] = None,
    rename: Optional[str] = None,
) -> Path:
    """Subset `src_ttf` to only the glyphs needed to render `text`.

    Args:
        src_ttf: Path to the source TrueType/OpenType font.
        text: The text string whose glyphs should be retained.
        out_dir: Directory to write the subsetted font into. Defaults to a
            temporary directory (the caller is responsible for cleaning it up).
        rename: Optional basename for the output file. Defaults to
            ``subset_<sha256-of-text>.ttf``.

    Returns:
        Path to the newly-created subsetted TTF.
    """
    src = Path(src_ttf)
    if not src.exists():
        raise FileNotFoundError(f"Font not found: {src}")

    codepoints = _text_to_unicode_codepoints(text)
    if not codepoints:
        raise ValueError("text must contain at least one character")

    out_dir = Path(out_dir) if out_dir else Path(tempfile.mkdtemp(prefix="font_subset_"))
    out_dir.mkdir(parents=True, exist_ok=True)

    if rename is None:
        h = hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]
        rename = f"subset_{h}.ttf"

    out_path = out_dir / rename

    # Work on a copy so the original is never modified.
    with tempfile.NamedTemporaryFile(suffix=".ttf", delete=False) as tmp:
        tmp_path = Path(tmp.name)

    try:
        shutil.copy2(src, tmp_path)

        font = TTFont(tmp_path)
        subsetter = Subsetter()
        # Tell the subsetter which Unicode codepoints we need.
        subsetter.populate(unicodes=codepoints)
        subsetter.subset(font)

        # Save in place. close() writes the updated font tables back.
        font.save(out_path)
        font.close()
    finally:
        tmp_path.unlink(missing_ok=True)

    return out_path


if __name__ == "__main__":
    import argparse

    p = argparse.ArgumentParser(description="Subset a TTF to the glyphs needed for TEXT")
    p.add_argument("font", help="Path to source TTF")
    p.add_argument("text", help="Text whose glyphs to keep")
    p.add_argument("-o", "--out-dir", default=None, help="Output directory (default: temp dir)")
    args = p.parse_args()

    out = subset_font(args.font, args.text, out_dir=args.out_dir)
    print(f"Subset written to: {out}")
    print(f"Size: {out.stat().st_size} bytes")

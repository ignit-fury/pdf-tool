"""03-01 Task 1: fonts/ -- the bundled Liberation Sans/Serif/Mono trio (D-07/FONT-01).

Two tests:
1. `test_bundled_font_set_is_complete` -- exact-set assertion that `fonts/` contains
   exactly the 12 expected filenames plus the shared license. EXPECTED_FONT_FILES is a
   fixed frozenset, not a glob computed at collection time -- decouples "what should
   exist" from "what does exist" so this test fails meaningfully even if `fonts/` is
   empty or missing files, matching this codebase's own
   KNOWN_MALFORMED_WALK_FAILURES-style exact-set convention (tests/test_roundtrip.py).
2. `test_bundled_font_fstype_is_installable` -- parametrized over all 12 files, per
   03-RESEARCH.md Pitfall 11's exact check: `fsType == 0` (Installable Embedding).
   Sans-Regular was already verified this way (from spike/fixtures/) in Phase 1; this
   is the first time Serif and Mono get the check at all -- OFL licensing does not by
   itself guarantee fsType=0, so it is verified directly rather than assumed.

No document content in assertion messages -- filenames and counts only, per this
project's standing convention (T-02-04).
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fontTools.ttLib import TTFont

REPO_ROOT = Path(__file__).parent.parent
FONTS_DIR = REPO_ROOT / "fonts"

EXPECTED_FONT_FILES = frozenset(
    {
        "LiberationSans-Regular.ttf",
        "LiberationSans-Bold.ttf",
        "LiberationSans-Italic.ttf",
        "LiberationSans-BoldItalic.ttf",
        "LiberationSerif-Regular.ttf",
        "LiberationSerif-Bold.ttf",
        "LiberationSerif-Italic.ttf",
        "LiberationSerif-BoldItalic.ttf",
        "LiberationMono-Regular.ttf",
        "LiberationMono-Bold.ttf",
        "LiberationMono-Italic.ttf",
        "LiberationMono-BoldItalic.ttf",
    }
)


def test_bundled_font_set_is_complete() -> None:
    found = {p.name for p in FONTS_DIR.glob("*.ttf")}
    assert found == EXPECTED_FONT_FILES, (
        f"fonts/ .ttf set changed: "
        f"new={found - EXPECTED_FONT_FILES} "
        f"missing={EXPECTED_FONT_FILES - found}"
    )
    assert (FONTS_DIR / "LICENSE-OFL.txt").exists()


@pytest.mark.parametrize("filename", sorted(EXPECTED_FONT_FILES))
def test_bundled_font_fstype_is_installable(filename: str) -> None:
    font = TTFont(str(FONTS_DIR / filename))
    fstype = font["OS/2"].fsType
    assert fstype == 0, f"{filename}: fsType={fstype}, expected 0 (Installable)"

"""Tests for spike/playa_decode_probe.py -- Phase 1 ENG-04 spike.

Throwaway per CONTEXT.md's discretion note (the probe's own code doesn't need to survive
into Phase 2), but the plan's acceptance criteria are concrete assertions, not vibes: the
probe must actually decode each selected fixture without an unhandled exception and yield
glyph_count > 0. This module makes those two claims real.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# Sibling-module import, not a package import: spike/ has no __init__.py and the probe is
# invoked directly as `python spike/playa_decode_probe.py ...` per its own CLI contract
# (mirrors harness/run_corpus_harness.py's sys.path.insert pattern for the same reason).
sys.path.insert(0, str(Path(__file__).parent.parent / "spike"))

from playa_decode_probe import (  # noqa: E402
    REQUIRED_CATEGORIES,
    decode_file,
    looks_sane,
    select_fixtures,
)

REPO_ROOT = Path(__file__).parent.parent
MANIFEST_PATH = REPO_ROOT / "corpus" / "manifest.json"
CORPUS_DIR = REPO_ROOT / "corpus" / "public"


def _manifest() -> list[dict]:
    return json.loads(MANIFEST_PATH.read_text())


def test_select_fixtures_covers_required_categories():
    fixtures = select_fixtures(_manifest(), min_files=4)
    assert len(fixtures) >= 4
    covered = {c for entry in fixtures for c in entry.get("categories", [])}
    assert REQUIRED_CATEGORIES <= covered


def test_playa_decodes_selected_fixtures_with_glyphs():
    fixtures = select_fixtures(_manifest(), min_files=4)
    for entry in fixtures:
        pdf_path = CORPUS_DIR / entry["filename"]
        outcome = decode_file(pdf_path, "playa", max_pages=5, timeout_s=30)
        assert outcome.ok, f"{entry['filename']}: {outcome.error}"
        assert outcome.glyph_count > 0, f"{entry['filename']}: zero glyphs decoded"
        assert looks_sane(outcome.sample_text), f"{entry['filename']}: decoded text looks garbled"


def test_looks_sane_rejects_empty_and_garbage():
    assert not looks_sane("")
    assert not looks_sane("����")
    assert looks_sane("Request for Taxpayer Identification Number")

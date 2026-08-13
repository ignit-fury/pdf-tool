"""Measure the TT-d/TT-e unusable-cmap population among the corpus's TT-b fonts (D-04 Open
Question 1; 02-RESEARCH.md Section 1 forward-encoding table + "Open Questions" item 1).

TT-b = an embedded, symbolic, simple TrueType font whose PDF font dictionary has no /Encoding
entry (37 of 216 documents per Section 1). Within that population, this script measures the one
thing Section 1 leaves unmeasured: how many of those fonts additionally land in the two REFUSE
branches that key off the *embedded font program's* cmap subtables, versus being usable —

  TT-d: the cmap table has a (3,1) subtable but neither (3,0) nor (1,0).
        ISO 32000-1 requires (3,0) or (1,0) for a symbolic font; ISO 19005-2 SS6.2.11.6 permits
        a sole non-standard cmap; veraPDF/Callas/3-Heights each behave differently. REFUSE.
  TT-e: the font program has no cmap table at all.
        PDFium falls back to identity, PDFBox to `post` -- both are guesses. REFUSE for editing.
  usable: a (3,0) or (1,0) subtable is present, so the TT-b lookup rule has something to consult.

Read-only font-program inspection only: pikepdf walks page /Resources to find qualifying font
dictionaries and hands their /FontFile2 bytes to fontTools; no content-stream interpretation
happens anywhere in this file, and it must never be wired into or import from anything under
engine/ (D-04's independent-prober rule -- see tools/probe_corpus.py's docstring for the same
rule applied to corpus-category verification).

The corpus deliberately contains 17 malformed documents and adversarial font programs, so every
per-document and per-font parse is wrapped in try/except and recorded as a row, never allowed to
crash the run (harness/run_corpus_harness.py's established convention). A font program fontTools
cannot decompile is classified "unparseable" -- a real, separate category, never folded into the
TT-d/TT-e/usable percentages.

[VERIFIED: measured 2026-08-13] Running against the full public corpus (corpus/manifest.json,
corpus/public, 217 documents): 80 embedded, symbolic, no-/Encoding TrueType fonts (TT-b,
deduplicated by PDF object) found across 25 documents.
    TT-d (only (3,1), no (3,0)/(1,0)): 0
    TT-e (no cmap table):              0
    usable ((3,0) or (1,0) present):   80
    unparseable (cmap subtable directory itself unreadable): 0
  Zero document-level open/traversal failures across the 217-document manifest.
  Headline: 0 of 80 examined TT-b fonts (0%) hit TT-d or TT-e -- the measured refusal-rate
  contribution from these two branches is 0%, not "nearer 2% or nearer 10%".

  An earlier run of this script classified 31 of the 80 as "unparseable" because it read the
  cmap via `TTFont()["cmap"]`, which decompiles every subtable body on access -- one malformed
  body then aborted the whole table read. All 31 carry a perfectly readable directory with both
  a (1,0) format-0 and a (3,0) format-4 subtable; only the outer cmap table's declared length in
  the sfnt directory is a few bytes short of what the format-4 subtable body needs (a real
  font-subsetting defect in those fonts, all TimesNewRoman family with IKH*+ subset tags -- see
  parse_cmap_subtable_ids()). Since classify_font_bytes() only needs platformID/platEncID, both
  of which live in the subtable directory ahead of any subtable body, reading the directory
  directly (this module's current approach) classifies all 31 correctly as "usable" without
  touching the malformed bodies at all. "unparseable" remains a real category -- reachable when
  the sfnt table directory or the cmap subtable directory itself cannot be read -- it is just not
  populated by this corpus.
"""

from __future__ import annotations

import argparse
import io
import json
import struct
import sys
from pathlib import Path
from typing import Iterator

import pikepdf
from fontTools.ttLib import TTFont
from fontTools.ttLib.sfnt import SFNTReader

# FontDescriptor /Flags bit 3 (1-indexed) == decimal value 4 -- same bit tools/probe_corpus.py
# checks for the `symbolic_fonts` category.
SYMBOLIC_FLAG_BIT = 1 << 2


def is_symbolic(font_descriptor: pikepdf.Object | None) -> bool:
    if font_descriptor is None:
        return False
    flags = font_descriptor.get("/Flags")
    return flags is not None and bool(int(flags) & SYMBOLIC_FLAG_BIT)


def classify_from_subtable_ids(subtable_ids: set[tuple[int, int]]) -> str:
    """Classify a cmap by its set of (platformID, platEncID) subtable ids into "TT-d", "TT-e",
    or "usable" per the exact rule in this module's docstring / 02-RESEARCH.md A-2/A-3."""
    if not subtable_ids:
        return "TT-e"
    has_3_0 = (3, 0) in subtable_ids
    has_1_0 = (1, 0) in subtable_ids
    has_3_1 = (3, 1) in subtable_ids
    if has_3_1 and not has_3_0 and not has_1_0:
        return "TT-d"
    return "usable"


def classify_font(tt: TTFont) -> str:
    """Classify an already-loaded fontTools TTFont's cmap. Used by this module's unit tests,
    which build small in-memory TTFont fixtures directly. The corpus measurement path does not
    call this -- see classify_font_bytes(), which reads the cmap subtable directory without
    building a TTFont at all (C1 fix, see that function's docstring)."""
    if "cmap" not in tt:
        return "TT-e"
    subtable_ids = {(t.platformID, t.platEncID) for t in tt["cmap"].tables}
    return classify_from_subtable_ids(subtable_ids)


def parse_cmap_subtable_ids(font_bytes: bytes) -> set[tuple[int, int]]:
    """Read the sfnt table directory and, if present, the cmap table's own subtable directory --
    the (platformID, platEncID, offset) triples at the front of the 'cmap' table -- without
    decompiling any subtable body.

    This exists because `TTFont()["cmap"]` (fontTools' normal access path) decompiles every
    cmap subtable's body on first touch, and one malformed body raises for the whole table even
    though the directory preceding it is perfectly readable. This module's real corpus has 31
    fonts exactly like that: a (1,0) format-0 and a (3,0) format-4 subtable, both present in the
    directory, where the outer cmap table's declared length in the sfnt directory is a few bytes
    short of what the format-4 subtable body needs -- a font-subsetting defect that has nothing
    to do with which platform/encoding subtables exist. classify_font() needs only platformID/
    platEncID, both of which live in the directory, so this reads only that.

    Raises whatever the sfnt reader / struct.unpack raises when the *table directory itself* is
    unreadable (bad sfnt header, truncated cmap directory, ...) -- callers must catch and record
    "unparseable" per this module's convention.
    """
    reader = SFNTReader(io.BytesIO(font_bytes))
    if "cmap" not in reader:
        return set()
    cmap_bytes = reader["cmap"]
    _version, num_subtables = struct.unpack_from(">HH", cmap_bytes, 0)
    subtable_ids = set()
    offset = 4
    for _ in range(num_subtables):
        platform_id, plat_enc_id, _subtable_offset = struct.unpack_from(">HHI", cmap_bytes, offset)
        subtable_ids.add((platform_id, plat_enc_id))
        offset += 8
    return subtable_ids


def classify_font_bytes(font_bytes: bytes) -> str:
    """Classify `font_bytes`'s cmap by reading its subtable directory only -- see
    parse_cmap_subtable_ids() for why. Raises whatever that function raises when the table
    directory itself is unreadable -- callers must catch and record "unparseable" per this
    module's convention.
    """
    return classify_from_subtable_ids(parse_cmap_subtable_ids(font_bytes))


def iter_tt_b_fonts(pdf: pikepdf.Pdf) -> Iterator[tuple[str, pikepdf.Object]]:
    """Yield (font_resource_name, font_dict) for every embedded, symbolic, no-/Encoding simple
    TrueType font (TT-b) in `pdf`, deduplicated by PDF object across pages -- the same font
    object is commonly referenced from every page's /Resources.
    """
    seen: set[tuple[int, int]] = set()
    for page in pdf.pages:
        resources = page.get("/Resources") or {}
        for name, font in (resources.get("/Font") or {}).items():
            try:
                key = font.objgen
            except AttributeError:
                continue
            if key in seen:
                continue

            if str(font.get("/Subtype", "")) != "/TrueType":
                continue
            if "/Encoding" in font:
                continue
            font_descriptor = font.get("/FontDescriptor")
            if not is_symbolic(font_descriptor):
                continue
            if font_descriptor.get("/FontFile2") is None:
                continue

            # Only qualifying fonts populate `seen` -- a dedup-key add before this point would
            # let the first direct (non-indirect, objgen == (0,0)) font dict of *any* kind, not
            # just TT-b, poison every later direct font dict in the same document (I1b).
            seen.add(key)
            yield str(name), font


def measure(manifest_path: str, corpus_dir: str) -> dict:
    """Run the measurement across every document in manifest_path/corpus_dir. Returns a dict
    with `rows` (per-font classification records), `doc_failures` (documents that failed to
    open or traverse), and `counts` (TT-d/TT-e/usable/unparseable totals across all rows).
    """
    manifest_file = Path(manifest_path)
    corpus_path = Path(corpus_dir)
    entries = json.loads(manifest_file.read_text())

    rows: list[dict] = []
    doc_failures: list[dict] = []
    counts = {"TT-d": 0, "TT-e": 0, "usable": 0, "unparseable": 0}

    for entry in entries:
        filename = entry.get("filename", "<missing filename>")
        file_path = corpus_path / filename
        if not file_path.is_file():
            doc_failures.append({"filename": filename, "reason": f"file not found at {file_path}"})
            continue

        try:
            pdf = pikepdf.open(file_path)
        except Exception as exc:  # noqa: BLE001 -- adversarial corpus, see module docstring
            doc_failures.append({"filename": filename, "reason": f"pikepdf.open failed: {exc}"})
            continue

        try:
            for font_name, font in iter_tt_b_fonts(pdf):
                base_font = str(font.get("/BaseFont", "<no /BaseFont>"))
                error = None
                try:
                    font_descriptor = font.get("/FontDescriptor")
                    font_bytes = bytes(font_descriptor.get("/FontFile2").read_bytes())
                    classification = classify_font_bytes(font_bytes)
                except Exception as exc:  # noqa: BLE001 -- adversarial font programs, see module docstring
                    classification = "unparseable"
                    error = str(exc)
                rows.append(
                    {
                        "filename": filename,
                        "font_name": font_name,
                        "base_font": base_font,
                        "classification": classification,
                        "error": error,
                    }
                )
                counts[classification] += 1
        except Exception as exc:  # noqa: BLE001 - any open failure is a recorded result, not a crash
            doc_failures.append({"filename": filename, "reason": f"traversal failed: {exc}"})
        finally:
            pdf.close()

    return {"rows": rows, "doc_failures": doc_failures, "counts": counts}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest_path", help="Path to corpus/manifest.json")
    parser.add_argument("corpus_dir", help="Path to corpus/public")
    args = parser.parse_args()

    result = measure(args.manifest_path, args.corpus_dir)
    rows = result["rows"]
    counts = result["counts"]
    doc_failures = result["doc_failures"]

    print(f"{'document':<45} {'font':<8} {'base_font':<35} classification")
    for row in rows:
        print(f"{row['filename']:<45} {row['font_name']:<8} {row['base_font']:<35} {row['classification']}")

    docs_examined = len({row["filename"] for row in rows})
    total = sum(counts.values())
    print()
    print(
        f"TT-b population examined: {total} embedded, symbolic, no-/Encoding TrueType fonts "
        f"across {docs_examined} documents"
    )
    for key in ("TT-d", "TT-e", "usable", "unparseable"):
        print(f"  {key}: {counts[key]}")

    if doc_failures:
        print(f"\nDocument-level open/traversal failures ({len(doc_failures)}, excluded above):")
        for failure in doc_failures:
            print(f"  {failure['filename']}: {failure['reason']}")

    return 0


if __name__ == "__main__":
    sys.exit(main())

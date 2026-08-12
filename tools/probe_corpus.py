"""Independent structural prober for the corpus manifest (D-04).

Cross-checks a manifest's declared categories against what plain, object-level structural
inspection of the actual PDF bytes can independently confirm. Deliberately serves BOTH the
public and private tiers via the same function/CLI (manifest_path, corpus_dir are always
parameters — never hardcoded to `corpus/manifest.json`/`corpus/public`).

This prober intentionally never interprets content-stream operators — that is Phase 2's job.
Once Phase 2's interpreter exists, verifying these four categories against it would make this
check circular and prove nothing (per D-04). If tightened later, add a SEPARATE non-circular
structural proxy signal instead (e.g. a font-size histogram for headings), never the
interpreter itself.

The four categories above `UNVERIFIED_CATEGORIES` below (ocr_scan, vector_outlined_text,
justified_right_aligned, tables) cannot be confirmed by object-layer inspection alone — they
are genuinely about rendered appearance — and are declared, unverified-by-prober.

`malformed` note: the D-03 malformed fixture (an ISO 19005 PDF/A conformance "fail" case for a
missing trailer /ID) parses cleanly under qpdf's own `--check` (confirmed independently in
Plan 01-04's harness) — it is not a base-PDF syntax error, so pikepdf.open() alone raises
nothing for it. Detection therefore also checks required trailer keys (/Root, /ID) directly via
pikepdf's trailer dictionary object, which is still plain object-level inspection, not content-
stream interpretation.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import warnings
from pathlib import Path

import pikepdf

# Categories this prober can independently confirm via pikepdf's object-layer API only.
DETECTABLE_CATEGORIES = {
    "type0_identity_h",
    "type3",
    "cid_keyed_cff",
    "encrypted",
    "form_xobjects",
    "annotation_appearance_streams",
    "contents_array",
    "subset_fonts",
    "symbolic_fonts",
    "inline_images",
    "malformed",
}

# Declared, unverified-by-prober — see module docstring. Never checked against a
# content-stream interpreter (that would be circular per D-04); if tightened later, use a
# separate non-circular structural proxy signal instead.
UNVERIFIED_CATEGORIES = {
    "ocr_scan",
    "vector_outlined_text",
    "justified_right_aligned",
    "tables",
}

CANONICAL_CATEGORIES = DETECTABLE_CATEGORIES | UNVERIFIED_CATEGORIES

SUBSET_TAG_RE = re.compile(r"^/[A-Z]{6}\+")
SYMBOLIC_FLAG_BIT = 1 << 2  # FontDescriptor /Flags bit 3 (1-indexed) == decimal value 4


def _content_stream_bytes(page: pikepdf.Object) -> bytes:
    """Raw (filter-decoded) content-stream bytes for a page. Byte presence scanning only —
    never a content-stream operator parser/serializer (see module docstring, D-04)."""
    contents = page.get("/Contents")
    if contents is None:
        return b""
    if isinstance(contents, pikepdf.Array):
        return b"".join(bytes(s.read_bytes()) for s in contents)
    return bytes(contents.read_bytes())


# The two Standard-14 base fonts that are inherently symbolic per PDF spec (Appendix D) even
# when no explicit /FontDescriptor /Flags entry is present — a plain structural (BaseFont-name)
# fact, not a rendering inference.
INHERENTLY_SYMBOLIC_BASE_FONTS = {"/Symbol", "/ZapfDingbats"}


def _flags_are_symbolic(font_descriptor: pikepdf.Object | None) -> bool:
    if font_descriptor is None:
        return False
    flags = font_descriptor.get("/Flags")
    return flags is not None and bool(int(flags) & SYMBOLIC_FLAG_BIT)


def _probe_font(font: pikepdf.Object, categories: set[str]) -> None:
    subtype = str(font.get("/Subtype", ""))
    if subtype == "/Type3":
        categories.add("type3")

    if subtype == "/Type0":
        encoding = str(font.get("/Encoding", ""))
        if "Identity-H" in encoding:
            categories.add("type0_identity_h")
        for descendant in font.get("/DescendantFonts", []):
            desc_subtype = str(descendant.get("/Subtype", ""))
            descendant_font_descriptor = descendant.get("/FontDescriptor")
            font_file3 = descendant_font_descriptor.get("/FontFile3") if descendant_font_descriptor else None
            ff3_subtype = str(font_file3.get("/Subtype", "")) if font_file3 else ""
            if desc_subtype == "/CIDFontType0" and ff3_subtype == "/CIDFontType0C":
                categories.add("cid_keyed_cff")
            # A Type0 composite font's /FontDescriptor lives on its descendant CIDFont, not on
            # the Type0 dict itself (ISO 32000-1 9.7.4) - check it there too.
            if _flags_are_symbolic(descendant_font_descriptor):
                categories.add("symbolic_fonts")

    base_font = font.get("/BaseFont")
    if base_font is not None:
        base_font_str = str(base_font)
        if SUBSET_TAG_RE.match(base_font_str):
            categories.add("subset_fonts")
        if base_font_str in INHERENTLY_SYMBOLIC_BASE_FONTS:
            categories.add("symbolic_fonts")

    if _flags_are_symbolic(font.get("/FontDescriptor")):
        categories.add("symbolic_fonts")


def probe_file(pdf_path: str) -> set[str]:
    """Return the set of structurally-detectable categories found in pdf_path via pikepdf's
    object-layer API only (never a content-stream operator parser/serializer, per D-04).
    Returns an empty set (not an exception) for a well-formed file with no detectable
    signatures.
    """
    categories: set[str] = set()

    try:
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            pdf = pikepdf.open(pdf_path, suppress_warnings=False)
    except pikepdf.PdfError:
        categories.add("malformed")
        return categories

    try:
        if any(issubclass(w.category, UserWarning) for w in caught):
            categories.add("malformed")
        # Plain trailer-dictionary key check — see module docstring's `malformed` note.
        if "/Root" not in pdf.trailer or "/ID" not in pdf.trailer:
            categories.add("malformed")

        if pdf.is_encrypted:
            categories.add("encrypted")

        for page in pdf.pages:
            resources = page.get("/Resources") or {}

            for font in (resources.get("/Font") or {}).values():
                _probe_font(font, categories)

            for xobject in (resources.get("/XObject") or {}).values():
                if str(xobject.get("/Subtype", "")) == "/Form":
                    categories.add("form_xobjects")

            for annot in page.get("/Annots") or []:
                appearance = annot.get("/AP")
                if appearance is not None and "/N" in appearance:
                    categories.add("annotation_appearance_streams")

            if isinstance(page.get("/Contents"), pikepdf.Array):
                categories.add("contents_array")

            if b"BI" in _content_stream_bytes(page):
                categories.add("inline_images")
    except pikepdf.PdfError:
        # A structural error surfacing mid-traversal (e.g. while walking a page tree that
        # opened but is broken deeper in) is itself malformed-category evidence.
        categories.add("malformed")
    finally:
        pdf.close()

    return categories


def check_manifest(manifest_path: str, corpus_dir: str, enforce_full_coverage: bool = True) -> list[str]:
    """Cross-check every manifest entry's declared categories against probe_file()'s
    independently-derived categories. Always runs the per-file wrong-label check. When
    enforce_full_coverage=True (default, used for the public manifest per D-03), also flags
    any of the 15 canonical categories with zero declared documents across the manifest. When
    False (used for the private manifest — D-03: private tier adds volume, never unique
    categories), that whole-manifest check is skipped; an empty/partial private manifest is
    not an error by itself.
    """
    errors: list[str] = []
    manifest_file = Path(manifest_path)
    corpus_path = Path(corpus_dir)

    try:
        entries = json.loads(manifest_file.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        return [f"could not read/parse manifest at {manifest_path}: {exc}"]

    declared_categories_seen: set[str] = set()
    for entry in entries:
        filename = entry.get("filename", "<missing filename>")
        declared = set(entry.get("categories", []))
        declared_categories_seen.update(declared)

        file_path = corpus_path / filename
        if not file_path.is_file():
            errors.append(f"{filename}: file not found at {file_path}")
            continue

        detected = probe_file(str(file_path))
        verifiable_declared = declared - UNVERIFIED_CATEGORIES
        wrong_labels = sorted(verifiable_declared - detected)
        for category in wrong_labels:
            errors.append(
                f"{filename}: declared category {category!r} not detected by probe_file()"
            )

    if enforce_full_coverage:
        missing_categories = CANONICAL_CATEGORIES - declared_categories_seen
        if missing_categories:
            errors.append(
                "zero-count categories (present in the canonical D-03 list but absent from "
                f"every manifest entry's categories array): {sorted(missing_categories)}"
            )

    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest_path", help="Path to a corpus manifest JSON (array of {filename, categories, ...})")
    parser.add_argument("corpus_dir", help="Directory containing the PDFs referenced by manifest_path")
    parser.add_argument(
        "--no-coverage-check",
        action="store_true",
        help="Skip the whole-manifest zero-count-category check (used for the private tier, D-03)",
    )
    args = parser.parse_args()

    errors = check_manifest(args.manifest_path, args.corpus_dir, enforce_full_coverage=not args.no_coverage_check)
    if not errors:
        print("probe_corpus: OK - every declared structurally-verifiable category confirmed")
        return 0
    for error in errors:
        print(error, file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())

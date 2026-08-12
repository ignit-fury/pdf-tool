"""Corpus manifest validator.

Independent, lightweight check that corpus/manifest.json accurately describes the files on
disk: every declared sha256 matches the actual file bytes, and the union of every entry's
`categories` covers all 15 canonical D-03 structural categories. This is a manifest-vs-disk
consistency check only — it does NOT parse content streams or open the PDFs with a PDF
library, so it stays independent of the engine this corpus will validate in later phases.

The category *prober* that independently re-derives categories from the PDF bytes themselves
(D-04) is Plan 01-03's job, not this script's.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

CANONICAL_CATEGORIES = {
    "subset_fonts",
    "type0_identity_h",
    "symbolic_fonts",
    "type3",
    "cid_keyed_cff",
    "contents_array",
    "inline_images",
    "form_xobjects",
    "annotation_appearance_streams",
    "justified_right_aligned",
    "tables",
    "ocr_scan",
    "vector_outlined_text",
    "encrypted",
    "malformed",
}


def validate_manifest(manifest_path: str, corpus_dir: str) -> list[str]:
    """Return a list of human-readable error strings. Empty list means valid."""
    errors: list[str] = []
    manifest_file = Path(manifest_path)
    corpus_path = Path(corpus_dir)

    try:
        entries = json.loads(manifest_file.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        return [f"could not read/parse manifest at {manifest_path}: {exc}"]

    seen_categories: set[str] = set()
    for entry in entries:
        filename = entry.get("filename", "<missing filename>")
        declared_sha256 = entry.get("sha256")
        file_path = corpus_path / filename
        if not file_path.is_file():
            errors.append(f"{filename}: file not found at {file_path}")
        else:
            actual_sha256 = hashlib.sha256(file_path.read_bytes()).hexdigest()
            if declared_sha256 != actual_sha256:
                errors.append(
                    f"{filename}: sha256 mismatch (manifest={declared_sha256!r}, "
                    f"actual={actual_sha256!r})"
                )
        seen_categories.update(entry.get("categories", []))

    missing_categories = CANONICAL_CATEGORIES - seen_categories
    if missing_categories:
        errors.append(
            "zero-count categories (present in the canonical D-03 list but absent from "
            f"every manifest entry's categories array): {sorted(missing_categories)}"
        )

    return errors


def main() -> int:
    if len(sys.argv) != 3:
        print("usage: validate_manifest.py <manifest.json> <corpus_dir>", file=sys.stderr)
        return 2
    errors = validate_manifest(sys.argv[1], sys.argv[2])
    if not errors:
        print("validate_manifest: OK - all hashes match, all 15 categories represented")
        return 0
    for error in errors:
        print(error, file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())

"""Gate G0 corpus-size gate — mechanical enforcement of the roadmap's 100-300 document target.

Combined public+private manifest entry count must reach 100 before Gate G0 can be signed off.
Intentionally a hard stop (nonzero exit), not a warning: the public tier alone was only ever
scoped to cover all 15 D-03 structural categories (25-45 files), never to reach the roadmap's
volume target by itself — the private tier supplies volume. See this plan's Task 3 checkpoint
for what the maintainer must do to satisfy this gate; do not synthesize/generate/fabricate
documents to satisfy this number (ENG-01, D-01).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

MINIMUM_COMBINED_DOCUMENTS = 100


def _entry_count(manifest_path: str) -> int:
    manifest_file = Path(manifest_path)
    if not manifest_file.is_file():
        return 0
    return len(json.loads(manifest_file.read_text()))


def check_corpus_size(public_manifest_path: str, private_manifest_path: str) -> int:
    """Return the combined entry count across both manifests."""
    return _entry_count(public_manifest_path) + _entry_count(private_manifest_path)


def main() -> int:
    if len(sys.argv) != 3:
        print("usage: check_corpus_size.py <public_manifest.json> <private_manifest.json>", file=sys.stderr)
        return 2

    public_manifest_path, private_manifest_path = sys.argv[1], sys.argv[2]
    pub_count = _entry_count(public_manifest_path)
    priv_count = _entry_count(private_manifest_path)
    combined = pub_count + priv_count

    if combined < MINIMUM_COMBINED_DOCUMENTS:
        print(
            f"Gate G0 requires >= {MINIMUM_COMBINED_DOCUMENTS} combined documents; "
            f"have {combined} (public={pub_count}, private={priv_count})"
        )
        return 1

    print(f"Gate G0 corpus-size gate: OK - {combined} combined documents (public={pub_count}, private={priv_count})")
    return 0


if __name__ == "__main__":
    sys.exit(main())

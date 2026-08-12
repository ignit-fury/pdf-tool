"""AGPL/Affero license gate over the RESOLVED, installed dependency closure.

Scans every distribution actually installed in the current environment (i.e. the
resolved lockfile closure `uv sync` produced), not just top-level `pyproject.toml`
declarations. This is what catches transitive traps like `pdf2docx` (MIT) pulling in
`PyMuPDF` (AGPL) — a top-level metadata scan would miss it entirely.

No AGPL anywhere in the runtime dependency tree, including transitively. See
PROJECT.md > Constraints > Licensing.
"""

from __future__ import annotations

import sys
from importlib import metadata

MATCH_SUBSTRINGS = ("agpl", "affero")


def _offending_distributions() -> list[tuple[str, str, str]]:
    """Internal: (name, version, matched_field) for every offending distribution."""
    offenders: list[tuple[str, str, str]] = []
    for dist in metadata.distributions():
        name = dist.metadata.get("Name", "unknown")
        version = dist.metadata.get("Version", "unknown")
        fields_to_check = [dist.metadata.get("License", "") or ""]
        fields_to_check.extend(dist.metadata.get_all("Classifier") or [])
        for field in fields_to_check:
            lowered = field.lower()
            if any(sub in lowered for sub in MATCH_SUBSTRINGS):
                offenders.append((name, version, field))
                break
    return offenders


def check_installed_distributions() -> list[tuple[str, str]]:
    """Return (package_name, version) for every installed distribution whose
    license metadata (the `License` field or any `Classifier: License ::` entry)
    contains "AGPL" or "Affero", case-insensitively. Empty list means the
    environment is clean.
    """
    return [(name, version) for name, version, _ in _offending_distributions()]


def main() -> int:
    offenders = _offending_distributions()
    if not offenders:
        print("license_gate: no AGPL/Affero licensed distributions found")
        return 0
    for name, version, field in offenders:
        print(f"{name}=={version}: {field}")
    return 1


if __name__ == "__main__":
    sys.exit(main())

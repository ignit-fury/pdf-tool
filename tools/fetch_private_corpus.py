"""Private-tier corpus fetch (D-01, D-02).

Downloads every file named in corpus/private-manifest.json from a bearer-token-gated HTTPS
object store into corpus/private/ (never committed - see .gitignore), verifying each
download's sha256 against the manifest entry. stdlib `urllib.request` only - no cloud SDK
dependency; any HTTPS object store supporting bearer-token GET (S3, R2, GCS presigned/gated
URLs) works without a provider-specific client.

D-02's central contract, proven by tests/test_fetch_private_corpus.py: an ABSENT private tier
(missing credentials - fork PRs, fresh clones) is a NORMAL state, not a failure. It must never
raise, never exit nonzero, and never warn at a level that would fail CI. A genuine fetch
ERROR (credentials present but download/verification fails) is a distinct, still-failing
outcome - the two must never collapse into each other.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

DEFAULT_MANIFEST_PATH = "corpus/private-manifest.json"
DEFAULT_DEST_DIR = "corpus/private"
FETCH_TIMEOUT_SECONDS = 30


@dataclass
class FetchResult:
    status: str  # "skipped" | "ok" | "error"
    detail: str = ""
    files_ok: int = 0


def fetch_private_corpus(
    bucket_base_url: str | None,
    bearer_token: str | None,
    manifest_path: str = DEFAULT_MANIFEST_PATH,
    dest_dir: str = DEFAULT_DEST_DIR,
) -> FetchResult:
    """Fetch every private-manifest-declared file from bucket_base_url, verifying sha256.

    Returns status="skipped" (never an exception, never nonzero-equivalent) when either
    credential is absent - the D-02 normal-absence case. Returns status="ok" once
    credentials are present and every declared file (zero or more) downloads and verifies
    cleanly - an empty manifest with valid credentials is "ok" trivially, since the fetch
    step itself has nothing to fail on. Returns status="error" only when credentials ARE
    present but a fetch or hash-verification genuinely fails.
    """
    if not bucket_base_url or not bearer_token:
        return FetchResult(status="skipped", detail="private tier unavailable, skipping (no credentials)")

    manifest_file = Path(manifest_path)
    try:
        entries = json.loads(manifest_file.read_text()) if manifest_file.is_file() else []
    except (OSError, json.JSONDecodeError) as exc:
        return FetchResult(status="error", detail=f"could not read manifest at {manifest_path}: {exc}")

    dest = Path(dest_dir)
    dest.mkdir(parents=True, exist_ok=True)

    files_ok = 0
    for entry in entries:
        filename = entry["filename"]
        expected_sha256 = entry["sha256"]
        url = bucket_base_url.rstrip("/") + "/" + filename
        request = urllib.request.Request(url, headers={"Authorization": f"Bearer {bearer_token}"})
        try:
            with urllib.request.urlopen(request, timeout=FETCH_TIMEOUT_SECONDS) as response:
                data = response.read()
        except (urllib.error.URLError, TimeoutError) as exc:
            return FetchResult(status="error", detail=f"{filename}: fetch failed: {exc}", files_ok=files_ok)

        actual_sha256 = hashlib.sha256(data).hexdigest()
        if actual_sha256 != expected_sha256:
            return FetchResult(
                status="error",
                detail=f"{filename}: sha256 mismatch (expected {expected_sha256}, got {actual_sha256})",
                files_ok=files_ok,
            )

        (dest / filename).write_bytes(data)
        files_ok += 1

    return FetchResult(status="ok", detail=f"{files_ok}/{len(entries)} file(s) fetched and verified", files_ok=files_ok)


def main() -> int:
    base_url = os.environ.get("PRIVATE_CORPUS_BASE_URL")
    token = os.environ.get("PRIVATE_CORPUS_TOKEN")
    result = fetch_private_corpus(base_url, token)

    if result.status == "skipped":
        print("private tier unavailable, skipping")
    else:
        print(result.detail)
    # Machine-readable line CI branches on (see .github/workflows/corpus.yml) - kept on its
    # own line, in addition to the human-readable summary above, never replacing it.
    print(f"status={result.status}")

    return 0 if result.status in ("skipped", "ok") else 1


if __name__ == "__main__":
    sys.exit(main())

"""03-01 Task 2: qpdf version-gap reconciliation tripwire (Dockerfile.ci 12.2.0-1 vs local dev).

RESEARCH.md's Environment Availability table flags a real gap: `Dockerfile.ci` pins
`qpdf=12.2.0-1` (the newest version Debian trixie's own apt repo offers) while local dev
commonly has a newer patch release installed. G2a's own acceptance criterion depends on
`qpdf --qdf` normalization output, and this project's stated discipline is "output differs
across versions and your golden tests will drift" (Dockerfile.ci's own header comment) --
so rather than trust "qpdf's docs say --qdf is stable across minor versions" on faith, this
test pins a measured fingerprint of that output and re-checks it on every run. A pass in CI
(against 12.2.0-1) is the empirical confirmation RESEARCH.md calls for; a failure is real,
previously invisible `--qdf` normalization drift, surfaced before G2a (03-08) depends on it.

Deviation from Pitfall 3's exact flags, deliberate and measured: this test adds
`--deterministic-id` to Pitfall 3's `--qdf --object-streams=disable --no-original-object-ids`.
Without it, `qpdf --qdf` regenerates the trailer's `/ID` second element (a PDF-spec-recommended
content+time-derived value) on every single invocation -- confirmed directly this session by
running the exact Pitfall-3 command three times in a row against the same input and getting
three different sha256 hashes each time, purely from that one trailer line. Pitfall 3 never hit
this because it only ran `--qdf` once per file for a one-off diff; this test needs the *same*
output on every future run (today, and again whenever CI executes it), which raw `--qdf` cannot
give. `--deterministic-id` is qpdf's own built-in fix for exactly this: content-derived, not
time-derived, so it doesn't reintroduce the "output differs across versions" risk this test
exists to catch -- a genuine `--qdf` normalization change between qpdf versions still changes
the hash; only the timestamp-driven noise is removed.
"""

from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
FIXTURE = REPO_ROOT / "spike" / "fixtures" / "tj_refit_sample.pdf"

# Measured this session directly against the fixture below (re-run, not copied from any other
# session -- this codebase's "measure, then pin, never guess" convention):
#   $ qpdf --version
#   qpdf version 12.4.0
#   $ qpdf --qdf --deterministic-id --object-streams=disable --no-original-object-ids \
#         spike/fixtures/tj_refit_sample.pdf /tmp/out.pdf
#   $ shasum -a 256 /tmp/out.pdf
# Verified stable across 3 repeated runs (identical hash each time). Date: 2026-08-23.
#
# Note for future maintainers: an earlier draft of this constant (from a different
# session/environment, also against qpdf 12.4.0, without --deterministic-id) produced a
# *different* hash despite an identical `qpdf --version` string -- that was the regenerated
# `/ID` noise described above, not real version drift. Re-measuring in-environment with
# --deterministic-id, as this test does, is what makes the value trustworthy.
EXPECTED_QDF_SHA256 = "bab137158db5885aa4130addd9aaecf7fd26036f965c4ec8766e22d22550948a"


def _qpdf_version() -> str:
    """Best-effort `qpdf --version` string for failure messages -- never document content."""
    try:
        result = subprocess.run(["qpdf", "--version"], capture_output=True, text=True)
        return (result.stdout or result.stderr).strip()
    except OSError as exc:
        return f"<qpdf --version failed to run: {exc}>"


def test_qdf_output_is_stable(tmp_path: Path) -> None:
    """`qpdf --qdf` normalization of the fixture must match the pinned fingerprint.

    A failure here means either (a) the executing qpdf's --qdf normalization genuinely
    differs from the version this constant was measured against -- the version-gap drift
    this test exists to catch -- or (b) this constant is stale for a legitimate reason
    (fixture changed, qpdf intentionally upgraded). Either way, re-measure locally with the
    exact command in the EXPECTED_QDF_SHA256 comment above before updating the constant.
    """
    assert FIXTURE.exists(), f"fixture missing: {FIXTURE}"

    output_path = tmp_path / "tj_refit_sample.qdf.pdf"
    result = subprocess.run(
        [
            "qpdf",
            "--qdf",
            "--deterministic-id",
            "--object-streams=disable",
            "--no-original-object-ids",
            str(FIXTURE),
            str(output_path),
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        f"qpdf --qdf exited {result.returncode} against {FIXTURE.name}. "
        f"Local `qpdf --version`: {_qpdf_version()!r}. stderr: {result.stderr.strip()!r}"
    )

    actual = hashlib.sha256(output_path.read_bytes()).hexdigest()
    assert actual == EXPECTED_QDF_SHA256, (
        f"qpdf --qdf normalization output for {FIXTURE.name} no longer matches the pinned "
        f"fingerprint -- expected sha256={EXPECTED_QDF_SHA256}, got {actual}. "
        f"Local `qpdf --version`: {_qpdf_version()!r}. "
        f"This is the qpdf version-gap tripwire (Dockerfile.ci pins 12.2.0-1; local dev may "
        f"differ) -- re-run the exact command in this file's EXPECTED_QDF_SHA256 comment "
        f"locally and confirm whether this is expected drift before updating the constant."
    )

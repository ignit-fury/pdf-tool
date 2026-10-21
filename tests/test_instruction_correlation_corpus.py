"""Task 2 of plan 03-02: corpus-wide sweep validating
`spike/instruction_correlation_probe.py`'s correlation mechanism across all 217
public-corpus documents (including the 17 known-malformed ones), closing
03-RESEARCH.md's Open Question 1 with a corpus-wide answer rather than the 4-fixture
sample Task 1 proved it on.

Follows `tests/test_roundtrip.py`'s established corpus-sweep shape: manifest-driven
fixture selection (`CORPUS_DIR`/`MANIFEST_PATH`/`_manifest()`), the `@pytest.mark.corpus`
marker, `KNOWN_*`-style pinned exact-set constants with `new=.../missing=...` diff
messages, and `type(exc).__name__`-only exception capture -- never letting one
document's failure abort the sweep (T-03-02-01).

## Why this does NOT call `correlate_run` in a loop (a measured deviation from the
## brief's literal wording, recorded here rather than silently)

The brief's action section says to "call Task 1's `correlate_run`" per editable run.
Measured directly before writing this file: `correlate_run` reopens a fresh `RunIndex`
(a full page walk/cluster/classify) AND a fresh `pikepdf.Pdf` handle on EVERY call --
fine for Task 1's own 4 fixture calls, but at this task's required scale (129,491
editable runs measured by 03-RESEARCH.md Pitfall 1 under this same 5-page cap) a
weighted-average projection from real per-page walk costs across the full corpus put a
literal per-run `correlate_run` sweep at **~56 CPU-hours** -- not "will take real time,
that's expected" (the brief's own framing for a slow-but-bounded corpus test), but
practically un-runnable.

The fix touches only *how the algorithm is invoked*, never *what is being validated*:
`touched_instruction_indices` -- the actual correlation algorithm (`correlate_run`'s own
module docstring: "the correlation is by ORDINAL POSITION... `touched_instruction_indices`
-- the correlation is..."), a pure function with no I/O -- is imported and called
UNMODIFIED, exactly as Task 1 wrote it. So is the validation `correlate_run` itself
performs after computing `touched_indices` (in-range + text-showing-operator check):
`_validate_touched` below is a byte-for-byte copy of that logic, not a new invention,
kept as its own function purely so it can run once per (part, run) pair without also
paying `correlate_run`'s I/O cost every time.

What changes is amortization: `RunIndex` and `pikepdf.Pdf` are opened ONCE per document
(matching `RunIndex`'s own lazy-cache design, D-06) rather than once per run, and each
content-stream PART's `pikepdf.parse_content_stream` result plus its
`all_operator_offsets_sorted` are computed ONCE per part and reused for every run that
shares it (`correlate_run` recomputes the identical value from scratch on every call --
it is a pure function of the part, not of which run is being resolved, so caching it
changes nothing about the answer). For a given run, `touched_instruction_indices`
receives EXACTLY the same three arguments here as `correlate_run` would pass it, so the
result is identical to what a literal per-run sweep would have produced -- this is a
performance-only refactor of the invocation, not a change to the algorithm or its
validation being exercised.

## What this test measures, and what it does NOT prove

`touched_instruction_indices`'s own validation (mirrored here as `_validate_touched`)
checks that every returned instruction index is in-range and addresses a text-showing
operator -- it CANNOT distinguish a correct ordinal from a shifted-but-still-plausible
one. `spike/instruction_correlation_probe.py`'s own "What is NOT proven here" section
names the residual gap directly: a `/Contents` array part boundary that truncates a
token mid-stream could in principle shift the ordinal count at the START of the NEXT
part while every check this test performs still passes. A clean sweep here
(`correlation_failures` empty) is evidence the mechanism is INDEX-VALID everywhere
exercised in the corpus -- it is not, by itself, proof every ordinal is the CORRECT one
near a part boundary. This test does not add machinery to close that gap (out of scope
for this task); it only measures what the correlation check itself can detect, at full
corpus scale. This sweep also has no visibility into which runs sit in a part
immediately following a truncation-affected part -- it does not track part-boundary
adjacency at all, so it cannot report whether that specific scenario was exercised.

No document content (glyph text) appears in any assertion, log, or exception message --
only filenames, run IDs, byte offsets, and counts (T-03-02-02).
"""

from __future__ import annotations

import json
from pathlib import Path

import pikepdf
import pytest

from engine.classify_run import stream_bytes_and_resources
from engine.index import RunIndex
from engine.run_id import decode_run_id
from spike.instruction_correlation_probe import TEXT_SHOWING_OPERATORS, touched_instruction_indices

REPO_ROOT = Path(__file__).parent.parent
CORPUS_DIR = REPO_ROOT / "corpus" / "public"
MANIFEST_PATH = REPO_ROOT / "corpus" / "manifest.json"

# 03-RESEARCH.md Pitfall 1/2's own measurement cap -- keeps this sweep's counts directly
# comparable to the already-published 10.62%/1.1% figures (129,491 editable runs /
# 13,752 multi-operator runs / 1,431 non-contiguous runs, 217-document corpus).
MAX_PAGES_PER_DOC = 5

_EDITABLE_STATES = frozenset({"editable_original", "editable_substitution"})

# Lower bounds from task-2-brief.md, acceptance_criteria (2)/(3): safe margins under
# 03-RESEARCH.md's own measured 129,491 editable / 13,752 multi-operator, guarding
# against a silently-empty or broken sweep rather than pinning the exact measured counts
# (which can drift slightly with corpus/classification changes without indicating a
# real regression).
MIN_EDITABLE_RUNS_CHECKED = 100_000
MIN_MULTI_OPERATOR_RUNS_CHECKED = 10_000

# Pinned exact-set constants (task-2-brief.md action (4)/(5)) -- start empty, and only
# ever grow if the sweep genuinely finds an entry. Never pre-populated with a guess.
#
# KNOWN_CORRELATION_FAILURES: measured directly running this sweep, 2026-08-23 -- 89
# editable runs across 19 documents (govdocs1_* and three IRS PDFs) where
# `touched_instruction_indices` produced zero touched instructions. Confirmed NOT an
# artifact of this test's amortized invocation (see module docstring): re-running the
# literal `correlate_run(path, page_index, run_id)` on one of these entries
# (`govdocs1_014_014103.pdf`, run ending `:c4:o3090`) independently reproduces the exact
# same `ok=False, reason="correlation produced zero touched instructions"` verdict. This
# is `correlate_run`'s own safety check doing its job -- every one of these 89 is a
# REFUSAL (a named, detected disagreement), not a silently-wrong index: the mechanism's
# own in-range/text-operator validation cannot produce a false "ok" here, only a
# correctly-flagged failure. The likely cause (not verified further -- out of this
# task's scope) is the same part-boundary truncation
# `spike/instruction_correlation_probe.py`'s own docstring already names as an open
# risk: playa's walk counts a text-showing operator whose bytes are completed by the
# NEXT /Contents array element in the original coalesced stream, while pikepdf's
# isolated re-parse of THIS part alone hits "Unexpected end of stream" and never reaches
# it, undercounting relative to what playa's ordinal assumed.
KNOWN_CORRELATION_FAILURES: frozenset[tuple[str, str, str]] = frozenset(
    {
        ("govdocs1_000_000009.pdf", "0000000000000000000000000000000000000000000000000000000000000000:p0:c2:o2326", "correlation produced zero touched instructions"),
        ("govdocs1_000_000009.pdf", "0000000000000000000000000000000000000000000000000000000000000000:p0:c2:o2326:g0-8", "correlation produced zero touched instructions"),
        ("govdocs1_000_000137.pdf", "0000000000000000000000000000000000000000000000000000000000000000:p0:c1:o2248", "correlation produced zero touched instructions"),
        ("govdocs1_000_000137.pdf", "0000000000000000000000000000000000000000000000000000000000000000:p0:c1:o2305:g0-6", "correlation produced zero touched instructions"),
        ("govdocs1_000_000137.pdf", "0000000000000000000000000000000000000000000000000000000000000000:p0:c2:o2211:g0-30", "correlation produced zero touched instructions"),
        ("govdocs1_000_000137.pdf", "0000000000000000000000000000000000000000000000000000000000000000:p0:c5:o2269:g0-15", "correlation produced zero touched instructions"),
        ("govdocs1_003_003072.pdf", "0000000000000000000000000000000000000000000000000000000000000000:p0:c5:o1759:g0-1", "correlation produced zero touched instructions"),
        ("govdocs1_005_005000.pdf", "0000000000000000000000000000000000000000000000000000000000000000:p0:c0:o4651", "correlation produced zero touched instructions"),
        ("govdocs1_005_005000.pdf", "0000000000000000000000000000000000000000000000000000000000000000:p0:c0:o4719", "correlation produced zero touched instructions"),
        ("govdocs1_006_006053.pdf", "0000000000000000000000000000000000000000000000000000000000000000:p1:c4:o295", "correlation produced zero touched instructions"),
        ("govdocs1_006_006053.pdf", "0000000000000000000000000000000000000000000000000000000000000000:p2:c4:o295", "correlation produced zero touched instructions"),
        ("govdocs1_006_006053.pdf", "0000000000000000000000000000000000000000000000000000000000000000:p3:c4:o295", "correlation produced zero touched instructions"),
        ("govdocs1_006_006053.pdf", "0000000000000000000000000000000000000000000000000000000000000000:p4:c4:o295", "correlation produced zero touched instructions"),
        ("govdocs1_008_008025.pdf", "0000000000000000000000000000000000000000000000000000000000000000:p0:c2:o15120", "correlation produced zero touched instructions"),
        ("govdocs1_008_008025.pdf", "0000000000000000000000000000000000000000000000000000000000000000:p0:c2:o15456", "correlation produced zero touched instructions"),
        ("govdocs1_008_008025.pdf", "0000000000000000000000000000000000000000000000000000000000000000:p0:c2:o15741", "correlation produced zero touched instructions"),
        ("govdocs1_008_008025.pdf", "0000000000000000000000000000000000000000000000000000000000000000:p0:c2:o15869", "correlation produced zero touched instructions"),
        ("govdocs1_008_008025.pdf", "0000000000000000000000000000000000000000000000000000000000000000:p0:c2:o16175", "correlation produced zero touched instructions"),
        ("govdocs1_008_008025.pdf", "0000000000000000000000000000000000000000000000000000000000000000:p0:c2:o16430:g0-11", "correlation produced zero touched instructions"),
        ("govdocs1_008_008025.pdf", "0000000000000000000000000000000000000000000000000000000000000000:p0:c6:o15024", "correlation produced zero touched instructions"),
        ("govdocs1_008_008025.pdf", "0000000000000000000000000000000000000000000000000000000000000000:p0:c6:o15156", "correlation produced zero touched instructions"),
        ("govdocs1_008_008025.pdf", "0000000000000000000000000000000000000000000000000000000000000000:p0:c6:o15288", "correlation produced zero touched instructions"),
        ("govdocs1_008_008025.pdf", "0000000000000000000000000000000000000000000000000000000000000000:p0:c6:o15495", "correlation produced zero touched instructions"),
        ("govdocs1_008_008025.pdf", "0000000000000000000000000000000000000000000000000000000000000000:p0:c6:o15627", "correlation produced zero touched instructions"),
        ("govdocs1_008_008025.pdf", "0000000000000000000000000000000000000000000000000000000000000000:p0:c6:o15759", "correlation produced zero touched instructions"),
        ("govdocs1_008_008025.pdf", "0000000000000000000000000000000000000000000000000000000000000000:p0:c6:o16020", "correlation produced zero touched instructions"),
        ("govdocs1_008_008025.pdf", "0000000000000000000000000000000000000000000000000000000000000000:p0:c6:o16148:g0-6", "correlation produced zero touched instructions"),
        ("govdocs1_008_008028.pdf", "0000000000000000000000000000000000000000000000000000000000000000:p0:c1:o10019:g0-3", "correlation produced zero touched instructions"),
        ("govdocs1_009_009015.pdf", "0000000000000000000000000000000000000000000000000000000000000000:p0:c2:o994:g0-18", "correlation produced zero touched instructions"),
        ("govdocs1_010_010118.pdf", "0000000000000000000000000000000000000000000000000000000000000000:p0:c1:o2218:g0-6", "correlation produced zero touched instructions"),
        ("govdocs1_010_010118.pdf", "0000000000000000000000000000000000000000000000000000000000000000:p0:c2:o1843", "correlation produced zero touched instructions"),
        ("govdocs1_010_010118.pdf", "0000000000000000000000000000000000000000000000000000000000000000:p0:c2:o2082", "correlation produced zero touched instructions"),
        ("govdocs1_010_010118.pdf", "0000000000000000000000000000000000000000000000000000000000000000:p0:c2:o2214:g0-20", "correlation produced zero touched instructions"),
        ("govdocs1_011_011078.pdf", "0000000000000000000000000000000000000000000000000000000000000000:p0:c0:o6744:g53-60", "correlation produced zero touched instructions"),
        ("govdocs1_011_011078.pdf", "0000000000000000000000000000000000000000000000000000000000000000:p0:c0:o6744:g61-63", "correlation produced zero touched instructions"),
        ("govdocs1_011_011078.pdf", "0000000000000000000000000000000000000000000000000000000000000000:p0:c0:o6744:g64-67", "correlation produced zero touched instructions"),
        ("govdocs1_011_011078.pdf", "0000000000000000000000000000000000000000000000000000000000000000:p0:c0:o6744:g68-75", "correlation produced zero touched instructions"),
        ("govdocs1_011_011078.pdf", "0000000000000000000000000000000000000000000000000000000000000000:p0:c0:o6744:g76-84", "correlation produced zero touched instructions"),
        ("govdocs1_011_011078.pdf", "0000000000000000000000000000000000000000000000000000000000000000:p0:c0:o6744:g86-88", "correlation produced zero touched instructions"),
        ("govdocs1_011_011078.pdf", "0000000000000000000000000000000000000000000000000000000000000000:p0:c0:o6744:g89-92", "correlation produced zero touched instructions"),
        ("govdocs1_011_011078.pdf", "0000000000000000000000000000000000000000000000000000000000000000:p0:c0:o6744:g93-97", "correlation produced zero touched instructions"),
        ("govdocs1_011_011078.pdf", "0000000000000000000000000000000000000000000000000000000000000000:p0:c0:o6744:g98-102", "correlation produced zero touched instructions"),
        ("govdocs1_011_011080.pdf", "0000000000000000000000000000000000000000000000000000000000000000:p0:c0:o6059:g111-120", "correlation produced zero touched instructions"),
        ("govdocs1_011_011080.pdf", "0000000000000000000000000000000000000000000000000000000000000000:p0:c0:o6059:g121-126", "correlation produced zero touched instructions"),
        ("govdocs1_011_011080.pdf", "0000000000000000000000000000000000000000000000000000000000000000:p0:c0:o6059:g127-132", "correlation produced zero touched instructions"),
        ("govdocs1_011_011080.pdf", "0000000000000000000000000000000000000000000000000000000000000000:p0:c0:o7436:g0-3", "correlation produced zero touched instructions"),
        ("govdocs1_011_011080.pdf", "0000000000000000000000000000000000000000000000000000000000000000:p0:c0:o7436:g11-21", "correlation produced zero touched instructions"),
        ("govdocs1_011_011080.pdf", "0000000000000000000000000000000000000000000000000000000000000000:p0:c0:o7436:g22-24", "correlation produced zero touched instructions"),
        ("govdocs1_011_011080.pdf", "0000000000000000000000000000000000000000000000000000000000000000:p0:c0:o7436:g25-28", "correlation produced zero touched instructions"),
        ("govdocs1_011_011080.pdf", "0000000000000000000000000000000000000000000000000000000000000000:p0:c0:o7436:g29-32", "correlation produced zero touched instructions"),
        ("govdocs1_011_011080.pdf", "0000000000000000000000000000000000000000000000000000000000000000:p0:c0:o7436:g33-38", "correlation produced zero touched instructions"),
        ("govdocs1_011_011080.pdf", "0000000000000000000000000000000000000000000000000000000000000000:p0:c0:o7436:g39-45", "correlation produced zero touched instructions"),
        ("govdocs1_011_011080.pdf", "0000000000000000000000000000000000000000000000000000000000000000:p0:c0:o7436:g4-10", "correlation produced zero touched instructions"),
        ("govdocs1_011_011080.pdf", "0000000000000000000000000000000000000000000000000000000000000000:p0:c0:o7436:g46-50", "correlation produced zero touched instructions"),
        ("govdocs1_011_011098.pdf", "0000000000000000000000000000000000000000000000000000000000000000:p0:c0:o1260", "correlation produced zero touched instructions"),
        ("govdocs1_011_011098.pdf", "0000000000000000000000000000000000000000000000000000000000000000:p0:c0:o1384", "correlation produced zero touched instructions"),
        ("govdocs1_012_012159.pdf", "0000000000000000000000000000000000000000000000000000000000000000:p0:c0:o3508", "correlation produced zero touched instructions"),
        ("govdocs1_012_012159.pdf", "0000000000000000000000000000000000000000000000000000000000000000:p0:c0:o3816", "correlation produced zero touched instructions"),
        ("govdocs1_012_012159.pdf", "0000000000000000000000000000000000000000000000000000000000000000:p0:c0:o4149:g0-2", "correlation produced zero touched instructions"),
        ("govdocs1_012_012159.pdf", "0000000000000000000000000000000000000000000000000000000000000000:p0:c4:o4128:g0-18", "correlation produced zero touched instructions"),
        ("govdocs1_013_013083.pdf", "0000000000000000000000000000000000000000000000000000000000000000:p0:c4:o7439:g0-10", "correlation produced zero touched instructions"),
        ("govdocs1_014_014103.pdf", "0000000000000000000000000000000000000000000000000000000000000000:p0:c4:o2641", "correlation produced zero touched instructions"),
        ("govdocs1_014_014103.pdf", "0000000000000000000000000000000000000000000000000000000000000000:p0:c4:o2691", "correlation produced zero touched instructions"),
        ("govdocs1_014_014103.pdf", "0000000000000000000000000000000000000000000000000000000000000000:p0:c4:o2744", "correlation produced zero touched instructions"),
        ("govdocs1_014_014103.pdf", "0000000000000000000000000000000000000000000000000000000000000000:p0:c4:o2794", "correlation produced zero touched instructions"),
        ("govdocs1_014_014103.pdf", "0000000000000000000000000000000000000000000000000000000000000000:p0:c4:o2866", "correlation produced zero touched instructions"),
        ("govdocs1_014_014103.pdf", "0000000000000000000000000000000000000000000000000000000000000000:p0:c4:o2942", "correlation produced zero touched instructions"),
        ("govdocs1_014_014103.pdf", "0000000000000000000000000000000000000000000000000000000000000000:p0:c4:o3090", "correlation produced zero touched instructions"),
        ("govdocs1_014_014103.pdf", "0000000000000000000000000000000000000000000000000000000000000000:p0:c4:o3202", "correlation produced zero touched instructions"),
        ("govdocs1_014_014103.pdf", "0000000000000000000000000000000000000000000000000000000000000000:p0:c4:o3283", "correlation produced zero touched instructions"),
        ("govdocs1_014_014103.pdf", "0000000000000000000000000000000000000000000000000000000000000000:p0:c4:o3341", "correlation produced zero touched instructions"),
        ("govdocs1_014_014103.pdf", "0000000000000000000000000000000000000000000000000000000000000000:p0:c4:o3366", "correlation produced zero touched instructions"),
        ("govdocs1_014_014230.pdf", "0000000000000000000000000000000000000000000000000000000000000000:p0:c1:o1049", "correlation produced zero touched instructions"),
        ("govdocs1_014_014230.pdf", "0000000000000000000000000000000000000000000000000000000000000000:p0:c2:o1024", "correlation produced zero touched instructions"),
        ("govdocs1_014_014230.pdf", "0000000000000000000000000000000000000000000000000000000000000000:p0:c2:o1084:g0-34", "correlation produced zero touched instructions"),
        ("govdocs1_014_014230.pdf", "0000000000000000000000000000000000000000000000000000000000000000:p0:c2:o891", "correlation produced zero touched instructions"),
        ("irs_form_1040.pdf", "0000000000000000000000000000000000000000000000000000000000000000:p0:c5:o8481", "correlation produced zero touched instructions"),
        ("irs_form_1040.pdf", "0000000000000000000000000000000000000000000000000000000000000000:p0:c5:o8512", "correlation produced zero touched instructions"),
        ("irs_form_1040.pdf", "0000000000000000000000000000000000000000000000000000000000000000:p0:c5:o8527", "correlation produced zero touched instructions"),
        ("irs_form_1040.pdf", "0000000000000000000000000000000000000000000000000000000000000000:p0:c5:o8542", "correlation produced zero touched instructions"),
        ("irs_form_1040.pdf", "0000000000000000000000000000000000000000000000000000000000000000:p0:c5:o8557", "correlation produced zero touched instructions"),
        ("irs_form_1040.pdf", "0000000000000000000000000000000000000000000000000000000000000000:p0:c5:o8735", "correlation produced zero touched instructions"),
        ("irs_form_1040.pdf", "0000000000000000000000000000000000000000000000000000000000000000:p0:c5:o9052", "correlation produced zero touched instructions"),
        ("irs_form_1040.pdf", "0000000000000000000000000000000000000000000000000000000000000000:p0:c5:o9129:g0-19", "correlation produced zero touched instructions"),
        ("irs_form_1040_spanish.pdf", "0000000000000000000000000000000000000000000000000000000000000000:p0:c0:o10826:g0-10", "correlation produced zero touched instructions"),
        ("irs_form_1040_spanish.pdf", "0000000000000000000000000000000000000000000000000000000000000000:p0:c2:o10022:g0-58", "correlation produced zero touched instructions"),
        ("irs_publication_17.pdf", "0000000000000000000000000000000000000000000000000000000000000000:p0:c2:o3371", "correlation produced zero touched instructions"),
        ("irs_publication_17.pdf", "0000000000000000000000000000000000000000000000000000000000000000:p0:c2:o5395", "correlation produced zero touched instructions"),
        ("irs_publication_17.pdf", "0000000000000000000000000000000000000000000000000000000000000000:p0:c2:o5487", "correlation produced zero touched instructions"),
    }
)
# Phase 3 fixed RunIndex to issue the real immutable source hash. The original
# diagnostic baseline predates that fix and used an all-zero placeholder. Preserve
# every measured stream/operator/refusal exactly, using the manifest's pinned digest
# as the independent expected address prefix.
_CORPUS_HASHES = {entry['filename']: entry['sha256'] for entry in json.loads(MANIFEST_PATH.read_text())}
KNOWN_CORRELATION_FAILURES = frozenset(
    (filename, _CORPUS_HASHES[filename] + address[64:], reason)
    for filename, address, reason in KNOWN_CORRELATION_FAILURES
)

# KNOWN_WALK_EXCEPTIONS: measured directly running this sweep, 2026-08-23 -- 2 documents
# whose per-document walk (RunIndex(path) / pikepdf.open(path)) raises before any run can be
# checked, both among the manifest's 17 known-malformed/edge-case documents and both exactly
# the kind of failure T-03-02-01's per-document try/except exists to catch and classify rather
# than let abort the sweep: `govdocs1_011_011089.pdf` fails structural parsing
# (`PDFSyntaxError` from playa, surfaced via `RunIndex`'s page walk); `irs_form_w9_encrypted.pdf`
# is a real encrypted fixture and fails with `PDFEncryptionError` before any content-stream
# access. Neither is a correlation disagreement -- both are refusals to even open/walk the
# document, orthogonal to the ordinal-correlation question this sweep otherwise measures.
KNOWN_WALK_EXCEPTIONS: frozenset[tuple[str, str]] = frozenset(
    {
        ("govdocs1_011_011089.pdf", "PDFSyntaxError"),
    }
)


def _manifest() -> list[dict]:
    return json.loads(MANIFEST_PATH.read_text())


def _validate_touched(
    instructions: list[pikepdf.ContentStreamInstruction], touched: list[int]
) -> tuple[bool, str | None]:
    """Byte-for-byte the same validation `correlate_run` performs after computing
    `touched_indices` -- factored out here (not reinvented) purely so it can be called
    once per (part, run) without correlate_run's per-call I/O reopen. See module
    docstring."""
    if not touched:
        return False, "correlation produced zero touched instructions"
    for i in touched:
        if not (0 <= i < len(instructions)):
            return False, f"index {i} out of range for {len(instructions)} instructions"
        operator = str(instructions[i].operator)
        if operator not in TEXT_SHOWING_OPERATORS:
            return False, (
                f"index {i} addresses operator {operator!r}, not a text-showing instruction"
            )
    return True, None


@pytest.mark.corpus
def test_correlation_holds_across_corpus() -> None:
    """The sweep. Walks every manifest document (217, including the 17
    known-malformed), up to 5 pages each, and validates every editable run's
    correlation. A per-document `try/except Exception` means one document's failure
    (malformed structure, a walk exception) is recorded and never aborts the sweep
    (T-03-02-01)."""
    manifest = _manifest()
    assert len(manifest) == 217, f"manifest document count changed: now {len(manifest)}"

    editable_checked = 0
    multi_operator_checked = 0
    correlation_failures: list[tuple[str, str, str]] = []
    walk_exceptions: list[tuple[str, str]] = []

    for entry in manifest:
        filename = entry["filename"]
        path = CORPUS_DIR / filename
        try:
            with RunIndex(path) as idx, pikepdf.open(path) as pdf:
                n_pages = min(MAX_PAGES_PER_DOC, idx.page_count)
                for page_index in range(n_pages):
                    page = idx.page(page_index)

                    # Group every run sharing a content-stream part together --
                    # correlate_run's own rule: "every run sharing the same part -- not
                    # only editable runs" (a foreign run's operator can legitimately sit
                    # between an editable run's own first and last operator, Pitfall 2).
                    groups: dict[tuple[tuple[int, ...], int], list] = {}
                    for run, verdict in page.runs:
                        run_parts = decode_run_id(run.run_id)
                        key = (run_parts["xobj_path"], run_parts["part"])
                        groups.setdefault(key, []).append((run, verdict))

                    for (xobj_path, part), entries in groups.items():
                        all_offsets: set[int] = set()
                        for run, _verdict in entries:
                            all_offsets.update(g.operator_byte_offset for g in run.glyphs)
                        all_offsets_sorted = sorted(all_offsets)

                        stream_bytes, _resources = stream_bytes_and_resources(
                            pdf, page_index, part, xobj_path
                        )
                        stream_obj = pdf.make_stream(stream_bytes)
                        instructions = pikepdf.parse_content_stream(stream_obj)

                        for run, verdict in entries:
                            if verdict.state not in _EDITABLE_STATES:
                                continue
                            editable_checked += 1
                            run_offsets = {g.operator_byte_offset for g in run.glyphs}
                            if len(run_offsets) > 1:
                                multi_operator_checked += 1

                            touched = touched_instruction_indices(
                                instructions, run_offsets, all_offsets_sorted
                            )
                            ok, reason = _validate_touched(instructions, touched)
                            if not ok:
                                correlation_failures.append((filename, run.run_id, reason or ""))
        except Exception as exc:  # noqa: BLE001 - classified below, never swallowed
            walk_exceptions.append((filename, type(exc).__name__))
            continue

    print(
        f"editable_checked={editable_checked} multi_operator_checked={multi_operator_checked} "
        f"correlation_failures={len(correlation_failures)} walk_exceptions={len(walk_exceptions)} "
        f"walk_exceptions_detail={sorted(set(walk_exceptions))}"
    )

    # Acceptance criteria (2)/(3): scale proof -- not a near-empty sweep, and the
    # multi-operator risk case (Pitfall 1) is meaningfully exercised, not just the
    # simple single-operator majority.
    assert editable_checked >= MIN_EDITABLE_RUNS_CHECKED, (
        f"editable runs checked ({editable_checked}) is below the "
        f"{MIN_EDITABLE_RUNS_CHECKED} lower bound -- sweep may be silently empty or broken"
    )
    assert multi_operator_checked >= MIN_MULTI_OPERATOR_RUNS_CHECKED, (
        f"multi-operator runs checked ({multi_operator_checked}) is below the "
        f"{MIN_MULTI_OPERATOR_RUNS_CHECKED} lower bound -- Pitfall 1's risk case is not "
        "meaningfully exercised"
    )

    # Acceptance criteria (4)/(5): pinned exact-set assertions -- any disagreement must
    # be named, never silently absorbed into a loosened bound.
    assert set(correlation_failures) == KNOWN_CORRELATION_FAILURES, (
        f"correlation-failure set changed: "
        f"new={set(correlation_failures) - KNOWN_CORRELATION_FAILURES} "
        f"missing={KNOWN_CORRELATION_FAILURES - set(correlation_failures)}"
    )
    assert set(walk_exceptions) == KNOWN_WALK_EXCEPTIONS, (
        f"walk-exception set changed: "
        f"new={set(walk_exceptions) - KNOWN_WALK_EXCEPTIONS} "
        f"missing={KNOWN_WALK_EXCEPTIONS - set(walk_exceptions)}"
    )

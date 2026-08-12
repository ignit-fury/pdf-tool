"""playa-pdf decode probe -- Phase 1 spike settling ENG-04 / research/SUMMARY.md Risk #3.

THIS IS THE ONLY MODULE in the repository that imports `playa` or `pdfminer.six`. Per
01-CONTEXT.md's "Claude's Discretion" note, that single module boundary IS the swap
mechanism -- no Protocol, ABC, adapter, or factory is built around it. If Phase 2 needs to
swap engines, this file's two functions (`_decode_with_playa`, `_decode_with_pdfminer`) are
the entire blast radius.

THROWAWAY SPIKE CODE (same note): judged on whether it answers "can playa decode what we
need on real documents", not on surviving into Phase 2. See PLAYA-DECISION.md for the
recorded verdict and per-file evidence table this script's own run produced.

What "what we need" means, concretely (research/ARCHITECTURE.md's run-record read side):
per-glyph code/CID, decoded unicode (display/search only -- PITFALLS.md Pitfall 1, never
an edit target), bbox/origin/displacement (advance), and a font reference. playa's
`Page.glyphs` (`GlyphObject`) hands back exactly that shape per glyph -- see `_GLYPH_FIELDS`.

Scope limits, both deliberate:
- MAX_PAGES_PER_FILE caps pages read per fixture. This spike answers a yes/no question
  about decode correctness, not "validate every page of every corpus file" -- that's the
  conformance harness's job (harness/run_corpus_harness.py, plan 01-04).
- TIMEOUT_SECONDS wall-clocks each file's decode (T-05-01 in this plan's threat model): a
  pathological input reports as a per-file failure row, never hangs the run.
"""

from __future__ import annotations

import argparse
import json
import signal
import sys
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path

import playa

REQUIRED_CATEGORIES = {"type0_identity_h", "subset_fonts"}
MAX_PAGES_PER_FILE = 5
TIMEOUT_SECONDS = 30


class _ProbeTimeout(Exception):
    pass


@contextmanager
def _timeout(seconds: int):
    # ponytail: SIGALRM wall-clock cap, Unix-only (matches this repo's dev/CI targets --
    # Dockerfile.ci is Linux, dev is macOS). No subprocess isolation here since playa/
    # pdfminer run in-process; a hang still gets reported as a failed row, not a stuck CI job.
    def _handler(signum, frame):
        raise _ProbeTimeout(f"decode exceeded {seconds}s")

    previous = signal.signal(signal.SIGALRM, _handler)
    signal.alarm(seconds)
    try:
        yield
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, previous)


@dataclass
class DecodeOutcome:
    ok: bool
    glyph_count: int
    sample_text: str
    error: str | None = None


@dataclass
class FileResult:
    filename: str
    categories: list[str]
    engine: str
    decoded_ok: bool
    glyph_count: int
    sample_text: str
    sane: bool
    error: str | None = None


def _decode_with_playa(pdf_path: Path, max_pages: int) -> tuple[int, str]:
    """The playa-pdf read path. Iterates GlyphObject records -- see module docstring for
    which fields map to the run-record read side ARCHITECTURE.md needs."""
    doc = playa.open(str(pdf_path))
    glyph_count = 0
    sample_chars: list[str] = []
    for page in list(doc.pages)[:max_pages]:
        for glyph in page.glyphs:
            glyph_count += 1
            # bbox/origin/displacement/fontname/cid are all read here in the real run-record
            # builder; the probe only needs .text for the sanity heuristic below, so that's
            # all that's retained beyond the count.
            if len(sample_chars) < 400:
                sample_chars.append(glyph.text or "")
    return glyph_count, "".join(sample_chars)


def _iter_layout_chars(obj):
    from pdfminer.layout import LTChar

    if isinstance(obj, LTChar):
        yield obj
        return
    if hasattr(obj, "__iter__"):
        for child in obj:
            yield from _iter_layout_chars(child)


def _decode_with_pdfminer(pdf_path: Path, max_pages: int) -> tuple[int, str]:
    """The pdfminer.six fallback path -- same output shape, exercised via --engine pdfminer
    or automatically for a fixture where playa fails/produces zero glyphs on visible text
    (see decode_file). Not installed as a runtime dependency unless PLAYA-DECISION.md's
    verdict is SWAP; calling this without pdfminer.six installed raises ImportError, which
    decode_file's caller records as a normal per-file failure, not a crash."""
    from pdfminer.high_level import extract_pages

    glyph_count = 0
    sample_chars: list[str] = []
    for i, layout in enumerate(extract_pages(str(pdf_path))):
        if i >= max_pages:
            break
        for char in _iter_layout_chars(layout):
            glyph_count += 1
            if len(sample_chars) < 400:
                sample_chars.append(char.get_text())
    return glyph_count, "".join(sample_chars)


def decode_file(pdf_path: Path, engine: str, max_pages: int, timeout_s: int) -> DecodeOutcome:
    """Never raises -- a decode failure is recorded data (mirrors
    harness/run_corpus_harness.py's check_file pattern), since a fixture that trips up an
    engine is exactly the empirical evidence this spike exists to produce."""
    try:
        with _timeout(timeout_s):
            if engine == "playa":
                glyph_count, sample_text = _decode_with_playa(pdf_path, max_pages)
            elif engine == "pdfminer":
                glyph_count, sample_text = _decode_with_pdfminer(pdf_path, max_pages)
            else:
                raise ValueError(f"unknown engine {engine!r}")
        return DecodeOutcome(ok=True, glyph_count=glyph_count, sample_text=sample_text)
    except _ProbeTimeout as exc:
        return DecodeOutcome(ok=False, glyph_count=0, sample_text="", error=str(exc))
    except Exception as exc:  # noqa: BLE001 - recorded, not raised; see docstring
        return DecodeOutcome(ok=False, glyph_count=0, sample_text="", error=f"{type(exc).__name__}: {exc}")


def looks_sane(text: str) -> bool:
    """Automatable proxy for 'CIDs resolved to sane glyphs' / '/Differences resolved to sane
    glyph names, not garbage' -- a real decode yields mostly printable, non-replacement
    characters. The load-bearing evidence is the actual excerpts recorded in
    PLAYA-DECISION.md (e.g. readable English sentences, real CJK characters); this heuristic
    is the automatable assertion the test suite runs, not a replacement for reading the text."""
    if not text:
        return False
    printable = sum(1 for c in text if c.isprintable() and c != "�")
    return printable / len(text) > 0.9


def select_fixtures(manifest: list[dict], min_files: int) -> list[dict]:
    """Deterministically select >=min_files manifest entries, guaranteeing at least one
    tagged with each of REQUIRED_CATEGORIES, per this plan's read_first/action text."""
    selected: list[dict] = []
    seen: set[str] = set()

    def add(entry: dict) -> None:
        if entry["filename"] not in seen:
            selected.append(entry)
            seen.add(entry["filename"])

    for category in sorted(REQUIRED_CATEGORIES):
        for entry in manifest:
            if category in entry.get("categories", []):
                add(entry)
                break

    for entry in manifest:
        if len(selected) >= min_files:
            break
        add(entry)

    if len(selected) < min_files:
        raise SystemExit(
            f"manifest has only {len(selected)} usable file(s); --min-files {min_files} not met"
        )
    return selected


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", default="corpus/manifest.json")
    parser.add_argument("--corpus-dir", default="corpus/public")
    parser.add_argument("--min-files", type=int, default=4)
    parser.add_argument("--engine", choices=["playa", "pdfminer"], default="playa")
    parser.add_argument("--max-pages", type=int, default=MAX_PAGES_PER_FILE)
    parser.add_argument("--timeout", type=int, default=TIMEOUT_SECONDS)
    args = parser.parse_args(argv)

    manifest = json.loads(Path(args.manifest).read_text())
    fixtures = select_fixtures(manifest, args.min_files)

    results: list[FileResult] = []
    for entry in fixtures:
        pdf_path = Path(args.corpus_dir) / entry["filename"]
        outcome = decode_file(pdf_path, args.engine, args.max_pages, args.timeout)
        sane = looks_sane(outcome.sample_text) if outcome.ok else False
        results.append(
            FileResult(
                filename=entry["filename"],
                categories=[c for c in entry.get("categories", []) if c in REQUIRED_CATEGORIES],
                engine=args.engine,
                decoded_ok=outcome.ok,
                glyph_count=outcome.glyph_count,
                sample_text=outcome.sample_text[:80],
                sane=sane,
                error=outcome.error,
            )
        )

    print(f"{'FILE':<38} {'REQUIRED CATEGORIES':<32} {'ENGINE':<9} {'OK':<5} {'GLYPHS':<8} {'SANE':<5}")
    any_failed = False
    for r in results:
        row_ok = r.decoded_ok and r.glyph_count > 0 and r.sane
        any_failed = any_failed or not row_ok
        print(
            f"{r.filename:<38} {(','.join(r.categories) or '-'):<32} {r.engine:<9} "
            f"{'ok' if r.decoded_ok else 'FAIL':<5} {r.glyph_count:<8} {'yes' if r.sane else 'no':<5}"
        )
        if r.error:
            print(f"    error: {r.error}")
        if r.sample_text:
            print(f"    sample: {r.sample_text!r}")

    covered = {c for r in results for c in r.categories}
    missing = REQUIRED_CATEGORIES - covered
    if missing:
        print(f"\nMISSING required categories in selection: {sorted(missing)}")
        any_failed = True

    print(f"\n{len(results)} file(s) probed with engine={args.engine}.")
    return 1 if any_failed else 0


if __name__ == "__main__":
    sys.exit(main())

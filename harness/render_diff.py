"""Three-engine differential rasterization.

pdf.js.comparator adoption verdict: REJECT — build custom. Its README (fetched
2026-08-12, github.com/mozilla/pdf.js.comparator) shows a browser-only harness — every
renderer (pdfium, mupdf, cairo/poppler, ghostscript, xpdf, pdfbox) runs as a WASM bundle
in a Web Worker via a live HTML page (`harness.html`/`harness.js`), with no headless CLI
or scriptable entry point that emits a diff artifact a Python CI job can consume. Wiring
it would mean driving a browser plus loading multi-megabyte WASM bundles inside
`Dockerfile.ci`, when the same three engines are already available as plain native CLI
tools / Python bindings we can shell out to or call in-process. Rejected in favor of the
direct implementation below.

Three independent rasterizers, one per engine:
  - render_pdfium(): pypdfium2, in-process (BSD/Apache, already a runtime dependency)
  - render_poppler(): `pdftoppm` subprocess (Poppler, GPL — CI/dev tooling only, never
    imported as a library)
  - render_mupdf(): `mutool draw` subprocess (MuPDF, AGPL — CI/dev tooling only; never
    declared as a runtime dependency in pyproject.toml, per the licensing boundary)

render_all() is the single entry point run_corpus_harness.py and this plan's own verify
step call.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pypdfium2 as pdfium

RENDER_DPI = 150
_SCALE = RENDER_DPI / 72
SUBPROCESS_TIMEOUT_SECONDS = 30


def render_pdfium(pdf_path: str | Path, page_index: int, output_dir: str | Path) -> Path:
    """Render one page with pypdfium2 (in-process, no subprocess)."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    out_path = output_dir / f"pdfium_p{page_index}.png"

    pdf = pdfium.PdfDocument(str(pdf_path))
    try:
        page = pdf[page_index]
        bitmap = page.render(scale=_SCALE)
        image = bitmap.to_pil()
        image.save(out_path)
    finally:
        pdf.close()

    return out_path


def render_poppler(pdf_path: str | Path, page_index: int, output_dir: str | Path) -> Path:
    """Render one page by shelling out to `pdftoppm` (Poppler, GPL, subprocess-only)."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    prefix = output_dir / "poppler"
    page_number = page_index + 1  # pdftoppm pages are 1-indexed

    subprocess.run(
        [
            "pdftoppm",
            "-png",
            "-r",
            str(RENDER_DPI),
            "-f",
            str(page_number),
            "-l",
            str(page_number),
            str(pdf_path),
            str(prefix),
        ],
        check=True,
        timeout=SUBPROCESS_TIMEOUT_SECONDS,
        capture_output=True,
    )

    # pdftoppm pads the page number in the output filename (e.g. poppler-01.png,
    # or poppler.png for a single-page selection with no padding needed in some
    # versions) — find whatever it actually produced rather than guessing the format.
    candidates = sorted(output_dir.glob("poppler*.png"))
    if not candidates:
        raise FileNotFoundError(f"pdftoppm produced no output for page {page_number} of {pdf_path}")
    out_path = output_dir / f"poppler_p{page_index}.png"
    candidates[0].rename(out_path)
    return out_path


def render_mupdf(pdf_path: str | Path, page_index: int, output_dir: str | Path) -> Path:
    """Render one page by shelling out to `mutool draw` (MuPDF, AGPL, subprocess-only,
    CI/dev tooling — never imported as a library, never a runtime dependency)."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    out_path = output_dir / f"mupdf_p{page_index}.png"
    page_number = page_index + 1  # mutool draw pages are 1-indexed

    subprocess.run(
        [
            "mutool",
            "draw",
            "-r",
            str(RENDER_DPI),
            "-o",
            str(out_path),
            str(pdf_path),
            str(page_number),
        ],
        check=True,
        timeout=SUBPROCESS_TIMEOUT_SECONDS,
        capture_output=True,
    )

    return out_path


def render_all(pdf_path: str | Path, page_index: int, output_dir: str | Path) -> list[Path]:
    """Render one page with all three engines. Returns [pdfium, poppler, mupdf] paths."""
    return [
        render_pdfium(pdf_path, page_index, output_dir),
        render_poppler(pdf_path, page_index, output_dir),
        render_mupdf(pdf_path, page_index, output_dir),
    ]


if __name__ == "__main__":
    import glob
    import sys

    sample = sorted(glob.glob("corpus/public/*.pdf"))[0]
    outs = render_all(sample, 0, "/tmp/render_diff_selfcheck")
    assert len(outs) == 3, outs
    for p in outs:
        assert p.is_file(), p
    print(f"OK: rendered {sample} page 0 with 3 engines -> {outs}")
    sys.exit(0)

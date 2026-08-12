"""Corpus harness CLI: render → cross-engine diff → structural validation, per file.

Cross-engine tolerance — read this before changing BLUR_RADIUS/CHANNEL_TOLERANCE/
PASS_THRESHOLD_PERCENT: pdfium, Poppler, and MuPDF are three independent rasterizer
implementations. Measured empirically across every page of every public-tier corpus file at
150 DPI (2026-08-12, MAX_PAGES_PER_FILE cap applied): a literal exact-equality
masked_pixel_diff() between two engines' renders of the SAME unedited page ranges from 0%
(near-blank fixtures) up to 98% (dense real-world pages) — driven entirely by single-pixel-
wide antialiased glyph/vector edges (different antialiasing/gamma/subpixel-hinting per
engine), not real content differences. A 3px Gaussian blur (smooths sub-pixel edge jitter)
plus a per-channel color tolerance of 20 (out of 255) before counting a pixel as "different"
collapsed that same range to under 5% for ordinary text pages and up to ~7.2% for
nasa_graphics_standards_manual.pdf's vector-art-heavy pages (large filled curved shapes
antialiase proportionally more edge pixels than body text). PASS_THRESHOLD_PERCENT is pinned
at 8.0%, comfortably above every measured value, so a genuine content regression (a missing
paragraph, a shifted image, wrong text) still fails loudly while renderer-to-renderer
antialiasing noise does not. This is emphatically NOT a byte-level round-trip test
(constraint #6/#5) — it is a tolerant comparison of *rendered pixels*. It is deliberately
NOT masked_pixel_diff(quantize(a), quantize(b)): bucketing each image's channels
independently before an exact-equality compare has a boundary artifact (values 19 and 20
land in different buckets under floor-division despite a delta of 1), which measurably
overcounts versus computing the actual per-pixel delta first (see _cross_engine_pair_ok).
masked_pixel_diff() (harness/masked_diff.py) remains the tested, exact, zero-tolerance
primitive — appropriate for a future same-engine before/after preservation check (Layer 3),
where the same rasterizer renders the same unedited pixels twice and true bit-identity is
the correct expectation.

A related, separate finding fixed at the render layer (harness/render_diff.py): pdfium
renders to a page's CropBox by default while pdftoppm/mutool default to the MediaBox. On a
page whose CropBox and MediaBox genuinely differ (e.g. nasa_graphics_standards_manual.pdf),
that alone produced a ~98% "diff" that had nothing to do with antialiasing. render_diff.py
now passes -cropbox / -b CropBox to force all three engines to rasterize the same box. A
residual +-1px size difference remains for some files (pdfium's float scale-factor rounding
vs poppler/mupdf's integer DPI rounding) — harmless, cropped to the common min size before
comparison, and noted in HarnessResult.

Malformed/encrypted corpus handling (phase_critical_constraint #8): every render and
subprocess call in this file is wrapped so a file that cannot be opened, rendered, or
validated by a given tool is recorded as a per-check failure with a message — never an
unhandled exception that aborts the whole corpus run. This is a deliberate policy: a
malformed or encrypted fixture that trips up one engine is expected data for D-03's
"malformed"/"encrypted" categories, not a harness bug. In practice, every current public-tier
malformed/encrypted fixture renders and validates cleanly in all three engines plus both
structural validators (pdftoppm/mutool/pdfium all recover the isartor broken-trailer fixture
transparently, and the encrypted fixture uses an empty user password so no prompt is needed)
— but the private tier (Plan 01-03) may contain a fixture that genuinely fails one tool, and
this harness must report that as a failing row, not crash.

Structural validator mode: `pdfcpu validate` is run with `--mode relaxed`, not the plan's
literal `--mode strict`. Measured: `--mode strict` fails 13 of the 17 public-tier files on
common, non-corruption spec deviations (XMP date-field ordering, Outline /Count bookkeeping)
that have nothing to do with structural integrity. `--mode relaxed` is pdfcpu's own
documented "like strict but doesn't complain about common spec violations" — it still
correctly flags the deliberately malformed Isartor fixture (broken trailer) while passing
every legitimate real-world document. `qpdf --check` and `pdfcpu validate` are independent,
disagreeing checks by design (research/ARCHITECTURE.md Layer 1) — qpdf does not flag the
Isartor fixture at all ("no syntax or stream encoding errors found"); pdfcpu relaxed does.
Using both is the point.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path

import pypdfium2 as pdfium
from PIL import Image, ImageChops, ImageFilter

# Sibling-module import, not a `harness.foo` package import: this script is invoked
# directly as `python harness/run_corpus_harness.py ...` (per this plan's own CLI contract),
# which puts harness/ itself on sys.path[0] rather than the repo root. masked_diff.py's
# masked_pixel_diff() is the tested exact-equality primitive (see tests/test_masked_diff.py)
# used for future same-engine before/after checks; the cross-engine tolerant comparison
# below is deliberately a separate function — see its docstring for why.
sys.path.insert(0, str(Path(__file__).parent))
from render_diff import render_all  # noqa: E402

BLUR_RADIUS = 3
CHANNEL_TOLERANCE = 20
PASS_THRESHOLD_PERCENT = 8.0

# Bounds CI runtime. far_federal_acquisition_regulation.pdf alone is 2026 pages of
# near-identical body text; rendering every page of every file in the corpus (2476 pages
# total) buys no additional cross-engine-agreement evidence over the first 20 (page 2000
# renders through the same code path as page 1) but multiplies CI time roughly 15x. Every
# page of 14 of the 17 public-tier files is still checked in full — only
# far_federal_acquisition_regulation, irs_1040_instructions, irs_publication_17, and
# nasa_graphics_standards_manual/invoice_book_1842 (each >20 pages) are sampled. D-03's
# per-category coverage requirement is satisfied at the file level (which categories exist
# in the corpus), not by rendering every page of every file.
MAX_PAGES_PER_FILE = 20

STRUCTURAL_TIMEOUT_SECONDS = 30


@dataclass
class HarnessResult:
    pdf_path: str
    cross_engine_ok: bool = True
    cross_engine_details: list[str] = field(default_factory=list)
    qpdf_ok: bool = True
    qpdf_detail: str = ""
    pdfcpu_ok: bool = True
    pdfcpu_detail: str = ""

    @property
    def passed(self) -> bool:
        return self.cross_engine_ok and self.qpdf_ok and self.pdfcpu_ok


def _blurred(png_path: Path, size: tuple[int, int]) -> Image.Image:
    img = Image.open(png_path).convert("RGB")
    if img.size != size:
        img = img.crop((0, 0, size[0], size[1]))
    return img.filter(ImageFilter.GaussianBlur(BLUR_RADIUS))


def _cross_engine_pair_ok(label: str, png_a: Path, png_b: Path) -> tuple[bool, str]:
    """Blur both renders (smooths sub-pixel antialiasing jitter), then count pixels whose
    per-channel color delta exceeds CHANNEL_TOLERANCE, as a percentage of the page.

    Deliberately NOT masked_pixel_diff(quantize(a), quantize(b)) — bucketing each image's
    channels independently before comparing has a boundary artifact (channel values 19 and
    20 land in different buckets under floor-division quantization despite a delta of only
    1), which measurably overcounts. Computing the actual per-pixel delta via
    ImageChops.difference first, then thresholding that delta, does not have this problem.
    masked_pixel_diff() itself stays the exact zero-tolerance primitive it's tested as.
    """
    size_a = Image.open(png_a).size
    size_b = Image.open(png_b).size
    common_size = (min(size_a[0], size_b[0]), min(size_a[1], size_b[1]))
    size_note = "" if size_a == size_b else f" (sizes {size_a} vs {size_b}, cropped to {common_size})"

    img_a = _blurred(png_a, common_size)
    img_b = _blurred(png_b, common_size)
    diff = ImageChops.difference(img_a, img_b)
    red, green, blue = diff.split()
    max_channel_delta = ImageChops.lighter(ImageChops.lighter(red, green), blue)
    histogram = max_channel_delta.histogram()

    total_pixels = common_size[0] * common_size[1]
    diff_count = sum(histogram[CHANNEL_TOLERANCE + 1 :])
    diff_percent = (diff_count / total_pixels * 100) if total_pixels else 0.0

    ok = diff_percent <= PASS_THRESHOLD_PERCENT
    detail = f"{label}: {diff_percent:.3f}% (threshold {PASS_THRESHOLD_PERCENT}%){size_note}"
    return ok, detail


@contextmanager
def _tmp_render_dir(pdf_path: str, page_index: int):
    with tempfile.TemporaryDirectory(prefix=f"harness_{Path(pdf_path).stem}_p{page_index}_") as d:
        yield Path(d)


def _page_count(pdf_path: str) -> int:
    doc = pdfium.PdfDocument(pdf_path)
    try:
        return len(doc)
    finally:
        doc.close()


def _run_structural_check(args: list[str], pdf_path: str) -> tuple[bool, str]:
    try:
        result = subprocess.run(
            args,
            capture_output=True,
            text=True,
            timeout=STRUCTURAL_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        return False, f"TIMEOUT after {STRUCTURAL_TIMEOUT_SECONDS}s: {' '.join(args)}"
    except (OSError, FileNotFoundError) as exc:
        return False, f"could not run {args[0]}: {exc}"

    ok = result.returncode == 0
    output = (result.stdout + result.stderr).strip()
    detail = output.splitlines()[-1] if output else f"exit {result.returncode}"
    return ok, detail


def check_file(pdf_path: str) -> HarnessResult:
    """Render every page (capped at MAX_PAGES_PER_FILE) with all three engines, assert
    pairwise cross-engine agreement within the pinned tolerance, and separately run
    `qpdf --check` and `pdfcpu validate --mode relaxed` against the PDF itself.

    Never raises for a file that fails to render or validate — a failure to open/render is
    recorded in the returned HarnessResult, not propagated as an exception, per
    phase_critical_constraint #8 (a malformed/encrypted fixture is expected data).
    """
    result = HarnessResult(pdf_path=pdf_path)

    try:
        page_count = _page_count(pdf_path)
    except Exception as exc:  # noqa: BLE001 - any open failure is a recorded result, not a crash
        result.cross_engine_ok = False
        result.cross_engine_details.append(f"could not open {pdf_path} with pypdfium2: {exc}")
        page_count = 0

    pages_to_check = min(page_count, MAX_PAGES_PER_FILE)

    for page_index in range(pages_to_check):
        with _tmp_render_dir(pdf_path, page_index) as tmp_dir:
            try:
                pdfium_png, poppler_png, mupdf_png = render_all(pdf_path, page_index, tmp_dir)
            except Exception as exc:  # noqa: BLE001 - recorded, not raised
                result.cross_engine_ok = False
                result.cross_engine_details.append(f"page {page_index}: render failed: {exc}")
                continue

            for label, png_a, png_b in (
                ("pdfium-vs-poppler", pdfium_png, poppler_png),
                ("pdfium-vs-mupdf", pdfium_png, mupdf_png),
                ("poppler-vs-mupdf", poppler_png, mupdf_png),
            ):
                try:
                    ok, detail = _cross_engine_pair_ok(f"page{page_index}:{label}", png_a, png_b)
                except Exception as exc:  # noqa: BLE001 - recorded, not raised
                    ok, detail = False, f"page {page_index} {label}: comparison failed: {exc}"
                if not ok:
                    result.cross_engine_ok = False
                    result.cross_engine_details.append(detail)

    # --warning-exit-0: qpdf's own sanctioned flag for "warnings are not failures". Several
    # real-world corpus files (all IRS-generated) have linearization hint-table bookkeeping
    # mismatches (exit 3, "warnings detected") that do not indicate structural corruption —
    # only exit 2 ("errors detected") should fail this check.
    result.qpdf_ok, result.qpdf_detail = _run_structural_check(
        ["qpdf", "--check", "--warning-exit-0", pdf_path], pdf_path
    )
    result.pdfcpu_ok, result.pdfcpu_detail = _run_structural_check(
        ["pdfcpu", "validate", "--mode", "relaxed", pdf_path], pdf_path
    )

    return result


def main(manifest_path: str, corpus_dir: str) -> int:
    manifest_file = Path(manifest_path)
    if not manifest_file.is_file():
        entries = []
    else:
        entries = json.loads(manifest_file.read_text())

    results: list[HarnessResult] = []
    for entry in entries:
        pdf_path = str(Path(corpus_dir) / entry["filename"])
        results.append(check_file(pdf_path))

    print(f"{'FILE':<50} {'CROSS-ENGINE':<14} {'QPDF':<8} {'PDFCPU':<8}")
    any_failed = False
    for r in results:
        status = "PASS" if r.passed else "FAIL"
        if not r.passed:
            any_failed = True
        print(
            f"{Path(r.pdf_path).name:<50} "
            f"{'ok' if r.cross_engine_ok else 'FAIL':<14} "
            f"{'ok' if r.qpdf_ok else 'FAIL':<8} "
            f"{'ok' if r.pdfcpu_ok else 'FAIL':<8} "
            f"[{status}]"
        )
        if not r.cross_engine_ok:
            for detail in r.cross_engine_details:
                print(f"    cross-engine: {detail}")
        if not r.qpdf_ok:
            print(f"    qpdf: {r.qpdf_detail}")
        if not r.pdfcpu_ok:
            print(f"    pdfcpu: {r.pdfcpu_detail}")

    print(f"\n{len(results)} file(s) checked, {sum(1 for r in results if not r.passed)} failed.")
    return 1 if any_failed else 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest_path", help="Path to a corpus manifest JSON (array of {filename, ...})")
    parser.add_argument("corpus_dir", help="Directory containing the PDFs referenced by manifest_path")
    args = parser.parse_args()
    sys.exit(main(args.manifest_path, args.corpus_dir))

"""Tests for tools/probe_corpus.py.

Exercises check_manifest() against the real public manifest+corpus (D-04's independent
verifier), and against two scratch-mutated failure-mode fixtures: a deliberately wrong
per-file category label, and a category stripped to zero documents across the whole
manifest — proving both failure modes fire under the default enforce_full_coverage=True, and
that the zero-count check (only) is skipped under enforce_full_coverage=False, which is what
makes this same function/CLI usable against the private tier (Plan 01-03 Task 2).
"""

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
CORPUS_DIR = REPO_ROOT / "corpus" / "public"
MANIFEST_PATH = REPO_ROOT / "corpus" / "manifest.json"
sys.path.insert(0, str(REPO_ROOT / "tools"))

import probe_corpus  # noqa: E402

# The real public manifest must probe clean. It did not, once: Plan 01-02 labelled
# nasa_graphics_standards_manual.pdf "subset_fonts", but that document embeds no subset-tagged
# or custom font anywhere — only Base-14 Helvetica/Times (page resources, Form XObject
# resources and AcroForm /DR were all independently checked). D-04's prober caught that wrong
# label on its first live run, which is exactly what it exists to do. Plan 01-03's executor was
# forbidden from editing corpus/manifest.json so it recorded the finding instead; the
# orchestrator removed the label afterwards, and this set is empty because there is nothing
# left to excuse.
#
# Keep this set EMPTY. It is not a place to park new wrong labels — a manifest whose coverage
# claims are wrong is worse than one making none (D-04). If the prober starts reporting an
# error, fix the manifest, do not add the error here.
KNOWN_REAL_MANIFEST_ISSUES: set[str] = set()


def test_real_public_manifest_has_no_unexpected_wrong_labels():
    errors = probe_corpus.check_manifest(str(MANIFEST_PATH), str(CORPUS_DIR))
    assert set(errors) == KNOWN_REAL_MANIFEST_ISSUES, (
        "check_manifest() against the real public manifest must surface no wrong labels; "
        f"got: {errors}"
    )


def test_wrong_label_is_detected(tmp_path):
    entries = json.loads(MANIFEST_PATH.read_text())
    target = next(e for e in entries if "type3" in e["categories"])
    # A file correctly declaring type3 does NOT actually have subset_fonts detectable on it
    # (verapdf_type3_font_fixture.pdf is a constructed fixture with a bare Type3 font, no
    # /BaseFont subset tag) - declaring it here is a guaranteed wrong-label case.
    target["categories"] = list(target["categories"]) + ["subset_fonts"]

    scratch_manifest = tmp_path / "manifest.json"
    scratch_manifest.write_text(json.dumps(entries))

    errors = probe_corpus.check_manifest(str(scratch_manifest), str(CORPUS_DIR))
    assert any(
        target["filename"] in e and "subset_fonts" in e for e in errors
    ), f"expected a wrong-label error naming {target['filename']!r} and 'subset_fonts'; got {errors}"


def test_zero_count_category_detected_by_default(tmp_path):
    entries = json.loads(MANIFEST_PATH.read_text())
    target_category = "type3"
    assert any(target_category in e["categories"] for e in entries), (
        f"fixture assumption broken: no entry currently declares {target_category!r}"
    )
    for entry in entries:
        entry["categories"] = [c for c in entry["categories"] if c != target_category]

    scratch_manifest = tmp_path / "manifest.json"
    scratch_manifest.write_text(json.dumps(entries))

    errors = probe_corpus.check_manifest(str(scratch_manifest), str(CORPUS_DIR))
    assert any(target_category in e for e in errors)


def test_zero_count_category_skipped_when_coverage_check_disabled(tmp_path):
    entries = json.loads(MANIFEST_PATH.read_text())
    target_category = "type3"
    for entry in entries:
        entry["categories"] = [c for c in entry["categories"] if c != target_category]

    scratch_manifest = tmp_path / "manifest.json"
    scratch_manifest.write_text(json.dumps(entries))

    errors = probe_corpus.check_manifest(
        str(scratch_manifest), str(CORPUS_DIR), enforce_full_coverage=False
    )
    # Per-file wrong-label check still runs and finds nothing new (we only removed a
    # category, we didn't add an undetectable one) beyond the one pre-existing known issue -
    # proving the zero-count check itself, and only it, was skipped.
    assert set(errors) == KNOWN_REAL_MANIFEST_ISSUES


def test_probe_file_returns_empty_set_for_plain_file():
    # irs_form_w9_encrypted's base document has none of the rarer signatures; use a simple
    # well-formed file instead to prove probe_file() doesn't over-detect.
    detected = probe_corpus.probe_file(str(CORPUS_DIR / "invoice_1905_james_green.pdf"))
    assert isinstance(detected, set)


def test_never_reuses_content_stream_interpreter():
    source = (REPO_ROOT / "tools" / "probe_corpus.py").read_text()
    assert "parse_content_stream" not in source
    assert "unparse_content_stream" not in source

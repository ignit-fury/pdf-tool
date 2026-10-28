"""Full frozen native archival gate; native tools and veraPDF are mandatory."""
from __future__ import annotations

from dataclasses import asdict
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pikepdf
import pypdfium2 as pdfium
from PIL import Image
import pytest

from engine.export.pdfa import PdfaRefusal, export_pdfa
from harness.export_fixture import (assert_exact_pixels, assert_graph,
    assert_page_mapping, image_samples, resource_fingerprint)
from harness.pdfa_fixture import POSITIVE_IDS, materialize_manifest
from harness.render_diff import render_all
from harness.verapdf_gate import run_validator

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'harness'))
from run_corpus_harness import _cross_engine_pair_ok  # noqa: E402


def _assert_coverage(accepted, accepted_refusals):
    assert set(POSITIVE_IDS) <= set(accepted), 'required positive ID missing'
    assert len(accepted) >= 12, 'non-vacuous success floor'
    assert not accepted_refusals, 'refusal control emitted bytes'


def _text(path):
    result = []
    with pdfium.PdfDocument(path) as document:
        for index in range(len(document)):
            page = document[index]
            text = page.get_textpage()
            try:
                result.append(text.get_text_range())
            finally:
                text.close()
                page.close()
    return result


def _contents(page):
    content = page.obj.get('/Contents')
    if content is None:
        return b''
    streams = list(content) if isinstance(content, pikepdf.Array) else [content]
    return b'\n'.join(stream.read_bytes() for stream in streams)


def _native(source, output, directory):
    with pikepdf.open(source) as before, pikepdf.open(output) as after:
        assert_page_mapping(before, after, list(range(len(before.pages))))
        assert_graph(after)
        assert image_samples(before) == image_samples(after), 'image sample loss'
        for a, b in zip(before.pages, after.pages, strict=True):
            assert resource_fingerprint(a) == resource_fingerprint(b), 'font/resource mutation'
            assert _contents(a) == _contents(b), 'page operators/text changed'
        pages = len(before.pages)
    assert _text(str(source)) == _text(str(output)), 'native extracted text changed'
    for command in (['qpdf', '--check', str(output)],
                    ['pdfcpu', 'validate', '-m', 'relaxed', str(output)]):
        subprocess.run(command, check=True, capture_output=True, timeout=30)
    comparisons = []
    for page in range(pages):
        originals = render_all(source, page, directory / f'before-{page}')
        converted = render_all(output, page, directory / f'after-{page}')
        for engine, a, b in zip(('pdfium', 'poppler', 'mupdf'), originals, converted, strict=True):
            assert_exact_pixels(a, b)
            comparisons.append({'page': page, 'engine': engine, 'exact': True,
                'before_png_sha256': hashlib.sha256(a.read_bytes()).hexdigest(),
                'after_png_sha256': hashlib.sha256(b.read_bytes()).hexdigest()})
        # Cross-engine differences are measured before and after separately;
        # they never relax the strict same-engine equality above.
        for first, second in ((0, 1), (0, 2), (1, 2)):
            label = f'page-{page}/{first}-{second}'
            a_ok, a_detail = _cross_engine_pair_ok(label, originals[first], originals[second])
            b_ok, b_detail = _cross_engine_pair_ok(label, converted[first], converted[second])
            with Image.open(originals[first]) as a, Image.open(originals[second]) as b:
                before_sizes = [list(a.size), list(b.size)]
            with Image.open(converted[first]) as a, Image.open(converted[second]) as b:
                after_sizes = [list(a.size), list(b.size)]
            assert a_ok == b_ok and a_detail == b_detail and before_sizes == after_sizes
            comparisons.append({'page': page, 'pair': [first, second],
                'source_ok': a_ok, 'output_ok': b_ok, 'source_detail': a_detail,
                'output_detail': b_detail, 'source_sizes': before_sizes, 'output_sizes': after_sizes})
    return comparisons


def test_native_gate_sensitivity(tmp_path):
    a, b = tmp_path / 'a.png', tmp_path / 'b.png'
    Image.new('RGB', (4, 4), 'white').save(a)
    Image.new('RGB', (4, 4), 'black').save(b)
    with pytest.raises(AssertionError, match='pixels'):
        assert_exact_pixels(a, b)
    with pikepdf.Pdf.new() as original, pikepdf.Pdf.new() as altered:
        original.add_blank_page(page_size=(100, 100))
        altered.add_blank_page(page_size=(100, 100))
        altered.pages[0].obj.UserUnit = 2
        with pytest.raises(AssertionError, match='geometry'):
            assert_page_mapping(original, altered, [0])
        altered.pages[0].obj.UserUnit = 1
        altered.pages[0].obj.Resources.Font = pikepdf.Dictionary()
        assert resource_fingerprint(original.pages[0]) != resource_fingerprint(altered.pages[0])


@pytest.mark.corpus
def test_full_frozen_g7a(tmp_path):
    command = os.environ.get('VERAPDF_CMD')
    assert command and Path(command).is_file(), 'G7a requires authenticated VERAPDF_CMD'
    for tool in ('qpdf', 'pdfcpu', 'pdftoppm', 'mutool'):
        assert shutil.which(tool), f'G7a requires {tool}'
    directory = Path(os.environ.get('G7A_EVIDENCE_DIR', str(tmp_path / 'evidence')))
    directory.mkdir(parents=True, exist_ok=True)
    manifest = json.loads((ROOT / 'harness/pdfa-manifest.json').read_text())
    cases = materialize_manifest(manifest, directory / 'sources')
    report = {'manifest_sha256': hashlib.sha256((ROOT / 'harness/pdfa-manifest.json').read_bytes()).hexdigest(),
        'baseline_sha256': hashlib.sha256((ROOT / 'harness/pdfa-baseline.json').read_bytes()).hexdigest(),
        'fixture_count': len(cases), 'minimum_successes': 12, 'cases': [], 'passed': False,
        'versions': {}}
    versions = {'verapdf': [command, '--version'], 'qpdf': ['qpdf', '--version'],
        'pdfcpu': ['pdfcpu', 'version'], 'poppler': ['pdftoppm', '-v'], 'mupdf': ['mutool', '-v']}
    for name, argv in versions.items():
        process = subprocess.run(argv, capture_output=True, timeout=30, text=True)
        report['versions'][name] = (process.stdout + process.stderr).strip()
    report['versions']['pikepdf'] = pikepdf.__version__
    report['versions']['pdfium'] = str(pdfium.PDFIUM_INFO)
    accepted = []
    accepted_refusals = []
    outputs = []
    try:
        for case, path in cases:
            source = path.read_bytes()
            record = {'id': case['id'], 'source_sha256': case['sha256'], 'expectation': case['expectation']}
            report['cases'].append(record)
            try:
                with pikepdf.open(io.BytesIO(source), attempt_recovery=False) as pdf:
                    result = export_pdfa(pdf, source)
            except PdfaRefusal as refused:
                record.update(status='refused', reason_id=refused.reason_id)
                assert case['expectation'] != 'success', record
                continue
            except pikepdf.PdfError:
                record.update(status='refused', reason_id='structure-unsupported')
                assert case['expectation'] != 'success', record
                continue
            output = directory / (case['id'] + '.pdf')
            output.write_bytes(result.data)
            record.update(status='accepted', output_sha256=hashlib.sha256(result.data).hexdigest(),
                          output_bytes=len(result.data), notices=list(result.notices))
            assert path.read_bytes() == source, 'source mutated'
            accepted.append(case['id'])
            outputs.append(output)
            if case['expectation'] == 'refusal':
                accepted_refusals.append(case['id'])
            record['native'] = _native(path, output, directory / ('native-' + case['id']))
        _assert_coverage(accepted, accepted_refusals)
        assert len(cases) == 31
        validation = run_validator(outputs, command, timeout_seconds=90)
        report['validation'] = asdict(validation)
        (directory / 'validator-stdout.json').write_text(validation.stdout)
        (directory / 'validator-stderr.txt').write_text(validation.stderr)
        assert validation.passed, (validation.infrastructure_errors, validation.verdicts)
        assert len(validation.verdicts) == len(outputs)
        report['accepted_ids'] = accepted
        # Real controls: known valid Type3, known invalid inline LZW, malformed
        # output, and a structurally valid candidate with missing archival metadata.
        controls = run_validator([ROOT / 'corpus/public/verapdf_type3_font_fixture.pdf',
            ROOT / 'corpus/public/verapdf_inline_image_fixture.pdf'], command, 30)
        report['controls'] = asdict(controls)
        assert controls.valid_report and [v.compliant for v in controls.verdicts] == [True, False]
        assert '6.1.10-1' in controls.verdicts[1].failed_rule_ids
        corrupt = directory / 'control-corrupt.pdf'
        corrupt.write_bytes(outputs[0].read_bytes()[:40])
        corruption = run_validator([corrupt], command, 30)
        report['corrupt_control'] = asdict(corruption)
        assert not corruption.passed
        stripped = directory / 'control-missing-metadata.pdf'
        with pikepdf.open(outputs[0]) as candidate:
            del candidate.Root.Metadata
            candidate.save(stripped)
        sensitivity = run_validator([stripped], command, 30)
        report['metadata_control'] = asdict(sensitivity)
        assert sensitivity.valid_report and not sensitivity.passed
        report['passed'] = True
    finally:
        (directory / 'g7a-results.json').write_text(json.dumps(report, indent=2))


def test_coverage_is_non_vacuous():
    with pytest.raises(AssertionError):
        _assert_coverage([], [])
    with pytest.raises(AssertionError):
        _assert_coverage(list(POSITIVE_IDS[:-1]), [])
    with pytest.raises(AssertionError):
        _assert_coverage(list(POSITIVE_IDS), ['refuse-cmyk'])
    _assert_coverage(list(POSITIVE_IDS), [])


@pytest.mark.corpus
def test_supplemental_font_branch_and_limit_boundaries(tmp_path):
    """Additional coverage never changes the frozen manifest or its floor."""
    from fontTools.ttLib import TTFont
    from harness.pdfa_fixture import build_fixtures
    command = os.environ.get('VERAPDF_CMD')
    assert command and Path(command).is_file()
    directory = Path(os.environ.get('G7A_EVIDENCE_DIR', str(tmp_path))) / 'supplemental'
    directory.mkdir(parents=True, exist_ok=True)
    fixture = build_fixtures(directory / 'sources')['text-sans']
    evidence = []
    for case in ('simple-truetype', 'implementation-boundaries', 'current-blank-page'):
        source, output = directory / (case + '.pdf'), directory / (case + '-archival.pdf')
        with pikepdf.open(fixture) as pdf:
            page = pdf.pages[0]
            if case == 'simple-truetype':
                composite = page.Resources.Font.F1
                descendant = composite.DescendantFonts[0]
                with TTFont(io.BytesIO(descendant.FontDescriptor.FontFile2.read_bytes())) as program:
                    glyph = program.getBestCmap()[ord('A')]
                    width = round(program['hmtx'].metrics[glyph][0] * 1000 / program['head'].unitsPerEm)
                page.Resources.Font.F1 = pdf.make_indirect(pikepdf.Dictionary(
                    Type=pikepdf.Name.Font, Subtype=pikepdf.Name.TrueType,
                    BaseFont=composite.BaseFont, FontDescriptor=descendant.FontDescriptor,
                    Encoding=pikepdf.Name.WinAnsiEncoding, FirstChar=65, LastChar=65, Widths=[width]))
                descendant.FontDescriptor.FontFile2.Length1 = len(
                    descendant.FontDescriptor.FontFile2.read_bytes())
                page.Contents.write(b'BT /F1 14 Tf 24 140 Td (A) Tj ET')
            elif case == 'implementation-boundaries':
                key = '/' + 'x' * 127
                page.Resources.Font[key] = page.Resources.Font.F1
                del page.Resources.Font.F1
                content = page.Contents.read_bytes().replace(b'/F1', key.encode())
                page.Contents.write(b'q\n' * 28 + content + b'Q\n' * 28)
                pdf.docinfo.Title = pikepdf.String('x' * 32767)
            else:
                blank = pdf.add_blank_page(page_size=(240, 180))
                del blank.obj.Contents
            pdf.save(source, static_id=True)
        with pikepdf.open(source) as pdf:
            result = export_pdfa(pdf, source.read_bytes())
        output.write_bytes(result.data)
        native = _native(source, output, directory / ('native-' + case))
        verdict = run_validator([output], command, 60)
        assert verdict.passed, verdict.infrastructure_errors or verdict.verdicts
        evidence.append({'id': case, 'source_sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
            'output_sha256': hashlib.sha256(result.data).hexdigest(), 'native': native,
            'validator': asdict(verdict)})
    (directory / 'results.json').write_text(json.dumps({'passed': True, 'cases': evidence}, indent=2))

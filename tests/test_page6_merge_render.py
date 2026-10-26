"""G5 independent readback and native render proof of production page writers.

No browser/native image decode claim follows from this file. Native compositor
observations are recorded separately in 06-G5-RESULTS.md.
"""
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pikepdf
import pytest

from harness.page6_fixture import build_fixtures, assert_graph, assert_pixels, font_provenance, FONTS
from harness.render_diff import render_all

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'harness'))
from run_corpus_harness import _cross_engine_pair_ok  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope='module')
def gate(tmp_path_factory):
    directory = tmp_path_factory.mktemp('page6-g5')
    manifest = build_fixtures(directory)
    subprocess.run(['node', str(ROOT / 'tools/materialize_page6.mjs'), str(manifest)],
                   cwd=ROOT, check=True, timeout=90, capture_output=True)
    data = json.loads((directory / 'outputs.json').read_text())
    return directory, data


def test_negative_control_bad_font_sharing(gate):
    directory, data = gate
    good = directory / 'font-controlled.pdf'
    bad = directory / 'bad-sharing.pdf'
    with pikepdf.open(good) as pdf:
        pdf.pages[0].Resources.Font['/TT2'] = pdf.pages[1].Resources.Font['/TT0']
        pdf.save(bad)
    for page in range(2):
        before = render_all(good, page, directory / f'negative-font-before-{page}')
        after = render_all(bad, page, directory / f'negative-font-after-{page}')
        for a, b in zip(before, after, strict=True):
            if page == 0:
                with pytest.raises(AssertionError, match='outside'):
                    assert_pixels(a, b)
            else:
                assert_pixels(a, b)


def test_negative_control_detached_widget_and_destination(gate):
    directory, _ = gate
    with pikepdf.open(directory / 'graph.pdf') as pdf:
        assert_graph(pdf)
        widget = pdf.pages[1].Annots[0]
        widget.P = pdf.make_indirect(pikepdf.Dictionary(Type=pikepdf.Name.Page))
        with pytest.raises(AssertionError, match='widget'):
            assert_graph(pdf)
    with pikepdf.open(directory / 'graph.pdf') as pdf:
        pdf.Root.Names.Dests.Names[1][0] = pdf.make_indirect(pikepdf.Dictionary(Type=pikepdf.Name.Page))
        with pytest.raises(AssertionError, match='destination'):
            assert_graph(pdf)


def test_negative_control_shared_sibling_and_vacuous_image(gate):
    directory, _ = gate
    good = directory / 'placed-1-90.pdf'
    bad = directory / 'bad-sibling.pdf'
    with pikepdf.open(good) as pdf:
        pdf.pages[1].Resources.Font.F1.BaseFont = pikepdf.Name.Courier
        pdf.save(bad)
    before = render_all(good, 1, directory / 'sibling-before')
    after = render_all(bad, 1, directory / 'sibling-after')
    for a, b in zip(before, after, strict=True):
        with pytest.raises(AssertionError, match='outside'):
            assert_pixels(a, b)
    regions = render_all(directory / 'image-region-1-90.pdf', 0, directory / 'vacuous-region')
    original = render_all(directory / 'resources-1-90.pdf', 0, directory / 'vacuous-original')
    for a, region in zip(original, regions, strict=True):
        with pytest.raises(AssertionError, match='nonvacuous'):
            assert_pixels(a, a, region=region, changed=True)


def test_font_programs_names_and_rename_itself_are_unchanged(gate):
    directory, data = gate
    for variant in ('real', 'controlled'):
        with pikepdf.open(directory / f'font-{variant}.pdf') as pdf:
            objects = []
            for index, (_, _, key, base, digest) in enumerate(FONTS):
                measured = font_provenance(pdf.pages[index], key)
                assert measured['programSha256'] == digest
                expected = '/ABCDEF+Arial' if variant == 'controlled' else '/'+base
                assert measured['baseFont'] == measured['fontName'] == expected
                objects.append(pdf.pages[index].Resources.Font[key].objgen)
            assert objects[0] != objects[1], 'same names must retain independent font dictionaries'
    # Six direct original-to-controlled-single-page comparisons establish renaming
    # itself is invisible; merges have twelve additional exact comparisons below.
    for index, original in enumerate(data['fontOriginals']):
        before = render_all(original['file'], original['page'], directory / f'rename-before-{index}')
        after = render_all(directory / f'font-literal-{index}.pdf', 0, directory / f'rename-after-{index}')
        for a, b in zip(before, after, strict=True):
            assert_pixels(a, b)


def test_graph_values_appearance_bytes_and_physical_targets(gate):
    directory, _ = gate
    def appearance_hashes(page):
        hashes = []
        for annot in page.obj.get('/Annots', []):
            if annot.get('/Subtype') != pikepdf.Name.Widget:
                continue
            value = annot.AP.N
            streams = [value] if isinstance(value, pikepdf.Stream) else list(value.values())
            hashes.extend(hashlib.sha256(stream.read_bytes()).hexdigest() for stream in streams)
        return sorted(hashes)
    with pikepdf.open(directory / 'graph-source.pdf') as source:
        appearances = appearance_hashes(source.pages[0])
    for filename, widget_pages, calculation_count in [('graph.pdf', [1], 1),
            ('graph-collision.pdf', [0, 1], 2), ('graph-deleted.pdf', [0], 1)]:
        with pikepdf.open(directory / filename) as pdf:
            assert_graph(pdf)
            assert len(pdf.Root.AcroForm.CO) == calculation_count
            for index in widget_pages:
                page = pdf.pages[index]
                assert appearance_hashes(page) == appearances
                fields = [annot.Parent for annot in page.Annots if '/Parent' in annot]
                assert {str(field.FT) for field in fields} == {'/Tx', '/Btn', '/Ch', '/Sig'}
                assert next(field for field in fields if str(field.FT) == '/Tx').V == 'value'
                assert next(field for field in fields if str(field.FT) == '/Ch').V == 'two'
                assert str(next(field for field in fields if str(field.FT) == '/Btn').V) == '/Yes'
            # Every explicit nested child destination must target a page actually
            # containing its imported widgets, rather than an orphan copied page.
            titles, direct_targets = [], []
            def visit(node):
                while node is not None:
                    titles.append(str(node.Title))
                    if '/A' in node and node.A.S == pikepdf.Name.GoTo:
                        direct_targets.append(node.A.D[0].objgen)
                    if '/Dest' in node and isinstance(node.Dest, pikepdf.Array):
                        direct_targets.append(node.Dest[0].objgen)
                    if '/First' in node:
                        visit(node.First)
                    node = node.get('/Next')
            visit(pdf.Root.Outlines.First)
            assert 'parent' in titles and 'child' in titles, 'nested outline hierarchy survives'
            assert direct_targets and set(direct_targets) <= {pdf.pages[i].obj.objgen for i in widget_pages}


def test_source_resources_and_flattened_native_pixels(gate):
    directory, _ = gate
    from PIL import Image
    with Image.open(directory / 'white-flattened.png') as image:
        assert image.getpixel((11, 3)) == (255, 255, 255)
        assert image.getpixel((0, 3)) == (247, 142, 132)
    for inherited in (0, 1):
        for rotation in (0, 90, 180, 270):
            with pikepdf.open(directory / f'resources-{inherited}-{rotation}.pdf', inherit_page_attributes=False) as source:
                if inherited:
                    assert '/Resources' not in source.pages[0].obj
                else:
                    assert source.pages[0].Resources.objgen == source.pages[1].Resources.objgen
            with pikepdf.open(directory / f'placed-{inherited}-{rotation}.pdf') as output:
                assert len(output.pages[0].Resources.XObject) == 1
                assert '/XObject' not in output.pages[1].Resources


def test_all_outputs_structure_provenance_and_pixels(gate):
    directory, data = gate
    cache = {}
    def renders(path, page):
        key = str(path), page
        if key not in cache:
            cache[key] = render_all(path, page, directory / f'render-{len(cache)}')
        return cache[key]
    for source in data['sources']:
        assert hashlib.sha256(Path(source['path']).read_bytes()).hexdigest() == source['sha256']
    comparison_count = 0
    cross_engine = []
    for output in data['outputs']:
        path = directory / output['file']
        assert hashlib.sha256(path.read_bytes()).hexdigest() == output['sha256']
        subprocess.run(['qpdf', '--check', '--warning-exit-0', str(path)],
                       check=True, timeout=30, capture_output=True)
        subprocess.run(['pdfcpu', 'validate', '-m', 'relaxed', str(path)],
                       check=True, timeout=30, capture_output=True)
        with pikepdf.open(path) as pdf:
            assert len(pdf.pages) == len(output['mapping'])
            assert_graph(pdf)
            metadata = output['localMetadata']
            assert metadata['pageCount'] == len(pdf.pages)
            for page, geometry in zip(pdf.pages, metadata['pages'], strict=True):
                box = geometry['mediaBox']
                assert list(page.MediaBox) == [box['x'], box['y'], box['x']+box['width'], box['y']+box['height']]
                assert int(page.obj.get('/Rotate', 0)) % 360 == geometry['rotation']
                assert float(page.obj.get('/UserUnit', 1)) == geometry['userUnit']
        for index, expected in enumerate(output['mapping']):
            after = renders(path, index)
            before = renders(directory / expected['file'], expected['page'])
            regions = renders(directory / expected['region'], 0) if 'region' in expected else [None]*3
            for a, b, region in zip(before, after, regions, strict=True):
                assert_pixels(a, b, expected.get('rect'), changed=expected.get('changed', False), region=region)
                comparison_count += 1
            if 'reference' in expected:
                reference = renders(directory / expected['reference'], 0)
                for a, b in zip(reference, after, strict=True):
                    assert_pixels(a, b)
            # Retain the pre-existing cross-engine comparator and its thresholds.
            # A native UserUnit size disagreement must already exist in the
            # corresponding independent source/oracle, never be introduced here.
            oracle = renders(directory / expected.get('reference', expected['file']),
                             0 if 'reference' in expected else expected['page'])
            for left, right in ((0, 1), (0, 2), (1, 2)):
                source_ok, source_detail = _cross_engine_pair_ok('source', oracle[left], oracle[right])
                output_ok, detail = _cross_engine_pair_ok('output', after[left], after[right])
                assert output_ok or (not source_ok and source_detail.removeprefix('source:') == detail.removeprefix('output:')), detail
                cross_engine.append({'file': output['file'], 'page': index,
                    'engines': [left, right], 'passed': output_ok, 'detail': detail,
                    'sourcePassed': source_ok, 'sourceDetail': source_detail})
    assert data['refusals']
    for source in data['sources']:
        assert hashlib.sha256(Path(source['path']).read_bytes()).hexdigest() == source['sha256']
    (directory / 'gate-evidence.json').write_text(json.dumps({'mappedSameEngineComparisons': comparison_count,
        'outputs': len(data['outputs']), 'pages': comparison_count//3, 'crossEngine': cross_engine}, indent=2))

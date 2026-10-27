"""G6: independently read/rasterize actual production export outputs.

MuPDF is used exclusively through the existing dev harness. No runtime imports.
Artifacts contain only generated fixtures and a public corpus compression sample.
"""
from __future__ import annotations

import base64
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import zipfile

import pikepdf
from PIL import Image
import pytest

from harness.export_fixture import (
    assert_archive, assert_exact_pixels, assert_graph, assert_page_mapping,
    assert_region_pixels, build_fixtures, image_samples, resource_fingerprint,
)
from harness.render_diff import render_all

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'harness'))
from run_corpus_harness import _cross_engine_pair_ok  # noqa: E402


def test_negative_region_union_and_missing_appearance():
    expected = Image.new('RGB', (20, 20), 'white')
    for x in range(2, 6):
        for y in range(2, 6):
            expected.putpixel((x, y), (255, 0, 0))
    expected.putpixel((15, 15), (0, 0, 255))
    regions = [(2, 2, 6, 6), (14, 14, 18, 18)]
    assert_region_pixels(expected, expected, regions)
    changed = expected.copy()
    changed.putpixel((10, 10), (0, 0, 0))
    with pytest.raises(AssertionError, match='outside'):
        assert_region_pixels(expected, changed, regions)
    dropped = expected.copy()
    dropped.paste('white', (2, 2, 6, 6))
    with pytest.raises(AssertionError, match='appearance'):
        assert_region_pixels(expected, dropped, regions)


def test_negative_archive_crc_and_directory():
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, 'w', compression=zipfile.ZIP_STORED) as archive:
        archive.writestr('part-001.pdf', b'production-output')
    good = stream.getvalue()
    assert_archive(good, {'part-001.pdf': b'production-output'})
    bad = bytearray(good)
    offset = 30 + struct.unpack_from('<H', good, 26)[0]
    bad[offset] ^= 1
    with pytest.raises(AssertionError, match='CRC'):
        assert_archive(bytes(bad), {'part-001.pdf': b'production-output'})
    with pytest.raises(AssertionError, match='archive'):
        assert_archive(good[:-22], {'part-001.pdf': b'production-output'})
    with pytest.raises(AssertionError, match='entries'):
        assert_archive(good, {})


@pytest.fixture(scope='module')
def gate(tmp_path_factory):
    directory = Path(os.environ.get('PDF_TOOL_G6_ARTIFACTS',
                     str(tmp_path_factory.mktemp('exports-g6'))))
    directory.mkdir(parents=True, exist_ok=True)
    for tool in ('node', 'qpdf', 'pdfcpu', 'pdftoppm', 'mutool'):
        assert shutil.which(tool), f'G6 requires native tool: {tool}'
    manifest = build_fixtures(directory)
    subprocess.run(['node', str(ROOT / 'tools/materialize_exports.mjs'), str(manifest)],
                   cwd=ROOT, check=True, capture_output=True, timeout=90)
    data = json.loads((directory / 'exports.json').read_text())
    # Exercise the real disposable worker rather than a second export writer.
    from server.isolation import run_worker
    outputs = data['outputs']
    for source, operation, downsample in [
        ('annotations.pdf', 'flatten', False),
        ('annotations.pdf', 'compress', False),
        ('image.pdf', 'compress', False),
        ('image.pdf', 'compress', True),
        ('corpus.pdf', 'compress', False),
    ]:
        before = (directory / source).read_bytes()
        result = run_worker('export', before, export_operation=operation,
                            downsample=downsample, acknowledge_signature=True)
        output = base64.b64decode(result['data'], validate=True)
        name = f'{Path(source).stem}-{operation}{"-downsample" if downsample else ""}.pdf'
        (directory / name).write_bytes(output)
        with pikepdf.open(io.BytesIO(before)) as pdf:
            mapping = list(range(len(pdf.pages)))
        outputs.append({'file': name, 'source': source, 'mapping': mapping,
                        'kind': 'downsample' if downsample else operation,
                        'sha256': hashlib.sha256(output).hexdigest(),
                        'notices': result['notices'],
                        'changed_images': result['changed_images'],
                        'before_bytes': result['before_bytes'], 'after_bytes': result['after_bytes']})
    (directory / 'exports.json').write_text(json.dumps(data, indent=2))
    return directory, data


def test_fixtures_production_archive_and_structure(gate):
    directory, data = gate
    entries = {output['filename']: (directory / output['file']).read_bytes()
               for output in data['outputs'] if output['kind'] == 'split'}
    assert_archive((directory / 'split.zip').read_bytes(), entries)
    for source in data['sources']:
        assert hashlib.sha256((directory / source['file']).read_bytes()).hexdigest() == source['sha256']
    for output in data['outputs']:
        path = directory / output['file']
        assert hashlib.sha256(path.read_bytes()).hexdigest() == output['sha256']
        subprocess.run(['qpdf', '--check', str(path)], check=True, timeout=30, capture_output=True)
        subprocess.run(['pdfcpu', 'validate', '-m', 'relaxed', str(path)],
                       check=True, timeout=30, capture_output=True)
        with pikepdf.open(path) as actual, pikepdf.open(directory / output['source']) as source:
            assert_page_mapping(source, actual, output['mapping'])
            assert_graph(actual)
            if output['kind'] == 'flatten':
                assert '/AcroForm' not in actual.Root
                assert all(not page.obj.get('/Annots') for page in actual.pages)
                assert resource_fingerprint(actual.pages[2]) == resource_fingerprint(source.pages[2])
            elif output['kind'] == 'compress':
                assert image_samples(actual) == image_samples(source)
                assert len(path.read_bytes()) <= len((directory / output['source']).read_bytes())
            elif output['kind'] == 'downsample':
                assert output['changed_images'] == 1
                assert output['after_bytes'] < output['before_bytes']
                image = actual.pages[0].Resources.XObject.Im
                assert (int(image.Width), int(image.Height)) == (1600, 800)


def test_negative_mapping_graph_resources_and_refusals(gate):
    directory, data = gate
    split = next(item for item in data['outputs'] if item['kind'] == 'split' and len(item['mapping']) == 2)
    with pikepdf.open(directory / split['source']) as source, pikepdf.open(directory / split['file']) as actual:
        with pytest.raises(AssertionError, match='mapping'):
            assert_page_mapping(source, actual, list(reversed(split['mapping'])))
        del actual.pages[-1]
        with pytest.raises(AssertionError, match='page count'):
            assert_page_mapping(source, actual, split['mapping'])
    with pikepdf.open(directory / 'annotations.pdf') as pdf:
        assert_graph(pdf)
        pdf.pages[0].Annots[1].P = pdf.make_indirect(pikepdf.Dictionary(Type=pikepdf.Name.Page))
        with pytest.raises(AssertionError, match='widget'):
            assert_graph(pdf)
    with pikepdf.open(directory / 'annotations.pdf') as pdf:
        pdf.Root.Names.Dests.Names[1][0] = pdf.make_indirect(pikepdf.Dictionary(Type=pikepdf.Name.Page))
        with pytest.raises(AssertionError, match='destination'):
            assert_graph(pdf)
    with pikepdf.open(directory / 'annotations.pdf') as pdf:
        before = resource_fingerprint(pdf.pages[2])
        pdf.pages[2].Resources.Font.F1.BaseFont = pikepdf.Name.Courier
        assert resource_fingerprint(pdf.pages[2]) != before
    from server.isolation import run_worker
    for file, code in [('missing-appearance.pdf', 'FLATTEN_APPEARANCE_REQUIRED'),
                       ('unsafe-appearance.pdf', 'EXPORT_UNSUPPORTED')]:
        from server.errors import ApiError
        with pytest.raises(ApiError) as error:
            run_worker('export', (directory / file).read_bytes(),
                       export_operation='flatten', acknowledge_signature=True)
        assert error.value.code == code


def test_native_three_engine_export_fidelity(gate):
    directory, data = gate
    renders = {}
    def rendered(file, page):
        key = file, page
        if key not in renders:
            renders[key] = render_all(directory / file, page, directory / f'render-{len(renders):03}')
        return renders[key]
    same_engine = inside = confined = 0
    cross = []
    for output in data['outputs']:
        for page, source_page in enumerate(output['mapping']):
            before = rendered(output['source'], source_page)
            after = rendered(output['file'], page)
            reference_file = 'painted-reference.pdf' if output['kind'] == 'flatten' else output['source']
            reference = rendered(reference_file, source_page)
            for engine, (a, b, expected) in enumerate(zip(before, after, reference, strict=True)):
                if output['kind'] in ('flatten', 'downsample'):
                    with Image.open(b) as raster:
                        geometry = data['geometry'][str(source_page)] if output['kind'] == 'flatten' else data['image_geometry']
                        from harness.export_fixture import physical_regions
                        regions = physical_regions(geometry, raster.size)
                    assert_region_pixels(expected if output['kind'] == 'flatten' else a, b, regions,
                                         check_inside=output['kind'] == 'flatten')
                    confined += 1
                    if output['kind'] == 'flatten':
                        # Full independent painted reference catches dropped APs
                        # even if the source engine did not display annotations.
                        assert_exact_pixels(expected, b)
                        inside += len(regions)
                else:
                    assert_exact_pixels(a, b)
                same_engine += 1
            for left, right in ((0, 1), (0, 2), (1, 2)):
                baseline_ok, baseline_detail = _cross_engine_pair_ok('source', reference[left], reference[right])
                ok, detail = _cross_engine_pair_ok('output', after[left], after[right])
                if output['kind'] != 'downsample':
                    assert ok or (not baseline_ok and baseline_detail.removeprefix('source:') == detail.removeprefix('output:')), detail
                cross.append({'file': output['file'], 'page': page, 'engines': [left, right],
                              'passed': ok, 'baselinePassed': baseline_ok,
                              'detail': detail, 'baselineDetail': baseline_detail})
    # Every source remains byte-identical after native and client output paths.
    for source in data['sources']:
        assert hashlib.sha256((directory / source['file']).read_bytes()).hexdigest() == source['sha256']
    evidence = {'outputs': len(data['outputs']), 'pages': same_engine // 3,
                'sameEngineComparisons': same_engine, 'confinedComparisons': confined,
                'appearanceRegionComparisons': inside, 'renderedPages': len(renders),
                'crossEngine': cross,
                'tools': {name: shutil.which(name) for name in ('node', 'qpdf', 'pdfcpu', 'pdftoppm', 'mutool')}}
    (directory / 'gate-evidence.json').write_text(json.dumps(evidence, indent=2))

"""G5 independent readback and native render proof of production page writers.

No browser/native image decode claim follows from this file. Native compositor
observations are recorded separately in 06-G5-RESULTS.md.
"""
import hashlib
import json
import subprocess
from pathlib import Path

import pikepdf
import pytest

from harness.page6_fixture import build_fixtures, assert_graph, assert_pixels
from harness.render_diff import render_all

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
        pdf.Root.OpenAction[0] = pdf.make_indirect(pikepdf.Dictionary(Type=pikepdf.Name.Page))
        with pytest.raises(AssertionError, match='destination'):
            assert_graph(pdf)


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
    for output in data['outputs']:
        path = directory / output['file']
        subprocess.run(['qpdf', '--check', '--warning-exit-0', str(path)],
                       check=True, timeout=30, capture_output=True)
        subprocess.run(['pdfcpu', 'validate', '-m', 'relaxed', str(path)],
                       check=True, timeout=30, capture_output=True)
        with pikepdf.open(path) as pdf:
            assert len(pdf.pages) == len(output['mapping'])
            assert_graph(pdf)
        for index, expected in enumerate(output['mapping']):
            after = renders(path, index)
            before = renders(directory / expected['file'], expected['page'])
            for a, b in zip(before, after, strict=True):
                assert_pixels(a, b, expected.get('rect'), changed=expected.get('changed', False))
    assert data['refusals']

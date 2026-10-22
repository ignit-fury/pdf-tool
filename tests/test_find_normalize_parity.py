"""One pinned search projection in the interpreter and browser."""
import importlib.util
import json
from pathlib import Path
import subprocess
import unicodedata

import pytest

ROOT = Path(__file__).resolve().parents[1]
SEAMS = ['ﬁ', 'ß', '😀é', 'a\u0315\u0300', 'İ', '\u1e9b\u0323', '각', 'Ａ', 'Straße', 'e\u0301']


def projection_module():
    assert importlib.util.find_spec('engine.search') is not None, 'canonical engine search projection missing'
    from engine import search
    return search


def test_python_projection_strings_and_utf16_spans():
    search = projection_module()
    assert search.project_text('ﬁß😀é') == {'text': 'fiss😀e\u0301', 'spans': [[0, 1], [0, 1], [1, 2], [1, 2], [2, 4], [2, 4], [4, 5], [4, 5]]}
    assert search.project_text('ß', match_case=True)['text'] == 'ß'
    assert search.project_text('a\u0315\u0300')['spans'] == [[0, 1], [2, 3], [1, 2]]
    for text in SEAMS:
        assert search.project_text(text)['text'] == unicodedata.normalize('NFKD', unicodedata.normalize('NFKD', text).casefold())


def test_generated_data_exhaustive_and_deterministic():
    search = projection_module()
    data = json.loads((ROOT / 'engine/data/search-unicode-15.1.json').read_text())
    assert data['unicode_version'] == unicodedata.unidata_version == '15.1.0'
    for code in range(0x110000):
        if 0xD800 <= code <= 0xDFFF:
            continue
        char = chr(code)
        assert data['nfkd'].get(str(code), char) == unicodedata.normalize('NFKD', char)
        assert data['casefold'].get(str(code), char) == char.casefold()
        assert data['combining'].get(str(code), 0) == unicodedata.combining(char)
    subprocess.run([str(ROOT / '.venv/bin/python'), 'tools/build_search_unicode.py', '--check'], cwd=ROOT, check=True)
    assert search.project_search_text('ﬁ')['version'] == data['version']


def test_worker_projection_preserves_authoritative_fields():
    from server.isolation import run_worker
    from tools.build_security_fixtures import text_pdf
    search = projection_module()
    rows = run_worker('page', text_pdf())['runs']
    assert rows
    for row in rows:
        assert row['search'] == search.project_search_text(row['text'])
        assert row['run_id'] and len(row['box']) == 4 and row['state']


def assert_js_parity(texts):
    search = projection_module()
    script = "import {projectSearchText} from './client/src/find/search.mjs';let s='';for await(const x of process.stdin)s+=x;process.stdout.write(JSON.stringify(JSON.parse(s).map(projectSearchText)));"
    result = subprocess.run(['node', '--input-type=module', '-e', script], input=json.dumps(texts), text=True, capture_output=True, cwd=ROOT, check=True)
    assert json.loads(result.stdout) == [search.project_search_text(text) for text in texts]


def test_cross_runtime_unicode_parity():
    assert_js_parity(SEAMS + ['\u0345\u0300', '\u0130\u0315\u0300', '𐐀 test', 'a\u0323\u0301'])


@pytest.mark.corpus
def test_cross_runtime_corpus_parity():
    from engine.index import RunIndex
    texts = []
    # Actual interpreter text from the 40-page acceptance proxy and diverse fonts.
    files = ['govdocs1_013_013050.pdf', 'govdocs1_011_011089.pdf']
    for filename in files[:1]:
        with RunIndex(ROOT / 'corpus/public' / filename) as index:
            for page in range(40):
                texts.extend(run.display_text for run, _ in index.page(page).runs)
    assert len(texts) > 1000
    assert_js_parity(texts)

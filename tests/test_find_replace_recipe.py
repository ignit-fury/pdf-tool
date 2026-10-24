"""Actual ordinary edit transport plus the browser's real match/recipe helpers.

These tests never mock a successful rewrite. A failed report's passing rows are
not applications, and removal of a proposed override must preserve older edits.
"""
from __future__ import annotations

import base64
import hashlib
import io
import json
from pathlib import Path
import subprocess

from fastapi.testclient import TestClient
from fontTools.ttLib import TTFont
import pikepdf
import pypdfium2 as pdfium
import pytest

from server.app import create_app
from server.isolation import run_worker
from tools.build_security_fixtures import text_pdf

ROOT = Path(__file__).resolve().parents[1]


def node_candidate(pages, *, query='cat', replacement='a', recipe=None,
                   excluded_ids=(), refused_ids=(), font_family=''):
    """Exercise the shipped pure client code, not a Python reimplementation."""
    script = """
import {readFileSync} from 'node:fs';
import {findMatches} from './client/src/find/search.mjs';
import {buildReplacementRecipe} from './client/src/find/buildRecipe.mjs';
const value=JSON.parse(readFileSync(0,'utf8'));
const matches=findMatches(value.pages,value.query,{recipe:value.recipe});
const candidate=buildReplacementRecipe({pages:value.pages,recipe:value.recipe,matches,
  replacement:value.replacement,fontFamily:value.fontFamily,
  excludedIds:new Set(value.excludedIds),refusedRunIds:new Set(value.refusedIds)});
process.stdout.write(JSON.stringify({matches,candidate}));
"""
    result = subprocess.run(['node', '--input-type=module', '-e', script], cwd=ROOT,
        input=json.dumps({'pages': pages, 'query': query, 'replacement': replacement,
                          'recipe': recipe or [], 'excludedIds': list(excluded_ids),
                          'refusedIds': list(refused_ids), 'fontFamily': font_family}),
        text=True, capture_output=True, check=True, timeout=30)
    return json.loads(result.stdout)


def _text(source, page=0):
    with pdfium.PdfDocument(source) as document:
        page_object = document[page]
        text = page_object.get_textpage()
        try:
            return text.get_text_range().strip()
        finally:
            text.close()
            page_object.close()


def _three_page_source():
    with pikepdf.Pdf.new() as document:
        for number, text in enumerate((b'cat cat CAT', b'Prior marker', b'cat')):
            with pikepdf.open(io.BytesIO(text_pdf(text))) as source:
                if number == 2:
                    source.pages[0].Resources.Font.F1.BaseFont = pikepdf.Name('/UnrecognizedBatchFace')
                document.pages.append(source.pages[0])
        output = io.BytesIO()
        document.save(output)
        return output.getvalue()


def _post(client, token, recipe, *, dry_run=True):
    response = client.post(f'/jobs/{token}/edit?dry_run={str(dry_run).lower()}', json=recipe)
    assert response.status_code == 200, response.status_code
    return response.json()


def test_node_builder_changes_one_of_two_occurrences_and_preserves_prior_style():
    pages = {1: {'runs': [{'run_id': 'source-run', 'text': 'cat cat',
                          'state': 'editable_original', 'reason': None,
                          'suggested_font_family': 'Sans'}]}}
    prior = [{'run_id': 'unrelated-run', 'new_text': 'Kept', 'style': {'bold': True}}]
    first = node_candidate(pages, recipe=prior)
    result = node_candidate(pages, recipe=prior, excluded_ids=[first['matches'][0]['id']])
    assert len(result['matches']) == 2
    assert result['candidate']['selectedCount'] == 1
    assert result['candidate']['recipe'] == [*prior, {'run_id': 'source-run', 'new_text': 'cat a'}]
    assert result['candidate']['changes'][0]['matchIds'] == [first['matches'][1]['id']]


def test_http_batch_filters_only_proposed_refusals_and_preserves_older_text_style():
    source = _three_page_source()
    digest = hashlib.sha256(source).digest()
    with TestClient(create_app()) as client:
        uploaded = client.post('/upload', content=source, headers={'content-type': 'application/pdf'})
        assert uploaded.status_code == 200
        token = uploaded.json()['job_id']
        pages = {number + 1: client.get(f'/jobs/{token}/pages/{number}/runs').json()
                 for number in range(3)}
        prior_run = pages[2]['runs'][0]
        prior = [{'run_id': prior_run['run_id'], 'new_text': 'Kept marker',
                  'style': {'font_family': 'Sans', 'bold': True, 'color': [0.7, 0.1, 0.1]}}]
        assert _post(client, token, prior)['ok'] is True
        initial = node_candidate(pages, recipe=prior)
        assert len(initial['matches']) == 4
        first_match = initial['matches'][0]['id']
        proposed = node_candidate(pages, recipe=prior, excluded_ids=[first_match])
        assert proposed['candidate']['selectedCount'] == 3
        assert len(proposed['candidate']['recipe']) == 3
        failed = _post(client, token, proposed['candidate']['recipe'])
        assert failed['ok'] is False and failed['pdf'] is None
        assert any(row['ok'] for row in failed['resolved'])
        refused = [row for row in failed['resolved'] if not row['ok']]
        assert len(refused) == 1
        assert refused[0]['reason'].startswith('no mapping table entry for BaseFont')

        filtered = node_candidate(pages, recipe=prior, excluded_ids=[first_match],
                                  refused_ids=[refused[0]['run_id']])
        candidate = filtered['candidate']
        assert len(filtered['matches']) == 4  # A refusal is still a visible match.
        assert candidate['selectedCount'] == 2
        assert candidate['recipe'][0] == prior[0]
        assert len(candidate['recipe']) == 2
        assert len({op['run_id'] for op in candidate['recipe']}) == 2
        preview = _post(client, token, candidate['recipe'])
        assert preview['ok'] is True and preview['pdf'] is None
        applied = _post(client, token, candidate['recipe'], dry_run=False)
        assert applied['ok'] is True and applied['resolved'] == preview['resolved']
        output = base64.b64decode(applied['pdf'])
        assert [_text(output, page) for page in range(3)] == ['cat a a', 'Kept marker', 'cat']
        with pikepdf.open(io.BytesIO(output)) as document:
            # The PDF subset alias intentionally names the family, not weight.
            # Read the actual embedded program instead of assuming alias text.
            weights = []
            for font in document.pages[1].Resources.Font.values():
                if str(font.get('/Subtype')) == '/Type0':
                    data = font.DescendantFonts[0].FontDescriptor.FontFile2.read_bytes()
                    with TTFont(io.BytesIO(data)) as program:
                        weights.append(program['OS/2'].usWeightClass)
            assert any(weight >= 700 for weight in weights)
            colors = [tuple(float(x) for x in item.operands)
                      for item in pikepdf.parse_content_stream(document.pages[1])
                      if str(item.operator) == 'rg']
            assert (0.7, 0.1, 0.1) in colors

        # Search the committed overlay, keeping the original immutable addresses.
        second = node_candidate(pages, query='marker', replacement='tag', recipe=candidate['recipe'])
        assert second['matches'][0]['text'] == 'marker'
        assert second['candidate']['recipe'][0] == {**prior[0], 'new_text': 'Kept tag'}
        assert second['candidate']['recipe'][1] == candidate['recipe'][1]
        final_preview = _post(client, token, second['candidate']['recipe'])
        final = _post(client, token, second['candidate']['recipe'], dry_run=False)
        assert final_preview['ok'] is True and final['ok'] is True
        assert final['resolved'] == final_preview['resolved']
        final_bytes = base64.b64decode(final['pdf'])
        assert [_text(final_bytes, page) for page in range(3)] == ['cat a a', 'Kept tag', 'cat']
    assert hashlib.sha256(source).digest() == digest


def test_actual_batch_source_and_fit_refusals_have_no_partial_output():
    source = text_pdf(b'cat cat')
    page = run_worker('page', source)
    run = page['runs'][0]
    too_wide = [{'run_id': run['run_id'], 'new_text': 'Extremely long replacement text ' * 20}]
    foreign = [{'run_id': 'f' * 64 + run['run_id'][64:], 'new_text': 'a'}]
    for recipe, expected in ((too_wide, 'delta '), (foreign, 'source_hash_mismatch')):
        preview = run_worker('edit', source, recipe=json.dumps(recipe).encode(), dry_run=True)
        applied = run_worker('edit', source, recipe=json.dumps(recipe).encode())
        assert preview['ok'] is False and applied['ok'] is False
        assert preview['resolved'] == applied['resolved']
        assert preview['pdf'] is None and applied['pdf'] is None
        assert preview['resolved'][0]['reason'].startswith(expected)


def test_explicit_batch_font_recovers_unmapped_substitution_without_hiding_matches():
    source = _three_page_source()
    page = run_worker('page', source, page=2)
    run = page['runs'][0]
    assert run['state'] == 'editable_substitution' and run['suggested_font_family'] is None
    built = node_candidate({3: page}, font_family='Serif')
    assert len(built['matches']) == 1
    recipe = built['candidate']['recipe']
    assert recipe == [{'run_id': run['run_id'], 'new_text': 'a', 'style': {'font_family': 'Serif'}}]
    preview = run_worker('edit', source, recipe=json.dumps(recipe).encode(), dry_run=True)
    applied = run_worker('edit', source, recipe=json.dumps(recipe).encode())
    assert preview['ok'] is True and applied['ok'] is True
    assert preview['resolved'] == applied['resolved'] and preview['pdf'] is None
    assert _text(base64.b64decode(applied['pdf']), 2) == 'a'


@pytest.mark.corpus
def test_explicit_batch_font_recovers_unmapped_original_cff():
    from test_corpus_font_shaping import _target
    source_path = ROOT / 'corpus/public/govdocs1_000_000013.pdf'
    source = source_path.read_bytes()
    target = _target(source_path)
    page = run_worker('page', source)
    run = next(row for row in page['runs'] if row['run_id'] == target.run_id)
    assert run['state'] == 'editable_original' and run['suggested_font_family'] is None
    pages = {1: {'runs': [run]}}
    automatic = node_candidate(pages, query=run['text'], replacement='Hi')
    failed = run_worker('edit', source, recipe=json.dumps(automatic['candidate']['recipe']).encode(), dry_run=True)
    assert failed['ok'] is False and failed['pdf'] is None
    assert failed['resolved'][0]['reason'].startswith('no mapping table entry for BaseFont')
    chosen = node_candidate(pages, query=run['text'], replacement='Hi', font_family='Serif')
    assert len(chosen['matches']) == 1
    assert chosen['candidate']['recipe'][0]['style']['font_family'] == 'Serif'
    preview = run_worker('edit', source, recipe=json.dumps(chosen['candidate']['recipe']).encode(), dry_run=True)
    applied = run_worker('edit', source, recipe=json.dumps(chosen['candidate']['recipe']).encode())
    assert preview['ok'] is True and applied['ok'] is True
    assert preview['resolved'] == applied['resolved'] and preview['pdf'] is None
    assert base64.b64decode(applied['pdf']).startswith(b'%PDF-')
    assert source_path.read_bytes() == source

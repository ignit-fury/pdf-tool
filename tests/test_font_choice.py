"""Unknown source font names can use an explicitly chosen replacement face."""
import base64
import io
import json
from pathlib import Path

import pikepdf
import pytest
from fastapi.testclient import TestClient

from engine.classify_run import classify_document
from engine.fonts import lookup_bundled_font
from engine.recipe import RecipeOp, apply_recipe, parse_recipe, plan_recipe
from server.app import create_app
from tools.build_security_fixtures import text_pdf


def named_font_pdf(name: str) -> bytes:
    with pikepdf.open(io.BytesIO(text_pdf(b'Hello world'))) as pdf:
        pdf.pages[0].Resources.Font.F1.BaseFont = pikepdf.Name('/' + name)
        output = io.BytesIO()
        pdf.save(output)
        return output.getvalue()


@pytest.mark.parametrize('name,family', [('Times New Roman', 'Serif'), ('Times New Roman,Bold', 'Serif'), ('Courier New', 'Mono')])
def test_spaced_names_are_recognized(name, family) -> None:
    assert lookup_bundled_font(name).family == family


def test_times_new_roman_is_editable_automatically(tmp_path: Path) -> None:
    source, output = tmp_path / 'times.pdf', tmp_path / 'out.pdf'
    source.write_bytes(named_font_pdf('Times New Roman'))
    run, _ = classify_document(source).runs[0]
    report = apply_recipe(source, (RecipeOp(run.run_id, run.display_text),), output)
    assert report.ok, report
    assert report.resolved[0].substitution_key == ('Serif', 'Regular')


@pytest.mark.parametrize('family,text', [('Sans', 'Hallo world'), ('Serif', 'Hello world'), ('Mono', 'Hey world')])
def test_unknown_source_uses_explicit_family(tmp_path: Path, family, text) -> None:
    source, output = tmp_path / 'in.pdf', tmp_path / 'out.pdf'
    source.write_bytes(named_font_pdf('UnrecognizedCustomFace'))
    run, _ = classify_document(source).runs[0]
    assert not plan_recipe(source, (RecipeOp(run.run_id, text),)).ok
    recipe = parse_recipe(json.dumps([{'run_id': run.run_id, 'new_text': text, 'style': {'font_family': family}}]).encode())
    report = apply_recipe(source, recipe, output)
    assert report.ok, report
    assert report.resolved[0].substitution_key == (family, 'Regular')
    assert ''.join(r.display_text for r, _ in classify_document(output).runs) == text


@pytest.mark.parametrize('family', ['Unknown', '../fonts/font.ttf', 'https://example.com/font.ttf', None, True, []])
def test_family_is_a_strict_enum(family) -> None:
    with pytest.raises(ValueError):
        parse_recipe(json.dumps([{'run_id': 'x', 'new_text': 'text', 'style': {'font_family': family}}]).encode())


def test_explicit_family_replaces_embedded_original_and_keeps_requested_style(tmp_path: Path) -> None:
    from test_recipe import _build_apply_fixture
    source, output = tmp_path / 'embedded.pdf', tmp_path / 'changed.pdf'
    _build_apply_fixture(source)
    run, verdict = classify_document(source).runs[0]
    assert verdict.state == 'editable_original'
    recipe = (RecipeOp(run.run_id, run.display_text, style={'font_family': 'Serif', 'italic': True}),)
    report = apply_recipe(source, recipe, output)
    assert report.ok, report
    assert report.resolved[0].substitution_key == ('Serif', 'Italic')
    with pikepdf.open(output) as pdf:
        assert any('LiberationSerif' in str(font.get('/BaseFont', '')) for font in pdf.pages[0].Resources.Font.values())


def test_explicit_choice_preserves_glyph_safety(tmp_path: Path) -> None:
    source, output = tmp_path / 'in.pdf', tmp_path / 'out.pdf'
    source.write_bytes(named_font_pdf('UnrecognizedCustomFace'))
    run, _ = classify_document(source).runs[0]
    report = apply_recipe(source, (RecipeOp(run.run_id, '你好', style={'font_family': 'Serif'}),), output)
    assert not report.ok
    assert report.resolved[0].reason == 'character_has_no_glyph_in_bundled_font'
    assert not output.exists()


def test_unknown_font_http_preview_apply_and_detection() -> None:
    with TestClient(create_app()) as client:
        uploaded = client.post('/upload', content=named_font_pdf('UnrecognizedCustomFace'), headers={'content-type': 'application/pdf'})
        token = uploaded.json()['job_id']
        run = client.get(f'/jobs/{token}/pages/0/runs').json()['runs'][0]
        assert run['source_font'] == 'UnrecognizedCustomFace'
        assert run['suggested_font_family'] is None
        recipe = [{'run_id': run['run_id'], 'new_text': 'Hello world', 'style': {'font_family': 'Serif'}}]
        assert client.post(f'/jobs/{token}/edit?dry_run=true', json=recipe).json()['ok']
        result = client.post(f'/jobs/{token}/edit', json=recipe).json()
        assert result['ok'], result
        with pikepdf.open(io.BytesIO(base64.b64decode(result['pdf']))) as pdf:
            assert any('LiberationSerif' in str(font.get('/BaseFont', '')) for font in pdf.pages[0].Resources.Font.values())


def test_known_font_http_reports_source_and_suggestion() -> None:
    with TestClient(create_app()) as client:
        uploaded = client.post('/upload', content=named_font_pdf('Times New Roman'), headers={'content-type': 'application/pdf'})
        token = uploaded.json()['job_id']
        run = client.get(f'/jobs/{token}/pages/0/runs').json()['runs'][0]
        assert run['source_font'] == 'Times New Roman'
        assert run['suggested_font_family'] == 'Serif'

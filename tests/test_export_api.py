"""Current-byte export transport through real disposable PDF workers."""
from __future__ import annotations

import base64
import io

from fastapi.testclient import TestClient
import pikepdf
import pytest

from server.app import create_app
from tools.build_security_fixtures import password_pdf, signed_pdf, text_pdf

HEADERS = {'content-type': 'application/pdf'}


def test_pdfa_real_worker_returns_current_archival_copy_without_cache(tmp_path):
    from harness.pdfa_fixture import build_fixtures
    source = build_fixtures(tmp_path)['text-sans'].read_bytes()
    app = create_app()
    with TestClient(app) as client:
        response = client.post('/exports?operation=pdfa', content=source, headers=HEADERS)
        assert response.status_code == 200, response.json()
        result = response.json()
        output = base64.b64decode(result['data'], validate=True)
        assert result['filename'] == 'archival.pdf'
        assert result['media_type'] == 'application/pdf' and result['changed_images'] == 0
        assert result['location'] == 'server' and result['before_bytes'] == len(source)
        assert result['after_bytes'] == len(output) and app.state.sources.total_bytes == 0
        assert response.headers['cache-control'] == 'no-store, private'
        with pikepdf.open(io.BytesIO(output)) as pdf:
            with pdf.open_metadata(set_pikepdf_as_editor=False) as metadata:
                assert str(metadata['pdfaid:part']) == '2'
                assert metadata['pdfaid:conformance'] == 'B'


def test_pdfa_real_child_preserves_safe_font_refusal():
    with TestClient(create_app()) as client:
        response = client.post('/exports?operation=pdfa', content=text_pdf(), headers=HEADERS)
        assert response.status_code == 422
        assert response.json() == {'detail': {'code': 'PDFA_UNSUPPORTED', 'reason_id': 'font-missing'}}


@pytest.mark.parametrize('suffix,reason', [
    ('FONT_MISSING', 'font-missing'), ('FONT_UNSUPPORTED', 'font-unsupported'),
    ('FONT_INVALID', 'font-invalid'), ('COLOR_UNSUPPORTED', 'color-unsupported'),
    ('CONTENT_UNSUPPORTED', 'content-unsupported'), ('STRUCTURE_UNSUPPORTED', 'structure-unsupported'),
    ('METADATA_UNSUPPORTED', 'metadata-unsupported'), ('VERSION_UNSUPPORTED', 'pdf-version'),
    ('LIMIT', 'limit'),
])
def test_pdfa_fixed_refusal_transport_drops_untrusted_worker_fields(monkeypatch, suffix, reason):
    from server import isolation
    monkeypatch.setattr(isolation, 'run_worker', lambda *a, **kw: {
        'error': 'PDFA_' + suffix, 'reason_id': '<source text>', 'exception': 'private data'})
    with TestClient(create_app()) as client:
        response = client.post('/exports?operation=pdfa', content=text_pdf(), headers=HEADERS)
        assert response.status_code == 422
        assert response.json() == {'detail': {'code': 'PDFA_UNSUPPORTED', 'reason_id': reason}}


def test_pdfa_signature_ack_and_invalid_downsample():
    with TestClient(create_app()) as client:
        response = client.post('/exports?operation=pdfa', content=signed_pdf(), headers=HEADERS)
        assert response.status_code == 409
        assert response.json()['detail']['code'] == 'SIGNATURE_ACKNOWLEDGEMENT_REQUIRED'
        invalid = client.post('/exports?operation=pdfa&downsample=true', content=text_pdf(), headers=HEADERS)
        assert invalid.status_code == 400


def test_pdfa_uses_existing_unicode_password_transport_before_safe_refusal():
    source = password_pdf('密碼')
    with TestClient(create_app()) as client:
        for password, expected in [(None, 'PASSWORD_REQUIRED'), ('wrong', 'PASSWORD_INCORRECT'),
                                   ('密碼', 'PDFA_UNSUPPORTED')]:
            headers = dict(HEADERS)
            if password is not None:
                headers['X-PDF-Password-B64'] = base64.b64encode(password.encode()).decode()
            response = client.post('/exports?operation=pdfa', content=source, headers=headers)
            assert response.status_code == 422
            assert response.json()['detail']['code'] == expected
            assert '密碼' not in response.text and 'wrong' not in response.text


@pytest.mark.parametrize('operation,filename,mime', [
    ('compress', 'compressed.pdf', 'application/pdf'),
    ('flatten', 'flattened.pdf', 'application/pdf'),
    ('text', 'document.txt', 'text/plain'),
    ('markdown', 'document.md', 'text/markdown'),
    ('html', 'document.html', 'text/html'),
])
def test_current_byte_exports_real_worker_without_cache(operation, filename, mime):
    source = text_pdf(b'Current materialized text')
    app = create_app()
    with TestClient(app) as client:
        response = client.post('/exports', params={'operation': operation}, content=source, headers=HEADERS)
        assert response.status_code == 200, response.json()
        result = response.json()
        output = base64.b64decode(result['data'], validate=True)
        assert result['before_bytes'] == len(source)
        assert result['after_bytes'] == len(output)
        assert result['filename'] == filename and result['media_type'] == mime
        assert result['location'] == 'server'
        assert app.state.sources.total_bytes == 0
        assert response.headers['cache-control'] == 'no-store, private'
        assert response.headers['x-content-type-options'] == 'nosniff'
        if mime == 'application/pdf':
            with pikepdf.open(io.BytesIO(output)) as pdf:
                assert len(pdf.pages) == 1
        else:
            assert 'Current materialized text' in output.decode('utf-8')


def test_encrypted_export_unicode_password_and_unlocked_copy():
    password = '密碼'
    headers = {**HEADERS, 'X-PDF-Password-B64': base64.b64encode(password.encode()).decode()}
    with TestClient(create_app()) as client:
        source = password_pdf(password)
        missing = client.post('/exports?operation=flatten', content=source, headers=HEADERS)
        assert missing.status_code == 422
        assert missing.json()['detail']['code'] == 'PASSWORD_REQUIRED'
        response = client.post('/exports?operation=flatten', content=source, headers=headers)
        assert response.status_code == 200, response.json()
        result = response.json()
        with pikepdf.open(io.BytesIO(base64.b64decode(result['data']))) as pdf:
            assert not pdf.is_encrypted
        assert 'UNLOCKED_COPY' in result['notices']


def test_signature_acknowledgement_only_for_pdf_rewrites():
    source = signed_pdf()
    with TestClient(create_app()) as client:
        refused = client.post('/exports?operation=compress', content=source, headers=HEADERS)
        assert refused.status_code == 409
        assert refused.json()['detail']['code'] == 'SIGNATURE_ACKNOWLEDGEMENT_REQUIRED'
        accepted = client.post('/exports?operation=compress&acknowledge_signature=true', content=source, headers=HEADERS)
        assert accepted.status_code == 200, accepted.json()
        text = client.post('/exports?operation=text', content=source, headers=HEADERS)
        assert text.status_code == 200, text.json()


@pytest.mark.parametrize('query', [
    '', 'operation=unknown', 'operation=flatten&downsample=true',
    'operation=compress&downsample=maybe', 'operation=compress&acknowledge_signature=1',
    'operation=text&operation=html', 'operation=text&unexpected=secret',
])
def test_invalid_options_are_fixed_errors_before_worker(monkeypatch, query):
    from server import isolation
    def no_worker(*args, **kwargs):
        raise AssertionError('invalid option reached PDF worker')
    monkeypatch.setattr(isolation, 'run_worker', no_worker)
    with TestClient(create_app()) as client:
        response = client.post('/exports?' + query, content=text_pdf(), headers=HEADERS)
        assert response.status_code == 400, response.json()
        assert response.json() == {'detail': {'code': 'EXPORT_OPTIONS_INVALID'}}


def test_export_ingest_is_bounded_and_import_is_parser_free():
    with TestClient(create_app(max_upload_bytes=12)) as client:
        assert client.post('/exports?operation=text', content=b'%PDF-' + b'x' * 20, headers=HEADERS).status_code == 413
        response = client.post('/exports?operation=text', content=b'not pdf', headers=HEADERS)
        assert response.status_code == 400 and response.json()['detail']['code'] == 'INVALID_PDF_MAGIC'
        assert client.post('/exports?operation=text', content=b'%PDF-', headers={'content-type':'text/plain'}).status_code == 415
    import subprocess
    import sys
    code = 'import server.app,sys; assert not any(n.startswith("engine.") or n=="pikepdf" or n=="PIL" for n in sys.modules)'
    assert subprocess.run([sys.executable, '-c', code], capture_output=True).returncode == 0


def test_export_parent_validates_options_without_spawning():
    from server.isolation import run_worker
    for options in [{'export_operation':'invalid'}, {'export_operation':'text','downsample':True}]:
        assert run_worker('export', text_pdf(), **options) == {'error':'EXPORT_OPTIONS_INVALID'}


def test_export_preflight_and_missing_appearance_fail_closed():
    from tools.build_security_fixtures import decompression_bomb
    with TestClient(create_app()) as client:
        limited = client.post('/exports?operation=text', content=decompression_bomb(), headers=HEADERS)
        assert limited.status_code == 422
        assert limited.json()['detail']['code'] == 'DOCUMENT_LIMIT'
        # The signature-detector fixture has no page widget; attach one so this
        # check actually exercises a visible field with a missing appearance.
        with pikepdf.open(io.BytesIO(signed_pdf())) as pdf:
            field = pdf.Root.AcroForm.Fields[0]
            field.Subtype, field.Rect, field.P = pikepdf.Name.Widget, [20, 20, 80, 50], pdf.pages[0].obj
            pdf.pages[0].obj.Annots = pikepdf.Array([field])
            output = io.BytesIO()
            pdf.save(output)
        unsafe = client.post('/exports?operation=flatten&acknowledge_signature=true',
                             content=output.getvalue(), headers=HEADERS)
        assert unsafe.status_code == 422
        assert unsafe.json()['detail']['code'] == 'FLATTEN_APPEARANCE_REQUIRED'


@pytest.mark.parametrize('operation', ['html', 'markdown'])
def test_empty_multpage_formats_report_no_text_despite_markup(operation):
    with pikepdf.Pdf.new() as pdf:
        pdf.add_blank_page()
        pdf.add_blank_page()
        source = io.BytesIO()
        pdf.save(source)
    with TestClient(create_app()) as client:
        response = client.post('/exports?operation=' + operation, content=source.getvalue(), headers=HEADERS)
        assert response.status_code == 200, response.json()
        assert 'NO_EXTRACTABLE_TEXT' in response.json()['notices']


def test_index_limits_are_reported_as_export_limits(monkeypatch, tmp_path):
    import engine.index
    from server.worker import WorkerRefusal, _execute
    monkeypatch.setenv('PDF_TOOL_WORKER_SCRATCH', str(tmp_path))
    monkeypatch.setattr(engine.index, 'MAX_DOCUMENT_GLYPHS', 0)
    with pytest.raises(WorkerRefusal, match='^EXPORT_LIMIT$'):
        _execute({'action':'export', 'export_operation':'text',
                  'source':base64.b64encode(text_pdf()).decode()})

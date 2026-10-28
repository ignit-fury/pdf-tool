"""Real two-action DOCX transport, CORS and full-projection acknowledgement."""
import base64
import io
import json
import zipfile

from fastapi.testclient import TestClient
import pytest

from server.app import create_app
from tools.build_security_fixtures import text_pdf

HEADERS = {'content-type':'application/pdf', 'origin':'http://localhost:5173'}


def acknowledgement(review):
    return json.dumps({k:review[k] for k in ('source_sha256','snapshot_sha256','policy_version')}, separators=(',', ':'))


def test_real_review_preflight_conversion_and_current_source_binding():
    source = text_pdf(b'Current DOCX body')
    app = create_app()
    with TestClient(app) as client:
        assert client.get('/exports/capabilities').json() == {'docx':True}
        preflight = client.options('/exports', headers={'Origin':HEADERS['origin'],
            'Access-Control-Request-Method':'POST',
            'Access-Control-Request-Headers':'content-type,x-pdf-password-b64,x-docx-review'})
        assert preflight.status_code == 200
        assert 'x-docx-review' in preflight.headers['access-control-allow-headers'].lower()
        denied = client.options('/exports', headers={'Origin':'https://unapproved.invalid',
            'Access-Control-Request-Method':'POST','Access-Control-Request-Headers':'x-docx-review'})
        assert denied.status_code == 400
        reviewed = client.post('/exports?operation=docx-review', content=source, headers=HEADERS)
        assert reviewed.status_code == 200, reviewed.json()
        data = reviewed.json()
        assert set(data) == {'source_sha256','snapshot_sha256','policy_version','review','location'}
        assert data['review']['has_text'] is True and data['review']['facts'] == []
        assert 'Current DOCX body' not in reviewed.text and 'data' not in data
        headers = {**HEADERS,'X-DOCX-Review':acknowledgement(data)}
        converted = client.post('/exports?operation=docx', content=source, headers=headers)
        assert converted.status_code == 200, converted.json()
        artifact = converted.json()
        assert artifact['filename'] == 'document.docx' and artifact['changed_images'] == 0
        with zipfile.ZipFile(io.BytesIO(base64.b64decode(artifact['data']))) as package:
            assert package.testzip() is None
            assert b'Current DOCX body' in package.read('word/document.xml')
        assert converted.headers['access-control-allow-origin'] == HEADERS['origin']
        changed = client.post('/exports?operation=docx', content=text_pdf(b'Changed'), headers=headers)
        assert changed.status_code == 409 and changed.json()['detail']['code'] == 'DOCX_REVIEW_MISMATCH'
        data['snapshot_sha256'] = '0' * 64
        mismatch = client.post('/exports?operation=docx', content=source,
            headers={**HEADERS,'X-DOCX-Review':acknowledgement(data)})
        assert mismatch.status_code == 409 and mismatch.json()['detail']['code'] == 'DOCX_REVIEW_MISMATCH'
        assert app.state.sources.total_bytes == 0


@pytest.mark.parametrize('value', [None, '', '{}', '[]', 'bad', 'x'*257,
    '{"source_sha256":"'+'a'*64+'","source_sha256":"'+'b'*64+'"}',
    json.dumps({'source_sha256':'a'*64,'snapshot_sha256':'b'*64,'policy_version':True}),
    json.dumps({'source_sha256':'A'*64,'snapshot_sha256':'b'*64,'policy_version':1}),
])
def test_malformed_or_missing_acknowledgement_never_dispatches(monkeypatch, value):
    import server.isolation as module
    def never(*args, **kwargs):
        raise AssertionError('invalid review reached worker')
    monkeypatch.setattr(module, 'run_worker', never)
    with TestClient(create_app()) as client:
        headers = dict(HEADERS)
        if value is not None:
            headers['X-DOCX-Review'] = value
        response = client.post('/exports?operation=docx', content=text_pdf(), headers=headers)
        assert response.status_code == 409
        assert response.json() == {'detail':{'code':'DOCX_REVIEW_REQUIRED'}}


def test_review_does_not_serialize_but_conversion_does(tmp_path, monkeypatch):
    import engine.export.docx as module
    from server.worker import _execute
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv('PDF_TOOL_WORKER_SCRATCH', str(tmp_path))
    def forbidden(snapshot):
        raise AssertionError('conversion reached serializer')
    monkeypatch.setattr(module, 'serialize_docx', forbidden)
    request = {'action':'export','source':base64.b64encode(text_pdf()).decode(),
               'password':'','export_operation':'docx-review'}
    review = _execute(request)
    assert set(review) == {'source_sha256','snapshot_sha256','policy_version','review'}
    request.update(export_operation='docx', reviewed_source_sha256=review['source_sha256'],
        reviewed_snapshot_sha256=review['snapshot_sha256'], reviewed_policy_version=1)
    with pytest.raises(AssertionError, match='conversion reached serializer'):
        _execute(request)


def test_unavailable_docx_leaves_other_exports_available(monkeypatch):
    import server.app as module
    monkeypatch.setattr(module, '_docx_available', lambda:False)
    with TestClient(create_app()) as client:
        assert client.get('/exports/capabilities').json() == {'docx':False}
        response = client.post('/exports?operation=docx-review', content=text_pdf(), headers=HEADERS)
        assert response.status_code == 503 and response.json()['detail']['code'] == 'DOCX_UNAVAILABLE'
        assert client.post('/exports?operation=text', content=text_pdf(), headers=HEADERS).status_code == 200

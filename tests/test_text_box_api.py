"""Current-source native text containers through the bounded disposable worker."""
from __future__ import annotations

import base64
import hashlib
import io
import json
import subprocess
import sys

from fastapi.testclient import TestClient
import pikepdf
import pytest

from server.app import MAX_RECIPE_BYTES, create_app
from server.cache import SourceCache
from server.isolation import run_worker
from server.errors import set_error_reporter
from tools.build_security_fixtures import decompression_bomb, password_pdf, signed_pdf, text_pdf

PDF_HEADERS = {'content-type': 'application/pdf'}
JSON_HEADERS = {'content-type': 'application/json'}

def test_replace_source_grows_atomically_and_uses_original_source_ids(tmp_path):
    from tests.test_source_text_box import source_pdf, request
    source,ids=source_pdf(tmp_path/'original.pdf')
    cache=SourceCache();job=cache.put(source)
    with TestClient(create_app(cache=cache)) as client:
        response=client.post(f'/jobs/{job}/text-box',json=request(ids))
    assert response.status_code==200,response.json()
    result=response.json();assert result['ok'] is True and result['boxes'][0]['rect']['height']>12
    import hashlib
    assert result['source_hash']==hashlib.sha256(source).hexdigest()


@pytest.mark.parametrize('protected',['signed','encrypted'])
def test_source_expansion_preserves_protection_acknowledgement_and_unicode_password(tmp_path,protected):
    from tests.test_source_text_box import source_pdf, request
    from engine.classify_run import classify_document
    original=tmp_path/'original.pdf';source_pdf(original)
    target=tmp_path/'protected.pdf'
    with pikepdf.open(original) as pdf:
        if protected=='signed':pdf.Root.AcroForm=pikepdf.Dictionary(SigFlags=1,Fields=[])
        pdf.save(target,**({'encryption':pikepdf.Encryption(user='密碼',owner='owner',R=6)} if protected=='encrypted' else {}))
    password='密碼' if protected=='encrypted' else ''
    ids={r.display_text:r.run_id for r,_ in classify_document(target,password=password).runs}
    cache=SourceCache();job=cache.put(target.read_bytes());path=f'/jobs/{job}/text-box'
    headers={'X-PDF-Password-B64':base64.b64encode(password.encode()).decode()} if password else {}
    with TestClient(create_app(cache=cache)) as client:
        refused=client.post(path,json=request(ids))
        assert refused.status_code==(422 if password else 409)
        response=client.post(path+'?acknowledge_signature=true',json=request(ids),headers=headers)
    assert response.status_code==200,response.json()
    assert response.json()['notices']==(['UNLOCKED_COPY'] if password else ['SIGNATURES_INVALIDATED'])



def upsert(**changes):
    return {'operation': 'upsert', 'page_index': 0, 'text': 'Native box',
            'rect': {'left': 20, 'top': 20, 'width': 220, 'height': 50}, **changes}


def test_real_candidate_and_reopened_list_bind_current_bytes_without_mutating_source():
    source = text_pdf(b'Current edited body')
    cache = SourceCache()
    app = create_app(cache=cache)
    with TestClient(app) as client:
        uploaded = client.post('/upload', content=source, headers=PDF_HEADERS).json()
        path = '/jobs/' + uploaded['job_id'] + '/text-box'
        listed = client.post(path, json={'operation': 'list'})
        assert listed.status_code == 200, listed.json()
        assert listed.json() == {'ok': True, 'source_hash': hashlib.sha256(source).hexdigest(),
                                 'boxes': [], 'location': 'server'}
        preview = client.post(path, json=upsert())
        assert preview.status_code == 200, preview.json()
        result = preview.json()
        assert set(result) == {'ok', 'source_hash', 'pdf', 'page_index', 'boxes', 'layout', 'notices', 'location'}
        assert result['ok'] is True and result['location'] == 'server'
        assert result['source_hash'] == uploaded['source_hash']
        candidate = base64.b64decode(result['pdf'], validate=True)
        assert candidate != source
        assert cache.get(uploaded['job_id']) == source and cache.total_bytes == len(source)
        assert client.get('/jobs/' + uploaded['job_id'] + '/download').content == source
        reopened = client.post('/upload', content=candidate, headers=PDF_HEADERS).json()
        next_path = '/jobs/' + reopened['job_id'] + '/text-box'
        relisted = client.post(next_path, json={'operation': 'list'})
        assert relisted.status_code == 200, relisted.json()
        boxes = relisted.json()
        assert boxes['source_hash'] == hashlib.sha256(candidate).hexdigest()
        assert len(boxes['boxes']) == 1 and boxes['boxes'][0]['text'] == 'Native box'
        removed = client.post(next_path, json={'operation': 'remove', 'id': boxes['boxes'][0]['id']})
        assert removed.status_code == 200, removed.json()
        assert removed.json()['ok'] is True and removed.json()['boxes'] == []
        assert cache.get(reopened['job_id']) == candidate
        assert preview.headers['cache-control'] == 'no-store, private'
        assert preview.headers['x-content-type-options'] == 'nosniff'


@pytest.mark.parametrize('payload', [b'', b'[]', b'null', b'{', b'\xff',
    b'{"operation":"list","operation":"upsert"}',
    b'{"operation":"list","extra":{"x":1,"x":2}}',
    b'{"operation":"upsert","text":NaN}', b'{"operation":"upsert","text":Infinity}',
    b'{"operation":"upsert","rect":{"width":1e999}}',
    b'{"operation":"list","value":' + b'[' * 2000 + b']' * 2000 + b'}'])
def test_malformed_json_is_a_fixed_error(payload):
    with TestClient(create_app()) as client:
        job = client.post('/upload', content=text_pdf(), headers=PDF_HEADERS).json()['job_id']
        response = client.post('/jobs/' + job + '/text-box', content=payload, headers=JSON_HEADERS)
        assert response.status_code == 400, response.json()
        assert response.json() == {'detail': {'code': 'INVALID_TEXT_BOX'}}


@pytest.mark.parametrize('query', ['acknowledge_signature=1', 'unexpected=secret',
    'acknowledge_signature=true&acknowledge_signature=false'])
def test_invalid_query_is_rejected_before_pdf_worker(monkeypatch, query):
    from server import isolation
    cache = SourceCache()
    job = cache.put(text_pdf())
    def forbidden(*args, **kwargs):
        raise AssertionError('invalid options reached worker')
    monkeypatch.setattr(isolation, 'run_worker', forbidden)
    with TestClient(create_app(cache=cache)) as client:
        response = client.post('/jobs/' + job + '/text-box?' + query, json={'operation': 'list'})
        assert response.status_code == 400
        assert response.json() == {'detail': {'code': 'INVALID_TEXT_BOX'}}


def test_missing_source_reupload_and_transport_bounds(monkeypatch):
    from server import isolation
    cache = SourceCache()
    source = text_pdf()
    job = cache.put(source)
    with TestClient(create_app(cache=cache)) as client:
        path = '/jobs/' + job + '/text-box'
        cache.clear()
        missing = client.post(path, json={'operation': 'list'})
        assert missing.status_code == 409
        assert missing.json() == {'detail': {'code': 'SOURCE_MISSING', 'missing': [job]}}
        uploaded = client.post('/upload', content=source, headers=PDF_HEADERS).json()
        assert uploaded['job_id'] == job
        listed = client.post(path, json={'operation': 'list'})
        assert listed.status_code == 200
        assert 'notices' not in listed.json()
        def forbidden(*args, **kwargs):
            raise AssertionError('invalid body reached worker')
        monkeypatch.setattr(isolation, 'run_worker', forbidden)
        wrong = client.post(path, content=b'{}', headers={'content-type': 'text/plain'})
        assert wrong.status_code == 415 and wrong.json()['detail']['code'] == 'JSON_CONTENT_TYPE_REQUIRED'
        oversized = client.post(path, content=b' ' * (MAX_RECIPE_BYTES + 1), headers=JSON_HEADERS)
        assert oversized.status_code == 413 and oversized.json()['detail']['code'] == 'BODY_TOO_LARGE'
    assert run_worker('text-box', source, recipe=b' ' * (MAX_RECIPE_BYTES + 1)) == {'error': 'RECIPE_TOO_LARGE'}


def test_signed_list_is_safe_but_all_changes_require_explicit_ack():
    source = signed_pdf()
    cache = SourceCache()
    job = cache.put(source)
    with TestClient(create_app(cache=cache)) as client:
        path = '/jobs/' + job + '/text-box'
        listed = client.post(path, json={'operation': 'list'})
        assert listed.status_code == 200
        assert 'notices' not in listed.json()
        for payload in [upsert(), {'operation': 'remove', 'id': 'missing'}]:
            refused = client.post(path, json=payload)
            assert refused.status_code == 409
            assert refused.json() == {'detail': {'code': 'SIGNATURE_ACKNOWLEDGEMENT_REQUIRED'}}
        accepted = client.post(path + '?acknowledge_signature=true', json=upsert())
        assert accepted.status_code == 200, accepted.json()
        assert accepted.json()['ok'] is True
        assert accepted.json()['notices'] == ['SIGNATURES_INVALIDATED']
        assert cache.get(job) == source


def test_unicode_password_reuses_existing_headers_and_never_leaks():
    cache = SourceCache()
    source = password_pdf('密碼')
    job = cache.put(source)
    with TestClient(create_app(cache=cache)) as client:
        path = '/jobs/' + job + '/text-box'
        for password, code in [(None, 'PASSWORD_REQUIRED'), ('wrong', 'PASSWORD_INCORRECT')]:
            headers = {} if password is None else {'X-PDF-Password-B64': base64.b64encode(password.encode()).decode()}
            response = client.post(path, json={'operation': 'list'}, headers=headers)
            assert response.status_code == 422 and response.json() == {'detail': {'code': code}}
            assert 'wrong' not in response.text and '密碼' not in response.text
        headers = {'X-PDF-Password-B64': base64.b64encode('密碼'.encode()).decode()}
        response = client.post(path, json=upsert(), headers=headers)
        assert response.status_code == 200, response.json()
        assert response.json()['notices'] == ['UNLOCKED_COPY']
        assert cache.get(job) == source
        candidate = base64.b64decode(response.json()['pdf'])
        with pikepdf.open(io.BytesIO(candidate)) as pdf:
            assert not pdf.is_encrypted
        ambiguous = client.post(path, json={'operation': 'list'}, headers={**headers, 'X-PDF-Password': 'wrong'})
        assert ambiguous.status_code == 400 and ambiguous.json()['detail']['code'] == 'AMBIGUOUS_PASSWORD_HEADERS'


@pytest.mark.parametrize('kind', ['ordinary', 'signed', 'encrypted'])
def test_overflow_has_numeric_facts_and_no_candidate(kind):
    cache = SourceCache()
    source = signed_pdf() if kind == 'signed' else password_pdf('密碼') if kind == 'encrypted' else text_pdf()
    job = cache.put(source)
    headers = {'X-PDF-Password-B64': base64.b64encode('密碼'.encode()).decode()} if kind == 'encrypted' else {}
    with TestClient(create_app(cache=cache)) as client:
        response = client.post('/jobs/' + job + '/text-box?acknowledge_signature=true', headers=headers, json=upsert(
            text='Several lines that need space ' * 20,
            rect={'left': 20, 'top': 20, 'width': 60, 'height': 1}))
        assert response.status_code == 200, response.json()
        result = response.json()
        assert set(result) == {'ok', 'source_hash', 'code', 'required_height', 'available_height', 'location'}
        assert result['ok'] is False and result['code'] == 'TEXT_BOX_OVERFLOW'
        assert result['required_height'] > result['available_height'] == 1
        assert cache.get(job) == source


def test_preflight_cannot_be_bypassed_by_text_box_list():
    assert run_worker('text-box', decompression_bomb(), recipe=b'{"operation":"list"}') == {'error': 'DOCUMENT_LIMIT'}


def test_text_box_safe_reporting_contains_only_fixed_codes():
    events = []
    set_error_reporter(events.append)
    try:
        assert run_worker('text-box', text_pdf(), recipe=b'{"operation":"private text password-marker"}') == {'error': 'INVALID_TEXT_BOX'}
    finally:
        set_error_reporter(None)
    assert events == [{'code': 'INVALID_TEXT_BOX', 'action': 'text-box'}]


@pytest.mark.parametrize('code,status', [
    ('INVALID_TEXT_BOX', 400), ('TEXT_BOX_UNSUPPORTED_TEXT', 422), ('TEXT_BOX_UNSAFE', 422),
    ('TEXT_BOX_NOT_FOUND', 422), ('TEXT_BOX_OVERLAP', 422), ('TEXT_BOX_LIMIT', 422),
    ('TEXT_BOX_OUTPUT_LIMIT', 422), ('private text password-marker', 422),
])
def test_native_errors_cross_real_worker_as_fixed_codes_only(monkeypatch, code, status):
    from server import isolation
    runner = (
        'import engine.text_boxes as module\n'
        'def reject(*args):\n'
        ' error=module.TextBoxError("TEXT_BOX_UNSAFE")\n'
        f' error.code={code!r}\n'
        ' raise error\n'
        'module.prepare_text_box=reject\n'
        'from server.worker import main\nmain()\n'
    )
    monkeypatch.setattr(isolation, '_worker_command', lambda: [sys.executable, '-c', runner])
    cache = SourceCache()
    source = text_pdf()
    job = cache.put(source)
    expected = code if code != 'private text password-marker' else 'WORKER_FAILED'
    events = []
    set_error_reporter(events.append)
    try:
        with TestClient(create_app(cache=cache)) as client:
            response = client.post('/jobs/' + job + '/text-box', json=upsert())
            assert response.status_code == status
            assert response.json() == {'detail': {'code': expected}}
            assert cache.get(job) == source
    finally:
        set_error_reporter(None)
    assert events == [{'code': expected, 'action': 'text-box'}]


def test_parent_import_remains_pdf_parser_free():
    code = 'import server.app,sys; assert not any(n.startswith("engine.") or n=="pikepdf" or n=="pypdfium2" for n in sys.modules)'
    assert subprocess.run([sys.executable, '-c', code], capture_output=True).returncode == 0


@pytest.mark.parametrize('valid,metadata', [(True, None), (False, b'private malformed ownership'),
    (False, b'[' * 2000 + b']' * 2000)])
def test_page_runs_lock_owned_content_and_only_verified_boxes_have_ids(valid, metadata):
    source = text_pdf(b'Ordinary source body')
    candidate = run_worker('text-box', source, recipe=json.dumps(upsert()).encode())
    assert candidate['ok'] is True
    identifier = candidate['boxes'][0]['id']
    current = base64.b64decode(candidate['pdf'])
    if not valid:
        with pikepdf.open(io.BytesIO(current)) as pdf:
            for stream in pdf.pages[0].Contents:
                if '/NativeTextBox' in stream:
                    stream.NativeTextBox = pikepdf.String(metadata)
            output = io.BytesIO()
            pdf.save(output)
            current = output.getvalue()
    with TestClient(create_app()) as client:
        uploaded = client.post('/upload', content=current, headers=PDF_HEADERS)
        assert uploaded.status_code == 200, uploaded.json()
        response = client.get('/jobs/' + uploaded.json()['job_id'] + '/pages/0/runs')
        assert response.status_code == 200, response.json()
        runs = response.json()['runs']
        ordinary = [run for run in runs if 'Ordinary source body' in run['text']]
        assert len(ordinary) == 1 and ordinary[0]['state'] != 'not_editable'
        assert 'text_box_id' not in ordinary[0]
        owned = [run for run in runs if run not in ordinary]
        assert owned and ''.join(run['text'] for run in owned) == 'Native box'
        assert all(run['state'] == 'not_editable' for run in owned)
        if valid:
            assert all(run['reason'] == 'managed_text_box' and run['text_box_id'] == identifier for run in owned)
        else:
            assert all(run['reason'] == 'managed_text_box_unverified' and 'text_box_id' not in run for run in owned)


def test_page_runs_include_paragraphs_and_paragraph_commit(tmp_path):
    from tests.test_paragraph_edit import two_line_pdf, payload
    source, paragraph = two_line_pdf(tmp_path / 'p.pdf')
    with TestClient(create_app(cache=SourceCache())) as client:
        job = client.post('/upload', content=source, headers=PDF_HEADERS).json()['job_id']
        page = client.get(f'/jobs/{job}/pages/0/runs').json()
        entry = next(p for p in page['paragraphs'] if p['paragraph_id'] == paragraph.paragraph_id)
        assert entry['lines'] == [[r.run_id for r in line] for line in paragraph.lines]
        assert entry['state'] == 'editable' and entry['single_style'] is True
        body = payload(paragraph, ['First line here', 'Second line hers'])
        result = client.post(f'/jobs/{job}/text-box', json=body).json()
        assert result['plan'] == 'lines' and result['location'] == 'server'
        stale = client.post(f'/jobs/{job}/text-box', json={**body, 'source_run_ids': body['source_run_ids'][:1]})
        assert stale.status_code == 422 and stale.json()['detail']['code'] == 'PARAGRAPH_STALE'

"""Real-worker cache eviction/reupload and immutable recipe transport checks."""
from __future__ import annotations

import base64
import hashlib
import io

import pikepdf
from fastapi.testclient import TestClient

from server.app import create_app
from tools.build_security_fixtures import password_pdf, signed_pdf, text_pdf


def upload(client: TestClient, source: bytes, password: str = ''):
    return client.post('/upload', content=source,
                       headers={'content-type': 'application/pdf', 'x-pdf-password': password})


def test_cache_eviction_reupload_restores_all_document_routes() -> None:
    app = create_app()
    source = text_pdf()
    with TestClient(app) as client:
        uploaded = upload(client, source)
        assert uploaded.status_code == 200, uploaded.text
        job = uploaded.json()['job_id']
        assert uploaded.json()['source_hash'] == hashlib.sha256(source).hexdigest()
        assert client.get(f'/jobs/{job}/pages/0/runs').json()['runs']
        app.state.sources.clear()
        for method, suffix in [('GET', '/status'), ('GET', '/pages/0/runs'), ('GET', '/download'), ('POST', '/edit')]:
            response = client.request(method, f'/jobs/{job}{suffix}')
            assert response.status_code == 409
            assert response.json()['detail']['code'] == 'SOURCE_MISSING'
        restored = upload(client, source).json()
        assert restored['job_id'] == job
        assert client.get(f'/jobs/{job}/pages/0/runs').status_code == 200
        assert client.get(f'/jobs/{job}/download').content == source
    assert app.state.sources.total_bytes == 0


def test_dry_run_and_commit_match_and_cache_keeps_original() -> None:
    source = text_pdf(b'Hello')
    app = create_app()
    with TestClient(app) as client:
        job = upload(client, source).json()['job_id']
        page = client.get(f'/jobs/{job}/pages/0/runs').json()
        recipe = [{'run_id': page['runs'][0]['run_id'], 'new_text': 'Hallo'}]
        plan = client.post(f'/jobs/{job}/edit?dry_run=true', json=recipe)
        commit = client.post(f'/jobs/{job}/edit', json=recipe)
        assert plan.status_code == commit.status_code == 200, commit.text
        assert commit.json()['ok'] is True, commit.json()
        assert plan.json()['resolved'] == commit.json()['resolved']
        assert plan.json()['pdf'] is None
        output = base64.b64decode(commit.json()['pdf'])
        with pikepdf.open(io.BytesIO(output)) as pdf:
            assert len(pdf.pages) == 1
        assert b'%PDF-' == output[:5]
        assert app.state.sources.get(job) == source
        assert client.get(f'/jobs/{job}/pages/0/runs').json()['runs'][0]['text'] == 'Hello'


def test_refused_recipe_never_returns_partial_output() -> None:
    with TestClient(create_app()) as client:
        job = upload(client, text_pdf()).json()['job_id']
        response = client.post(f'/jobs/{job}/edit', json=[{'run_id': 'invalid', 'new_text': 'no'}])
        assert response.status_code == 200
        assert response.json()['ok'] is False
        assert response.json()['pdf'] is None


def test_password_stays_in_browser_not_cache() -> None:
    source = password_pdf('never-store-password')
    app = create_app()
    with TestClient(app) as client:
        assert upload(client, source).json()['detail']['code'] == 'PASSWORD_REQUIRED'
        assert upload(client, source, 'wrong').status_code == 422
        response = upload(client, source, 'never-store-password')
        assert response.status_code == 200, response.text
        job = response.json()['job_id']
        assert client.get(f'/jobs/{job}/pages/0/runs').status_code == 422
        assert client.get(f'/jobs/{job}/pages/0/runs', headers={'x-pdf-password': 'never-store-password'}).status_code == 200
        assert all(isinstance(value[1], bytes) for value in app.state.sources._items.values())


def test_signature_requires_explicit_acknowledgement() -> None:
    with TestClient(create_app()) as client:
        response = upload(client, signed_pdf())
        assert response.json()['signed'] is True
        job = response.json()['job_id']
        assert client.post(f'/jobs/{job}/edit', json=[]).status_code == 409
        assert client.post(f'/jobs/{job}/edit?acknowledge_signature=true', json=[]).status_code == 200

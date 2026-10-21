"""Phase 4 HTTP invariants: bounded ingest, ephemeral source and honest transport."""
from __future__ import annotations

from fastapi.testclient import TestClient

from server.app import create_app


def test_encoded_unicode_password_opens_and_classifies_pdf() -> None:
    import base64
    from tools.build_security_fixtures import password_pdf
    password = '密碼'
    headers = {'X-PDF-Password-B64': base64.b64encode(password.encode()).decode()}
    with TestClient(create_app()) as client:
        response = client.post('/upload', content=password_pdf(password),
                               headers={**headers, 'content-type': 'application/pdf'})
        assert response.status_code == 200, response.json()
        token = response.json()['job_id']
        page = client.get(f'/jobs/{token}/pages/0/runs', headers=headers)
        assert page.status_code == 200, page.json()
        assert page.json()['runs']


def test_encoded_password_is_exact_bounded_and_validated(monkeypatch) -> None:
    import base64
    from server import isolation
    seen = []

    def worker(action, source, **options):
        seen.append(options['password'])
        return {'page_count': 1}

    monkeypatch.setattr(isolation, 'run_worker', worker)
    with TestClient(create_app()) as client:
        password = ' \t密碼\r\n '
        encoded = base64.b64encode(password.encode()).decode()
        valid = client.post('/upload', content=b'%PDF-', headers={
            'content-type': 'application/pdf', 'X-PDF-Password-B64': encoded})
        assert valid.status_code == 200
        assert seen == [password]
        for encoded in ['!!!', '/w==', 'A' * 5465]:
            response = client.post('/upload', content=b'%PDF-', headers={
                'content-type': 'application/pdf', 'X-PDF-Password-B64': encoded})
            assert response.status_code == 400
        assert seen == [password]


def test_magic_bytes_and_size_checked_before_worker() -> None:
    app = create_app(max_upload_bytes=12)
    with TestClient(app) as client:
        bad = client.post('/upload', content=b'not a pdf', headers={'content-type': 'application/pdf'})
        assert bad.status_code == 400
        assert bad.json()['detail']['code'] == 'INVALID_PDF_MAGIC'
        large = client.post('/upload', content=b'%PDF-' + b'X' * 20, headers={'content-type': 'application/pdf'})
        assert large.status_code == 413


def test_all_error_responses_have_privacy_headers() -> None:
    with TestClient(create_app()) as client:
        for method, path in [('GET', '/jobs/missing/pages/0/runs'), ('POST', '/jobs/missing/edit'), ('GET', '/jobs/missing/download')]:
            response = client.request(method, path)
            assert response.status_code == 409
            assert response.json()['detail']['code'] == 'SOURCE_MISSING'
            assert response.headers['cache-control'] == 'no-store, private'
            assert "'unsafe-eval'" not in response.headers['content-security-policy']
            assert response.headers['x-content-type-options'] == 'nosniff'


def test_ocr_signal_has_no_document_payload() -> None:
    with TestClient(create_app()) as client:
        assert client.post('/ocr-notify').json()['count'] == 1
        assert client.post('/ocr-notify').json()['count'] == 2
        assert client.post('/ocr-notify', content=b'secret').status_code == 400


def test_server_import_does_not_load_pdf_engine() -> None:
    import subprocess
    import sys
    check = subprocess.run([sys.executable, '-c', 'import server.app,sys; assert not any(n.startswith("engine.") for n in sys.modules)'], capture_output=True)
    assert check.returncode == 0, check.stderr.decode()


def test_cache_is_bounded_eviction_and_restoration() -> None:
    from server.cache import SourceCache
    cache = SourceCache(max_bytes=10)
    first = cache.put(b'123456')
    second = cache.put(b'abcdef')
    assert cache.get(first) is None
    assert cache.get(second) == b'abcdef'
    assert cache.put(b'123456') == first
    assert cache.get(first) == b'123456'
    cache.clear()
    assert cache.get(first) is None


def test_cache_expiration_removes_bytes() -> None:
    from server.cache import SourceCache
    now = [10.0]
    cache = SourceCache(max_bytes=100, ttl=2, clock=lambda: now[0])
    token = cache.put(b'bytes')
    now[0] = 13
    assert cache.get(token) is None
    assert cache.total_bytes == 0


def test_idle_cache_expires_without_another_document_request() -> None:
    import time
    from server.cache import SourceCache
    cache = SourceCache(max_bytes=100, ttl=0.01)
    with TestClient(create_app(cache=cache, cleanup_interval=0.01)):
        cache.put(b'private-document')
        time.sleep(0.05)
        assert cache.total_bytes == 0


def test_upload_admission_happens_before_reading_more_bodies() -> None:
    import asyncio
    import httpx

    async def scenario() -> None:
        entered, release = asyncio.Event(), asyncio.Event()

        async def slow_body():
            entered.set()
            yield b'%PDF-'
            await release.wait()

        app = create_app(max_inflight=1, admission_timeout=0.01)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as client:
            first = asyncio.create_task(client.post('/upload', content=slow_body(), headers={'content-type': 'application/pdf'}))
            await entered.wait()
            second = await client.post('/upload', content=b'%PDF-more', headers={'content-type': 'application/pdf'})
            assert second.status_code == 429
            release.set()
            await first
    asyncio.run(scenario())


def test_slow_upload_body_has_a_deadline() -> None:
    import asyncio
    import httpx

    async def scenario() -> None:
        async def slow_body():
            yield b'%PDF-'
            await asyncio.sleep(0.2)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=create_app(body_timeout=0.01)), base_url='http://test') as client:
            response = await client.post('/upload', content=slow_body(), headers={'content-type': 'application/pdf'})
            assert response.status_code == 408
            assert response.json()['detail']['code'] == 'BODY_TIMEOUT'
    asyncio.run(scenario())


def test_cancelled_requests_keep_worker_capacity_until_child_finishes(monkeypatch) -> None:
    import asyncio
    import threading
    import time
    import httpx
    from server import isolation
    active = 0
    peak = 0
    lock = threading.Lock()

    def slow_worker(*args, **kwargs):
        nonlocal active, peak
        with lock:
            active += 1
            peak = max(peak, active)
        time.sleep(0.3)
        with lock:
            active -= 1
        return {'page_count': 1, 'signed': False, 'encrypted': False}

    monkeypatch.setattr(isolation, 'run_worker', slow_worker)

    async def scenario() -> None:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=create_app()), base_url='http://test') as client:
            for _ in range(4):
                task = asyncio.create_task(client.post('/upload', content=b'%PDF-fixture', headers={'content-type': 'application/pdf'}))
                await asyncio.sleep(0.03)
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
            await asyncio.sleep(0.4)
        assert peak <= 2
    asyncio.run(scenario())


def test_slow_download_holds_admission_until_response_is_sent() -> None:
    import asyncio
    import httpx

    async def scenario() -> None:
        app = create_app(max_inflight=1, admission_timeout=0.01)
        token = app.state.sources.put(b'%PDF-fixture')
        sending, release, finished = asyncio.Event(), asyncio.Event(), asyncio.Event()
        received = False

        async def receive():
            nonlocal received
            if not received:
                received = True
                return {'type': 'http.request', 'body': b'', 'more_body': False}
            await finished.wait()
            return {'type': 'http.disconnect'}

        async def send(message):
            if message['type'] == 'http.response.body' and message.get('body'):
                sending.set()
                await release.wait()

        scope = {'type': 'http', 'asgi': {'version': '3.0', 'spec_version': '2.4'},
                 'method': 'GET', 'path': f'/jobs/{token}/download', 'raw_path': b'/',
                 'query_string': b'', 'headers': [], 'scheme': 'http',
                 'server': ('test', 80), 'client': ('test', 123)}
        task = asyncio.create_task(app(scope, receive, send))
        await asyncio.wait_for(sending.wait(), 2)
        try:
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as client:
                second = await client.get(f'/jobs/{token}/download')
            assert second.status_code == 429
        finally:
            release.set()
            await task
            finished.set()
    asyncio.run(scenario())

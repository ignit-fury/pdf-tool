"""Image-only transport shares the existing anonymous resource lifecycle."""
from __future__ import annotations

import asyncio
import threading
import time

from fastapi.testclient import TestClient
import httpx

from server.app import create_app
from tests.test_image_conversion import heic, png

HEADERS = {'content-type': 'image/heic', 'origin': 'http://localhost:5173'}


def privacy(response):
    assert response.headers['cache-control'] == 'no-store, private'
    assert response.headers['x-content-type-options'] == 'nosniff'
    assert response.headers['content-security-policy']
    assert response.headers['referrer-policy'] == 'no-referrer'
    assert response.headers['x-frame-options'] == 'DENY'
    assert response.headers['access-control-allow-origin'] == 'http://localhost:5173'


def test_allowed_and_rejected_cors_preflights_keep_universal_headers():
    with TestClient(create_app()) as client:
        for origin, method, expected in [
            ('http://localhost:5173', 'POST', 200),
            ('http://localhost:5173', 'DELETE', 400),
            ('https://rejected.invalid', 'POST', 400),
        ]:
            response = client.options('/images/heic-decode', headers={
                'origin': origin, 'access-control-request-method': method,
                'access-control-request-headers': 'content-type',
            })
            assert response.status_code == expected
            assert response.headers['cache-control'] == 'no-store, private'
            assert response.headers['content-security-policy']
            assert response.headers['x-content-type-options'] == 'nosniff'
            assert response.headers['referrer-policy'] == 'no-referrer'
            assert response.headers['x-frame-options'] == 'DENY'
            if origin == 'http://localhost:5173':
                assert response.headers['access-control-allow-origin'] == origin
            else:
                assert 'access-control-allow-origin' not in response.headers
        privacy(client.get('/missing-route', headers=HEADERS))
        privacy(client.post('/images/heic-decode', content=b'invalid', headers=HEADERS))


def test_route_is_image_only_without_cache_or_job():
    seen = []
    def converter(source):
        seen.append(source)
        return png()
    with TestClient(create_app(heic_converter=converter)) as client:
        response = client.post('/images/heic-decode', content=heic(), headers=HEADERS)
        assert response.status_code == 200
        assert response.content == png()
        assert response.headers['content-type'] == 'image/png'
        assert client.app.state.sources.total_bytes == 0
        assert seen == [heic()]
        privacy(response)
        for headers, path in [({**HEADERS, 'x-pdf-password': 'secret'}, '/images/heic-decode'),
                              (HEADERS, '/images/heic-decode?job_id=secret')]:
            rejected = client.post(path, content=heic(), headers=headers)
            assert rejected.status_code == 400
        assert len(seen) == 1


def test_validation_and_fixed_errors_preserve_privacy():
    from server.image_conversion import ImageConversionError
    def unavailable(source):
        raise ImageConversionError('HEIC_UNAVAILABLE')
    with TestClient(create_app(heic_converter=unavailable)) as client:
        for body, headers, status, code in [
            (heic(), HEADERS, 503, 'HEIC_UNAVAILABLE'),
            (b'private invalid content', HEADERS, 400, 'INVALID_HEIC'),
            (heic(), {**HEADERS, 'content-type': 'application/pdf'}, 415, 'HEIC_CONTENT_TYPE_REQUIRED'),
            (heic(), {**HEADERS, 'content-length': '-2'}, 400, 'INVALID_CONTENT_LENGTH'),
            (heic(), {**HEADERS, 'content-length': str(20 * 1024 * 1024 + 1)}, 413, 'BODY_TOO_LARGE'),
        ]:
            response = client.post('/images/heic-decode', content=body, headers=headers)
            assert response.status_code == status
            assert response.json() == {'detail': {'code': code}}
            privacy(response)


def test_native_exceptions_and_reporting_cannot_leak():
    from server.errors import set_error_reporter
    from server.image_conversion import ImageConversionError
    events = []
    failures = [ImageConversionError('IMAGE_CONVERSION_TIMEOUT'), RuntimeError('secret path /tmp/private')]
    def converter(source):
        if failures:
            raise failures.pop(0)
        return png()
    set_error_reporter(events.append)
    try:
        with TestClient(create_app(heic_converter=converter)) as client:
            for code in ['IMAGE_CONVERSION_TIMEOUT', 'IMAGE_CONVERSION_FAILED']:
                response = client.post('/images/heic-decode', content=heic(), headers=HEADERS)
                assert response.json() == {'detail': {'code': code}}
                privacy(response)
            assert client.post('/images/heic-decode', content=heic(), headers=HEADERS).status_code == 200
        assert events == [{'code': code, 'action': 'heic-decode'} for code in ['IMAGE_CONVERSION_TIMEOUT', 'IMAGE_CONVERSION_FAILED']]
    finally:
        set_error_reporter(None)


def test_image_admission_precedes_read_and_body_deadline():
    async def scenario():
        entered, release = asyncio.Event(), asyncio.Event()
        async def slow():
            entered.set()
            yield heic()
            await release.wait()
        app = create_app(heic_converter=lambda _: png(), max_inflight=1, admission_timeout=0.01, body_timeout=0.1)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as client:
            first = asyncio.create_task(client.post('/images/heic-decode', content=slow(), headers=HEADERS))
            await entered.wait()
            read = False
            async def second_body():
                nonlocal read
                read = True
                yield heic()
            second = await client.post('/images/heic-decode', content=second_body(), headers=HEADERS)
            assert second.status_code == 429 and not read
            privacy(second)
            first_response = await first
            assert first_response.status_code == 408
            privacy(first_response)
    asyncio.run(scenario())


def test_content_length_lie_and_streamed_limit():
    async def scenario():
        seen = []
        async def large():
            yield heic()
            yield b'X' * (20 * 1024 * 1024)
        app = create_app(heic_converter=lambda source: seen.append(source) or png())
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as client:
            response = await client.post('/images/heic-decode', content=large(), headers={**HEADERS, 'content-length': '1'})
            assert response.status_code == 413
            assert not seen
            privacy(response)
    asyncio.run(scenario())


def test_cancelled_image_and_pdf_share_two_slots(monkeypatch):
    from server import isolation
    active = peak = 0
    lock = threading.Lock()
    def work():
        nonlocal active, peak
        with lock:
            active += 1
            peak = max(peak, active)
        time.sleep(0.3)
        with lock:
            active -= 1
    def converter(source):
        work()
        return png()
    def pdf(*args, **kwargs):
        work()
        return {'page_count': 1}
    monkeypatch.setattr(isolation, 'run_worker', pdf)
    async def scenario():
        app = create_app(heic_converter=converter)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as client:
            first = asyncio.create_task(client.post('/images/heic-decode', content=heic(), headers=HEADERS))
            second = asyncio.create_task(client.post('/upload', content=b'%PDF-', headers={'content-type': 'application/pdf'}))
            await asyncio.sleep(0.04)
            first.cancel()
            try:
                await first
            except asyncio.CancelledError:
                pass
            busy = await client.post('/images/heic-decode', content=heic(), headers=HEADERS)
            assert busy.status_code == 429
            privacy(busy)
            await second
            await asyncio.sleep(0.1)
            assert (await client.post('/images/heic-decode', content=heic(), headers=HEADERS)).status_code == 200
        assert peak == 2 and active == 0
    asyncio.run(scenario())


def test_image_response_backpressure_holds_ingress():
    async def scenario():
        app = create_app(heic_converter=lambda _: png(), max_inflight=1, admission_timeout=0.01)
        sending, release, finished = asyncio.Event(), asyncio.Event(), asyncio.Event()
        received = False
        async def receive():
            nonlocal received
            if not received:
                received = True
                return {'type': 'http.request', 'body': heic(), 'more_body': False}
            await finished.wait()
            return {'type': 'http.disconnect'}
        async def send(message):
            if message['type'] == 'http.response.body' and message.get('body'):
                sending.set()
                await release.wait()
        scope = {'type': 'http', 'http_version': '1.1', 'method': 'POST', 'scheme': 'http',
                 'path': '/images/heic-decode', 'raw_path': b'/images/heic-decode', 'query_string': b'',
                 'headers': [(b'content-type', b'image/heic')], 'server': ('test', 80), 'client': ('test', 1)}
        first = asyncio.create_task(app(scope, receive, send))
        await asyncio.wait_for(sending.wait(), 2)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as client:
            busy = await client.post('/images/heic-decode', content=heic(), headers=HEADERS)
            assert busy.status_code == 429
        release.set()
        finished.set()
        await first
    asyncio.run(scenario())

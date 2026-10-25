"""Bounded HTTP transport. All PDF inspection and mutation happens in a worker.

The browser keeps authoritative source bytes and the undo stack. Losing this process or
its evictable memory cache is recoverable by reuploading those original bytes. There is
no queue, object store, database, document logging, or server-side operation history.
"""
from __future__ import annotations

import asyncio
import base64
import binascii
import hashlib
import os
import time
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager, suppress
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from starlette.types import Receive, Scope, Send

from server.cache import SourceCache
from server.disclosure import operation_location

MAX_UPLOAD_BYTES = 50 * 1024 * 1024
MAX_RECIPE_BYTES = 1024 * 1024
CSP = ("default-src 'self'; script-src 'self' 'wasm-unsafe-eval'; worker-src 'self' blob:; "
       "style-src 'self' 'unsafe-inline'; img-src 'self' blob: data:; "
       "font-src 'self' blob:; connect-src 'self'; object-src 'none'; "
       "base-uri 'none'; frame-ancestors 'none'; form-action 'self'")


class _AdmittedResponse(StreamingResponse):
    """Hold admission through backpressure, chunking large JSON/PDF responses."""
    def __init__(self, original: Response, release: Callable[[], None], timeout: float) -> None:
        iterator = getattr(original, 'body_iterator', None)
        body = getattr(original, 'body', b'')

        async def chunks() -> AsyncIterator[bytes]:
            if iterator is None:
                for offset in range(0, len(body), 65536):
                    yield body[offset:offset + 65536]
            else:
                async for chunk in iterator:
                    for offset in range(0, len(chunk), 65536):
                        yield chunk[offset:offset + 65536]

        super().__init__(chunks(), status_code=original.status_code, background=original.background)
        self.raw_headers = list(original.raw_headers)
        self._release = release
        self._deadline = time.monotonic() + timeout

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        try:
            async with asyncio.timeout(max(0.001, self._deadline - time.monotonic())):
                await super().__call__(scope, receive, send)
        finally:
            self._release()


async def _body(request: Request, limit: int, timeout: float = 15) -> bytes:
    length = request.headers.get('content-length')
    if length is not None:
        try:
            count = int(length)
        except ValueError:
            raise HTTPException(400, {'code': 'INVALID_CONTENT_LENGTH'}) from None
        if count < 0:
            raise HTTPException(400, {'code': 'INVALID_CONTENT_LENGTH'})
        if count > limit:
            raise HTTPException(413, {'code': 'BODY_TOO_LARGE'})
    chunks = bytearray()
    try:
        async with asyncio.timeout(timeout):
            async for chunk in request.stream():
                if len(chunks) + len(chunk) > limit:
                    raise HTTPException(413, {'code': 'BODY_TOO_LARGE'})
                chunks.extend(chunk)
    except TimeoutError:
        raise HTTPException(408, {'code': 'BODY_TIMEOUT'}) from None
    return bytes(chunks)


def create_app(*, max_upload_bytes: int = MAX_UPLOAD_BYTES,
               cache: SourceCache | None = None, cleanup_interval: float = 1,
               max_inflight: int = 4, admission_timeout: float = 0.1,
               body_timeout: float = 15, response_timeout: float = 15,
               heic_converter: Callable[[bytes], bytes] | None = None) -> FastAPI:
    sources = cache if cache is not None else SourceCache()
    slots = asyncio.Semaphore(2)
    ingress = asyncio.Semaphore(max_inflight)
    workers: set[asyncio.Task[Any]] = set()

    def worker_finished(task: asyncio.Task[Any]) -> None:
        # Request cancellation does not cancel a running thread or child process.
        # Release capacity only when the real operation terminates.
        slots.release()
        workers.discard(task)
        if not task.cancelled():
            task.exception()  # Consume failure without logging exception text/locals.

    async def expire_sources() -> None:
        while True:
            await asyncio.sleep(cleanup_interval)
            sources.expire()

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        expiry = asyncio.create_task(expire_sources())
        try:
            yield
        finally:
            if workers:
                await asyncio.gather(*workers, return_exceptions=True)
            expiry.cancel()
            with suppress(asyncio.CancelledError):
                await expiry
            sources.clear()

    api = FastAPI(title='PDF Tool', version='0.2.0', lifespan=lifespan,
                  docs_url=None, redoc_url=None)
    api.state.sources = sources
    api.state.ocr_requests = 0
    origins = os.environ.get('PDF_TOOL_ALLOWED_ORIGINS',
                             'http://localhost:5173,http://127.0.0.1:5173').split(',')
    @api.middleware('http')
    async def privacy_headers(request: Request, call_next: Any) -> Response:
        admitted = False
        needs_admission = (request.url.path in ('/upload', '/images/heic-decode') or
                           request.url.path.startswith('/jobs/'))
        try:
            if needs_admission:
                try:
                    await asyncio.wait_for(ingress.acquire(), timeout=admission_timeout)
                    admitted = True
                except TimeoutError:
                    response = JSONResponse({'detail': {'code': 'WORKER_BUSY'}}, status_code=429,
                                            headers={'Retry-After': '1'})
            if admitted or not needs_admission:
                async with asyncio.timeout(body_timeout + 35):
                    response = await call_next(request)
        except Exception:
            # Deliberately omit traceback, locals and exception text from reporting.
            from server.errors import report_error
            report_error('REQUEST_FAILED', 'http')
            response = JSONResponse({'detail': {'code': 'REQUEST_FAILED'}}, status_code=500)
        except BaseException:
            if admitted:
                ingress.release()
            raise
        response.headers['Cache-Control'] = 'no-store, private'
        response.headers['Content-Security-Policy'] = CSP
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Referrer-Policy'] = 'no-referrer'
        response.headers['X-Frame-Options'] = 'DENY'
        if admitted:
            return _AdmittedResponse(response, ingress.release, response_timeout)
        return response

    # CORS wraps synthesized admission/transport errors as well as route replies.
    api.add_middleware(CORSMiddleware, allow_origins=origins,
                       allow_methods=['GET', 'POST'],
                       allow_headers=['Content-Type', 'X-PDF-Password', 'X-PDF-Password-B64'])

    def require_source(job_id: str) -> bytes:
        source = sources.get(job_id)
        if source is None:
            raise HTTPException(409, {'code': 'SOURCE_MISSING', 'missing': [job_id]})
        return source

    async def dispatch(action: str, source: bytes, request: Request,
                       **options: Any) -> dict[str, Any]:
        from server.isolation import run_worker
        password = request.headers.get('x-pdf-password', '')
        encoded_password = request.headers.get('x-pdf-password-b64')
        if encoded_password is not None:
            if 'x-pdf-password' in request.headers:
                raise HTTPException(400, {'code': 'AMBIGUOUS_PASSWORD_HEADERS'})
            if len(encoded_password) > 5464:
                raise HTTPException(400, {'code': 'PASSWORD_TOO_LONG'})
            try:
                password = base64.b64decode(encoded_password, validate=True).decode('utf-8')
            except (binascii.Error, UnicodeError, ValueError):
                raise HTTPException(400, {'code': 'INVALID_PASSWORD_ENCODING'}) from None
        if len(password) > 1024:
            raise HTTPException(400, {'code': 'PASSWORD_TOO_LONG'})
        try:
            await asyncio.wait_for(slots.acquire(), timeout=0.1)
        except TimeoutError:
            raise HTTPException(429, {'code': 'WORKER_BUSY'}) from None
        worker = asyncio.create_task(asyncio.to_thread(run_worker, action, source,
                                                       password=password, **options))
        workers.add(worker)
        worker.add_done_callback(worker_finished)
        result = await asyncio.shield(worker)
        error = result.get('error')
        if error:
            status = {'PASSWORD_REQUIRED': 422, 'PASSWORD_INCORRECT': 422,
                      'SIGNATURE_ACKNOWLEDGEMENT_REQUIRED': 409,
                      'PAGE_OUT_OF_RANGE': 400, 'INVALID_RECIPE': 400,
                      'RECIPE_TOO_LARGE': 413, 'WORKER_TIMEOUT': 422,
                      'WORKER_LIMIT_EXCEEDED': 422}.get(str(error), 422)
            raise HTTPException(status, {'code': error})
        return result

    @api.get('/health')
    async def health() -> dict[str, str]:
        return {'status': 'ok'}

    @api.post('/upload')
    async def upload(request: Request) -> dict[str, Any]:
        if request.headers.get('content-type', '').split(';')[0] != 'application/pdf':
            raise HTTPException(415, {'code': 'PDF_CONTENT_TYPE_REQUIRED'})
        source = await _body(request, max_upload_bytes, body_timeout)
        if source[:5] != b'%PDF-':
            raise HTTPException(400, {'code': 'INVALID_PDF_MAGIC'})
        result = await dispatch('inspect', source, request)
        try:
            token = sources.put(source)
        except ValueError:
            raise HTTPException(413, {'code': 'BODY_TOO_LARGE'}) from None
        return {**result, 'job_id': token, 'source_hash': hashlib.sha256(source).hexdigest()}

    @api.post('/images/heic-decode')
    async def heic_decode(request: Request) -> Response:
        from server.errors import report_error
        from server.image_conversion import (MAX_INPUT_BYTES, ImageConversionError,
                                             convert_heic, validate_heic)
        if request.headers.get('content-type', '').split(';')[0].lower() not in ('image/heic', 'image/heif'):
            raise HTTPException(415, {'code': 'HEIC_CONTENT_TYPE_REQUIRED'})
        if request.query_params or any(name in request.headers for name in ('x-pdf-password', 'x-pdf-password-b64')):
            raise HTTPException(400, {'code': 'INVALID_HEIC'})
        source = await _body(request, MAX_INPUT_BYTES, body_timeout)
        try:
            validate_heic(source)
        except ImageConversionError as error:
            report_error(error.code, 'heic-decode')
            raise HTTPException(413 if error.code == 'IMAGE_LIMIT_EXCEEDED' else 400,
                                {'code': error.code}) from None
        try:
            await asyncio.wait_for(slots.acquire(), timeout=0.1)
        except TimeoutError:
            raise HTTPException(429, {'code': 'WORKER_BUSY'}) from None
        # Same slots, task tracking, shield and completion callback as PDF work.
        # Disconnect/cancellation cannot release a live native worker's capacity.
        worker = asyncio.create_task(asyncio.to_thread(heic_converter or convert_heic, source))
        workers.add(worker)
        worker.add_done_callback(worker_finished)
        try:
            result = await asyncio.shield(worker)
        except ImageConversionError as error:
            report_error(error.code, 'heic-decode')
            status = {'HEIC_UNAVAILABLE': 503, 'INVALID_HEIC': 400,
                      'IMAGE_LIMIT_EXCEEDED': 413}.get(error.code, 422)
            raise HTTPException(status, {'code': error.code}) from None
        except Exception:
            report_error('IMAGE_CONVERSION_FAILED', 'heic-decode')
            raise HTTPException(422, {'code': 'IMAGE_CONVERSION_FAILED'}) from None
        return Response(result, media_type='image/png')

    @api.get('/jobs/{job_id}/status')
    async def status(job_id: str, request: Request) -> dict[str, Any]:
        return await dispatch('inspect', require_source(job_id), request)

    @api.get('/jobs/{job_id}/pages/{page}/runs')
    async def page_runs(job_id: str, page: int, request: Request) -> dict[str, Any]:
        return await dispatch('page', require_source(job_id), request, page=page)

    @api.get('/jobs/{job_id}/download')
    async def original_download(job_id: str) -> Response:
        return Response(require_source(job_id), media_type='application/pdf',
                        headers={'Content-Disposition': 'attachment; filename="document.pdf"'})

    @api.post('/jobs/{job_id}/edit')
    async def edit(job_id: str, request: Request,
                   dry_run: bool = Query(default=False),
                   acknowledge_signature: bool = Query(default=False)) -> dict[str, Any]:
        source = require_source(job_id)
        if request.headers.get('content-type', '').split(';')[0] != 'application/json':
            raise HTTPException(415, {'code': 'JSON_CONTENT_TYPE_REQUIRED'})
        recipe = await _body(request, MAX_RECIPE_BYTES, body_timeout)
        result = await dispatch('edit', source, request, recipe=recipe,
                                dry_run=dry_run, acknowledge_signature=acknowledge_signature)
        return {**result, 'location': operation_location([1])}

    @api.post('/ocr-notify')
    async def ocr_notify(request: Request) -> dict[str, int]:
        if await _body(request, 1024, body_timeout):
            raise HTTPException(400, {'code': 'PAYLOAD_NOT_ALLOWED'})
        api.state.ocr_requests += 1
        return {'count': api.state.ocr_requests}

    dist = Path(__file__).resolve().parent.parent / 'client' / 'dist'
    if (dist / 'assets').is_dir():
        api.mount('/assets', StaticFiles(directory=dist / 'assets'), name='assets')

    @api.get('/')
    async def index() -> Response:
        if (dist / 'index.html').is_file():
            return FileResponse(dist / 'index.html')
        return JSONResponse({'status': 'client_not_built', 'command': 'cd client && npm run build'})

    return api


app = create_app()

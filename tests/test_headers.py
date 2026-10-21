from __future__ import annotations

from pathlib import Path
import re

from fastapi.testclient import TestClient

from server.app import create_app


def test_http_headers_and_route_inventory() -> None:
    app = create_app()
    with TestClient(app) as client:
        for route in app.routes:
            path = getattr(route, 'path', '')
            assert '.pdf' not in path
            if path.startswith('/jobs/'):
                url = path.replace('{job_id}', 'evicted').replace('{page}', '0')
                for method in getattr(route, 'methods', []):
                    response = client.request(method, url)
                    assert response.headers['cache-control'] == 'no-store, private'
                    assert response.status_code == 409
        response = client.get('/health')
        csp = response.headers['content-security-policy']
        assert "'unsafe-eval'" not in csp
        assert "object-src 'none'" in csp
        assert "frame-ancestors 'none'" in csp


def test_pinned_pdfjs_has_no_dynamic_eval() -> None:
    root = Path(__file__).resolve().parents[1] / 'client/node_modules/pdfjs-dist/build'
    files = [root / 'pdf.mjs', root / 'pdf.worker.mjs']
    # CI installs the client before Python checks; absence is a failed verification,
    # not a silent skip of the pinned browser parser's posture.
    for path in files:
        source = path.read_text()
        assert re.search(r'\beval\s*\(', source) is None
        assert re.search(r'\bnew\s+Function\s*\(', source) is None

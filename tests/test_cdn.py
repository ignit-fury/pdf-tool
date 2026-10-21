"""Live edge-cache gate, parameterized without assuming a deployment exists."""
import os

import httpx
import pytest


@pytest.mark.cdn
def test_document_routes_are_not_cached_at_edge() -> None:
    base = os.environ.get('PDF_TOOL_DEPLOYMENT_URL')
    if not base:
        pytest.skip('No live deployment URL supplied; CDN verification remains pending')
    for suffix in ('/health', '/jobs/evicted/status', '/jobs/evicted/download'):
        with httpx.Client(timeout=20, follow_redirects=False) as client:
            for _ in range(2):
                response = client.get(base.rstrip('/') + suffix)
                assert response.headers['cache-control'] == 'no-store, private'
                assert response.headers.get('cf-cache-status', '').upper() in {'BYPASS', 'DYNAMIC'}

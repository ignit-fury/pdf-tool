"""Tests for tools/fetch_private_corpus.py.

Uses a local http.server-based mock bearer-token-gated file server - never a real bucket.
Covers the three status outcomes (D-02): skipped (absent credentials, the normal case),
ok (present credentials, successful fetch/verify - including the empty-manifest case), and
error (present credentials, genuine fetch/verification failure) - and proves these never
collapse into each other.
"""

from __future__ import annotations

import hashlib
import http.server
import json
import sys
import threading
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT / "tools"))

import fetch_private_corpus as fpc  # noqa: E402

VALID_TOKEN = "test-bearer-token"


class _MockBucketHandler(http.server.BaseHTTPRequestHandler):
    files: dict[str, bytes] = {}

    def do_GET(self):  # noqa: N802 - http.server's required method name
        if self.headers.get("Authorization") != f"Bearer {VALID_TOKEN}":
            self.send_response(401)
            self.end_headers()
            return
        data = self.files.get(self.path.lstrip("/"))
        if data is None:
            self.send_response(404)
            self.end_headers()
            return
        self.send_response(200)
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, format, *args):  # noqa: A002 - silence test output
        pass


@pytest.fixture
def mock_bucket():
    def _start(files: dict[str, bytes]):
        _MockBucketHandler.files = files
        server = http.server.HTTPServer(("127.0.0.1", 0), _MockBucketHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        return server, f"http://127.0.0.1:{server.server_port}"

    started: list[http.server.HTTPServer] = []

    def factory(files: dict[str, bytes]):
        server, base_url = _start(files)
        started.append(server)
        return base_url

    yield factory

    for server in started:
        server.shutdown()


def test_absent_credentials_both_none_is_skipped():
    result = fpc.fetch_private_corpus(None, None)
    assert result.status == "skipped"


def test_absent_credentials_both_empty_string_is_skipped():
    result = fpc.fetch_private_corpus("", "")
    assert result.status == "skipped"


def test_absent_credentials_partial_is_skipped():
    assert fpc.fetch_private_corpus("https://example.test", None).status == "skipped"
    assert fpc.fetch_private_corpus(None, "some-token").status == "skipped"


def test_cli_absent_credentials_prints_status_skipped_and_exits_zero(monkeypatch, capsys):
    monkeypatch.delenv("PRIVATE_CORPUS_BASE_URL", raising=False)
    monkeypatch.delenv("PRIVATE_CORPUS_TOKEN", raising=False)
    exit_code = fpc.main()
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "status=skipped" in captured.out


def test_ok_status_with_empty_manifest_and_valid_credentials(mock_bucket, tmp_path):
    base_url = mock_bucket({})
    manifest = tmp_path / "manifest.json"
    manifest.write_text("[]")

    result = fpc.fetch_private_corpus(
        base_url, VALID_TOKEN, manifest_path=str(manifest), dest_dir=str(tmp_path / "private")
    )
    assert result.status == "ok"


def test_ok_status_downloads_and_verifies_a_real_file(mock_bucket, tmp_path):
    content = b"%PDF-1.4 fake private-tier fixture bytes"
    sha256 = hashlib.sha256(content).hexdigest()
    base_url = mock_bucket({"invoice.pdf": content})

    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps([{"filename": "invoice.pdf", "sha256": sha256}]))
    dest_dir = tmp_path / "private"

    result = fpc.fetch_private_corpus(
        base_url, VALID_TOKEN, manifest_path=str(manifest), dest_dir=str(dest_dir)
    )
    assert result.status == "ok"
    assert (dest_dir / "invoice.pdf").read_bytes() == content


def test_error_status_on_wrong_token(mock_bucket, tmp_path):
    content = b"%PDF-1.4 fake"
    sha256 = hashlib.sha256(content).hexdigest()
    base_url = mock_bucket({"invoice.pdf": content})

    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps([{"filename": "invoice.pdf", "sha256": sha256}]))

    result = fpc.fetch_private_corpus(
        base_url, "wrong-token", manifest_path=str(manifest), dest_dir=str(tmp_path / "private")
    )
    assert result.status == "error"


def test_error_status_on_sha256_mismatch(mock_bucket, tmp_path):
    content = b"%PDF-1.4 fake"
    base_url = mock_bucket({"invoice.pdf": content})

    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps([{"filename": "invoice.pdf", "sha256": "0" * 64}]))

    result = fpc.fetch_private_corpus(
        base_url, VALID_TOKEN, manifest_path=str(manifest), dest_dir=str(tmp_path / "private")
    )
    assert result.status == "error"

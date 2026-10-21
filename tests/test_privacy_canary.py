"""Five retention surfaces on success/crash paths. This bounds exercised paths only.

Cache bytes are intentionally evictable memory. Scratch must be gone when an operation
returns. There is no queue/object store; reporter events carry fixed codes, never frames.
"""
from __future__ import annotations

import importlib.metadata
import logging
import sys

import pytest

from server import isolation
from server.errors import set_error_reporter
from tools.build_security_fixtures import password_pdf, text_pdf


@pytest.mark.parametrize('crash', [False, True])
def test_five_surfaces_never_retain_canary(tmp_path, caplog, monkeypatch, crash) -> None:
    content = 'canary-a729d8d4-content'
    filename = 'canary-c38293a6-filename'
    password = 'canary-b01a819e-password'
    monkeypatch.setenv('PDF_TOOL_SCRATCH_ROOT', str(tmp_path))
    # macOS development permits a private temp directory. Linux requires actual tmpfs
    # in production; separate linux_only tests pin the fail-closed deployment posture.
    monkeypatch.delenv('PDF_TOOL_ENV', raising=False)
    events = []
    set_error_reporter(events.append)
    if crash:
        # Test-only process-factory injection; no request-controlled fault hook exists.
        monkeypatch.setattr(isolation, '_worker_command', lambda: [sys.executable, '-c',
            'import os,sys; data=sys.stdin.buffer.read(); open(os.path.join(os.environ["TMPDIR"],"' + filename + '"),"wb").write(data); raise RuntimeError("' + content + '")'])
    try:
        with caplog.at_level(logging.DEBUG):
            result = isolation.run_worker('page', text_pdf(content.encode()), password=password)
        assert ('error' in result) is crash
        assert list(tmp_path.iterdir()) == []
        captured = caplog.text + repr(events)
        for marker in (content, filename, password):
            assert marker not in captured
        for event in events:
            assert set(event) == {'code', 'action'}
        installed = {dist.metadata['Name'].lower() for dist in importlib.metadata.distributions() if dist.metadata['Name']}
        assert not installed.intersection({'redis', 'arq', 'boto3', 'google-cloud-storage', 'azure-storage-blob'})
    finally:
        set_error_reporter(None)


def test_password_failure_event_contains_no_password(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv('PDF_TOOL_SCRATCH_ROOT', str(tmp_path))
    monkeypatch.delenv('PDF_TOOL_ENV', raising=False)
    events = []
    set_error_reporter(events.append)
    try:
        result = isolation.run_worker('inspect', password_pdf('real-password'), password='private-wrong-password')
        assert 'error' in result
        assert 'private-wrong-password' not in repr(events)
        assert 'real-password' not in repr(events)
        assert list(tmp_path.iterdir()) == []
    finally:
        set_error_reporter(None)

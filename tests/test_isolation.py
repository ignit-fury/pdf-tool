"""A parser crash must not survive as files, content logs, or reporter locals."""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

from server import errors, isolation
from server.secrets import SecretStr
from tools.build_security_fixtures import text_pdf


def test_secret_repr_is_redacted() -> None:
    secret = SecretStr("password-canary")
    assert "password-canary" not in repr(secret)
    assert "password-canary" not in str(secret)


def test_inspection_runs_outside_parent_and_cleans_scratch(tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PDF_TOOL_SCRATCH_ROOT", str(tmp_path))
    result = isolation.run_worker("inspect", text_pdf())
    assert result.get("error") is None, result
    assert result["page_count"] == 1
    assert result["worker_pid"] != os.getpid()
    assert list(tmp_path.iterdir()) == []


def test_wall_timeout_kills_worker_and_cleans_scratch(tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PDF_TOOL_SCRATCH_ROOT", str(tmp_path))
    monkeypatch.setattr(isolation, "_worker_command", lambda: [sys.executable, "-c",
        "import sys,time; sys.stdin.buffer.read(); time.sleep(60)"])
    assert isolation.run_worker("inspect", text_pdf(), timeout=0.1) == {"error": "WORKER_TIMEOUT"}
    assert list(tmp_path.iterdir()) == []


def test_crash_reports_only_sanitized_event(tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setenv("PDF_TOOL_SCRATCH_ROOT", str(tmp_path))
    monkeypatch.setattr(isolation, "_worker_command", lambda: [sys.executable, "-c",
        "import sys; sys.stderr.write('content-canary password-canary'); sys.exit(23)"])
    events: list[dict[str, str]] = []
    errors.set_error_reporter(events.append)
    try:
        result = isolation.run_worker("inspect", text_pdf(b"content-canary"), password="password-canary")
    finally:
        errors.set_error_reporter(None)
    assert result == {"error": "WORKER_FAILED"}
    assert events == [{"code": "WORKER_FAILED", "action": "inspect"}]
    assert not capsys.readouterr().err
    assert list(tmp_path.iterdir()) == []


def test_unbounded_worker_stdout_is_killed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(isolation, "MAX_OUTPUT_BYTES", 1024)
    monkeypatch.setattr(isolation, "_worker_command", lambda: [sys.executable, "-c",
        "import sys; sys.stdout.buffer.write(b'x'*100000)"])
    assert isolation.run_worker("inspect", text_pdf()) == {"error": "WORKER_OUTPUT_LIMIT"}


def test_bad_child_json_is_not_echoed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(isolation, "_worker_command", lambda: [sys.executable, "-c",
        "print('content-canary')"])
    assert isolation.run_worker("inspect", text_pdf()) == {"error": "WORKER_FAILED"}


def test_unknown_action_never_spawns(monkeypatch: pytest.MonkeyPatch) -> None:
    def forbidden() -> list[str]:
        raise AssertionError("spawned unknown action")
    monkeypatch.setattr(isolation, "_worker_command", forbidden)
    assert isolation.run_worker("content-canary", text_pdf()) == {"error": "INVALID_ACTION"}


def test_source_and_recipe_size_caps_precede_spawn(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(isolation, "MAX_SOURCE_BYTES", 5)
    assert isolation.run_worker("inspect", b"%PDF-xx") == {"error": "SOURCE_TOO_LARGE"}
    monkeypatch.setattr(isolation, "MAX_RECIPE_BYTES", 2)
    assert isolation.run_worker("inspect", b"%PDF-", recipe=b"[ ]") == {"error": "RECIPE_TOO_LARGE"}


def test_cpu_and_core_limits_set_in_child(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(isolation, "_worker_command", lambda: [sys.executable, "-c",
        "import json,resource; from server.worker import _set_limits; _set_limits(); "
        "print(json.dumps({'cpu':resource.getrlimit(resource.RLIMIT_CPU)[0],"
        "'core':resource.getrlimit(resource.RLIMIT_CORE)[0]}))"])
    result = isolation.run_worker("inspect", text_pdf())
    assert result == {"cpu": 20, "core": 0}


@pytest.mark.linux_only
@pytest.mark.skipif(sys.platform != "linux", reason="RLIMIT_AS is not enforceable on macOS")
def test_linux_memory_limit_is_enforced_in_child(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(isolation, "_worker_command", lambda: [sys.executable, "-c",
        "import json,resource; from server.worker import _set_limits; _set_limits(); "
        "limited=False\ntry: bytearray(2*1024*1024*1024)\nexcept MemoryError: limited=True\n"
        "print(json.dumps({'limited':limited,'limit':resource.getrlimit(resource.RLIMIT_AS)[0]}))"])
    assert isolation.run_worker("inspect", text_pdf()) == {"limited": True, "limit": 1024**3}


@pytest.mark.linux_only
@pytest.mark.skipif(sys.platform != "linux", reason="Linux memory and tmpfs gate")
def test_production_disk_scratch_fails_closed(tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PDF_TOOL_ENV", "production")
    monkeypatch.setenv("PDF_TOOL_SCRATCH_ROOT", str(tmp_path))
    monkeypatch.setattr(isolation, "_is_tmpfs", lambda path: False)
    assert isolation.run_worker("inspect", text_pdf()) == {"error": "SCRATCH_UNSAFE"}

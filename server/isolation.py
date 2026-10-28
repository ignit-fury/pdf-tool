"""Bounded subprocess transport. This parent module imports no PDF engine.

Linux production requires a tmpfs scratch mount (default /dev/shm). macOS uses
private OS temporary directories for development; it cannot claim Linux's memory
limit/tmpfs guarantees. The parent owns cleanup even when the child is killed.
"""
from __future__ import annotations

import base64
import json
import os
from pathlib import Path
import selectors
import signal
import subprocess
import sys
import tempfile
import time

from server.errors import ACTIONS, ERROR_CODES, report_error
from server.secrets import SecretStr

MAX_SOURCE_BYTES = 50 * 1024 * 1024
MAX_RECIPE_BYTES = 1024 * 1024
MAX_OUTPUT_BYTES = 80 * 1024 * 1024


class _BoundaryError(Exception):
    pass


def _worker_command() -> list[str]:
    """Private injectable process factory seam; no public crash operation exists."""
    return [sys.executable, "-m", "server.worker"]


def _is_tmpfs(path: Path) -> bool:
    try:
        resolved = path.resolve()
        matches: list[tuple[int, bool]] = []
        for line in Path("/proc/self/mountinfo").read_text().splitlines():
            before, after = line.split(" - ", 1)
            mount = Path(before.split()[4].replace("\\040", " "))
            if resolved == mount or mount in resolved.parents:
                matches.append((len(str(mount)), after.split()[0] == "tmpfs"))
        return max(matches, default=(0, False))[1]
    except (OSError, ValueError, IndexError):
        return False


def _scratch_root() -> Path:
    default = "/dev/shm" if sys.platform == "linux" else tempfile.gettempdir()
    root = Path(os.environ.get("PDF_TOOL_SCRATCH_ROOT", default))
    if not root.is_dir():
        raise _BoundaryError("SCRATCH_UNSAFE")
    if sys.platform == "linux" and os.environ.get("PDF_TOOL_ENV") == "production" and not _is_tmpfs(root):
        raise _BoundaryError("SCRATCH_UNSAFE")
    return root


def _kill_group(process: subprocess.Popen[bytes]) -> None:
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    process.wait()


def _exchange(process: subprocess.Popen[bytes], payload: bytes, timeout: float) -> bytes:
    """Read and write concurrently with a strict output ceiling and wall deadline."""
    assert process.stdin is not None and process.stdout is not None
    output = bytearray()
    offset = 0
    deadline = time.monotonic() + timeout
    with selectors.DefaultSelector() as selector:
        os.set_blocking(process.stdin.fileno(), False)
        os.set_blocking(process.stdout.fileno(), False)
        selector.register(process.stdin, selectors.EVENT_WRITE)
        selector.register(process.stdout, selectors.EVENT_READ)
        while selector.get_map():
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise _BoundaryError("WORKER_TIMEOUT")
            for key, _mask in selector.select(min(remaining, 0.1)):
                if key.fileobj is process.stdin:
                    try:
                        offset += os.write(key.fd, payload[offset:offset + 65536])
                    except BrokenPipeError:
                        offset = len(payload)
                    if offset == len(payload):
                        selector.unregister(process.stdin)
                        process.stdin.close()
                else:
                    chunk = os.read(key.fd, 65536)
                    if not chunk:
                        selector.unregister(process.stdout)
                        process.stdout.close()
                    else:
                        output.extend(chunk)
                        if len(output) > MAX_OUTPUT_BYTES:
                            raise _BoundaryError("WORKER_OUTPUT_LIMIT")
        remaining = deadline - time.monotonic()
        try:
            process.wait(timeout=max(0, remaining))
        except subprocess.TimeoutExpired:
            raise _BoundaryError("WORKER_TIMEOUT") from None
    if process.returncode:
        raise _BoundaryError("WORKER_FAILED")
    return bytes(output)


def run_worker(action: str, source: bytes, *, password: str = "", page: int = 0,
               recipe: bytes = b"[]", dry_run: bool = False,
               acknowledge_signature: bool = False, timeout: float = 30,
               export_operation: str = "", downsample: bool = False) -> dict[str, object]:
    """Run one operation. Failures are fixed codes, never exception messages."""
    code: str | None = None
    if action not in ACTIONS:
        code = "INVALID_ACTION"
    elif action == 'export' and (export_operation not in ('compress', 'flatten', 'text', 'markdown', 'html', 'pdfa')
            or not isinstance(downsample, bool) or (downsample and export_operation != 'compress')):
        code = 'EXPORT_OPTIONS_INVALID'
    elif len(source) > MAX_SOURCE_BYTES:
        code = "SOURCE_TOO_LARGE"
    elif len(recipe) > MAX_RECIPE_BYTES:
        code = "RECIPE_TOO_LARGE"
    elif not source.startswith(b"%PDF-") or len(password) > 1024 or timeout <= 0:
        code = "INVALID_INPUT"
    if code is not None:
        report_error(code, action)
        return {"error": code}
    secret = SecretStr(password)
    try:
        with tempfile.TemporaryDirectory(prefix="pdf-worker-", dir=_scratch_root()) as scratch:
            request = {"action": action, "source": base64.b64encode(source).decode("ascii"),
                "password": secret.get_secret_value(), "page": page,
                "recipe": base64.b64encode(recipe).decode("ascii"), "dry_run": dry_run,
                "acknowledge_signature": acknowledge_signature,
                "export_operation": export_operation, "downsample": downsample}
            payload = json.dumps(request, separators=(",", ":")).encode()
            # Never give an untrusted-document parser cloud/service credentials,
            # import-path overrides, dynamic-loader hooks, or proxy secrets.
            allowed = {"PATH", "TZ", "LANG", "LC_ALL"}
            if sys.platform == "win32":
                allowed.add("SYSTEMROOT")
            environment = {name: value for name, value in os.environ.items() if name in allowed}
            environment.update({"PDF_TOOL_WORKER_SCRATCH": scratch, "TMPDIR": scratch,
                                "TEMP": scratch, "TMP": scratch})
            process = subprocess.Popen(_worker_command(), stdin=subprocess.PIPE,
                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, env=environment,
                cwd=Path(__file__).resolve().parent.parent, start_new_session=True, close_fds=True)
            try:
                response = _exchange(process, payload, timeout)
            finally:
                _kill_group(process)
                for stream in (process.stdin, process.stdout):
                    if stream is not None:
                        stream.close()
            parsed: object = json.loads(response)
            if not isinstance(parsed, dict):
                raise _BoundaryError("WORKER_FAILED")
            result: dict[str, object] = parsed
            if "error" in result:
                received = result["error"]
                code = received if isinstance(received, str) and received in ERROR_CODES else "WORKER_FAILED"
            else:
                return result
    except _BoundaryError as error:
        candidate = error.args[0]
        code = candidate if isinstance(candidate, str) and candidate in ERROR_CODES else "WORKER_FAILED"
    except Exception:
        code = "WORKER_FAILED"
    report_error(code, action)
    return {"error": code}

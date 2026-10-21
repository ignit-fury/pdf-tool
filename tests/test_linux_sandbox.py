"""OS-level worker egress denial; never represented as verified on macOS."""
import subprocess
import sys
import errno

import pytest


def _evaluate_filter(program: list[tuple[int, int, int, int]], arch: int, number: int) -> int:
    """Small cBPF interpreter verifies control flow, not kernel enforcement."""
    accumulator = 0
    pc = 0
    while pc < len(program):
        code, yes, no, value = program[pc]
        if code == 0x20:  # LD W ABS of seccomp_data fields
            accumulator = {0: number, 4: arch}[value]
        elif code == 0x15:  # JMP JEQ K
            pc += yes if accumulator == value else no
        elif code == 0x45:  # JMP JSET K
            pc += yes if accumulator & value else no
        elif code == 0x35:  # JMP JGE K
            pc += yes if accumulator >= value else no
        elif code == 0x06:  # RET K
            return value
        else:
            raise AssertionError(f"unsupported BPF opcode {code}")
        pc += 1
    raise AssertionError("filter fell through")


@pytest.mark.parametrize("machine,arch,socket,connect,execve,clone", [
    ("x86_64", 0xC000003E, 41, 42, 59, 56),
    ("aarch64", 0xC00000B7, 198, 203, 221, 220),
])
def test_filter_assembly_denies_egress_exec_and_fork(machine, arch, socket, connect, execve, clone) -> None:
    from server.linux_sandbox import build_filter
    program = build_filter(machine)
    denied = 0x00050000 | errno.EPERM
    for syscall in (socket, connect, execve, clone, 435, 425, 438):
        assert _evaluate_filter(program, arch, syscall) == denied
    assert _evaluate_filter(program, arch, 0) == 0x7FFF0000
    assert _evaluate_filter(program, 0x40000003, socket) == 0x80000000


def test_filter_rejects_x32_and_unknown_architecture() -> None:
    from server.linux_sandbox import SandboxUnavailable, build_filter
    program = build_filter("x86_64")
    assert _evaluate_filter(program, 0xC000003E, 0x40000000 | 41) != 0x7FFF0000
    assert _evaluate_filter(program, 0xC000003E, 539) != 0x7FFF0000
    with pytest.raises(SandboxUnavailable):
        build_filter("unknown-architecture")


def test_worker_receives_no_parent_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    from server import isolation
    from tools.build_security_fixtures import text_pdf
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "credential-canary")
    monkeypatch.setenv("OPENAI_API_KEY", "credential-canary")
    monkeypatch.setenv("PYTHONPATH", "/unsafe-import-root")
    runner = "import os,json; print(json.dumps({'keys':sorted(os.environ)}))"
    monkeypatch.setattr(isolation, "_worker_command", lambda: [sys.executable, "-c", runner])
    result = isolation.run_worker("inspect", text_pdf())
    assert "AWS_SECRET_ACCESS_KEY" not in result["keys"]
    assert "OPENAI_API_KEY" not in result["keys"]
    assert "PYTHONPATH" not in result["keys"]
    assert "PDF_TOOL_WORKER_SCRATCH" in result["keys"]


def test_failed_sandbox_initialization_prevents_pdf_parse(monkeypatch: pytest.MonkeyPatch) -> None:
    from server import isolation
    from tools.build_security_fixtures import text_pdf
    runner = (
        "import server.linux_sandbox as sandbox\n"
        "def reject(): raise RuntimeError('credential-canary')\n"
        "sandbox.restrict_worker=reject\n"
        "from server.worker import main\nmain()\n"
    )
    monkeypatch.setattr(isolation, "_worker_command", lambda: [sys.executable, "-c", runner])
    assert isolation.run_worker("inspect", text_pdf()) == {"error": "WORKER_FAILED"}


@pytest.mark.linux_only
@pytest.mark.skipif(sys.platform != 'linux', reason='Linux seccomp is unavailable on macOS development')
def test_worker_cannot_create_network_socket() -> None:
    result = subprocess.run([sys.executable, '-c', '''
from server.linux_sandbox import restrict_worker
import socket
restrict_worker()
try:
    socket.socket()
except PermissionError:
    pass
else:
    raise AssertionError('worker networking is not denied')
'''], capture_output=True, timeout=10)
    assert result.returncode == 0, result.stderr


@pytest.mark.linux_only
@pytest.mark.skipif(sys.platform != 'linux', reason='Linux seccomp is unavailable on macOS development')
def test_kernel_denies_socketpair_process_access_exec_and_process_escape() -> None:
    runner = '''
import ctypes, errno, platform
from server.linux_sandbox import restrict_worker
libc=ctypes.CDLL(None,use_errno=True)
libc.syscall.restype=ctypes.c_long
machine=platform.machine().lower()
numbers=([42,53,101,310,311,59,322,56,435,109,112,425,426,427,438]
         if machine in ('x86_64','amd64') else
         [203,199,117,270,271,221,281,220,435,154,157,425,426,427,438])
restrict_worker()
for number in numbers:
    ctypes.set_errno(0)
    result=libc.syscall(ctypes.c_long(number),ctypes.c_long(-1),ctypes.c_long(0),
        ctypes.c_long(0),ctypes.c_long(0),ctypes.c_long(0),ctypes.c_long(0))
    assert result == -1 and ctypes.get_errno() == errno.EPERM, number
'''
    result = subprocess.run([sys.executable, '-c', runner], capture_output=True, timeout=10)
    assert result.returncode == 0, result.stderr

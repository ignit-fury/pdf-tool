"""Reduce Linux worker syscall surface; this is one layer, not a full sandbox.

Based on Linux seccomp-filter documentation and upstream syscall tables:
https://www.kernel.org/doc/html/latest/userspace-api/seccomp_filter.html
https://github.com/torvalds/linux/blob/master/arch/x86/entry/syscalls/syscall_64.tbl
https://github.com/torvalds/linux/blob/master/include/uapi/asm-generic/unistd.h

Install only in the disposable child, after trusted imports and before parsing
untrusted requests. Linux failures are fatal. macOS development has no equivalent
filter here and must not be described as a production egress boundary.
"""
from __future__ import annotations

import ctypes
import errno
from pathlib import Path
import platform
import sys

BPF_LD_W_ABS = 0x20
BPF_JMP_JEQ_K = 0x15
BPF_JMP_JSET_K = 0x45
BPF_JMP_JGE_K = 0x35
BPF_RET_K = 0x06
SECCOMP_RET_KILL_PROCESS = 0x80000000
SECCOMP_RET_ERRNO = 0x00050000
SECCOMP_RET_ALLOW = 0x7FFF0000
PR_SET_NO_NEW_PRIVS = 38
PR_SET_SECCOMP = 22
SECCOMP_MODE_FILTER = 2

# Native 64-bit syscall numbers from upstream Linux. AArch64 has no separate
# fork/vfork calls; clone/clone3 are its process/thread creation interfaces.
_ARCHITECTURES: dict[str, tuple[int, tuple[int, ...]]] = {
    "x86_64": (0xC000003E, (
        41, 53, 42,                 # socket, socketpair, connect
        101, 310, 311, 438,        # ptrace, process_vm_readv/writev, pidfd_getfd
        59, 322,                   # execve, execveat
        57, 58, 56, 435,          # fork, vfork, clone, clone3
        112, 109,                 # setsid, setpgid
        425, 426, 427,            # io_uring_setup/enter/register
    )),
    "aarch64": (0xC00000B7, (
        198, 199, 203,            # socket, socketpair, connect
        117, 270, 271, 438,        # ptrace, process_vm_readv/writev, pidfd_getfd
        221, 281,                 # execve, execveat
        220, 435,                 # clone, clone3 (no fork/vfork ABI)
        157, 154,                 # setsid, setpgid
        425, 426, 427,            # io_uring_setup/enter/register
    )),
}


class SandboxUnavailable(RuntimeError):
    """Only a fixed reason; no native errno, environment, or exception details."""


def build_filter(machine: str) -> list[tuple[int, int, int, int]]:
    """Return classic BPF instructions; callable on macOS for static checks only."""
    canonical = {"amd64": "x86_64", "arm64": "aarch64"}.get(machine.lower(), machine.lower())
    if canonical not in _ARCHITECTURES:
        raise SandboxUnavailable("worker_sandbox_unavailable")
    arch, denied = _ARCHITECTURES[canonical]
    refuse = SECCOMP_RET_ERRNO | errno.EPERM
    program = [
        (BPF_LD_W_ABS, 0, 0, 4),              # seccomp_data.arch
        (BPF_JMP_JEQ_K, 1, 0, arch),         # match skips the kill
        (BPF_RET_K, 0, 0, SECCOMP_RET_KILL_PROCESS),
        (BPF_LD_W_ABS, 0, 0, 0),              # seccomp_data.nr
    ]
    if canonical == "x86_64":
        # x32 shares AUDIT_ARCH_X86_64 but uses a second syscall-number ABI.
        program.extend([
            (BPF_JMP_JSET_K, 0, 1, 0x40000000),
            (BPF_RET_K, 0, 0, refuse),
            # Reject the legacy x32 range even without its flag (old kernels).
            (BPF_JMP_JGE_K, 0, 1, 512),
            (BPF_RET_K, 0, 0, refuse),
        ])
    for number in denied:
        program.extend([(BPF_JMP_JEQ_K, 0, 1, number), (BPF_RET_K, 0, 0, refuse)])
    program.append((BPF_RET_K, 0, 0, SECCOMP_RET_ALLOW))
    return program


class _SockFilter(ctypes.Structure):
    _fields_ = [("code", ctypes.c_ushort), ("jt", ctypes.c_ubyte),
                ("jf", ctypes.c_ubyte), ("k", ctypes.c_uint32)]


class _SockFprog(ctypes.Structure):
    _fields_ = [("len", ctypes.c_ushort), ("filter", ctypes.POINTER(_SockFilter))]


def restrict_worker() -> bool:
    """Install irreversible Linux restrictions or raise; return False on macOS."""
    if sys.platform != "linux":
        if sys.platform == "darwin":
            return False
        raise SandboxUnavailable("worker_sandbox_unavailable")
    program = build_filter(platform.machine())
    if ctypes.sizeof(ctypes.c_void_p) != 8 or sys.byteorder != "little":
        raise SandboxUnavailable("worker_sandbox_unavailable")
    try:
        # prctl applies to the calling thread. All parsing must remain in this
        # one filtered thread; clone/clone3 subsequently prohibit new threads.
        if len(list(Path("/proc/self/task").iterdir())) != 1:
            raise SandboxUnavailable("worker_sandbox_unavailable")
        instructions = (_SockFilter * len(program))(*(_SockFilter(*row) for row in program))
        descriptor = _SockFprog(len(program), instructions)
        libc = ctypes.CDLL(None, use_errno=True)
        prctl = libc.prctl
        prctl.argtypes = [ctypes.c_int, ctypes.c_ulong, ctypes.c_void_p,
                          ctypes.c_ulong, ctypes.c_ulong]
        prctl.restype = ctypes.c_int
        if prctl(PR_SET_NO_NEW_PRIVS, 1, None, 0, 0) != 0:
            raise SandboxUnavailable("worker_sandbox_unavailable")
        if prctl(PR_SET_SECCOMP, SECCOMP_MODE_FILTER, ctypes.byref(descriptor), 0, 0) != 0:
            raise SandboxUnavailable("worker_sandbox_unavailable")
    except (AttributeError, OSError, ValueError):
        raise SandboxUnavailable("worker_sandbox_unavailable") from None
    return True

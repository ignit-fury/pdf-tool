"""Opt-in reporting of fixed codes only; never accept exceptions or frame locals."""
from __future__ import annotations

from collections.abc import Callable

ErrorReporter = Callable[[dict[str, str]], None]
_reporter: ErrorReporter | None = None
ERROR_CODES = frozenset({
    "INVALID_ACTION", "INVALID_INPUT", "SOURCE_TOO_LARGE", "RECIPE_TOO_LARGE",
    "SCRATCH_UNSAFE", "WORKER_TIMEOUT", "WORKER_OUTPUT_LIMIT", "WORKER_FAILED",
    "PDF_INVALID", "PASSWORD_REQUIRED", "PASSWORD_INCORRECT", "PAGE_OUT_OF_RANGE",
    "SIGNATURE_ACKNOWLEDGEMENT_REQUIRED", "INVALID_RECIPE", "DOCUMENT_LIMIT", "PDF_CYCLE", "REQUEST_FAILED",
})
ACTIONS = frozenset({"inspect", "page", "edit", "plan"})


def set_error_reporter(reporter: ErrorReporter | None) -> None:
    """Reporting is deliberately unconfigured until the application injects it."""
    global _reporter
    _reporter = reporter


def report_error(code: str, action: str) -> None:
    if _reporter is None:
        return
    event = {"code": code if code in ERROR_CODES else "WORKER_FAILED",
             "action": action if action in ACTIONS or action == "http" else "unknown"}
    try:
        _reporter(event)
    except Exception:
        # Reporter failure must neither alter the request nor expose a traceback.
        pass

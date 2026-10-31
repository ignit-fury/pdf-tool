"""Opt-in reporting of fixed codes only; never accept exceptions or frame locals."""
from __future__ import annotations

from collections.abc import Callable

ErrorReporter = Callable[[dict[str, str]], None]
_reporter: ErrorReporter | None = None
PDFA_REASON_CODES = {
    'PDFA_FONT_MISSING': 'font-missing', 'PDFA_FONT_UNSUPPORTED': 'font-unsupported',
    'PDFA_FONT_INVALID': 'font-invalid', 'PDFA_COLOR_UNSUPPORTED': 'color-unsupported',
    'PDFA_CONTENT_UNSUPPORTED': 'content-unsupported',
    'PDFA_STRUCTURE_UNSUPPORTED': 'structure-unsupported',
    'PDFA_METADATA_UNSUPPORTED': 'metadata-unsupported',
    'PDFA_VERSION_UNSUPPORTED': 'pdf-version', 'PDFA_LIMIT': 'limit',
}
TEXT_BOX_ERROR_CODES = frozenset({
    'INVALID_TEXT_BOX', 'TEXT_BOX_UNSUPPORTED_TEXT', 'TEXT_BOX_UNSAFE',
    'TEXT_BOX_NOT_FOUND', 'TEXT_BOX_OVERLAP', 'TEXT_BOX_LIMIT', 'TEXT_BOX_OUTPUT_LIMIT', 'TEXT_BOX_SOURCE_UNSAFE',
    'PARAGRAPH_STALE', 'PARAGRAPH_NEEDS_REBUILD', 'PARAGRAPH_UNCHANGED',
})
ERROR_CODES = frozenset({
    *PDFA_REASON_CODES,
    *TEXT_BOX_ERROR_CODES,
    'DOCX_REVIEW_REQUIRED', 'DOCX_REVIEW_MISMATCH', 'DOCX_UNAVAILABLE', 'DOCX_UNSUPPORTED',
    "INVALID_ACTION", "INVALID_INPUT", "SOURCE_TOO_LARGE", "RECIPE_TOO_LARGE",
    "SCRATCH_UNSAFE", "WORKER_TIMEOUT", "WORKER_OUTPUT_LIMIT", "WORKER_FAILED",
    "PDF_INVALID", "PASSWORD_REQUIRED", "PASSWORD_INCORRECT", "PAGE_OUT_OF_RANGE",
    "SIGNATURE_ACKNOWLEDGEMENT_REQUIRED", "INVALID_RECIPE", "DOCUMENT_LIMIT", "PDF_CYCLE", "REQUEST_FAILED",
    "HEIC_UNAVAILABLE", "INVALID_HEIC", "IMAGE_LIMIT_EXCEEDED",
    "IMAGE_CONVERSION_FAILED", "IMAGE_CONVERSION_TIMEOUT",
    "EXPORT_OPTIONS_INVALID", "EXPORT_LIMIT", "EXPORT_UNSUPPORTED", "FLATTEN_APPEARANCE_REQUIRED",
})
# PDF worker actions stay separate: accepting heic-decode here would make it a
# valid action in the PDF transport. Only reporting accepts the image action.
ACTIONS = frozenset({"inspect", "page", "edit", "plan", "export", "text-box"})


def set_error_reporter(reporter: ErrorReporter | None) -> None:
    """Reporting is deliberately unconfigured until the application injects it."""
    global _reporter
    _reporter = reporter


def report_error(code: str, action: str) -> None:
    if _reporter is None:
        return
    event = {"code": code if code in ERROR_CODES else "WORKER_FAILED",
             "action": action if action in ACTIONS or action in ("http", "heic-decode") else "unknown"}
    try:
        _reporter(event)
    except Exception:
        # Reporter failure must neither alter the request nor expose a traceback.
        pass

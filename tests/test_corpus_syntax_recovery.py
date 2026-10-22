"""Malformed inline images fail closed without a generic worker crash or partial runs."""
from __future__ import annotations

import hashlib
import io
from pathlib import Path

import pikepdf
import pytest

from server.isolation import run_worker
from tools.build_security_fixtures import text_pdf


def _inline_image_pdf(*, malformed: bool) -> bytes:
    # Three unfiltered grayscale pixels, including a newline. Without the
    # whitespace before EI, PLAYA's fallback cannot find the end across that
    # newline and encounters the second BI inside the first image instead.
    separator = b"" if malformed else b" "
    image = b"BI /W 3 /H 1 /BPC 8 /CS /G ID \x01\n\x02" + separator + b"EI\n"
    with pikepdf.open(io.BytesIO(text_pdf(b"before-image-canary"))) as pdf:
        text = pdf.pages[0].Contents.read_bytes()
        pdf.pages[0].Contents = pdf.make_stream(text + b"\n" + image + image)
        output = io.BytesIO()
        pdf.save(output)
        return output.getvalue()


def test_malformed_inline_image_refuses_entire_page_and_next_request_works() -> None:
    source = _inline_image_pdf(malformed=True)
    assert run_worker("page", source, page=0) == {"error": "PDF_INVALID"}
    healthy = run_worker("page", text_pdf(), page=0)
    assert healthy.get("error") is None
    assert healthy.get("runs")


def test_valid_inline_image_keeps_text_before_image() -> None:
    result = run_worker("page", _inline_image_pdf(malformed=False), page=0)
    assert result.get("error") is None
    assert "".join(run["text"] for run in result["runs"]) == "before-image-canary"


@pytest.mark.corpus
def test_known_malformed_corpus_page_has_named_refusal_and_source_is_unchanged() -> None:
    path = Path(__file__).resolve().parents[1] / "corpus/public/govdocs1_011_011089.pdf"
    source = path.read_bytes()
    before = hashlib.sha256(source).digest()
    assert run_worker("page", source, page=0) == {"error": "PDF_INVALID"}
    assert hashlib.sha256(path.read_bytes()).digest() == before

from __future__ import annotations

import pytest

from server.isolation import run_worker
from tools.build_security_fixtures import cyclic_page_tree, decompression_bomb, self_referencing_form, text_pdf


@pytest.mark.parametrize("builder", [cyclic_page_tree, decompression_bomb, self_referencing_form])
def test_hostile_document_fails_with_named_response_and_host_survives(builder: object) -> None:
    assert callable(builder)
    source = builder()
    result = run_worker("page", source, timeout=8)
    assert result.get("error") in {
        "PDF_INVALID", "DOCUMENT_LIMIT", "WORKER_TIMEOUT", "WORKER_FAILED", "PDF_CYCLE",
    }, result
    assert run_worker("inspect", text_pdf()).get("page_count") == 1

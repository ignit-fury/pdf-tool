from __future__ import annotations

import json
import io
import sys

import pikepdf
import pytest

from server.isolation import run_worker
from tools.build_security_fixtures import decompression_bomb, password_pdf, signed_pdf, text_pdf


def test_password_required_wrong_and_correct() -> None:
    source = password_pdf("password-marker")
    assert run_worker("inspect", source) == {"error": "PASSWORD_REQUIRED"}
    assert run_worker("inspect", source, password="wrong") == {"error": "PASSWORD_INCORRECT"}
    result = run_worker("inspect", source, password="password-marker")
    assert result.get("encrypted") is True
    assert result.get("page_count") == 1


def test_signature_detection_does_not_confuse_append_only() -> None:
    assert run_worker("inspect", signed_pdf())["signed"] is True
    assert run_worker("inspect", signed_pdf(flags=0))["signed"] is True
    assert run_worker("inspect", signed_pdf(flags=2, field=False))["signed"] is False


def test_signed_edit_requires_acknowledgment() -> None:
    source = signed_pdf()
    assert run_worker("edit", source) == {"error": "SIGNATURE_ACKNOWLEDGEMENT_REQUIRED"}
    assert run_worker("edit", source, dry_run=True).get("ok") is True
    assert run_worker("edit", source, acknowledge_signature=True).get("ok") is True


def test_page_has_geometry_and_server_minted_ids() -> None:
    result = run_worker("page", text_pdf(), page=0)
    assert result.get("error") is None, result
    assert result["width"] == 300
    assert result["height"] == 200
    runs = result["runs"]
    assert isinstance(runs, list) and len(runs) > 0
    assert all(len(run["box"]) == 4 and run["box"][3] > run["box"][1] for run in runs)


def test_edit_and_plan_return_same_report_source_immutable() -> None:
    source = text_pdf()
    before = bytes(source)
    page = run_worker("page", source)
    runs = page["runs"]
    assert isinstance(runs, list)
    recipe = json.dumps([{"run_id": runs[0]["run_id"], "new_text": "Security canarz"}]).encode()
    planned = run_worker("edit", source, recipe=recipe, dry_run=True)
    edited = run_worker("edit", source, recipe=recipe)
    assert edited["ok"] is True, edited
    assert planned["resolved"] == edited["resolved"]
    assert planned["pdf"] is None
    assert isinstance(edited["pdf"], str)
    assert before == source


def test_invalid_recipe_error_has_no_user_text() -> None:
    result = run_worker("edit", text_pdf(), recipe=b'{"content-canary":"password-marker"}')
    assert result == {"error": "INVALID_RECIPE"}


def test_invalid_page_is_named() -> None:
    assert run_worker("page", text_pdf(), page=9) == {"error": "PAGE_OUT_OF_RANGE"}


def test_worker_indexes_only_requested_page(monkeypatch: pytest.MonkeyPatch) -> None:
    from server import isolation
    with pikepdf.open(io.BytesIO(text_pdf())) as pdf:
        pdf.pages.append(pdf.pages[0])
        output = io.BytesIO()
        pdf.save(output)
        source = output.getvalue()
    # An internal test runner wraps the real parse method; no testing operation
    # or crash route is exposed in the shipped worker protocol.
    runner = (
        "from engine.index import RunIndex\n"
        "original=RunIndex._parse_page\n"
        "calls=[]\n"
        "def only_requested(self,number):\n"
        " calls.append(number)\n"
        " if calls != [1]: raise AssertionError('eager_document_parse')\n"
        " return original(self,number)\n"
        "RunIndex._parse_page=only_requested\n"
        "from server.worker import main\nmain()\n"
    )
    monkeypatch.setattr(isolation, "_worker_command", lambda: [sys.executable, "-c", runner])
    assert run_worker("page", source, page=1).get("page") == 1


def test_later_page_bomb_does_not_block_inspection_or_first_page() -> None:
    source = decompression_bomb(safe_first_page=True)
    assert run_worker("inspect", source).get("page_count") == 2
    assert run_worker("page", source, page=0).get("bucket") == "empty"
    assert run_worker("page", source, page=1) == {"error": "DOCUMENT_LIMIT"}

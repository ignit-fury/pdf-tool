"""Actual bounded worker proof on a 40-page USGS technical-document proxy."""
import base64
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import resource
import time

import pytest

from engine.index import RunIndex
from server.isolation import run_worker
from server.worker import CPU_LIMIT_SECONDS, MEMORY_LIMIT_BYTES

SOURCE = Path(__file__).resolve().parents[1] / "corpus/public/govdocs1_013_013050.pdf"
DIGEST = "d0a3b06606378733a2ec96cfa01e3b12c111d13059d070e3e039b751347a4529"


def _measure(source, recipe, dry_run):
    before = resource.getrusage(resource.RUSAGE_CHILDREN)
    start = time.monotonic()
    # Intentionally use run_worker's real default wall limit, never a relaxed timeout.
    result = run_worker("edit", source, recipe=json.dumps(recipe, separators=(",", ":")).encode(),
                        dry_run=dry_run)
    after = resource.getrusage(resource.RUSAGE_CHILDREN)
    elapsed = time.monotonic() - start
    cpu = after.ru_utime + after.ru_stime - before.ru_utime - before.ru_stime
    print(json.dumps({"dry_run": dry_run, "ops": len(recipe), "wall_seconds": round(elapsed, 3),
                      "child_cpu_seconds": round(cpu, 3), "ok": result.get("ok"),
                      "error": result.get("error")}))
    assert "error" not in result, result
    assert cpu < CPU_LIMIT_SECONDS
    assert elapsed < 30
    return result


@pytest.fixture(scope="module")
def batch():
    if not SOURCE.exists():
        pytest.skip("public 40-page USGS proxy absent")
    source = SOURCE.read_bytes()
    assert hashlib.sha256(source).hexdigest() == DIGEST
    assert CPU_LIMIT_SECONDS == 20
    assert MEMORY_LIMIT_BYTES == 1024 * 1024 * 1024
    operations = []
    occurrences = runs = 0
    with RunIndex(SOURCE) as index:
        assert index.page_count == 40
        for page in range(index.page_count):
            for run, _ in index.page(page).runs:
                runs += 1
                matches = list(re.finditer("the", run.display_text, re.I))
                if not matches:
                    continue
                occurrences += len(matches)
                text = run.display_text
                for match in reversed(matches):
                    text = text[:match.start()] + "a" + text[match.end():]
                operations.append({"run_id": run.run_id, "new_text": text})
    assert (runs, occurrences, len(operations)) == (3000, 1029, 772)
    initial = _measure(source, operations, True)
    assert initial["ok"] is False
    refusals = Counter(row["reason"] for row in initial["resolved"] if not row["ok"])
    assert sum(refusals.values()) == 97
    assert refusals["operator_shared_by_multiple_runs"] == 75
    assert sum(count for reason, count in refusals.items() if reason.startswith("no mapping table entry")) == 22
    rejected = {row["run_id"] for row in initial["resolved"] if not row["ok"]}
    accepted = [op for op in operations if op["run_id"] not in rejected]
    assert len(accepted) == 675
    return source, accepted


@pytest.mark.corpus
def test_40page_batch_worker_preview(batch):
    source, recipe = batch
    result = _measure(source, recipe, True)
    assert result["ok"] is True, result
    assert len(result["resolved"]) == 675
    assert result["pdf"] is None
    assert SOURCE.read_bytes() == source


@pytest.mark.corpus
def test_40page_batch_worker_apply(batch):
    source, recipe = batch
    preview = _measure(source, recipe, True)
    assert preview["ok"] is True, preview
    result = _measure(source, recipe, False)
    assert result["ok"] is True, result
    assert result["resolved"] == preview["resolved"]
    assert base64.b64decode(result["pdf"]).startswith(b"%PDF-")
    assert SOURCE.read_bytes() == source

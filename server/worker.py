"""Disposable PDF parser entry point. Only this child imports the engine.

Transport is one bounded JSON request and one JSON result; stderr is discarded
by the parent. No filenames from callers are accepted or propagated.
"""
from __future__ import annotations

import base64
import binascii
import io
import json
import logging
import os
from pathlib import Path
import resource
import sys
import zlib

from server.isolation import MAX_OUTPUT_BYTES, MAX_RECIPE_BYTES, MAX_SOURCE_BYTES
from server.secrets import SecretStr

MAX_REQUEST_BYTES = (MAX_SOURCE_BYTES + MAX_RECIPE_BYTES) * 4 // 3 + 8192
MAX_STREAM_BYTES = 16 * 1024 * 1024
MEMORY_LIMIT_BYTES = 1024 * 1024 * 1024
CPU_LIMIT_SECONDS = 20


class WorkerRefusal(Exception):
    pass


def _set_limits() -> None:
    # Core dumps would persist document memory outside the parent scratch tree.
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    resource.setrlimit(resource.RLIMIT_CPU, (CPU_LIMIT_SECONDS, CPU_LIMIT_SECONDS))
    if sys.platform == "linux":
        # Linux fails closed if the memory limit cannot be set.
        resource.setrlimit(resource.RLIMIT_AS, (MEMORY_LIMIT_BYTES, MEMORY_LIMIT_BYTES))
    else:
        try:
            resource.setrlimit(resource.RLIMIT_AS, (MEMORY_LIMIT_BYTES, MEMORY_LIMIT_BYTES))
        except (ValueError, OSError):
            pass  # macOS development; parent wall deadline still applies.


def _signed(pdf: object) -> bool:
    import pikepdf
    assert isinstance(pdf, pikepdf.Pdf)
    form = pdf.Root.get("/AcroForm")
    if form is None:
        return False
    if int(form.get("/SigFlags", 0)) & 1:
        return True
    stack: list[tuple[pikepdf.Object, pikepdf.Object | None]] = [
        (field, None) for field in form.get("/Fields", [])]
    seen: set[tuple[int, int]] = set()
    count = 0
    while stack:
        field, inherited = stack.pop()
        count += 1
        if count > 10000:
            raise WorkerRefusal("DOCUMENT_LIMIT")
        key = field.objgen
        if key != (0, 0):
            if key in seen:
                continue
            seen.add(key)
        kind = field.get("/FT", inherited)
        if str(kind) == "/Sig" and field.get("/V") is not None:
            return True
        stack.extend((child, kind) for child in field.get("/Kids", []))
    return False


def _reachable_streams(root: object) -> list[object]:
    """Walk one page's values without following page-tree or annotation backrefs."""
    import pikepdf
    pending = [root]
    seen: set[tuple[int, int]] = set()
    streams: list[object] = []
    visited = 0
    while pending:
        obj = pending.pop()
        visited += 1
        if visited > 50000:
            raise WorkerRefusal("DOCUMENT_LIMIT")
        if not isinstance(obj, (pikepdf.Dictionary, pikepdf.Array, pikepdf.Stream)):
            continue
        key = obj.objgen
        if key != (0, 0):
            if key in seen:
                continue
            seen.add(key)
        if isinstance(obj, pikepdf.Stream):
            streams.append(obj)
        if isinstance(obj, pikepdf.Array):
            pending.extend(obj)
        else:
            pending.extend(value for name, value in obj.items()
                           if name not in {"/Parent", "/P", "/Pg"})
    return streams


def _preflight(pdf: object, page: int | None = None) -> None:
    """Cap expansion before parser libraries materialize Flate streams.

    This guards the common single-Flate bomb with a 16MiB max_length call;
    other filters remain contained by the child's memory/CPU/wall limits.
    """
    import pikepdf
    assert isinstance(pdf, pikepdf.Pdf)
    candidates = pdf.objects if page is None else _reachable_streams(pdf.pages[page].obj)
    for obj in candidates:
        if not isinstance(obj, pikepdf.Stream):
            continue
        filters = obj.get("/Filter")
        if filters == pikepdf.Name.FlateDecode or (
            isinstance(filters, pikepdf.Array) and len(filters) == 1
            and filters[0] == pikepdf.Name.FlateDecode
        ):
            raw = obj.read_raw_bytes()
            decoder = zlib.decompressobj()
            expanded = decoder.decompress(raw, MAX_STREAM_BYTES + 1)
            if len(expanded) > MAX_STREAM_BYTES or decoder.unconsumed_tail:
                raise WorkerRefusal("DOCUMENT_LIMIT")
        if str(obj.get("/Subtype")) == "/Form":
            # Explicit DFS prevents a recursive Form graph entering any parser.
            pending = [(obj, frozenset[tuple[int, int]]())]
            traversed = 0
            while pending:
                form, ancestors = pending.pop()
                traversed += 1
                if traversed > 10000:
                    raise WorkerRefusal("DOCUMENT_LIMIT")
                if form.objgen in ancestors:
                    raise WorkerRefusal("PDF_CYCLE")
                resources = form.get("/Resources", pikepdf.Dictionary())
                xobjects = resources.get("/XObject", pikepdf.Dictionary())
                lineage = ancestors | {form.objgen}
                pending.extend((child, lineage) for _name, child in xobjects.items()
                    if isinstance(child, pikepdf.Stream) and str(child.get("/Subtype")) == "/Form")


def _execute(request: dict[str, object]) -> dict[str, object]:
    import pikepdf
    from engine.index import RunIndex
    from engine.recipe import RecipeTooLargeError, apply_recipe, parse_recipe, plan_recipe, source_font_info

    action = request.get("action")
    source64 = request.get("source")
    password = request.get("password", "")
    if action not in {"inspect", "page", "edit", "plan"} or not isinstance(source64, str) or not isinstance(password, str):
        raise WorkerRefusal("INVALID_INPUT")
    source = base64.b64decode(source64, validate=True)
    if len(source) > MAX_SOURCE_BYTES or not source.startswith(b"%PDF-"):
        raise WorkerRefusal("INVALID_INPUT")
    secret = SecretStr(password)
    scratch = os.environ.get("PDF_TOOL_WORKER_SCRATCH")
    if not scratch or not Path(scratch).is_dir():
        raise WorkerRefusal("SCRATCH_UNSAFE")
    path = Path(scratch) / "source.pdf"
    path.write_bytes(source)
    try:
        pdf = pikepdf.open(io.BytesIO(source), password=secret.get_secret_value())
    except pikepdf.PasswordError:
        raise WorkerRefusal("PASSWORD_INCORRECT" if secret.get_secret_value() else "PASSWORD_REQUIRED") from None
    except pikepdf.PdfError:
        raise WorkerRefusal("PDF_INVALID") from None
    with pdf:
        signed = _signed(pdf)
        count = len(pdf.pages)
        if action == "inspect":
            return {"page_count": count, "signed": signed, "encrypted": pdf.is_encrypted,
                    "worker_pid": os.getpid()}
        if action == "page":
            from engine.boxes import run_box
            from engine.classify_run import stream_bytes_and_resources
            from engine.run_id import decode_run_id
            number = request.get("page", 0)
            if not isinstance(number, int) or isinstance(number, bool) or not 0 <= number < count:
                raise WorkerRefusal("PAGE_OUT_OF_RANGE")
            _preflight(pdf, number)
            with RunIndex(path, password=secret.get_secret_value()) as index:
                indexed = index.page(number)
                runs = []
                for run, verdict in indexed.runs:
                    parts = decode_run_id(run.run_id)
                    raw, resources = stream_bytes_and_resources(pdf, number, parts["part"], parts["xobj_path"])
                    source_font, suggested_family = source_font_info(raw, resources, run.glyphs[0].operator_byte_offset)
                    runs.append({"run_id": run.run_id, "text": run.display_text,
                        "box": run_box(run, raw, resources), "state": verdict.state,
                        "reason": verdict.reason, "source_font": source_font,
                        "suggested_font_family": suggested_family})
            box = [float(x) for x in pdf.pages[number].cropbox]
            return {"page": number, "bucket": indexed.bucket, "runs": runs,
                "width": box[2] - box[0], "height": box[3] - box[1],
                "rotation": int(pdf.pages[number].get("/Rotate", 0)), "view_box": box}
        _preflight(pdf)
        if signed and action != "plan" and request.get("dry_run") is not True and request.get("acknowledge_signature") is not True:
            raise WorkerRefusal("SIGNATURE_ACKNOWLEDGEMENT_REQUIRED")
        recipe64 = request.get("recipe")
        if not isinstance(recipe64, str):
            raise WorkerRefusal("INVALID_RECIPE")
        recipe_bytes = base64.b64decode(recipe64, validate=True)
        if len(recipe_bytes) > MAX_RECIPE_BYTES:
            raise WorkerRefusal("RECIPE_TOO_LARGE")
        try:
            recipe = parse_recipe(recipe_bytes)
        except (ValueError, RecipeTooLargeError):
            raise WorkerRefusal("INVALID_RECIPE") from None
        output = Path(scratch) / "output.pdf"
        if request.get("dry_run") is True or action == "plan":
            report = plan_recipe(path, recipe, password=secret.get_secret_value())
        else:
            report = apply_recipe(path, recipe, output, password=secret.get_secret_value())
        return {"ok": report.ok, "resolved": [
            {"run_id": resolved.op.run_id, "ok": resolved.ok, "reason": resolved.reason,
             "strategy": resolved.strategy, "delta_pt": resolved.delta_pt}
            for resolved in report.resolved], "pdf": base64.b64encode(output.read_bytes()).decode("ascii")
            if output.exists() and report.ok else None}


def main() -> None:
    logging.disable(logging.CRITICAL)
    try:
        _set_limits()
        # Trusted imports finish before the irreversible syscall filter. No PDF
        # bytes or recipe JSON are parsed until restriction has succeeded.
        import pikepdf  # noqa: F401
        import engine.index  # noqa: F401
        import engine.recipe  # noqa: F401
        import engine.boxes  # noqa: F401
        from server.linux_sandbox import restrict_worker
        restrict_worker()
        raw = sys.stdin.buffer.read(MAX_REQUEST_BYTES + 1)
        if len(raw) > MAX_REQUEST_BYTES:
            raise WorkerRefusal("INVALID_INPUT")
        request: object = json.loads(raw)
        if not isinstance(request, dict):
            raise WorkerRefusal("INVALID_INPUT")
        result = _execute(request)
    except WorkerRefusal as refusal:
        result = {"error": str(refusal.args[0])}
    except (MemoryError, RecursionError):
        result = {"error": "DOCUMENT_LIMIT"}
    except (ValueError, TypeError, KeyError, binascii.Error, zlib.error):
        result = {"error": "PDF_INVALID"}
    except Exception:
        result = {"error": "WORKER_FAILED"}
    encoded = json.dumps(result, separators=(",", ":"), allow_nan=False).encode()
    if len(encoded) > MAX_OUTPUT_BYTES:
        encoded = b'{"error":"WORKER_OUTPUT_LIMIT"}'
    sys.stdout.buffer.write(encoded)


if __name__ == "__main__":
    main()

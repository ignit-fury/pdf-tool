"""Disposable PDF parser entry point. Only this child imports the engine.

Transport is one bounded JSON request and one JSON result; stderr is discarded
by the parent. No filenames from callers are accepted or propagated.
"""
from __future__ import annotations

import base64
import binascii
import io
import hashlib
import json
import logging
import math
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


def _text_box_payload(encoded: object) -> dict[str, object]:
    """Decode the existing recipe transport without ambiguous JSON semantics."""
    if not isinstance(encoded, str):
        raise WorkerRefusal('INVALID_TEXT_BOX')
    try:
        raw = base64.b64decode(encoded, validate=True)
    except (ValueError, binascii.Error):
        raise WorkerRefusal('INVALID_TEXT_BOX') from None
    if len(raw) > MAX_RECIPE_BYTES:
        raise WorkerRefusal('RECIPE_TOO_LARGE')

    def unique(pairs: list[tuple[str, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError('duplicate')
            result[key] = value
        return result

    def finite(value: str) -> float:
        number = float(value)
        if not math.isfinite(number):
            raise ValueError('nonfinite')
        return number

    try:
        payload: object = json.loads(raw.decode('utf-8'), object_pairs_hook=unique,
                                     parse_float=finite, parse_constant=finite)
    except (ValueError, UnicodeError, RecursionError):
        raise WorkerRefusal('INVALID_TEXT_BOX') from None
    if not isinstance(payload, dict) or payload.get('operation') not in ('list', 'upsert', 'remove', 'replace-source'):
        raise WorkerRefusal('INVALID_TEXT_BOX')
    return payload


def _managed_text_box_parts(pdf: object, source: bytes, page: int) -> dict[int, str | None]:
    """Lock marked direct parts; link IDs only after the native ownership proof."""
    import pikepdf
    from engine.text_boxes import TextBoxError, prepare_text_box
    assert isinstance(pdf, pikepdf.Pdf)
    contents = pdf.pages[page].obj.get('/Contents')
    streams = list(contents) if isinstance(contents, pikepdf.Array) else [contents]
    marked = {part: stream for part, stream in enumerate(streams)
              if isinstance(stream, pikepdf.Stream) and '/NativeTextBox' in stream}
    result: dict[int, str | None] = dict.fromkeys(marked)
    if not marked:
        return result
    try:
        verified = prepare_text_box(pdf, source, {'operation': 'list'})
        boxes = verified.get('boxes')
        if verified.get('ok') is not True or not isinstance(boxes, list):
            return result
        identifiers = {box['id'] for box in boxes if isinstance(box, dict)
                       and isinstance(box.get('id'), str) and box.get('page_index') == page}
        for part, stream in marked.items():
            metadata: object = json.loads(bytes(stream['/NativeTextBox']))
            if isinstance(metadata, dict):
                spec = metadata.get('spec')
                if isinstance(spec, dict) and isinstance(spec.get('id'), str) and spec['id'] in identifiers:
                    result[part] = spec['id']
    except (TextBoxError, ValueError, TypeError, KeyError, pikepdf.PdfError):
        # An invalid marker must not suppress unrelated source-run analysis.
        # No document-derived verification details cross the transport.
        return dict.fromkeys(marked)
    return result


def _execute(request: dict[str, object]) -> dict[str, object]:
    import pikepdf
    from engine.index import DocumentTooLargeError, RunIndex
    from engine.recipe import RecipeTooLargeError, apply_recipe, parse_recipe, plan_recipe, source_font_info, source_formatting_metadata

    action = request.get("action")
    source64 = request.get("source")
    password = request.get("password", "")
    if action not in {"inspect", "page", "edit", "plan", "export", "text-box"} or not isinstance(source64, str) or not isinstance(password, str):
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
            from engine.search import project_search_text
            from engine.boxes import run_box
            from engine.classify_run import stream_bytes_and_resources
            from engine.run_id import decode_run_id
            from engine.records import RunRecord
            number = request.get("page", 0)
            if not isinstance(number, int) or isinstance(number, bool) or not 0 <= number < count:
                raise WorkerRefusal("PAGE_OUT_OF_RANGE")
            _preflight(pdf, number)
            managed_parts = _managed_text_box_parts(pdf, source, number)
            with RunIndex(path, password=secret.get_secret_value()) as index:
                indexed = index.page(number)
                runs = []
                streams: dict[tuple[int, tuple[int, ...]], tuple[bytes, pikepdf.Object | None]] = {}
                stream_runs: dict[tuple[int, tuple[int, ...]], list[RunRecord]] = {}
                formatting: dict[str, dict[str, object]] = {}
                for source_run, _ in indexed.runs:
                    address = decode_run_id(source_run.run_id)
                    stream_runs.setdefault((address['part'], address['xobj_path']), []).append(source_run)
                for run, verdict in indexed.runs:
                    parts = decode_run_id(run.run_id)
                    stream_key = (parts["part"], parts["xobj_path"])
                    if stream_key not in streams:
                        streams[stream_key] = stream_bytes_and_resources(pdf, number, *stream_key)
                        formatting.update(source_formatting_metadata(
                            pdf, streams[stream_key][0], stream_runs[stream_key],
                            page_start=stream_key == (0, ())))
                    raw, resources = streams[stream_key]
                    source_font, suggested_family = source_font_info(raw, resources, run.glyphs[0].operator_byte_offset)
                    ownership: dict[str, object] = {}
                    if (not parts['xobj_path'] and parts['annot'] is None and parts['pattern'] is None
                            and parts['charproc'] is None and parts['part'] in managed_parts):
                        identifier = managed_parts[parts['part']]
                        ownership = {'state': 'not_editable', 'reason': 'managed_text_box' if identifier is not None
                                     else 'managed_text_box_unverified'}
                        if identifier is not None:
                            ownership['text_box_id'] = identifier
                    runs.append({"run_id": run.run_id, "text": run.display_text,
                        "search": project_search_text(run.display_text),
                        "box": run_box(run, raw, resources), "state": verdict.state,
                        "reason": verdict.reason, "source_font": source_font,
                        "suggested_font_family": suggested_family,
                        **formatting.get(run.run_id, {}), **ownership})
            box = [float(x) for x in pdf.pages[number].cropbox]
            return {"page": number, "bucket": indexed.bucket, "runs": runs,
                "width": box[2] - box[0], "height": box[3] - box[1],
                "rotation": int(pdf.pages[number].get("/Rotate", 0)), "view_box": box}
        _preflight(pdf)
        if action == 'text-box':
            payload = _text_box_payload(request.get('recipe'))
            if (signed and payload['operation'] != 'list'
                    and request.get('acknowledge_signature') is not True):
                raise WorkerRefusal('SIGNATURE_ACKNOWLEDGEMENT_REQUIRED')
            from engine.text_boxes import TextBoxError, prepare_text_box
            from server.errors import TEXT_BOX_ERROR_CODES
            encrypted = pdf.is_encrypted
            try:
                if payload['operation']=='replace-source':
                    from engine.source_text_box import prepare_source_text_box
                    result=prepare_source_text_box(path,source,payload,Path(scratch)/'source-without-run.pdf',
                                                   password=secret.get_secret_value())
                else:
                    result = prepare_text_box(pdf, source, payload)
            except TextBoxError as error:
                code = error.code
                raise WorkerRefusal(code if isinstance(code, str) and code in TEXT_BOX_ERROR_CODES
                                    else 'WORKER_FAILED') from None
            if payload['operation'] != 'list' and result.get('ok') is True and isinstance(result.get('pdf'), str):
                # These facts come from the opened input; never propagate arbitrary
                # native notice values through the fixed public notice protocol.
                text_box_notices: list[str] = []
                if signed:
                    text_box_notices.append('SIGNATURES_INVALIDATED')
                if encrypted:
                    text_box_notices.append('UNLOCKED_COPY')
                result = {**result, 'notices': text_box_notices}
            return result
        if action == 'export':
            from engine.export.pdf import ExportRefusal, MAX_EXPORT_BYTES, export_pdf
            from engine.export.text import ExportLimitError, export_document_result
            operation = request.get('export_operation')
            downsample = request.get('downsample', False)
            if (operation not in ('compress', 'flatten', 'text', 'markdown', 'html', 'pdfa', 'docx-review', 'docx')
                    or not isinstance(operation, str) or not isinstance(downsample, bool)
                    or (downsample and operation != 'compress')):
                raise WorkerRefusal('EXPORT_OPTIONS_INVALID')
            notices: list[str] = []
            changed_images = 0
            if operation in ('docx-review','docx'):
                try:
                    from engine.export.docx import (DocxRefusal, POLICY_VERSION, prepare_docx,
                                                    serialize_docx, snapshot_digest)
                except ImportError:
                    raise WorkerRefusal('DOCX_UNAVAILABLE') from None
                from engine.blocks import build_document
                try:
                    with RunIndex(path, password=secret.get_secret_value(), include_images=True) as index:
                        snapshot = prepare_docx(build_document(index))
                    source_hash = hashlib.sha256(source).hexdigest()
                    digest = snapshot_digest(snapshot)
                    if operation == 'docx-review':
                        return {'source_sha256':source_hash, 'snapshot_sha256':digest,
                                'policy_version':POLICY_VERSION, 'review':snapshot.review}
                    if (type(request.get('reviewed_policy_version')) is not int
                            or request.get('reviewed_policy_version') != POLICY_VERSION
                            or request.get('reviewed_source_sha256') != source_hash
                            or request.get('reviewed_snapshot_sha256') != digest):
                        raise WorkerRefusal('DOCX_REVIEW_MISMATCH')
                    data = serialize_docx(snapshot)
                except (ExportLimitError, DocumentTooLargeError):
                    raise WorkerRefusal('EXPORT_LIMIT') from None
                except DocxRefusal:
                    raise WorkerRefusal('DOCX_UNSUPPORTED') from None
                if len(data) > MAX_EXPORT_BYTES:
                    raise WorkerRefusal('EXPORT_LIMIT')
                if signed:
                    notices.append('DOCX_SIGNATURES_NOT_PRESERVED')
                if pdf.is_encrypted:
                    notices.append('UNLOCKED_COPY')
                if not snapshot.review['has_text']:
                    notices.append('NO_EXTRACTABLE_TEXT')
                return {'data':base64.b64encode(data).decode('ascii'),
                    'media_type':'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
                    'filename':'document.docx','before_bytes':len(source),'after_bytes':len(data),
                    'notices':notices,'changed_images':0}
            if operation in ('compress', 'flatten', 'pdfa'):
                if signed and request.get('acknowledge_signature') is not True:
                    raise WorkerRefusal('SIGNATURE_ACKNOWLEDGEMENT_REQUIRED')
                if operation == 'pdfa':
                    from engine.export.pdfa import PdfaRefusal, export_pdfa
                    from server.errors import PDFA_REASON_CODES
                    try:
                        archival = export_pdfa(pdf, source)
                    except PdfaRefusal as error:
                        code = next((code for code, reason in PDFA_REASON_CODES.items()
                                     if reason == error.reason_id), 'PDFA_CONTENT_UNSUPPORTED')
                        raise WorkerRefusal(code) from None
                    data = archival.data
                    notices.extend(archival.notices)
                    if pdf.is_encrypted:
                        notices.append('UNLOCKED_COPY')
                else:
                    try:
                        exported = export_pdf(pdf, source, operation, downsample=downsample)
                    except ExportRefusal as error:
                        raise WorkerRefusal(str(error)) from None
                    data = exported.data
                    notices.extend(exported.notices)
                    changed_images = exported.changed_images
                if signed and data != source:
                    notices.append('SIGNATURES_INVALIDATED')
                filename = {'compress': 'compressed.pdf', 'flatten': 'flattened.pdf',
                            'pdfa': 'archival.pdf'}[operation]
                media_type = 'application/pdf'
            else:
                try:
                    with RunIndex(path, password=secret.get_secret_value()) as index:
                        text_result = export_document_result(index, operation)
                except (ExportLimitError, DocumentTooLargeError):
                    raise WorkerRefusal('EXPORT_LIMIT') from None
                data = text_result.text.encode('utf-8')
                if not text_result.has_text:
                    notices.append('NO_EXTRACTABLE_TEXT')
                extension = {'text': 'txt', 'markdown': 'md', 'html': 'html'}[operation]
                filename = 'document.' + extension
                media_type = {'text': 'text/plain', 'markdown': 'text/markdown', 'html': 'text/html'}[operation]
            if len(data) > MAX_EXPORT_BYTES:
                raise WorkerRefusal('EXPORT_LIMIT')
            return {'data': base64.b64encode(data).decode('ascii'), 'media_type': media_type,
                    'filename': filename, 'before_bytes': len(source), 'after_bytes': len(data),
                    'notices': notices, 'changed_images': changed_images}
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
        if action == "plan":
            report = plan_recipe(path, recipe, password=secret.get_secret_value())
        else:
            # Preview must exercise the same splice and layout guards as Apply.
            # Its output stays inside this disposable worker's scratch directory.
            report = apply_recipe(path, recipe, output, password=secret.get_secret_value())
        return {"ok": report.ok, "resolved": [
            {"run_id": resolved.op.run_id, "ok": resolved.ok, "reason": resolved.reason,
             "strategy": resolved.strategy, "delta_pt": resolved.delta_pt}
            for resolved in report.resolved], "pdf": base64.b64encode(output.read_bytes()).decode("ascii")
            if request.get("dry_run") is not True and output.exists() and report.ok else None}


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
        import engine.text_boxes  # noqa: F401
        import engine.source_text_box  # noqa: F401
        import pypdfium2  # type: ignore[import-untyped]  # noqa: F401
        import engine.export.pdf  # noqa: F401
        import engine.export.text  # noqa: F401
        import engine.export.pdfa  # noqa: F401
        try:
            import engine.export.docx  # noqa: F401
        except ImportError:
            pass  # Optional writer removal must not affect other operations.
        from PIL import Image
        Image.init()  # Trusted codec plugins load before irreversible filtering.
        from engine.playa_boundary import PDFSyntaxError
        from server.linux_sandbox import restrict_worker
        restrict_worker()
        raw = sys.stdin.buffer.read(MAX_REQUEST_BYTES + 1)
        if len(raw) > MAX_REQUEST_BYTES:
            raise WorkerRefusal("INVALID_INPUT")
        request: object = json.loads(raw)
        if not isinstance(request, dict):
            raise WorkerRefusal("INVALID_INPUT")
        try:
            result = _execute(request)
        except PDFSyntaxError:
            # Malformed content must refuse the whole operation. The parser's
            # message can contain document bytes, so only return the fixed code.
            raise WorkerRefusal("PDF_INVALID") from None
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

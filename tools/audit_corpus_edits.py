"""Bounded, reproducible edit audit of real PDF files; never changes corpus inputs.

Uses the shipped isolated inspect/page/edit workers, including all refusal guards.
Samples the first three pages and at most three genuine editable runs per document.
Successful output is checked with qpdf/pikepdf and independently with PDFium.
Reports contain identifiers, counts and fixed reasons, never decoded source text.
"""
from __future__ import annotations

import argparse
import base64
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import hashlib
import io
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import unicodedata

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def normalize(text: str) -> str:
    """Ignore extraction whitespace and canonical compatibility ligatures only."""
    return ''.join(unicodedata.normalize('NFKC', text).split())


def pipeline_fingerprint() -> str:
    digest = hashlib.sha256()
    for path in sorted([*ROOT.glob('engine/*.py'), *ROOT.glob('server/*.py')]):
        digest.update(str(path.relative_to(ROOT)).encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()


def text_verdict(before: str, after: str, old: str, new: str) -> str:
    """Prove one replacement anywhere in independent full-page extraction.

    Duplicate source strings are handled by considering each possible occurrence;
    seeing the requested new text elsewhere on the page does not prove success.
    """
    before, after, old, new = map(normalize, (before, after, old, new))
    if not old or old not in before:
        return 'unverifiable_source_text'
    start = before.find(old)
    while start >= 0:
        if before[:start] + new + before[start + len(old):] == after:
            return 'verified'
        start = before.find(old, start + 1)
    return 'wrong_text'


def verified_pair(result: dict, mode: str | None = None) -> bool:
    verified = {}
    for item in result.get('attempts', []):
        if (mode is None or item['mode'] == mode) and item.get('validation', {}).get('independent_text') == 'verified':
            verified.setdefault((item['run_id'], item['mode']), set()).add(item['kind'])
    return any({'identity', 'shorter'} <= kinds for kinds in verified.values())


def pdfium_text(source: bytes, page_number: int, *, render: bool = False) -> str:
    import pypdfium2 as pdfium
    with pdfium.PdfDocument(source) as document:
        page = document[page_number]
        try:
            if render:
                bitmap = page.render(scale=0.25)
                bitmap.close()
            textpage = page.get_textpage()
            try:
                return textpage.get_text_range()
            finally:
                textpage.close()
        finally:
            page.close()


def validate_output(source: bytes, output: bytes, page: int, old: str, new: str,
                    expected_pages: int) -> dict:
    import pikepdf
    result = {'structure': 'unchecked', 'pdfium_render': 'unchecked',
              'independent_text': 'unchecked', 'corrupt': False, 'wrong_text': False}
    try:
        with pikepdf.open(io.BytesIO(output)) as pdf:
            result['output_pages'] = len(pdf.pages)
            result['syntax_warning_count'] = len(pdf.check_pdf_syntax())
            if len(pdf.pages) != expected_pages:
                result.update(structure='page_count_changed', corrupt=True)
                return result
        with tempfile.TemporaryDirectory(prefix='pdf-edit-check-') as scratch:
            path = Path(scratch) / 'output.pdf'
            path.write_bytes(output)
            try:
                checked = subprocess.run(['qpdf', '--check', str(path)],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=20)
                result['qpdf_exit_code'] = checked.returncode
                if checked.returncode not in (0, 3):
                    result.update(structure='qpdf_error', corrupt=True)
                    return result
            except FileNotFoundError:
                result['qpdf_exit_code'] = None
            except subprocess.TimeoutExpired:
                result.update(structure='qpdf_timeout', corrupt=True)
                return result
        result['structure'] = 'valid'
    except Exception as error:
        result.update(structure='pikepdf_error', corrupt=True, exception_type=type(error).__name__)
        return result
    try:
        before = pdfium_text(source, page)
        after = pdfium_text(output, page, render=True)
        result['pdfium_render'] = 'valid'
        result['independent_text'] = text_verdict(before, after, old, new)
        result['source_extracted_chars'] = len(before)
        result['output_extracted_chars'] = len(after)
        result['wrong_text'] = result['independent_text'] == 'wrong_text'
    except Exception as error:
        result.update(pdfium_render='error', corrupt=True, exception_type=type(error).__name__)
    return result


def explicit_family(source: bytes, run: dict) -> dict:
    """Descriptor informs an explicitly labelled substitution, never an auto match."""
    import pikepdf
    from engine.classify_run import stream_bytes_and_resources
    from engine.recipe import active_font_name_and_size
    from engine.run_id import decode_run_id
    serif = None
    try:
        address = decode_run_id(run['run_id'])
        with pikepdf.open(io.BytesIO(source)) as pdf:
            raw, resources = stream_bytes_and_resources(pdf, address['page'],
                address['part'], address['xobj_path'])
            active = active_font_name_and_size(raw, address['byte_offset'])
            if active is not None and resources is not None:
                font = resources.get('/Font', {}).get('/' + active[0].decode('latin-1'))
                descriptor = font.get('/FontDescriptor') if font is not None else None
                if descriptor is None and font is not None and font.get('/DescendantFonts'):
                    descriptor = font['/DescendantFonts'][0].get('/FontDescriptor')
                if descriptor is not None and '/Flags' in descriptor:
                    serif = bool(int(descriptor['/Flags']) & 2)
    except Exception:
        pass
    return {'font_family': 'Serif' if serif else 'Sans', 'descriptor_serif': serif,
            'choice_basis': 'descriptor_flags' if serif is not None else 'explicit_audit_default',
            'manual_substitution': True}


def attempt_edit(source: bytes, run: dict, page: int, text: str, kind: str,
                 page_count: int, worker, *, family: dict | None = None) -> dict:
    operation = {'run_id': run['run_id'], 'new_text': text}
    if family:
        operation['style'] = {'font_family': family['font_family']}
    recipe = json.dumps([operation]).encode()
    start = time.monotonic()
    preview = worker('edit', source, recipe=recipe, dry_run=True)
    outcome = worker('edit', source, recipe=recipe, acknowledge_signature=False)
    resolved_ok = sum(item.get('ok') is True for item in outcome.get('resolved', []))
    result = {'kind': kind, 'page': page, 'run_id': run['run_id'],
              'source_chars': len(run['text']), 'replacement_chars': len(text),
              'mode': 'manual_substitution' if family else 'automatic',
              'elapsed_seconds': round(time.monotonic() - start, 3),
              'worker_error': outcome.get('error'), 'report_ok': outcome.get('ok'),
              'preview_ok': preview.get('ok'), 'preview_error': preview.get('error'),
              'preview_refusals': [item.get('reason') for item in preview.get('resolved', []) if not item.get('ok')],
              'preview_apply_agree': preview.get('resolved') == outcome.get('resolved'),
              'application_count': resolved_ok if outcome.get('ok') is True and outcome.get('pdf') else 0,
              'resolved_ok_count': resolved_ok,
              'resolved_count': len(outcome.get('resolved', [])),
              'refusal_reasons': [item.get('reason') for item in outcome.get('resolved', []) if not item.get('ok')],
              'strategies': [item.get('strategy') for item in outcome.get('resolved', [])],
              'output_present': bool(outcome.get('pdf')), 'corrupt': False, 'wrong_text': False}
    if family:
        result['explicit_font_choice'] = family
    if outcome.get('ok') is True:
        if not isinstance(outcome.get('pdf'), str):
            result.update(corrupt=True, validation={'structure': 'missing_output'})
        else:
            try:
                output = base64.b64decode(outcome['pdf'], validate=True)
                result['output_bytes'] = len(output)
                validation = validate_output(source, output, page, run['text'], text, page_count)
                result.update(validation=validation, corrupt=validation['corrupt'],
                              wrong_text=validation['wrong_text'])
            except Exception as error:
                result.update(corrupt=True, validation={'structure': 'invalid_output',
                                                       'exception_type': type(error).__name__})
    return result


def audit_file(path: Path, *, max_pages: int = 3, max_candidates: int = 3,
               worker=None, progress=lambda _result: None, extra_pages: tuple[int, ...] = ()) -> dict:
    if worker is None:
        from server.isolation import run_worker
        worker = run_worker
    started = time.monotonic()
    source = path.read_bytes()
    digest = hashlib.sha256(source).hexdigest()
    result = {'filename': path.name, 'source_sha256': digest, 'source_bytes': len(source),
              'started_utc': datetime.now(timezone.utc).isoformat(),
              'pipeline_sha256': pipeline_fingerprint(),
              'requested_extra_pages': list(extra_pages),
              'pages_sampled': [], 'page_errors': [], 'page_buckets': {},
              'run_states': {}, 'run_refusals': {}, 'candidates_tested': 0, 'attempts': [],
              'status': 'in_progress'}
    progress(result)
    inspected = worker('inspect', source)
    result['inspect_error'] = inspected.get('error')
    if inspected.get('error'):
        result['status'] = 'inspect_error'
        result['source_unchanged'] = hashlib.sha256(path.read_bytes()).hexdigest() == digest
        result['elapsed_seconds'] = round(time.monotonic() - started, 3)
        return result
    count = int(inspected['page_count'])
    result.update(page_count=count, signed=inspected.get('signed', False))
    progress(result)
    states, refusals = Counter(), Counter()
    sampled_pages = list(dict.fromkeys([*range(min(count, max_pages)), *extra_pages]))
    for number in sampled_pages:
        data = worker('page', source, page=number)
        result['pages_sampled'].append(number)
        if data.get('error'):
            result['page_errors'].append({'page': number, 'error': data['error']})
            progress(result)
            continue
        result['page_buckets'][str(number)] = data.get('bucket')
        runs = data.get('runs', [])
        states.update(run.get('state', 'unknown') for run in runs)
        refusals.update(run.get('reason') for run in runs if run.get('reason'))
        # Prefer independently observable, useful strings; retain genuine run IDs.
        candidates = [run for run in runs if run.get('state') in
            ('editable_original', 'editable_substitution') and
            len(normalize(run.get('text', ''))) >= 2 and
            not any(unicodedata.category(c) == 'Cc' for c in run.get('text', ''))]
        candidates.sort(key=lambda run: (-min(len(run['text']), 80), run['run_id']))
        for run in candidates:
            if result['candidates_tested'] >= max_candidates:
                break
            result['candidates_tested'] += 1
            text = run['text']
            # Keep source characters: no novel script/glyph or arbitrary edit input.
            shorter = text[:max(1, min(5, len(text) // 2))].rstrip() or text[:1]
            pair = []
            for kind, replacement in (('identity', text), ('shorter', shorter)):
                item = attempt_edit(source, run, number, replacement, kind, count, worker)
                pair.append(item)
                result['attempts'].append(item)
                progress(result)
            # Only an unmapped font allows this separate, explicitly chosen face test.
            unmapped = any(isinstance(reason, str) and (reason in {
                'font_not_in_substitution_table', 'source_font_not_mapped', 'font_not_mapped',
                'unmapped_font'} or reason.startswith(('unmapped-base-font:', 'no mapping table entry for BaseFont ')))
                for item in pair for reason in item['refusal_reasons'])
            if unmapped:
                family = explicit_family(source, run)
                pair = []
                for kind, replacement in (('identity', text), ('shorter', shorter)):
                    item = attempt_edit(source, run, number, replacement, kind, count, worker, family=family)
                    pair.append(item)
                    result['attempts'].append(item)
                    progress(result)
            if all(item['report_ok'] is True and not item['corrupt'] and not item['wrong_text']
                   for item in pair):
                break
            if any(item['worker_error'] in {'WORKER_TIMEOUT', 'WORKER_FAILED', 'DOCUMENT_LIMIT'} for item in pair):
                break
        if result['attempts'] or result['candidates_tested'] >= max_candidates:
            break
    result['run_states'], result['run_refusals'] = dict(states), dict(refusals)
    attempts = result['attempts']
    if any(item['corrupt'] for item in attempts):
        status = 'corrupt_output'
    elif any(item['wrong_text'] for item in attempts):
        status = 'wrong_text'
    elif any(item['report_ok'] is True and item.get('validation', {}).get('independent_text') == 'verified'
             for item in attempts):
        status = 'edited_verified' if verified_pair(result) else 'partially_edited_verified'
    elif any(item['report_ok'] is True for item in attempts):
        status = 'edited_text_unverifiable'
    elif attempts:
        status = 'edit_refused_or_failed'
    elif result['page_errors']:
        status = 'page_error'
    else:
        status = 'no_editable_candidate_in_sample'
    result.update(status=status, elapsed_seconds=round(time.monotonic() - started, 3),
                  source_unchanged=hashlib.sha256(path.read_bytes()).hexdigest() == digest,
                  pipeline_sha256_after=pipeline_fingerprint())
    result['pipeline_changed_during_file'] = result['pipeline_sha256'] != result['pipeline_sha256_after']
    if not result['source_unchanged']:
        result['status'] = 'source_mutated'
    progress(result)
    return result


def run_file_process(path: Path, max_pages: int, max_candidates: int, timeout: float,
                     extra_pages: tuple[int, ...] = ()) -> dict:
    with tempfile.TemporaryDirectory(prefix='pdf-audit-evidence-') as scratch:
        return _run_file_process(path, max_pages, max_candidates, timeout, Path(scratch) / 'checkpoint.json', extra_pages)


def _run_file_process(path: Path, max_pages: int, max_candidates: int, timeout: float,
                      checkpoint: Path, extra_pages: tuple[int, ...] = ()) -> dict:
    command = [sys.executable, str(Path(__file__).resolve()), '--file-worker', str(path),
               '--max-pages', str(max_pages), '--max-candidates', str(max_candidates),
               '--checkpoint', str(checkpoint)]
    for number in extra_pages:
        command.extend(['--extra-page', f'{path.name}:{number}'])
    started = time.monotonic()
    environment = dict(os.environ, TMPDIR=str(checkpoint.parent), TEMP=str(checkpoint.parent),
                       TMP=str(checkpoint.parent))
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                               start_new_session=True, cwd=ROOT, env=environment)
    try:
        output, _ = process.communicate(timeout=timeout)
        if process.returncode:
            return {'filename': path.name, 'status': 'audit_process_error',
                    'returncode': process.returncode, 'attempts': []}
        return json.loads(output)
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGKILL)
        process.communicate()
        result = json.loads(checkpoint.read_text()) if checkpoint.exists() else {'filename': path.name, 'attempts': []}
        result.update(status='audit_file_timeout', elapsed_seconds=round(time.monotonic() - started, 3))
        if result.get('source_sha256'):
            result['source_unchanged'] = hashlib.sha256(path.read_bytes()).hexdigest() == result['source_sha256']
        return result
    except (ValueError, OSError) as error:
        return {'filename': path.name, 'status': 'audit_process_error', 'attempts': [],
                'exception_type': type(error).__name__}


def summarize(results: list[dict]) -> dict:
    attempts = [item for result in results for item in result.get('attempts', [])]
    return {'files': len(results), 'file_statuses': dict(Counter(item['status'] for item in results)),
            'pages_sampled': sum(len(item.get('pages_sampled', [])) for item in results),
            'attempts': len(attempts), 'applications_reported': sum(item['application_count'] for item in attempts),
            'outputs': sum(item['output_present'] for item in attempts),
            'independently_verified_outputs': sum(item.get('validation', {}).get('independent_text') == 'verified' for item in attempts),
            'corrupt_outputs': sum(item['corrupt'] for item in attempts),
            'wrong_text_outputs': sum(item['wrong_text'] for item in attempts),
            'files_automatic_pair_verified': sum(verified_pair(item, 'automatic') for item in results),
            'files_manual_pair_verified': sum(verified_pair(item, 'manual_substitution') for item in results),
            'files_with_refusals': sum(any(item['refusal_reasons'] for item in result.get('attempts', [])) for result in results),
            'preview_apply_disagreements': sum(not item.get('preview_apply_agree', True) for item in attempts),
            'pipeline_revisions': dict(Counter(item.get('pipeline_sha256', 'not_recorded') for item in results)),
            'files_changed_pipeline_mid_audit': sum(item.get('pipeline_changed_during_file', False) for item in results),
            'worker_errors': dict(Counter(item['worker_error'] for item in attempts if item['worker_error'])),
            'refusal_reasons': dict(Counter(reason for item in attempts for reason in item['refusal_reasons'])),
            'manual_substitution_attempts': sum(item['mode'] == 'manual_substitution' for item in attempts)}


def write_report(path: Path, report: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(report, indent=2, sort_keys=True) + '\n')
    temporary.replace(path)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--corpus', type=Path, default=ROOT / 'corpus/public')
    parser.add_argument('--output', type=Path, default=ROOT / '.planning/audits/corpus-edits-2026-10-22.json')
    parser.add_argument('--only', action='append', default=[], help='Exact filename; repeat for targeted reruns')
    parser.add_argument('--extra-page', action='append', default=[], metavar='FILENAME:INDEX',
                        help='One additional zero-based page per file, e.g. a late editable page found by the read audit')
    parser.add_argument('--max-pages', type=int, default=3)
    parser.add_argument('--max-candidates', type=int, default=3)
    parser.add_argument('--concurrency', type=int, choices=(1, 2), default=2)
    parser.add_argument('--file-timeout', type=float, default=240)
    parser.add_argument('--file-worker', type=Path, help=argparse.SUPPRESS)
    parser.add_argument('--checkpoint', type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args()
    if not 1 <= args.max_pages <= 3 or not 1 <= args.max_candidates <= 3 or args.file_timeout <= 0:
        parser.error('page/candidate samples must be 1..3 and timeout positive')
    extra_pages = {}
    for item in args.extra_page:
        try:
            name, index = item.rsplit(':', 1)
            number = int(index)
            if number < 0 or name in extra_pages:
                raise ValueError
            extra_pages[name] = (number,)
        except ValueError:
            parser.error('--extra-page requires FILENAME:nonnegative_zero_based_index, once per file')
    if args.file_worker:
        try:
            progress = (lambda result: write_report(args.checkpoint, result)) if args.checkpoint else (lambda _result: None)
            result = audit_file(args.file_worker, max_pages=args.max_pages, max_candidates=args.max_candidates,
                                progress=progress, extra_pages=extra_pages.get(args.file_worker.name, ()))
        except Exception as error:
            result = {'filename': args.file_worker.name, 'status': 'audit_exception',
                      'exception_type': type(error).__name__, 'attempts': []}
        print(json.dumps(result))
        return 0
    # Actual filesystem inventory; manifest labels cannot manufacture coverage.
    paths = list(args.corpus.glob('*.pdf'))
    if set(extra_pages) - {path.name for path in paths}:
        parser.error('--extra-page filename is absent from corpus')
    if args.output.resolve().is_relative_to(args.corpus.resolve()):
        parser.error('audit reports must be outside the immutable corpus directory')
    if args.only:
        missing = sorted(set(args.only) - {path.name for path in paths})
        if missing:
            parser.error('unknown corpus filenames: ' + ', '.join(missing))
        paths = [path for path in paths if path.name in args.only]
    # Object-level page counts only: no content decode for this scheduling hint.
    import pikepdf
    def order(path: Path) -> tuple:
        try:
            with pikepdf.open(path) as pdf:
                return len(pdf.pages), path.name
        except Exception:
            return 0, path.name
    page_counts = {path.name: order(path)[0] for path in paths}
    paths.sort(key=lambda path: (page_counts[path.name], path.name))
    report = {'created_utc': datetime.now(timezone.utc).isoformat(), 'inventory_files': len(paths),
              'inventory_pages': sum(max(0, count) for count in page_counts.values()),
              'auditor_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              'complete': False,
              'sampling': {'max_first_pages': args.max_pages, 'max_candidate_runs': args.max_candidates,
                           'additional_zero_based_pages': extra_pages,
                           'stop_after_successful_pair': True, 'all_pages_edit_tested': False},
              'pipeline': 'server.isolation.run_worker inspect/page/edit; original source for each attempt',
              'verification': 'pikepdf syntax, qpdf --check, PDFium edited-page render and full-page normalized text replacement',
              'results': [], 'summary': {}}
    write_report(args.output, report)
    with ThreadPoolExecutor(max_workers=args.concurrency) as executor:
        pending = {executor.submit(run_file_process, path, args.max_pages, args.max_candidates,
                                   args.file_timeout, extra_pages.get(path.name, ())): path for path in paths}
        for future in as_completed(pending):
            result = future.result()
            report['results'].append(result)
            report['results'].sort(key=lambda item: item['filename'])
            report['summary'] = summarize(report['results'])
            write_report(args.output, report)
            print(f"{len(report['results'])}/{len(paths)} {result['filename']} {result['status']}", flush=True)
    report.update(complete=True, completed_utc=datetime.now(timezone.utc).isoformat())
    write_report(args.output, report)
    print(json.dumps(report['summary'], sort_keys=True), flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

"""Audit evidence must distinguish refusals, unchanged inputs and wrong output."""
import base64
import io
import json
from pathlib import Path
import subprocess
import sys

import pikepdf

from tools.audit_corpus_edits import (audit_file, explicit_family, summarize,
                                      text_verdict, validate_output, write_report)
from tools.build_security_fixtures import text_pdf


def test_text_check_requires_one_actual_page_replacement() -> None:
    assert text_verdict('alpha beta alpha', 'alpha beta omega', 'alpha', 'omega') == 'verified'
    assert text_verdict('alpha omega', 'alpha omega', 'alpha', 'omega') == 'wrong_text'
    assert text_verdict('alpha beta', 'omega', 'alpha', 'omega') == 'wrong_text'
    assert text_verdict('alpha beta', 'alpha beta', 'missing', 'new') == 'unverifiable_source_text'


def test_text_check_tolerates_pdfium_whitespace_and_ligature_expansion() -> None:
    assert text_verdict('ofﬁce\r\nnotes', 'office notes', 'office', 'office') == 'verified'


def test_validation_detects_structure_and_independent_text_corruption() -> None:
    source = text_pdf(b'Original marker')
    broken = validate_output(source, b'not a pdf', 0, 'Original marker', 'Tiny', 1)
    assert broken['corrupt'] is True
    unchanged = validate_output(source, source, 0, 'Original marker', 'Tiny', 1)
    assert unchanged['structure'] == 'valid'
    assert unchanged['pdfium_render'] == 'valid'
    assert unchanged['wrong_text'] is True
    assert unchanged['corrupt'] is False


def test_successful_real_worker_audit_preserves_source_and_omits_document_text(tmp_path: Path) -> None:
    source = text_pdf(b'Private decoded canary')
    path = tmp_path / 'fixture.pdf'
    path.write_bytes(source)
    result = audit_file(path)
    assert result['status'] == 'edited_verified'
    assert result['source_unchanged'] is True
    assert path.read_bytes() == source
    assert len(result['attempts']) == 2
    assert all(item['application_count'] == 1 for item in result['attempts'])
    assert all(item['preview_apply_agree'] for item in result['attempts'])
    assert all(item['validation']['independent_text'] == 'verified' for item in result['attempts'])
    assert 'Private decoded canary' not in json.dumps(result)


def test_worker_refusals_are_not_counted_as_applications(tmp_path: Path) -> None:
    path = tmp_path / 'fixture.pdf'
    source = text_pdf()
    path.write_bytes(source)
    def refused(action, _source, **_options):
        if action == 'inspect':
            return {'page_count': 1}
        if action == 'page':
            return {'bucket': 'editable', 'runs': [{'run_id': 'opaque', 'text': 'Secret phrase',
                'state': 'editable_original'}]}
        # A successfully resolved entry in a refused transaction was never applied.
        return {'ok': False, 'resolved': [{'ok': True, 'reason': None}], 'pdf': None}
    result = audit_file(path, worker=refused)
    assert result['status'] == 'edit_refused_or_failed'
    assert summarize([result])['applications_reported'] == 0
    assert result['source_unchanged'] is True
    assert path.read_bytes() == source
    assert 'Secret phrase' not in json.dumps(result)


def test_page_errors_and_no_candidate_are_honest_and_bounded(tmp_path: Path) -> None:
    path = tmp_path / 'fixture.pdf'
    path.write_bytes(text_pdf())
    calls = []
    def failed(action, _source, **options):
        calls.append((action, options.get('page')))
        return {'page_count': 100} if action == 'inspect' else {'error': 'DOCUMENT_LIMIT'}
    result = audit_file(path, worker=failed)
    assert result['status'] == 'page_error'
    assert result['pages_sampled'] == [0, 1, 2]
    assert result['attempts'] == []
    assert len(calls) == 4


def test_unknown_font_manual_choice_is_disclosed_and_uses_descriptor(tmp_path: Path) -> None:
    source = text_pdf(b'Private unknown font canary')
    with pikepdf.open(io.BytesIO(source)) as pdf:
        font = pdf.pages[0].Resources.Font.F1
        font.BaseFont = pikepdf.Name('/CustomPrivateFace')
        font.FontDescriptor = pikepdf.Dictionary(Flags=2, Type=pikepdf.Name.FontDescriptor)
        output = io.BytesIO()
        pdf.save(output)
        source = output.getvalue()
    path = tmp_path / 'fixture.pdf'
    path.write_bytes(source)
    result = audit_file(path)
    manual = [item for item in result['attempts'] if item['mode'] == 'manual_substitution']
    assert len(manual) == 2
    assert manual[0]['explicit_font_choice']['font_family'] == 'Serif'
    assert manual[0]['explicit_font_choice']['choice_basis'] == 'descriptor_flags'
    assert all(item['validation']['independent_text'] == 'verified' for item in manual)
    assert result['source_unchanged'] is True


def test_report_roundtrip_keeps_completed_and_failed_files(tmp_path: Path) -> None:
    report = {'results': [{'filename': 'a.pdf', 'status': 'inspect_error', 'attempts': []},
                          {'filename': 'b.pdf', 'status': 'no_editable_candidate_in_sample', 'attempts': []}]}
    report['summary'] = summarize(report['results'])
    output = tmp_path / 'nested/report.json'
    write_report(output, report)
    assert json.loads(output.read_text()) == report
    assert report['summary']['files'] == 2
    assert report['summary']['applications_reported'] == 0
    assert not output.with_suffix('.json.tmp').exists()


def test_cli_refuses_to_overwrite_corpus_input(tmp_path: Path) -> None:
    path = tmp_path / 'fixture.pdf'
    source = text_pdf()
    path.write_bytes(source)
    completed = subprocess.run([sys.executable, '-m', 'tools.audit_corpus_edits',
        '--corpus', str(tmp_path), '--output', str(path)], capture_output=True)
    assert completed.returncode == 2
    assert path.read_bytes() == source


def test_summary_pair_coverage_requires_both_edits_on_same_run() -> None:
    base = {'application_count': 1, 'output_present': True, 'corrupt': False,
            'wrong_text': False, 'worker_error': None, 'refusal_reasons': [],
            'mode': 'automatic', 'validation': {'independent_text': 'verified'}}
    result = {'status': 'edited_verified', 'attempts': [
        dict(base, run_id='one', kind='identity'), dict(base, run_id='two', kind='shorter')]}
    assert summarize([result])['files_automatic_pair_verified'] == 0
    result['attempts'].append(dict(base, run_id='one', kind='shorter'))
    assert summarize([result])['files_automatic_pair_verified'] == 1


def test_late_page_sampling_is_explicit_and_does_not_claim_whole_document(tmp_path: Path) -> None:
    path = tmp_path / 'fixture.pdf'
    path.write_bytes(text_pdf())
    def empty(action, _source, **options):
        if action == 'inspect':
            return {'page_count': 10}
        return {'bucket': 'outlined' if options['page'] < 3 else 'empty', 'runs': []}
    result = audit_file(path, worker=empty, extra_pages=(5,))
    assert result['pages_sampled'] == [0, 1, 2, 5]
    assert result['requested_extra_pages'] == [5]
    assert result['status'] == 'no_editable_candidate_in_sample'

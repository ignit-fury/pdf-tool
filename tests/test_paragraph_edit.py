import pytest

from engine.paragraph_edit import line_ops, line_segments, rebuild_text
from engine.records import RunRecord

SEGS = [('r1', 'Hello'), (None, ' '), ('r2', 'bold'), (None, ' '), ('r3', 'world')]


@pytest.mark.parametrize('new,expected', [
    ('Hello bold world', []),
    ('Hallo bold world', [('r1', 'Hallo')]),
    ('Hello BOLD world', [('r2', 'BOLD')]),
    ('Hello bold world!', [('r3', 'world!')]),
    ('Hello there world', [('r2', 'there')]),
    ('Hi world', [('r1', 'Hi'), ('r2', '')]),          # r3 untouched keeps its style
    ('Hello  bold world', [('r2', ' bold')]),
    ('', [('r1', ''), ('r2', ''), ('r3', '')]),
])
def test_line_ops_touch_only_changed_runs(new, expected):
    assert line_ops(SEGS, new) == expected


def test_line_ops_without_runs_is_none():
    assert line_ops([(None, ' ')], 'x') is None


def test_line_ops_keeps_graphemes_whole():
    assert line_ops([('r1', 'café')], 'cafés') == [('r1', 'cafés')]


def test_line_ops_gap_only_deletion_needs_rebuild():
    assert line_ops(SEGS, 'Hellobold world') is None


def test_line_ops_combining_guard_holds_base_letter_with_decomposed_mark():
    # change starts at U+0301; the guard steps back to the base 'e'
    assert line_ops([('r1', 'café')], 'cafè') == [('r1', 'cafè')]


def test_line_segments_gap_override_and_leading_space():
    runs = [RunRecord('a', [], 'Hel', 1), RunRecord('b', [], 'lo', 1)]
    assert line_segments(runs, {}) == [('a', 'Hel'), (None, ' '), ('b', 'lo')]
    assert line_segments(runs, {'a': 'HEL'}) == [('a', 'HEL'), (None, ' '), ('b', 'lo')]
    runs = [RunRecord('a', [], 'Hel', 1), RunRecord('b', [], ' lo', 1)]
    assert line_segments(runs, {}) == [('a', 'Hel'), ('b', ' lo')]


def test_rebuild_text_joins_soft_wraps_with_spaces_and_keeps_new_breaks():
    assert rebuild_text(2, ['Left first longer', 'Left second']) == 'Left first longer Left second'
    assert rebuild_text(2, ['Left', 'first', 'Left second']) == 'Left\nfirst\nLeft second'


import base64
from pathlib import Path

import pikepdf
import pypdfium2 as pdfium


def two_line_pdf(path: Path):
    with pikepdf.Pdf.new() as pdf:
        page = pdf.add_blank_page(page_size=(400, 400))
        page.obj.Resources = pikepdf.Dictionary(Font=pikepdf.Dictionary(F1=pdf.make_indirect(
            pikepdf.Dictionary(Type=pikepdf.Name.Font, Subtype=pikepdf.Name.Type1, BaseFont=pikepdf.Name.Helvetica))))
        page.obj.Contents = pdf.make_stream(b'BT /F1 12 Tf 30 340 Td (First line here) Tj ET\n'
                                            b'BT /F1 12 Tf 30 326 Td (Second line here) Tj ET')
        pdf.save(path)
    from engine.index import RunIndex
    from engine.paragraphs import page_paragraphs
    with RunIndex(path) as index:
        return path.read_bytes(), next(p for p in page_paragraphs(0, index.page(0)) if len(p.lines) == 2)


def text_of(b64: str) -> str:
    with pdfium.PdfDocument(base64.b64decode(b64)) as pdf:
        page = pdf[0].get_textpage()
        try:
            return page.get_text_range()
        finally:
            page.close()


def payload(paragraph, lines, **extra):
    return {'operation': 'replace-paragraph', 'paragraph_id': paragraph.paragraph_id,
            'source_run_ids': list(paragraph.run_ids), 'page_index': 0, 'lines': lines,
            'style': {}, 'recipe': [], 'allow_rebuild': False,
            'run_styles': {i: {'font_family': 'Sans', 'font_size': 12} for i in paragraph.run_ids},
            'rect': {'left': 30, 'top': 48, 'width': 200, 'height': 28}, **extra}


def test_styled_runs_keep_each_words_style():
    from engine.paragraph_edit import styled_runs
    S = {'a': {}, 'b': {'bold': True}}
    one = [[('a', 'Hello'), (None, ' '), ('b', 'bold')]]
    assert styled_runs(one, 'Hellobold', S) == [{'text': 'Hello', 'style': {}}, {'text': 'bold', 'style': {'bold': True}}]
    assert styled_runs(one, 'Hello bold!', S) == [{'text': 'Hello ', 'style': {}}, {'text': 'bold!', 'style': {'bold': True}}]
    assert styled_runs(one, 'Hi bold', S) == [{'text': 'Hi ', 'style': {}}, {'text': 'bold', 'style': {'bold': True}}]
    two = [[('a', 'First')], [('b', 'Second')]]
    assert styled_runs(two, 'First more Second', S) == [{'text': 'First more ', 'style': {}}, {'text': 'Second', 'style': {'bold': True}}]
    assert styled_runs(two, 'First\nSecond', S) == [{'text': 'First\n', 'style': {}}, {'text': 'Second', 'style': {'bold': True}}]
    assert styled_runs(one, '', S) == []


def test_gap_deletion_rebuild_keeps_both_styles(tmp_path):
    from engine.paragraph_edit import prepare_paragraph_edit
    path = tmp_path / 's.pdf'; source, p = two_line_pdf(path)
    a, b = p.lines[0][0].run_id, p.lines[1][0].run_id
    styles = {a: {'font_family': 'Sans', 'font_size': 12}, b: {'font_family': 'Sans', 'font_size': 12, 'bold': True}}
    # Joining the two lines into one changes the line count, so the paragraph is rebuilt.
    result = prepare_paragraph_edit(path, source, payload(p, ['First line here Second line here'],
                                                          allow_rebuild=True, run_styles=styles), tmp_path)
    assert result['plan'] == 'rebuild'
    assert [r['style'].get('bold', False) for r in result['boxes'][0]['runs']] == [False, True]


def test_small_edit_uses_line_plan(tmp_path):
    from engine.paragraph_edit import prepare_paragraph_edit
    path = tmp_path / 's.pdf'; source, p = two_line_pdf(path)
    result = prepare_paragraph_edit(path, source, payload(p, ['First line here', 'Second line hers']), tmp_path)
    assert result['plan'] == 'lines'
    assert result['recipe'] == [{'run_id': p.lines[1][0].run_id, 'new_text': 'Second line hers'}]
    assert 'Second line hers' in text_of(result['pdf'])
    assert path.read_bytes() == source


def test_overflow_needs_consent_then_rebuilds(tmp_path):
    from engine.paragraph_edit import prepare_paragraph_edit
    from engine.text_boxes import TextBoxError
    path = tmp_path / 's.pdf'; source, p = two_line_pdf(path)
    long = ['First line here with a great deal of extra words added', 'Second line here']
    with pytest.raises(TextBoxError, match='PARAGRAPH_NEEDS_REBUILD'):
        prepare_paragraph_edit(path, source, payload(p, long), tmp_path)
    result = prepare_paragraph_edit(path, source, payload(p, long, allow_rebuild=True), tmp_path)
    assert result['plan'] == 'rebuild' and 'great deal' in text_of(result['pdf'])


def test_added_line_rebuilds_with_explicit_break(tmp_path):
    from engine.paragraph_edit import prepare_paragraph_edit
    path = tmp_path / 's.pdf'; source, p = two_line_pdf(path)
    result = prepare_paragraph_edit(path, source, payload(p, ['First', 'line here', 'Second line here'], allow_rebuild=True), tmp_path)
    assert result['plan'] == 'rebuild'

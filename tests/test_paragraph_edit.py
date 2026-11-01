import base64
import io
from pathlib import Path

import pikepdf
import pypdfium2 as pdfium
import pytest

from engine.index import RunIndex
from engine.paragraph_edit import line_ops, line_segments, prepare_paragraph_edit, rebuild_text, styled_runs
from engine.paragraphs import page_paragraphs
from engine.records import RunRecord
from engine.text_boxes import TextBoxError

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


def two_line_pdf(path: Path):
    with pikepdf.Pdf.new() as pdf:
        page = pdf.add_blank_page(page_size=(400, 400))
        page.obj.Resources = pikepdf.Dictionary(Font=pikepdf.Dictionary(F1=pdf.make_indirect(
            pikepdf.Dictionary(Type=pikepdf.Name.Font, Subtype=pikepdf.Name.Type1, BaseFont=pikepdf.Name.Helvetica))))
        page.obj.Contents = pdf.make_stream(b'BT /F1 12 Tf 30 340 Td (First line here) Tj ET\n'
                                            b'BT /F1 12 Tf 30 326 Td (Second line here) Tj ET')
        pdf.save(path)
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
    S = {'a': {}, 'b': {'bold': True}}
    one = [[('a', 'Hello'), (None, ' '), ('b', 'bold')]]
    assert styled_runs(one, 'Hellobold', S) == [{'text': 'Hello', 'style': {}}, {'text': 'bold', 'style': {'bold': True}}]
    assert styled_runs(one, 'Hello bold!', S) == [{'text': 'Hello ', 'style': {}}, {'text': 'bold!', 'style': {'bold': True}}]
    assert styled_runs(one, 'Hi bold', S) == [{'text': 'Hi ', 'style': {}}, {'text': 'bold', 'style': {'bold': True}}]
    two = [[('a', 'First')], [('b', 'Second')]]
    assert styled_runs(two, 'First more Second', S) == [{'text': 'First more ', 'style': {}}, {'text': 'Second', 'style': {'bold': True}}]
    assert styled_runs(two, 'First\nSecond', S) == [{'text': 'First\n', 'style': {}}, {'text': 'Second', 'style': {'bold': True}}]
    assert styled_runs(one, '', S) == []
    assert styled_runs(one, 'Hello BOLD', S) == [{'text': 'Hello ', 'style': {}}, {'text': 'BOLD', 'style': {'bold': True}}]
    assert styled_runs(two, 'First Other', S) == [{'text': 'First ', 'style': {}}, {'text': 'Other', 'style': {'bold': True}}]


def test_gap_deletion_rebuild_keeps_both_styles(tmp_path):
    path = tmp_path / 's.pdf'; source, p = two_line_pdf(path)
    a, b = p.lines[0][0].run_id, p.lines[1][0].run_id
    styles = {a: {'font_family': 'Sans', 'font_size': 12}, b: {'font_family': 'Sans', 'font_size': 12, 'bold': True}}
    # Joining the two lines into one changes the line count, so the paragraph is rebuilt.
    result = prepare_paragraph_edit(path, source, payload(p, ['First line here Second line here'],
                                                          allow_rebuild=True, run_styles=styles), tmp_path)
    assert result['plan'] == 'rebuild'
    assert [r['style'].get('bold', False) for r in result['boxes'][0]['runs']] == [False, True]


def test_rebuild_keeps_each_runs_own_family(tmp_path):
    path = tmp_path / 's.pdf'; source, p = two_line_pdf(path)
    a, b = p.lines[0][0].run_id, p.lines[1][0].run_id
    styles = {a: {'font_family': 'Sans', 'font_size': 12}, b: {'font_family': 'Serif', 'font_size': 12}}
    result = prepare_paragraph_edit(path, source, payload(p, ['First line here Second line here'],
                                                          allow_rebuild=True, run_styles=styles), tmp_path)
    assert result['plan'] == 'rebuild'
    assert [r['style']['font_family'] for r in result['boxes'][0]['runs']] == ['Sans', 'Serif']


def test_small_edit_uses_line_plan(tmp_path):
    path = tmp_path / 's.pdf'; source, p = two_line_pdf(path)
    result = prepare_paragraph_edit(path, source, payload(p, ['First line here', 'Second line hers']), tmp_path)
    assert result['plan'] == 'lines'
    assert result['recipe'] == [{'run_id': p.lines[1][0].run_id, 'new_text': 'Second line hers'}]
    assert 'Second line hers' in text_of(result['pdf'])
    assert path.read_bytes() == source


def test_overflow_rebuilds_without_consent(tmp_path):
    path = tmp_path / 's.pdf'; source, p = two_line_pdf(path)
    long = ['First line here with a great deal of extra words added', 'Second line here']
    result = prepare_paragraph_edit(path, source, payload(p, long), tmp_path)  # allow_rebuild False is ignored
    assert result['plan'] == 'rebuild' and 'great deal' in text_of(result['pdf'])
    assert result['pushed'] == 0  # nothing below to move
    assert path.read_bytes() == source


def neighbor_pdf(path: Path, footer: bool = False, box_below: bool = False, neighbor_y: int = 305):
    with pikepdf.Pdf.new() as pdf:
        page = pdf.add_blank_page(page_size=(400, 400))
        page.obj.Resources = pikepdf.Dictionary(Font=pikepdf.Dictionary(F1=pdf.make_indirect(
            pikepdf.Dictionary(Type=pikepdf.Name.Font, Subtype=pikepdf.Name.Type1, BaseFont=pikepdf.Name.Helvetica))))
        page.obj.Contents = pdf.make_stream(b'BT /F1 12 Tf 30 375 Td (Header above) Tj ET\n'
                                            b'BT /F1 12 Tf 30 340 Td (First line here) Tj ET\n'
                                            b'BT /F1 12 Tf 30 326 Td (Second line here) Tj ET\n'
                                            b'BT /F1 12 Tf 30 %d Td (Keep neighbor) Tj ET' % neighbor_y
                                            + (b'\nBT /F1 12 Tf 30 8 Td (Footer) Tj ET' if footer else b''))
        pdf.save(path)
    if box_below:
        from engine.text_boxes import prepare_text_box
        with pikepdf.open(path) as pdf:
            made = prepare_text_box(pdf, path.read_bytes(), {'operation': 'upsert', 'page_index': 0, 'text': 'Boxed note',
                'rect': {'left': 30, 'top': 200, 'width': 150, 'height': 20}, 'style': {'font_family': 'Sans'}})
        path.write_bytes(base64.b64decode(made['pdf']))
    with RunIndex(path) as index:
        return path.read_bytes(), next(p for p in page_paragraphs(0, index.page(0)) if len(p.lines) == 2)


def top_of(data: bytes, word: str) -> float:
    with pdfium.PdfDocument(data) as pdf:
        page = pdf[0]; text = page.get_textpage()
        try:
            start = text.get_text_range().index(word)
            return text.get_charbox(start)[3]
        finally:
            text.close(); page.close()


LONG = ['First line here with a great deal of extra words added to it so that it wraps', 'Second line here']


def test_long_edit_pushes_the_neighbor_down(tmp_path):
    path = tmp_path / 's.pdf'; source, p = neighbor_pdf(path)
    result = prepare_paragraph_edit(path, source, payload(p, LONG), tmp_path)
    assert result['ok'] and result['plan'] == 'rebuild' and result['pushed'] > 0
    pdf = base64.b64decode(result['pdf'])
    assert 'great deal' in text_of(result['pdf']) and 'Keep neighbor' in text_of(result['pdf'])
    assert top_of(source, 'Keep') - top_of(pdf, 'Keep') == pytest.approx(result['pushed'], abs=.01)
    assert path.read_bytes() == source


@pytest.mark.parametrize('neighbor_y', [290, 280])
def test_free_space_below_is_kept_and_the_neighbor_still_moves(tmp_path, neighbor_y):
    path = tmp_path / 's.pdf'; source, p = neighbor_pdf(path, neighbor_y=neighbor_y)
    result = prepare_paragraph_edit(path, source, payload(p, LONG), tmp_path)
    box = next(b for b in result['boxes'] if 'great deal' in b['text'])
    # The base height runs to the server's paragraph bottom (76.4: baseline 326 + 0.2em), not the client's 76.
    assert result['pushed'] > 0 and box['rect']['height'] - 28.4 == pytest.approx(result['pushed'])
    pdf = base64.b64decode(result['pdf'])
    assert top_of(source, 'Keep') - top_of(pdf, 'Keep') == pytest.approx(result['pushed'], abs=.01)
    assert top_of(pdf, 'Header') == top_of(source, 'Header')  # content above stays exactly in place


def test_two_column_page_refuses_push(tmp_path):
    from tools.build_export_fixtures import build_export_fixture
    path = tmp_path / 'cols.pdf'; build_export_fixture(path); source = path.read_bytes()
    with RunIndex(path) as index:
        p = next(p for p in page_paragraphs(0, index.page(0)) if p.lines[0][0].display_text.startswith('Left'))
    lines = [' '.join(r.display_text for r in line) for line in p.lines]
    lines[0] += ' with many more words that make this paragraph wrap onto extra lines'
    with pytest.raises(TextBoxError, match='PUSH_DOWN_UNSUPPORTED'):
        prepare_paragraph_edit(path, source, payload(p, lines, rect={'left': 40, 'top': 88, 'width': 200, 'height': 30}), tmp_path)
    assert path.read_bytes() == source


def test_native_box_below_moves_with_the_push(tmp_path):
    path = tmp_path / 's.pdf'; source, p = neighbor_pdf(path, box_below=True)
    result = prepare_paragraph_edit(path, source, payload(p, LONG), tmp_path)
    assert result['pushed'] > 0
    moved = next(b for b in result['boxes'] if b['text'] == 'Boxed note')
    assert moved['rect']['top'] == pytest.approx(200 + result['pushed'])
    assert top_of(source, 'Boxed') - top_of(base64.b64decode(result['pdf']), 'Boxed') == pytest.approx(result['pushed'], abs=.01)


def test_push_past_the_page_bottom_is_refused_atomically(tmp_path):
    path = tmp_path / 's.pdf'; source, p = neighbor_pdf(path, footer=True)
    with pytest.raises(TextBoxError, match='PUSH_DOWN_PAGE_FULL'):
        prepare_paragraph_edit(path, source, payload(p, LONG), tmp_path)
    assert path.read_bytes() == source


def test_added_line_rebuilds_with_explicit_break(tmp_path):
    path = tmp_path / 's.pdf'; source, p = two_line_pdf(path)
    result = prepare_paragraph_edit(path, source, payload(p, ['First', 'line here', 'Second line here'], allow_rebuild=True), tmp_path)
    assert result['plan'] == 'rebuild'


@pytest.mark.parametrize('style', [{'font_size': 99999}, {'alignment': 'center'}])
def test_bad_payload_style_is_invalid(tmp_path, style):
    path = tmp_path / 's.pdf'; source, p = two_line_pdf(path)
    with pytest.raises(TextBoxError, match='INVALID_TEXT_BOX'):
        prepare_paragraph_edit(path, source, payload(p, ['First line here', 'Second line hers'], style=style), tmp_path)


def test_edit_keeps_earlier_restyle(tmp_path):
    path = tmp_path / 's.pdf'; source, p = two_line_pdf(path)
    b = p.lines[1][0].run_id
    prior = [{'run_id': b, 'new_text': 'Second line here', 'style': {'bold': True}}]
    result = prepare_paragraph_edit(path, source, payload(p, ['First line here', 'Second line hers'], recipe=prior), tmp_path)
    assert result['recipe'] == [{'run_id': b, 'new_text': 'Second line hers', 'style': {'bold': True}}]


def test_unchanged_draft_is_refused(tmp_path):
    path = tmp_path / 's.pdf'; source, p = two_line_pdf(path)
    with pytest.raises(TextBoxError, match='PARAGRAPH_UNCHANGED'):
        prepare_paragraph_edit(path, source, payload(p, ['First line here', 'Second line here']), tmp_path)


def test_bad_run_styles_invalid_even_when_line_plan_works(tmp_path):
    path = tmp_path / 's.pdf'; source, p = two_line_pdf(path)
    with pytest.raises(TextBoxError, match='INVALID_TEXT_BOX'):
        prepare_paragraph_edit(path, source, payload(p, ['First line here', 'Second line hers'], run_styles={'x': {}}), tmp_path)


def test_character_spacing_stays_out_of_run_styles(tmp_path):
    path = tmp_path / 's.pdf'; source, p = two_line_pdf(path)
    result = prepare_paragraph_edit(path, source, payload(p, ['First line here Second line here'],
                                                          allow_rebuild=True, style={'character_spacing': 1}), tmp_path)
    assert result['plan'] == 'rebuild'
    assert all('character_spacing' not in r['style'] for r in result['boxes'][0]['runs'])


def rotated_pdf(path: Path):
    with pikepdf.Pdf.new() as pdf:
        page = pdf.add_blank_page(page_size=(400, 400))
        page.obj.Resources = pikepdf.Dictionary(Font=pikepdf.Dictionary(F1=pdf.make_indirect(
            pikepdf.Dictionary(Type=pikepdf.Name.Font, Subtype=pikepdf.Name.Type1, BaseFont=pikepdf.Name.Helvetica))))
        page.obj.Contents = pdf.make_stream(b'BT /F1 12 Tf 0 1 -1 0 100 50 Tm (Rotated words here) Tj ET')
        pdf.save(path)
    with RunIndex(path) as index:
        return path.read_bytes(), page_paragraphs(0, index.page(0))[0]


def test_rotated_paragraph_is_refused(tmp_path):
    from engine.source_text_box import prepare_source_text_box
    path = tmp_path / 'r.pdf'; source, p = rotated_pdf(path)
    assert p.angled
    with pytest.raises(TextBoxError, match='TEXT_BOX_SOURCE_UNSAFE'):
        prepare_paragraph_edit(path, source, payload(p, ['Rotated words there'], allow_rebuild=True), tmp_path)
    with pytest.raises(TextBoxError, match='TEXT_BOX_SOURCE_UNSAFE'):
        prepare_source_text_box(path, source, {'operation': 'replace-source', 'paragraph_id': p.paragraph_id,
            'source_run_ids': list(p.run_ids), 'recipe': [], 'page_index': 0, 'text': 'x',
            'rect': {'left': 30, 'top': 48, 'width': 200, 'height': 28}, 'style': {'font_family': 'Sans'}},
            tmp_path / 'base.pdf')


def test_rotated_paragraph_is_not_editable_in_page_listing():
    import io
    from server.isolation import run_worker
    buf = io.BytesIO()
    with pikepdf.Pdf.new() as pdf:
        page = pdf.add_blank_page(page_size=(400, 400))
        page.obj.Resources = pikepdf.Dictionary(Font=pikepdf.Dictionary(F1=pdf.make_indirect(
            pikepdf.Dictionary(Type=pikepdf.Name.Font, Subtype=pikepdf.Name.Type1, BaseFont=pikepdf.Name.Helvetica))))
        page.obj.Contents = pdf.make_stream(b'BT /F1 12 Tf 0 1 -1 0 100 50 Tm (Rotated words here) Tj ET\n'
                                            b'BT /F1 12 Tf 30 340 Td (Level words here) Tj ET')
        pdf.save(buf)
    paragraphs = run_worker('page', buf.getvalue(), page=0)['paragraphs']
    states = {p['state']: p['reason'] for p in paragraphs}
    assert states == {'not_editable': 'unsupported_text_direction', 'editable': None}


def test_whitespace_only_rebuild_is_refused(tmp_path):
    path = tmp_path / 's.pdf'; source, p = two_line_pdf(path)
    with pytest.raises(TextBoxError, match='TEXT_BOX_UNSUPPORTED_TEXT'):
        prepare_paragraph_edit(path, source, payload(p, ['   '], allow_rebuild=True), tmp_path)


def test_negative_page_is_invalid(tmp_path):
    path = tmp_path / 's.pdf'; source, p = two_line_pdf(path)
    with pytest.raises(TextBoxError, match='INVALID_TEXT_BOX'):
        prepare_paragraph_edit(path, source, payload(p, ['x', 'y'], page_index=-1), tmp_path)


def stacked_pdf(path: Path, boxes: int, height: int = 400, extra: bytes = b'', styled: bool = False):
    """The neighbor page (visible geometry unchanged) with `boxes` native boxes stacked below."""
    from engine.text_boxes import prepare_text_box
    with pikepdf.Pdf.new() as pdf:
        page = pdf.add_blank_page(page_size=(400, height))
        page.obj.Resources = pikepdf.Dictionary(Font=pikepdf.Dictionary(F1=pdf.make_indirect(
            pikepdf.Dictionary(Type=pikepdf.Name.Font, Subtype=pikepdf.Name.Type1, BaseFont=pikepdf.Name.Helvetica))))
        top = height - 400
        page.obj.Contents = pdf.make_stream(b'BT /F1 12 Tf 30 %d Td (Header above) Tj ET\n' % (top + 375)
                                            + b'BT /F1 12 Tf 30 %d Td (First line here) Tj ET\n' % (top + 340)
                                            + b'BT /F1 12 Tf 30 %d Td (Second line here) Tj ET\n' % (top + 326) + extra)
        pdf.save(path)
    for i in range(boxes):
        text = f'Box {i} note'
        spec = {'operation': 'upsert', 'page_index': 0, 'text': text, 'allow_overlap': True,
                'rect': {'left': 30, 'top': 120 + 30 * i, 'width': 150, 'height': 20}, 'style': {'font_family': 'Sans'}}
        if styled and i == 1:
            spec['runs'] = [{'text': 'Box 1 ', 'style': {'bold': True}}, {'text': 'note', 'style': {'font_family': 'Serif'}}]
        with pikepdf.open(path) as pdf:
            made = prepare_text_box(pdf, path.read_bytes(), spec)
        path.write_bytes(base64.b64decode(made['pdf']))
    with RunIndex(path) as index:
        return path.read_bytes(), next(p for p in page_paragraphs(0, index.page(0))
                                       if p.lines[0][0].display_text.startswith('First'))


def box_order(data: bytes) -> list[str]:
    import json
    with pikepdf.open(io.BytesIO(data)) as pdf:
        return [json.loads(bytes(s.NativeTextBox))['spec']['id'] for s in pdf.pages[0].Contents
                if '/NativeTextBox' in s]


def listed(data: bytes) -> list[dict]:
    from engine.text_boxes import prepare_text_box
    with pikepdf.open(io.BytesIO(data)) as pdf:
        return prepare_text_box(pdf, data, {'operation': 'list'})['boxes']


def test_boxes_below_move_by_exactly_dy_in_place(tmp_path):
    path = tmp_path / 's.pdf'; source, p = stacked_pdf(path, 3, styled=True)
    before = {b['id']: b for b in listed(source)}
    result = prepare_paragraph_edit(path, source, payload(p, LONG), tmp_path)
    out = base64.b64decode(result['pdf']); dy = result['pushed']
    assert dy > 0
    after = {b['id']: b for b in listed(out)}  # the reopen proof accepts the moved boxes
    assert set(before) <= set(after)
    for box_id, old in before.items():
        new = after[box_id]
        assert new['rect'] == {**old['rect'], 'top': pytest.approx(old['rect']['top'] + dy)}
        assert (new['text'], new['style'], new.get('runs')) == (old['text'], old['style'], old.get('runs'))
        assert top_of(source, old['text'][:5]) - top_of(out, old['text'][:5]) == pytest.approx(dy, abs=.01)
    assert [i for i in box_order(out) if i in before] == box_order(source)  # z-order kept
    assert after[box_order(source)[1]]['runs'][0]['style']['bold'] is True


@pytest.mark.perf
def test_twenty_six_boxes_below_push_inside_the_cpu_budget(tmp_path):
    import time
    path = tmp_path / 's.pdf'; source, p = stacked_pdf(path, 26, height=1000)
    start = time.process_time()
    result = prepare_paragraph_edit(path, source, payload(p, LONG), tmp_path)
    spent = time.process_time() - start
    assert result['pushed'] > 0 and len(result['boxes']) == 27
    print(f'push CPU {spent:.2f}s'); assert spent < 5, f'{spent:.2f}s CPU against the 20s worker limit'


def test_forged_rect_is_refused(tmp_path):
    path = tmp_path / 's.pdf'; source, p = neighbor_pdf(path)
    for rect in ({'left': 30, 'top': 48, 'width': 200, 'height': 200},   # bottom below the paragraph
                 {'left': 30, 'top': 48, 'width': 200, 'height': 10},    # bottom inside it
                 {'left': 30, 'top': 60, 'width': 200, 'height': 16},    # top below its first line
                 {'left': 30, 'top': 48, 'width': 20, 'height': 28}):    # narrower than its runs
        with pytest.raises(TextBoxError, match='INVALID_TEXT_BOX'):
            prepare_paragraph_edit(path, source, payload(p, LONG, rect=rect), tmp_path)
    assert path.read_bytes() == source


FRAME = b'0 0 0 RG 390 20 m 390 390 l S'  # page-high rule: visible bottom at 380


def test_moved_box_crossing_a_page_frame_is_refused(tmp_path):
    from engine.text_boxes import prepare_text_box
    for frame, expect in ((b'', None), (FRAME, 'PUSH_DOWN_PAGE_FULL')):
        path = tmp_path / f'f{len(frame)}.pdf'; stacked_pdf(path, 0, extra=frame)
        with pikepdf.open(path) as pdf:
            made = prepare_text_box(pdf, path.read_bytes(), {'operation': 'upsert', 'page_index': 0, 'text': 'Low note',
                'allow_overlap': True, 'rect': {'left': 30, 'top': 355, 'width': 150, 'height': 20}, 'style': {'font_family': 'Sans'}})
        path.write_bytes(base64.b64decode(made['pdf'])); source = path.read_bytes()
        with RunIndex(path) as index:
            p = next(p for p in page_paragraphs(0, index.page(0)) if p.lines[0][0].display_text.startswith('First'))
        if expect is None:
            result = prepare_paragraph_edit(path, source, payload(p, LONG), tmp_path)
            assert 375 + result['pushed'] > 380  # the frame alone is what refuses below
        else:
            with pytest.raises(TextBoxError, match=expect):
                prepare_paragraph_edit(path, source, payload(p, LONG), tmp_path)
            assert path.read_bytes() == source


def test_item_in_the_margin_zone_moves_on_overlap_retry(tmp_path):
    # Wholly inside the 0.1em (1.2pt) zone under the paragraph bottom (PDF y 323.6): a hairline.
    path = tmp_path / 's.pdf'; source, p = stacked_pdf(path, 0, extra=b'0 g 30 322.6 100 0.6 re f')
    result = prepare_paragraph_edit(path, source, payload(p, LONG), tmp_path)
    box = next(b for b in result['boxes'] if 'great deal' in b['text'])
    assert result['pushed'] > 0 and box['rect']['height'] - 28.4 == pytest.approx(result['pushed'])  # no extra line


def test_rotated_box_below_refuses_push_as_unsupported():
    from engine.text_boxes import _move_boxes, prepare_text_box
    with pikepdf.Pdf.new() as pdf:
        pdf.add_blank_page(page_size=(400, 400)).obj.Rotate = 90
        data = io.BytesIO(); pdf.save(data)
    with pikepdf.open(io.BytesIO(data.getvalue())) as pdf:
        made = prepare_text_box(pdf, data.getvalue(), {'operation': 'upsert', 'page_index': 0, 'text': 'Turned',
            'rect': {'left': 30, 'top': 200, 'width': 150, 'height': 20}, 'style': {'font_family': 'Sans'}})
    with pikepdf.open(io.BytesIO(base64.b64decode(made['pdf']))) as pdf:
        del pdf.pages[0].obj['/Rotate']  # the box now reads as quarter-turned on an upright page
        box_id = listed(base64.b64decode(made['pdf']))[0]['id']
        with pytest.raises(TextBoxError, match='PUSH_DOWN_UNSUPPORTED'):
            _move_boxes(pdf, 0, [box_id], 10, 400)

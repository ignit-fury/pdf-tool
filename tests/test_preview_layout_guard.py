"""A successful fit preview must also pass the actual rewrite layout guard."""
import base64
from collections import Counter
import io
import json
import math
from pathlib import Path
import sys

import pikepdf
import pypdfium2 as pdfium
import pytest
from PIL import ImageChops

from engine.index import RunIndex
from engine.rewrite import _part_glyphs_in_stream_order, _part_key, _stream_position
from server import isolation
from server.isolation import run_worker
from tools.build_security_fixtures import text_pdf


@pytest.mark.corpus
def test_corrected_terminal_pen_preserves_real_corpus_layout(tmp_path: Path) -> None:
    source = Path(__file__).resolve().parents[1] / "corpus/public/govdocs1_002_002154.pdf"
    original = source.read_bytes()
    with RunIndex(source) as index:
        target = next(run for run, _verdict in index.page(0).runs
                      if run.run_id.endswith(":p0:c0:o198"))
    recipe = json.dumps([{"run_id": target.run_id, "new_text": target.display_text[:3],
                          "style": {"font_family": "Sans"}}]).encode()
    preview = run_worker("edit", original, recipe=recipe, dry_run=True)
    applied = run_worker("edit", original, recipe=recipe)
    # This once failed D04 because program and written font widths differed.
    # Actual-width terminal correction now makes the edit safe; verify that
    # independently instead of retaining a refusal as the expected behavior.
    assert preview.get("ok") is True, preview
    assert preview["resolved"] == applied["resolved"]
    assert preview["resolved"][0]["strategy"] == "trailing_kern"
    assert preview["pdf"] is None and applied["pdf"] is not None
    output = tmp_path / 'edited.pdf'
    output.write_bytes(base64.b64decode(applied['pdf']))
    with RunIndex(source) as original_index, RunIndex(output) as edited_index:
        before = [run for run, _ in original_index.page(0).runs]
        after = [run for run, _ in edited_index.page(0).runs]
    written = next(run for run in after if run.display_text == target.display_text[:3]
                   and (run.glyphs[0].x, run.glyphs[0].y) == pytest.approx(
                       (target.glyphs[0].x, target.glyphs[0].y), abs=1e-6))
    source_glyphs = _part_glyphs_in_stream_order(before, _part_key(target))
    last = max(_stream_position(glyph) for glyph in target.glyphs)
    following = [glyph for glyph in source_glyphs if _stream_position(glyph) > last]
    assert len(following) == 663
    current = _part_glyphs_in_stream_order(after, _part_key(written))[-len(following):]
    for before_glyph, after_glyph in zip(following, current, strict=True):
        assert (after_glyph.x, after_glyph.y, *after_glyph.advance) == pytest.approx(
            (before_glyph.x, before_glyph.y, *before_glyph.advance), abs=1e-6)

    images, texts = [], []
    scale = 150 / 72
    for path in (source, output):
        with pdfium.PdfDocument(path) as document:
            page = document[0]
            text = page.get_textpage()
            try:
                texts.append(text.get_text_range(0, text.count_chars()))
                bitmap = page.render(scale=scale)
                try:
                    images.append(bitmap.to_pil().convert('RGB'))
                finally:
                    bitmap.close()
            finally:
                text.close()
                page.close()
    counter = lambda value: Counter(char for char in value if not char.isspace())
    expected = counter(texts[0])
    expected.subtract(counter(target.display_text))
    expected.update(counter(target.display_text[:3]))
    assert counter(texts[1]) == +expected
    difference = ImageChops.difference(*images)
    assert difference.getbbox() is not None
    # Original source-run envelope plus the harness's existing3pt tolerance.
    mask = (math.floor((min(g.x for g in target.glyphs) - 3) * scale),
            math.floor((target.glyphs[0].y - target.effective_em - 3) * scale),
            math.ceil((max(g.x + g.advance[0] for g in target.glyphs) + 3) * scale),
            math.ceil((target.glyphs[0].y + .3 * target.effective_em + 3) * scale))
    difference.paste((0, 0, 0), mask)
    assert difference.getbbox() is None
    assert source.read_bytes() == original


def test_preview_refuses_actual_layout_shift_without_returning_output(monkeypatch) -> None:
    with pikepdf.open(io.BytesIO(text_pdf())) as pdf:
        pdf.pages[0].Contents = pdf.make_stream(
            b'BT /F1 12 Tf 20 170 Td (First line) Tj '
            b'1 0 0 1 20 110 Tm (Hello world) Tj 0.4 g (FOLLOWER) Tj ET')
        source_buffer = io.BytesIO()
        pdf.save(source_buffer)
    source = source_buffer.getvalue()
    runs = run_worker('page', source, page=0)['runs']
    ids = {run['text']: run['run_id'] for run in runs}
    recipe = json.dumps([{'run_id': ids['First line'], 'new_text': 'First'},
                         {'run_id': ids['Hello world'], 'new_text': 'Hi'}]).encode()
    # Inject only a real trailing TJ operand error inside the disposable worker.
    # The first operation succeeds; the second moves an advance-dependent follower.
    # The normal preview/apply path must detect that and discard the whole output.
    runner = (
        'import pikepdf\n'
        'import engine.rewrite as module\n'
        'original=module._show_instruction\n'
        'def corrupt(units,fit):\n'
        ' instruction=original(units,fit)\n'
        ' if "".join(char for _,char in units)=="Hi":\n'
        '  values=list(instruction.operands[0])\n'
        '  values[-1]=float(values[-1])+1000\n'
        '  return pikepdf.ContentStreamInstruction([pikepdf.Array(values)],pikepdf.Operator("TJ"))\n'
        ' return instruction\n'
        'module._show_instruction=corrupt\n'
        'from server.worker import main\n'
        'main()\n')
    monkeypatch.setattr(isolation, '_worker_command', lambda: [sys.executable, '-c', runner])
    preview = run_worker('edit', source, recipe=recipe, dry_run=True)
    applied = run_worker('edit', source, recipe=recipe)
    assert preview.get('ok') is False, preview
    assert preview['resolved'] == applied['resolved']
    assert [row['ok'] for row in preview['resolved']] == [True, False]
    assert preview['resolved'][1]['reason'] == 'text_matrix_shifted_after_edit'
    assert preview['pdf'] is None and applied['pdf'] is None
    assert source == source_buffer.getvalue()


def test_successful_preview_returns_report_without_pdf_bytes() -> None:
    source = text_pdf(b"Hello world")
    page = run_worker("page", source, page=0)
    recipe = json.dumps([{"run_id": page["runs"][0]["run_id"], "new_text": "Hi"}]).encode()
    preview = run_worker("edit", source, recipe=recipe, dry_run=True)
    applied = run_worker("edit", source, recipe=recipe)
    assert preview.get("ok") is True, preview
    assert preview["resolved"] == applied["resolved"]
    assert preview["pdf"] is None
    assert applied["pdf"] is not None

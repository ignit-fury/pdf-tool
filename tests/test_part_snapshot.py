"""Selective glyph decoding must prove every retained operator's state is unchanged."""
import io
from dataclasses import replace

import pikepdf
import pytest

from engine.index import RunIndex
from tools.build_security_fixtures import text_pdf


def _context(tmp_path, content=None, extra_font=False):
    from engine.part_snapshot import PartSnapshot
    source = tmp_path / "source.pdf"
    with pikepdf.open(io.BytesIO(text_pdf(b"Hello"))) as pdf:
        if extra_font:
            pdf.pages[0].Resources.Font.F2 = pikepdf.Dictionary(
                Type=pikepdf.Name.Font, Subtype=pikepdf.Name.Type1,
                BaseFont=pikepdf.Name("/Helvetica" if extra_font == "same_name" else "/Times-Roman"),
                Encoding=pikepdf.Name.MacRomanEncoding if extra_font == "same_name" else pikepdf.Name.WinAnsiEncoding)
        actual = content or (
            b"BT /F1 12 Tf 72 700 Td (Hello) Tj ET\n"
            b"BT /F1 12 Tf 72 660 Td (Second) Tj ET\n"
            b"BT /F1 12 Tf 72 620 Td (Third) Tj ET")
        pdf.pages[0].Contents = (pikepdf.Array([pdf.make_stream(part) for part in actual])
                                if isinstance(actual, list) else pdf.make_stream(actual))
        pdf.save(source)
    with RunIndex(source) as index:
        runs = tuple(index.page(0).runs)
    pdf = pikepdf.open(source)
    context = PartSnapshot.create(pdf, 0, runs)
    assert context is not None
    return pdf, context, runs


def _splice(pdf, context, run, replacement):
    from engine.rewrite import _correlate, _write_part_bytes
    from engine.run_id import decode_run_id
    instructions, touched = _correlate(pdf, 0, run, [r for r, _ in context.runs])
    new = list(pikepdf.parse_content_stream(pdf.make_stream(replacement)))
    first = touched[0]
    surviving = instructions[:first] + new + instructions[first + 1:]
    shift = len(new) - 1
    for index in sorted(touched[1:], reverse=True):
        del surviving[index + shift]
    parts = decode_run_id(run.run_id)
    context.before_witness(run)
    _write_part_bytes(pdf, 0, parts["part"], (), b"\n".join(
        pikepdf.unparse_content_stream([item]) for item in surviving))
    context.splice(run, instructions, touched, new)


def test_rebases_untouched_targets_and_retains_actual_text(tmp_path):
    pdf, context, original = _context(tmp_path)
    try:
        run, verdict = context.resolve(original[0][0])
        _splice(pdf, context, run, b"(Hello) Tj")
        assert context.check_after(pdf) is None
        second, second_verdict = context.resolve(original[1][0])
        assert second.display_text == "Second"
        assert second.glyphs[0].x == 72
        assert second.glyphs[0].y == original[1][0].glyphs[0].y
        assert second_verdict.state == original[1][1].state
        assert verdict.state == original[0][1].state
        assert len(context.runs) == 3
    finally:
        context.close()
        pdf.close()


def test_post_splice_interpretation_avoids_reopening_scratch_files(tmp_path, monkeypatch):
    import engine.part_snapshot as snapshot_module
    pdf, context, original = _context(tmp_path)
    try:
        opened = []
        real_open = getattr(snapshot_module, "open_document", None)

        def counted_open(*args, **kwargs):
            opened.append(1)
            return real_open(*args, **kwargs)

        monkeypatch.setattr(snapshot_module, "open_document", counted_open, raising=False)
        run, _ = context.resolve(original[0][0])
        _splice(pdf, context, run, b"(Hello) Tj")
        assert context.check_after(pdf) is None
        assert context.resolve(original[1][0])[0].display_text == "Second"
        assert not opened
    finally:
        context.close()
        pdf.close()


def test_freezes_each_operator_font_before_later_Tf_changes(tmp_path):
    pdf, context, original = _context(tmp_path, (
        b"BT /F1 12 Tf 72 700 Td (Hello) Tj ET\n"
        b"BT /F2 12 Tf 72 660 Td (Other) Tj ET"), extra_font=True)
    try:
        fresh = context.resolve(original[0][0])
        assert fresh is not None
        assert fresh[0].glyphs[1].x == original[0][0].glyphs[1].x
        assert context.resolve(original[1][0]) is not None
    finally:
        context.close()
        pdf.close()


def test_refuses_real_following_glyph_shift(tmp_path):
    pdf, context, original = _context(tmp_path, b"BT /F1 12 Tf 72 700 Td (Hello) Tj 1 0 0 rg (Second) Tj ET")
    try:
        # Fill-color change creates distinct runs without resetting the text matrix.
        run, _ = context.resolve(original[0][0])
        _splice(pdf, context, run, b"(A much longer string) Tj")
        assert context.check_after(pdf) == "text_matrix_shifted_after_edit"
    finally:
        context.close()
        pdf.close()


def test_refuses_changed_unselected_font_state(tmp_path):
    pdf, context, original = _context(tmp_path)
    try:
        run, _ = context.resolve(original[0][0])
        _splice(pdf, context, run, b"(Hello) Tj 80 Tz")
        assert context.check_after(pdf) == "text_matrix_shifted_after_edit"
    finally:
        context.close()
        pdf.close()


def test_refuses_unannounced_operand_tampering(tmp_path):
    pdf, context, original = _context(tmp_path)
    try:
        run, _ = context.resolve(original[0][0])
        _splice(pdf, context, run, b"(Hello) Tj")
        data = pdf.pages[0].Contents.read_bytes().replace(b"Second", b"Bogus!")
        pdf.pages[0].Contents = pdf.make_stream(data)
        assert context.check_after(pdf) == "correlation_failed"
    finally:
        context.close()
        pdf.close()


def test_resolves_multioperator_target_without_losing_interleaved_run(tmp_path):
    pdf, context, original = _context(tmp_path, (
        b"BT /F1 12 Tf 72 700 Td (Hel) Tj (lo) Tj ET\n"
        b"BT /F1 12 Tf 72 660 Td (Other) Tj ET"))
    try:
        run, _ = context.resolve(original[0][0])
        assert run.display_text == "Hello"
        assert len({g.operator_byte_offset for g in run.glyphs}) == 2
        _splice(pdf, context, run, b"(Hello) Tj")
        assert context.check_after(pdf) is None
        assert context.resolve(original[1][0])[0].display_text == "Other"
    finally:
        context.close()
        pdf.close()


def test_forms_use_classified_fallback(tmp_path):
    from engine.part_snapshot import PartSnapshot
    pdf, context, original = _context(tmp_path)
    context.close()
    try:
        form = pdf.make_stream(b"BT /F1 12 Tf (Nested) Tj ET")
        form.Subtype = pikepdf.Name.Form
        form.BBox = pikepdf.Array([0, 0, 100, 100])
        pdf.pages[0].Resources.XObject = pikepdf.Dictionary(Fm=form)
        assert PartSnapshot.create(pdf, 0, original) is None
    finally:
        pdf.close()


def test_same_basefont_does_not_hide_wrong_restored_alias(tmp_path):
    pdf, context, original = _context(tmp_path, extra_font="same_name")
    try:
        run, _ = context.resolve(original[0][0])
        _splice(pdf, context, run, b"(Hello) Tj /F2 12 Tf")
        # The next BT explicitly restores F1, so put the wrong alias into the next
        # unchanged instruction's owning resource instead to exercise binding proof.
        pdf.pages[0].Resources.Font.F1 = pdf.pages[0].Resources.Font.F2
        assert context.check_after(pdf) == "text_matrix_shifted_after_edit"
    finally:
        context.close()
        pdf.close()


def test_shared_operator_is_rejected_even_with_distinct_source_runs(tmp_path):
    from engine.rewrite import _correlate
    pdf, context, original = _context(tmp_path, b"BT /F1 12 Tf 72 700 Td [(Hello) -10000 (Other)] TJ ET")
    try:
        assert len(original) == 2
        assert len(context.runs) == 2
        assert context.resolve(original[0][0]) is None
        run = context.runs[0][0]
        instructions, touched = _correlate(pdf, 0, run, [r for r, _ in context.runs])
        new = list(pikepdf.parse_content_stream(pdf.make_stream(b"(Hello) Tj")))
        with pytest.raises(ValueError, match="shared text operator"):
            context.splice(run, instructions, touched, new)
    finally:
        context.close()
        pdf.close()


def test_lost_source_identity_is_not_guessed_from_matching_text(tmp_path):
    pdf, context, original = _context(tmp_path)
    try:
        assert context.resolve(replace(original[0][0], run_id="unknown-source-identity")) is None
    finally:
        context.close()
        pdf.close()


def test_interleaved_foreign_run_survives_multioperator_splice(tmp_path):
    pdf, context, original = _context(tmp_path, (
        b"BT /F1 12 Tf 0 0 0 rg 1 0 0 1 72 700 Tm (Hel) Tj\n"
        b"1 0 0 rg 1 0 0 1 72 660 Tm (Other) Tj\n"
        b"0 0 0 rg 1 0 0 1 90 700 Tm (lo) Tj ET"))
    try:
        hello = next(r for r, _ in original if r.display_text == "Hello")
        other = next(r for r, _ in original if r.display_text == "Other")
        run, _ = context.resolve(hello)
        _splice(pdf, context, run, b"(Hello) Tj")
        assert context.check_after(pdf) is None
        fresh = context.resolve(other)
        assert fresh is not None
        assert fresh[0].display_text == "Other"
        assert fresh[0].glyphs[0].x == other.glyphs[0].x
        assert fresh[0].glyphs[0].y == other.glyphs[0].y
    finally:
        context.close()
        pdf.close()


def test_rebases_multiple_content_parts_independently(tmp_path):
    pdf, context, original = _context(tmp_path, [
        b"BT /F1 12 Tf 72 700 Td (Hello) Tj ET",
        b"BT /F1 12 Tf 72 660 Td (Other) Tj ET"])
    try:
        run, _ = context.resolve(original[0][0])
        _splice(pdf, context, run, b"(Hello) Tj")
        assert context.check_after(pdf) is None
        assert context.resolve(original[1][0])[0].display_text == "Other"
    finally:
        context.close()
        pdf.close()


def test_growth_preserves_current_page_glyph_limit(tmp_path, monkeypatch):
    import engine.part_snapshot as module
    pdf, context, original = _context(tmp_path)
    try:
        monkeypatch.setattr(module, "MAX_DOCUMENT_GLYPHS", 20, raising=False)
        run, _ = context.resolve(original[0][0])
        _splice(pdf, context, run, b"(Twenty letters added here) Tj")
        assert context.check_after(pdf) == "correlation_failed"
    finally:
        context.close()
        pdf.close()

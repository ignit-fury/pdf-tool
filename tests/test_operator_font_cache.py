"""A text-showing operator cannot change font between its individual glyphs."""
from pathlib import Path

import pikepdf

from engine import classify_run as module
from engine.classify_run import classify_document
from tools.build_security_fixtures import text_pdf


def test_shared_operator_resolves_font_once_without_dropping_glyphs(tmp_path: Path, monkeypatch) -> None:
    source = tmp_path / 'many-glyphs.pdf'
    source.write_bytes(text_pdf(b'Long text with many glyphs'))
    original = module._resolve_font_for_glyph
    calls = []

    def counted(*args, **kwargs):
        calls.append((args[2], args[3].operator_byte_offset))
        return original(*args, **kwargs)

    monkeypatch.setattr(module, '_resolve_font_for_glyph', counted)
    document = classify_document(source)
    assert ''.join(run.display_text for run, _ in document.runs) == 'Long text with many glyphs'
    assert len(calls) == len(set(calls)) == 1


def test_one_decoded_stream_keeps_distinct_operator_font_changes(tmp_path: Path, monkeypatch) -> None:
    source = tmp_path / 'font-changes.pdf'
    with pikepdf.Pdf.new() as pdf:
        page = pdf.add_blank_page(page_size=(300, 200))
        page.Resources = pikepdf.Dictionary(Font=pikepdf.Dictionary(
            F1=pikepdf.Dictionary(Type=pikepdf.Name.Font, Subtype=pikepdf.Name.Type1, BaseFont=pikepdf.Name.Helvetica),
            F2=pikepdf.Dictionary(Type=pikepdf.Name.Font, Subtype=pikepdf.Name.Type1, BaseFont=pikepdf.Name.Courier)))
        page.Contents = pdf.make_stream(b'BT /F1 12 Tf 20 100 Td (First) Tj /F2 12 Tf 0 -30 Td (Second) Tj ET')
        pdf.save(source)
    original = module.stream_bytes_and_resources
    reads = []

    def counted(*args, **kwargs):
        reads.append((args[1], args[2], args[3]))
        return original(*args, **kwargs)

    monkeypatch.setattr(module, 'stream_bytes_and_resources', counted)
    document = classify_document(source)
    assert {run.display_text for run, _ in document.runs} == {'First', 'Second'}
    fonts = {run.glyphs[0].font_id for run, _ in document.runs}
    assert len(fonts) == 2
    assert len(reads) == 1

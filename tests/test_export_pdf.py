"""Native export behavior; independent renderer acceptance lives in G6."""
from __future__ import annotations

import io
import random

import pikepdf
import pytest

from engine.export.pdf import ExportRefusal, export_pdf


def source_pdf(*, image: bool = False, masked: bool = False,
               annotation: bool = False, missing_appearance: bool = False) -> bytes:
    with pikepdf.Pdf.new() as pdf:
        page = pdf.add_blank_page(page_size=(200, 160))
        page.obj.Contents = pdf.make_stream(b'q 0 0 1 rg 10 10 15 15 re f Q\n' * 200)
        if image:
            pixels = random.Random(7).randbytes(2048 * 1024 * 3)
            stream = pdf.make_stream(pixels)
            stream.update(pikepdf.Dictionary(Type=pikepdf.Name.XObject, Subtype=pikepdf.Name.Image,
                          Width=2048, Height=1024, ColorSpace=pikepdf.Name.DeviceRGB,
                          BitsPerComponent=8))
            if masked:
                stream.Mask = pikepdf.Array([0, 0, 0, 0, 0, 0])
            page.obj.Resources = pikepdf.Dictionary(XObject=pikepdf.Dictionary(Im=stream))
            page.obj.Contents = pdf.make_stream(b'q 120 0 0 60 40 60 cm /Im Do Q')
        if annotation:
            annot = pikepdf.Dictionary(Type=pikepdf.Name.Annot, Subtype=pikepdf.Name.Widget,
                FT=pikepdf.Name.Tx, T='field', V='filled', Rect=[30, 35, 90, 59], F=4)
            if not missing_appearance:
                appearance = pdf.make_stream(b'q 0 1 0 rg 0 0 60 24 re f Q')
                appearance.update(pikepdf.Dictionary(Type=pikepdf.Name.XObject, Subtype=pikepdf.Name.Form,
                                  BBox=[0, 0, 60, 24], Resources=pikepdf.Dictionary()))
                annot.AP = pikepdf.Dictionary(N=appearance)
            field = pdf.make_indirect(annot)
            page.obj.Annots = pikepdf.Array([field])
            pdf.Root.AcroForm = pikepdf.Dictionary(Fields=pikepdf.Array([field]))
        output = io.BytesIO()
        pdf.save(output, compress_streams=False, object_stream_mode=pikepdf.ObjectStreamMode.disable)
        return output.getvalue()


def perform(source: bytes, operation: str = 'compress', **kwargs: bool):
    with pikepdf.open(io.BytesIO(source)) as pdf:
        return export_pdf(pdf, source, operation, **kwargs)


def image_data(source: bytes) -> bytes:
    with pikepdf.open(io.BytesIO(source)) as pdf:
        return pdf.pages[0].Resources.XObject.Im.read_bytes()


def test_compress_default_reduces_structure_without_changing_content():
    source = source_pdf()
    result = perform(source)
    assert len(result.data) < len(source)
    with pikepdf.open(io.BytesIO(source)) as before, pikepdf.open(io.BytesIO(result.data)) as after:
        assert before.pages[0].Contents.read_bytes() == after.pages[0].Contents.read_bytes()
        assert tuple(before.pages[0].mediabox) == tuple(after.pages[0].mediabox)
    assert result.changed_images == 0


def test_compress_default_keeps_decoded_image_pixels():
    source = source_pdf(image=True)
    result = perform(source)
    assert image_data(result.data) == image_data(source)
    assert result.changed_images == 0


def test_compress_no_reduction_returns_exact_original():
    source = perform(source_pdf()).data
    result = perform(source)
    assert result.data == source
    assert 'NO_SIZE_REDUCTION' in result.notices


def test_compress_downsample_is_explicit_and_changes_supported_image():
    source = source_pdf(image=True)
    result = perform(source, downsample=True)
    with pikepdf.open(io.BytesIO(result.data)) as pdf:
        image = pdf.pages[0].Resources.XObject.Im
        assert (image.Width, image.Height) == (1600, 800)
        assert image.Filter == pikepdf.Name.DCTDecode
    assert result.changed_images == 1
    assert len(result.data) < len(source)


def test_compress_unsupported_mask_is_untouched_and_disclosed():
    source = source_pdf(image=True, masked=True)
    result = perform(source, downsample=True)
    assert image_data(result.data) == image_data(source)
    assert result.changed_images == 0 and 'IMAGES_SKIPPED' in result.notices


def test_compress_huge_header_refuses_before_decode():
    source = source_pdf(image=True)
    with pikepdf.open(io.BytesIO(source)) as pdf:
        pdf.pages[0].Resources.XObject.Im.Width = 20000
        with pytest.raises(ExportRefusal, match='^EXPORT_LIMIT$'):
            export_pdf(pdf, source, 'compress', downsample=True)


def test_flatten_burns_saved_appearance_and_removes_widgets():
    result = perform(source_pdf(annotation=True), 'flatten')
    with pikepdf.open(io.BytesIO(result.data)) as pdf:
        assert len(pdf.pages) == 1
        assert not pdf.pages[0].obj.get('/Annots', [])
        assert not pdf.Root.get('/AcroForm', {}).get('/Fields', [])
        contents = pdf.pages[0].Contents
        streams = [contents] if isinstance(contents, pikepdf.Stream) else contents
        assert b'Do' in b''.join(part.read_bytes() for part in streams)
    assert 'ANNOTATIONS_FLATTENED' in result.notices


def test_flatten_missing_appearance_refuses_instead_of_dropping_value():
    with pytest.raises(ExportRefusal, match='^FLATTEN_APPEARANCE_REQUIRED$'):
        perform(source_pdf(annotation=True, missing_appearance=True), 'flatten')


def test_flatten_xfa_and_bad_appearance_geometry_refuse():
    source = source_pdf(annotation=True)
    with pikepdf.open(io.BytesIO(source)) as pdf:
        pdf.Root.AcroForm.XFA = pdf.make_stream(b'unsupported')
        with pytest.raises(ExportRefusal, match='^EXPORT_UNSUPPORTED$'):
            export_pdf(pdf, source, 'flatten')
    with pikepdf.open(io.BytesIO(source)) as pdf:
        pdf.pages[0].Annots[0].AP.N.BBox = [0, 0, 0, 0]
        with pytest.raises(ExportRefusal, match='^EXPORT_UNSUPPORTED$'):
            export_pdf(pdf, source, 'flatten')


@pytest.mark.parametrize('operation,downsample', [('unknown', False), ('flatten', True)])
def test_invalid_options_refuse(operation, downsample):
    with pytest.raises(ExportRefusal, match='^EXPORT_OPTIONS_INVALID$'):
        perform(source_pdf(), operation, downsample=downsample)

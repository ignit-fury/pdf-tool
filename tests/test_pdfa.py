"""The archival support policy accepts real fonts and refuses unknown features."""
import io

import pikepdf
import pytest

from harness.pdfa_fixture import POSITIVE_IDS, REFUSAL_IDS, build_fixtures


@pytest.fixture(scope='module')
def fixtures(tmp_path_factory):
    return build_fixtures(tmp_path_factory.mktemp('pdfa'))


@pytest.mark.parametrize('case', POSITIVE_IDS)
def test_positive_native_copy(fixtures, case):
    from engine.export.pdfa import export_pdfa
    source = fixtures[case].read_bytes()
    with pikepdf.open(io.BytesIO(source)) as pdf:
        result = export_pdfa(pdf, source)
        assert fixtures[case].read_bytes() == source
    with pikepdf.open(io.BytesIO(result.data)) as actual:
        assert not actual.is_encrypted
        assert actual.pdf_version == '1.7'
        assert actual.Root.OutputIntents[0].DestOutputProfile.N == 3
        with actual.open_metadata() as metadata:
            assert metadata['pdfaid:part'] == '2'
            assert metadata['pdfaid:conformance'] == 'B'
    assert set(result.notices) <= {'PDFA_METADATA_ADDED', 'PDFA_OUTPUT_INTENT_ADDED',
                                  'PDFA_RESOURCES_NORMALIZED'}


@pytest.mark.parametrize('case', [x for x in REFUSAL_IDS if x != 'refuse-malformed'])
def test_controls_refuse_without_candidate(fixtures, case):
    from engine.export.pdfa import PdfaRefusal, export_pdfa
    source = fixtures[case].read_bytes()
    with pikepdf.open(io.BytesIO(source)) as pdf:
        with pytest.raises(PdfaRefusal) as refused:
            export_pdfa(pdf, source)
    assert refused.value.code == 'PDFA_UNSUPPORTED'
    assert not hasattr(refused.value, 'data')
    assert fixtures[case].read_bytes() == source


@pytest.mark.parametrize('mutation,reason', [
    ('font-program', 'font-invalid'), ('font-width', 'font-invalid'),
    ('font-permission', 'font-invalid'), ('font-map', 'font-invalid'),
    ('font-name', 'font-invalid'), ('font-type', 'font-unsupported'),
    ('resource', 'structure-unsupported'), ('nested-action', 'structure-unsupported'),
    ('xmp', 'metadata-unsupported'), ('version', 'pdf-version'),
    ('inline', 'content-unsupported'), ('operands', 'content-unsupported'),
])
def test_mutated_controls(fixtures, mutation, reason):
    from engine.export.pdfa import PdfaRefusal, export_pdfa
    with pikepdf.open(fixtures['text-sans']) as pdf:
        font = pdf.pages[0].Resources.Font.F1
        descendant = font.DescendantFonts[0]
        if mutation == 'font-program':
            descendant.FontDescriptor.FontFile2.write(b'bad font')
        elif mutation == 'font-width':
            descendant.W = [1, [1] * 30]
        elif mutation == 'font-permission':
            from fontTools.ttLib import TTFont
            program = TTFont(io.BytesIO(descendant.FontDescriptor.FontFile2.read_bytes()))
            program['OS/2'].fsType = 2
            data = io.BytesIO()
            program.save(data)
            descendant.FontDescriptor.FontFile2.write(data.getvalue())
        elif mutation == 'font-map':
            descendant.CIDToGIDMap = pdf.make_stream(b'\0\0')
        elif mutation == 'font-name':
            font.BaseFont = pikepdf.Name('/bad+Subset')
        elif mutation == 'font-type':
            font.Subtype = pikepdf.Name.Type3
        elif mutation == 'resource':
            pdf.pages[0].Resources.Unknown = pikepdf.Dictionary()
        elif mutation == 'nested-action':
            descendant.FontDescriptor.AA = pikepdf.Dictionary()
        elif mutation == 'xmp':
            pdf.Root.Metadata = pdf.make_stream(b'<arbitrary/>')
        elif mutation == 'version':
            pdf.Root.Version = pikepdf.Name('/2.0')
        elif mutation == 'inline':
            pdf.pages[0].Contents.write(b'BI /W 1 /H 1 /BPC 8 /CS /RGB ID abc EI')
        elif mutation == 'operands':
            pdf.pages[0].Contents.write(b'1 2 rg')
        with pytest.raises(PdfaRefusal) as refused:
            export_pdfa(pdf, fixtures['text-sans'].read_bytes())
        assert refused.value.reason_id == reason


def test_unknown_reason_is_fixed():
    from engine.export.pdfa import PdfaRefusal
    error = PdfaRefusal('raw-secret')
    assert error.reason_id == str(error) == 'content-unsupported'


def test_limits(fixtures, monkeypatch):
    import engine.export.pdfa as module
    monkeypatch.setattr(module, 'MAX_OPERATORS', 1)
    with pikepdf.open(fixtures['text-sans']) as pdf:
        with pytest.raises(module.PdfaRefusal, match='limit'):
            module.export_pdfa(pdf, fixtures['text-sans'].read_bytes())


@pytest.mark.parametrize('length', ['valid', 'missing', 'wrong'])
def test_simple_embedded_truetype(fixtures, tmp_path, length):
    from engine.export.pdfa import PdfaRefusal, export_pdfa
    from fontTools.ttLib import TTFont
    with pikepdf.open(fixtures['text-sans']) as pdf:
        composite = pdf.pages[0].Resources.Font.F1
        descendant = composite.DescendantFonts[0]
        program = TTFont(io.BytesIO(descendant.FontDescriptor.FontFile2.read_bytes()))
        glyph = program.getBestCmap()[ord('A')]
        width = round(program['hmtx'].metrics[glyph][0] * 1000 / program['head'].unitsPerEm)
        pdf.pages[0].Resources.Font.F1 = pdf.make_indirect(pikepdf.Dictionary(
            Type=pikepdf.Name.Font, Subtype=pikepdf.Name.TrueType,
            BaseFont=composite.BaseFont, FontDescriptor=descendant.FontDescriptor,
            Encoding=pikepdf.Name.WinAnsiEncoding, FirstChar=65, LastChar=65, Widths=[width]))
        pdf.pages[0].Contents.write(b'BT /F1 14 Tf 24 140 Td (A) Tj ET')
        if length != 'missing':
            descendant.FontDescriptor.FontFile2.Length1 = len(
                descendant.FontDescriptor.FontFile2.read_bytes()) + (length == 'wrong')
        source = io.BytesIO()
        pdf.save(source)
        if length != 'valid':
            with pytest.raises(PdfaRefusal, match='font-invalid'):
                export_pdfa(pdf, source.getvalue())
            return
        result = export_pdfa(pdf, source.getvalue())
    with pikepdf.open(io.BytesIO(result.data)) as output:
        assert output.pages[0].Resources.Font.F1.Subtype == pikepdf.Name.TrueType


@pytest.mark.parametrize('mutation', ['q-depth', 'resource-name', 'info-string',
    'text-string', 'integer', 'tiny-real', 'small-box', 'large-box'])
def test_pdfa_implementation_limits_refuse_before_emitting(fixtures, mutation):
    from decimal import Decimal
    from engine.export.pdfa import PdfaRefusal, export_pdfa
    source = fixtures['text-sans'].read_bytes()
    with pikepdf.open(io.BytesIO(source)) as pdf:
        page = pdf.pages[0]
        if mutation == 'q-depth':
            page.Contents.write(b'q\n' * 29 + b'Q\n' * 29)
        elif mutation == 'resource-name':
            name = '/' + 'x' * 128
            page.Resources.Font[name] = page.Resources.Font.F1
            del page.Resources.Font.F1
            page.Contents.write(b'BT ' + name.encode() + b' 14 Tf ET')
        elif mutation == 'info-string':
            pdf.docinfo.Title = pikepdf.String('x' * 32768)
        elif mutation == 'text-string':
            page.Contents.write(b'BT /F1 14 Tf <' + b'0001' * 16384 + b'> Tj ET')
        elif mutation == 'integer':
            pdf.docinfo.Creator = 2147483648
        elif mutation == 'tiny-real':
            page.Contents.write(b'0.' + b'0' * 39 + b'1 0 1 1 re f')
        elif mutation == 'small-box':
            page.obj.MediaBox = [0, 0, 2, 180]
        else:
            page.obj.MediaBox = [0, 0, 14401, 180]
        with pytest.raises(PdfaRefusal):
            export_pdfa(pdf, source)


def test_inserted_blank_page_without_contents_is_supported(fixtures):
    from engine.export.pdfa import export_pdfa
    with pikepdf.open(fixtures['text-sans']) as pdf:
        blank = pdf.add_blank_page(page_size=(240, 180))
        del blank.obj.Contents
        source = io.BytesIO()
        pdf.save(source)
        result = export_pdfa(pdf, source.getvalue())
    with pikepdf.open(io.BytesIO(result.data)) as result:
        assert len(result.pages) == 2 and '/Contents' not in result.pages[1].obj

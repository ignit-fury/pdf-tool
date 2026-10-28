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

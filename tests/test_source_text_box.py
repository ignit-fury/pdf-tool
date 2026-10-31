"""Original-run expansion must remove real source text and preserve committed edits."""
import base64
import io
from pathlib import Path

import pikepdf
import pypdfium2 as pdfium
import pytest

from engine.classify_run import classify_document


def source_pdf(path: Path):
    with pikepdf.Pdf.new() as pdf:
        page=pdf.add_blank_page(page_size=(400,400))
        page.obj.Resources=pikepdf.Dictionary(Font=pikepdf.Dictionary(F1=pdf.make_indirect(
            pikepdf.Dictionary(Type=pikepdf.Name.Font,Subtype=pikepdf.Name.Type1,BaseFont=pikepdf.Name.Helvetica))))
        page.obj.Contents=pdf.make_stream(b'BT /F1 12 Tf 1 0 0 1 30 340 Tm (Original title) Tj ET\nBT /F1 12 Tf 1 0 0 1 30 100 Tm (Keep neighbor) Tj ET')
        pdf.save(path)
    return path.read_bytes(),{r.display_text:r.run_id for r,_ in classify_document(path).runs}


def request(ids,**changes):
    return {'operation':'replace-source','source_run_id':ids['Original title'],'recipe':[],
        'page_index':0,'text':'Longer first line\nSecond searchable line',
        'rect':{'left':30,'top':45,'width':220,'height':12},
        'style':{'font_family':'Sans','font_size':14},'auto_expand':True,**changes}


def extract(data):
    with pdfium.PdfDocument(data) as pdf:
        page=pdf[0].get_textpage()
        try:return page.get_text_range()
        finally:page.close()


def test_source_expansion_removes_original_and_retains_prior_recipe(tmp_path):
    from engine.source_text_box import prepare_source_text_box
    path=tmp_path/'source.pdf';source,ids=source_pdf(path)
    payload=request(ids,recipe=[{'run_id':ids['Keep neighbor'],'new_text':'Kept neighbor'}])
    result=prepare_source_text_box(path,source,payload,tmp_path/'candidate-base.pdf')
    assert result['ok'] is True
    data=base64.b64decode(result['pdf']);text=extract(data)
    assert 'Original title' not in text and 'Second searchable line' in text and 'Kept neighbor' in text
    assert result['boxes'][0]['rect']['height']>12
    assert path.read_bytes()==source
    import hashlib
    assert result['source_hash']==hashlib.sha256(source).hexdigest()


def test_source_expansion_refuses_forged_id_and_collision_without_publishing(tmp_path):
    from engine.source_text_box import prepare_source_text_box
    from engine.text_boxes import TextBoxError
    path=tmp_path/'source.pdf';source,ids=source_pdf(path)
    with pytest.raises(TextBoxError,match='TEXT_BOX_SOURCE_UNSAFE'):
        prepare_source_text_box(path,source,request(ids,source_run_id='forged'),tmp_path/'bad.pdf')
    with pytest.raises(TextBoxError,match='TEXT_BOX_OVERLAP'):
        prepare_source_text_box(path,source,request(ids,rect={'left':30,'top':285,'width':220,'height':12}),tmp_path/'blocked.pdf')
    assert path.read_bytes()==source and 'Original title' in extract(source)


def test_existing_managed_box_survives_but_its_glyph_cannot_be_converted(tmp_path):
    from engine.source_text_box import prepare_source_text_box
    from engine.text_boxes import prepare_text_box, TextBoxError
    from engine.run_id import decode_run_id
    path=tmp_path/'source.pdf';source,_=source_pdf(path)
    with pikepdf.open(path) as pdf:
        managed=prepare_text_box(pdf,source,{'operation':'upsert','page_index':0,'text':'Existing note',
            'rect':{'left':30,'top':160,'width':200,'height':40}})
    source=base64.b64decode(managed['pdf']);path.write_bytes(source)
    runs=classify_document(path).runs;ids={r.display_text:r.run_id for r,_ in runs}
    result=prepare_source_text_box(path,source,request(ids),tmp_path/'base.pdf')
    data=base64.b64decode(result['pdf']);assert 'Existing note' in extract(data)
    with pikepdf.open(io.BytesIO(data)) as pdf:
        assert len(prepare_text_box(pdf,data,{'operation':'list'})['boxes'])==2
    with pikepdf.open(path) as pdf:
        owned_parts={i for i,s in enumerate(pdf.pages[0].Contents) if '/NativeTextBox' in s}
    owned=next(r for r,_ in runs if decode_run_id(r.run_id)['part'] in owned_parts)
    with pytest.raises(TextBoxError,match='TEXT_BOX_SOURCE_UNSAFE'):
        prepare_source_text_box(path,source,request(ids,source_run_id=owned.run_id),tmp_path/'bad-owned.pdf')
    assert path.read_bytes()==source


def paragraph_pdf(path: Path):
    with pikepdf.Pdf.new() as pdf:
        page=pdf.add_blank_page(page_size=(400,400))
        page.obj.Resources=pikepdf.Dictionary(Font=pikepdf.Dictionary(F1=pdf.make_indirect(
            pikepdf.Dictionary(Type=pikepdf.Name.Font,Subtype=pikepdf.Name.Type1,BaseFont=pikepdf.Name.Helvetica))))
        page.obj.Contents=pdf.make_stream(b'BT /F1 12 Tf 1 0 0 1 30 340 Td (First line here) Tj ET\n'
            b'BT /F1 12 Tf 1 0 0 1 30 326 Td (Second line here) Tj ET\n'
            b'BT /F1 12 Tf 1 0 0 1 30 100 Td (Keep neighbor) Tj ET')
        pdf.save(path)
    from engine.index import RunIndex
    from engine.paragraphs import page_paragraphs
    with RunIndex(path) as index:
        paragraph=next(p for p in page_paragraphs(0,index.page(0)) if len(p.lines)==2)
    return path.read_bytes(),paragraph


def test_paragraph_rebuild_removes_every_line(tmp_path):
    from engine.source_text_box import prepare_source_text_box
    path=tmp_path/'p.pdf';source,paragraph=paragraph_pdf(path)
    payload={'operation':'replace-source','paragraph_id':paragraph.paragraph_id,
        'source_run_ids':list(paragraph.run_ids),'recipe':[],'page_index':0,
        'text':'First line here and much more text Second line here',
        'rect':{'left':30,'top':48,'width':200,'height':28},
        'style':{'font_family':'Sans','font_size':12},'auto_expand':True}
    result=prepare_source_text_box(path,source,payload,tmp_path/'base.pdf')
    text=extract(base64.b64decode(result['pdf']))
    assert 'much more text' in text and 'Keep neighbor' in text
    assert text.count('First line here')==1
    assert path.read_bytes()==source


def test_paragraph_rebuild_refuses_stale_ids(tmp_path):
    from engine.source_text_box import prepare_source_text_box
    from engine.text_boxes import TextBoxError
    path=tmp_path/'p.pdf';source,paragraph=paragraph_pdf(path)
    payload={'operation':'replace-source','paragraph_id':paragraph.paragraph_id,
        'source_run_ids':list(paragraph.run_ids)[:1],'recipe':[],'page_index':0,'text':'x',
        'rect':{'left':30,'top':48,'width':200,'height':28},'style':{'font_family':'Sans'}}
    with pytest.raises(TextBoxError,match='PARAGRAPH_STALE'):
        prepare_source_text_box(path,source,payload,tmp_path/'base.pdf')

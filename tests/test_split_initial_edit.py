"""The public 2026-page FAR file stores the title initial as a separate show."""
import base64
import hashlib
from pathlib import Path

import pypdfium2 as pdfium
import pytest

from engine.index import RunIndex
from engine.source_text_box import prepare_source_text_box
from engine.text_boxes import TextBoxError


SOURCE = Path(__file__).resolve().parents[1] / 'corpus/public/far_federal_acquisition_regulation.pdf'


def _payload(ids):
    return {'operation':'replace-source','source_run_ids':ids,'recipe':[],
            'page_index':0,'text':'FEDERAL',
            'rect':{'left':54,'top':164.8,'width':295.6,'height':75},
            'style':{'font_family':'Serif','font_size':60,'bold':True,'italic':False,
                     'color':[0,0,0],'character_spacing':0,'line_spacing':1.2,
                     'paragraph_spacing':0,'alignment':'left'},
            'allow_overlap':False,'auto_expand':True}


def test_split_title_word_is_one_atomic_preview_and_unrelated_page_stays_intact(tmp_path):
    original=SOURCE.read_bytes()
    with RunIndex(SOURCE) as index:
        runs=[run for run,_ in index.page(0).runs]
    assert [run.display_text for run in runs[7:9]]==['F','EDERAL']
    ids=[run.run_id for run in runs[7:9]]
    with pytest.raises(TextBoxError,match='TEXT_BOX_SOURCE_UNSAFE'):
        prepare_source_text_box(SOURCE,original,_payload([ids[0],runs[10].run_id]),
                                tmp_path/'rejected.pdf')
    styled=_payload(ids)
    styled['recipe']=[{'run_id':ids[1],'new_text':'EDERAL','style':{'font_family':'Serif'}}]
    assert prepare_source_text_box(SOURCE,original,styled,tmp_path/'styled.pdf')['ok'] is True
    result=prepare_source_text_box(SOURCE,original,_payload(ids),tmp_path/'prepared.pdf')
    assert result['ok'] is True
    assert result['source_hash']==hashlib.sha256(original).hexdigest()
    assert result['layout']['line_count']==1
    longer=_payload(ids)
    longer['text']='FEDERALS'
    longer['rect']['width']=550
    longer['style']['initial_font_size']=75
    expanded=prepare_source_text_box(SOURCE,original,longer,tmp_path/'expanded.pdf')
    assert expanded['ok'] is True
    assert expanded['layout']['line_count']==1
    with pdfium.PdfDocument(base64.b64decode(expanded['pdf'])) as widened:
        assert 'FEDERALS' in widened[0].get_textpage().get_text_range()
    expanded_path=tmp_path/'expanded-output.pdf'
    expanded_path.write_bytes(base64.b64decode(expanded['pdf']))
    with RunIndex(expanded_path) as index:
        expanded_runs=[run for run,_ in index.page(0).runs]
    assert any(run.display_text=='F' and run.effective_em==75 for run in expanded_runs)
    assert any(run.display_text=='EDERALS' and run.effective_em==60 for run in expanded_runs)
    output=base64.b64decode(result['pdf'])
    with pdfium.PdfDocument(original) as before, pdfium.PdfDocument(output) as after:
        assert len(after)==len(before)==2026
        text=after[0].get_textpage().get_text_range()
        assert text.count('FEDERAL')==1
        assert 'EDERAL' not in text.replace('FEDERAL','')
        assert 'ACQUISITION' in text and 'REGULATION' in text
        assert before[1].get_textpage().get_text_range()==after[1].get_textpage().get_text_range()
    assert SOURCE.read_bytes()==original

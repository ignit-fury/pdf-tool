"""Native owned text: transport, real drawing, reopening, and conservative refusal."""
import base64
import hashlib
import io

import pikepdf
import pypdfium2 as pdfium
import pytest
from PIL import ImageChops

from engine.text_boxes import TextBoxError, prepare_text_box


def source_pdf(content=b'', rotation=0, unit=1, crop=None):
    pdf = pikepdf.Pdf.new()
    page = pdf.add_blank_page(page_size=(400, 300))
    page.obj.Contents = pikepdf.Stream(pdf, content)
    page.obj.Rotate = rotation
    page.obj.UserUnit = unit
    if crop is not None:
        page.obj.CropBox = pikepdf.Array(crop)
    out = io.BytesIO()
    pdf.save(out)
    return out.getvalue()


def perform(source, payload):
    with pikepdf.Pdf.open(io.BytesIO(source)) as pdf:
        return prepare_text_box(pdf, source, payload)


def draft(**kw):
    return {'operation': 'upsert', 'page_index': 0, 'text': 'Hello world',
            'rect': {'left': 20, 'top': 20, 'width': 200, 'height': 60}, **kw}


def output(result):
    assert result['ok'] is True, result
    return base64.b64decode(result['pdf'])


def image_and_text(source):
    with pdfium.PdfDocument(source) as doc:
        page = doc[0]
        textpage = page.get_textpage()
        text = textpage.get_text_range()
        textpage.close()
        bitmap = page.render(scale=2)
        image = bitmap.to_pil().convert('RGB')
        bitmap.close()
        page.close()
        return image, text


def test_real_searchable_native_and_reopened_list_remove_preserves_source():
    original = source_pdf(b'0 0 1 rg 320 10 30 30 re f')
    before, _ = image_and_text(original)
    result = perform(original, draft())
    assert set(result) == {'ok','source_hash','pdf','page_index','boxes','layout','notices'}
    assert result['source_hash'] == hashlib.sha256(original).hexdigest()
    candidate = output(result)
    after, text = image_and_text(candidate)
    assert 'Hello world' in text
    assert ImageChops.difference(before, after).getbbox() is not None
    assert before.crop((600, 500, 800, 600)).tobytes() == after.crop((600, 500, 800, 600)).tobytes()
    listed = perform(candidate, {'operation': 'list'})
    assert listed['boxes'] == result['boxes']
    removed = output(perform(candidate, {'operation':'remove','id':listed['boxes'][0]['id']}))
    assert image_and_text(removed)[0].tobytes() == before.tobytes()
    with pikepdf.Pdf.open(io.BytesIO(candidate)) as pdf:
        assert b'0 0 1 rg 320 10 30 30 re f' in [s.read_bytes() for s in pdf.pages[0].Contents]


def test_wrapping_long_tokens_explicit_newlines_spaces_and_overflow():
    original = source_pdf()
    result = perform(original, draft(text='abcdefghijklmno  X\n\nY ', rect={'left':20,'top':20,'width':45,'height':150}))
    assert result['layout']['line_count'] >= 5
    assert result['boxes'][0]['text'] == 'abcdefghijklmno  X\n\nY '
    result = perform(original, draft(text='A\nB',rect={'left':20,'top':20,'width':100,'height':10}))
    assert result['ok'] is False and result['code'] == 'TEXT_BOX_OVERFLOW'
    assert result['required_height'] > result['available_height'] == 10
    assert 'pdf' not in result


def test_opt_in_auto_growth_fits_complete_text_and_keeps_collision_checks():
    request=draft(text='First line\nSecond line\nThird line',rect={'left':20,'top':20,'width':160,'height':10},auto_expand=True)
    result=perform(source_pdf(),request)
    assert result['ok'] is True
    assert result['boxes'][0]['rect']['height']>=result['layout']['required_height']>10
    assert 'Third line' in image_and_text(output(result))[1]
    blocked=source_pdf(b'0 0 1 rg 20 200 160 55 re f')
    with pytest.raises(TextBoxError,match='TEXT_BOX_OVERLAP'):perform(blocked,request)
    overflow=perform(source_pdf(),{**request,'rect':{'left':20,'top':285,'width':160,'height':10}})
    assert overflow['ok'] is False and overflow['code']=='TEXT_BOX_OVERFLOW' and 'pdf' not in overflow


def test_overlap_actual_pixels_annotations_and_transparent_optin():
    original = source_pdf(b'1 0 0 rg 0 200 300 100 re f')
    with pytest.raises(TextBoxError, match='TEXT_BOX_OVERLAP'):
        perform(original, draft())
    candidate = output(perform(original, draft(allow_overlap=True)))
    image, text = image_and_text(candidate)
    assert 'Hello world' in text
    assert image.getpixel((400, 50)) == (255, 0, 0)
    with pikepdf.Pdf.open(io.BytesIO(source_pdf())) as pdf:
        pdf.pages[0].obj.Annots = pikepdf.Array([pdf.make_indirect(pikepdf.Dictionary(Type=pikepdf.Name.Annot,Subtype=pikepdf.Name.Text,Rect=[20,220,40,280]))])
        out=io.BytesIO(); pdf.save(out)
    with pytest.raises(TextBoxError, match='TEXT_BOX_OVERLAP'):
        perform(out.getvalue(), draft())


@pytest.mark.parametrize('rotation', [0,90,180,270])
def test_visible_physical_geometry(rotation):
    original=source_pdf(rotation=rotation,unit=2,crop=[30,40,330,240])
    candidate=output(perform(original,draft(text='Top left',rect={'left':20,'top':20,'width':180,'height':50})))
    image,text=image_and_text(candidate)
    assert 'Top left' in text
    # PDFium canvas ignores UserUnit; 2x render cancels the unit=2 physical scaling.
    bbox=ImageChops.difference(image, __import__('PIL').Image.new('RGB',image.size,'white')).getbbox()
    assert bbox is not None and 18 <= bbox[0] <= 25 and 18 <= bbox[1] <= 35


def test_edit_excludes_own_stream_and_tamper_refuses():
    first=perform(source_pdf(),draft())
    candidate=output(first)
    box=first['boxes'][0]
    second=perform(candidate,draft(id=box['id'],text='Updated'))
    assert len(second['boxes'])==1
    assert 'Updated' in image_and_text(output(second))[1]
    with pikepdf.Pdf.open(io.BytesIO(candidate)) as pdf:
        owned=next(s for s in pdf.pages[0].Contents if s.get('/NativeTextBox') is not None)
        owned.write(owned.read_bytes()+b'\n0 0 10 10 re f')
        out=io.BytesIO();pdf.save(out)
    with pytest.raises(TextBoxError,match='TEXT_BOX_UNSAFE'):
        perform(out.getvalue(),{'operation':'list'})


@pytest.mark.parametrize('text',['A\tB','مرحبا','a\u0301','😀'])
def test_unsafe_unicode_refuses(text):
    with pytest.raises(TextBoxError,match='TEXT_BOX_UNSUPPORTED_TEXT'):
        perform(source_pdf(),draft(text=text))


@pytest.mark.parametrize('payload',[None,{}, {'operation':'unknown'},draft(page_index=True),draft(style={'font_size':float('nan')}),draft(style={'initial_font_size':513}),draft(style={'unknown':1}),draft(allow_overlap=1)])
def test_strict_schema(payload):
    with pytest.raises(TextBoxError,match='INVALID_TEXT_BOX'):
        perform(source_pdf(),payload)


def test_mixed_initial_size_is_searchable_and_reopens_as_one_owned_box():
    original=source_pdf()
    prepared=perform(original,draft(text='FEDERALS',style={
        'font_family':'Serif','font_size':24,'initial_font_size':30,'bold':True}))
    candidate=output(prepared)
    assert 'FEDERALS' in image_and_text(candidate)[1]
    listed=perform(candidate,{'operation':'list'})
    assert len(listed['boxes'])==1
    assert listed['boxes'][0]['style']['initial_font_size']==30
    assert listed['boxes']==prepared['boxes']


def test_reopen_proof_survives_later_clock(monkeypatch):
    import fontTools.ttLib.tables._h_e_a_d
    original=source_pdf()
    first=output(perform(original,draft()))
    # fontTools normally rewrites head.modified on every subset serialization.
    monkeypatch.setattr(fontTools.ttLib.tables._h_e_a_d, 'timestampNow', lambda: 4000000000)
    assert len(perform(first,{'operation':'list'})['boxes'])==1


def test_edit_preserves_source_use_of_shared_owned_font_resource():
    first=perform(source_pdf(),draft())
    with pikepdf.Pdf.open(io.BytesIO(output(first))) as pdf:
        name=next(iter(pdf.pages[0].Resources.Font.keys()))
        glyph=next(s for s in pdf.pages[0].Contents if s.get('/NativeTextBox')).read_bytes()
        # A legitimate external producer reuses our font on unrelated source text.
        show=next(line for line in glyph.splitlines() if b'Tj' in line)
        unrelated=b'q BT '+str(name).encode()+b' 12 Tf 1 0 0 1 300 40 Tm '+show[show.index(b'<'):]+b' ET Q'
        pdf.pages[0].obj.Contents=pikepdf.Array([*pdf.pages[0].Contents,pikepdf.Stream(pdf,unrelated)])
        out=io.BytesIO();pdf.save(out)
    source=out.getvalue();before,_=image_and_text(source)
    edited=output(perform(source,draft(id=first['boxes'][0]['id'],text='Different glyphs')))
    after,_=image_and_text(edited)
    assert before.crop((550,450,800,600)).tobytes()==after.crop((550,450,800,600)).tobytes()


@pytest.mark.parametrize('damage',['version','font','shared-stream','metadata','bomb'])
def test_untrusted_owned_drawing_never_grants_deletion(damage):
    import json
    import zlib
    candidate=output(perform(source_pdf(),draft()))
    with pikepdf.Pdf.open(io.BytesIO(candidate)) as pdf:
        page=pdf.pages[0]
        stream=next(s for s in page.Contents if s.get('/NativeTextBox'))
        if damage=='version':
            meta=json.loads(bytes(stream.NativeTextBox));meta['version']=2
            stream.NativeTextBox=pikepdf.String(json.dumps(meta))
        elif damage=='metadata':
            meta=json.loads(bytes(stream.NativeTextBox));meta['spec']['text']='Forged'
            stream.NativeTextBox=pikepdf.String(json.dumps(meta))
        elif damage=='font':
            font=next(iter(page.Resources.Font.values()))
            font.DescendantFonts[0].W=pikepdf.Array([1,[1]])
        elif damage=='shared-stream':
            page.obj.Contents=pikepdf.Array([*page.Contents,stream])
        else:
            stream.write(zlib.compress(b'x'*(2*1024*1024)),filter=pikepdf.Name.FlateDecode)
        out=io.BytesIO();pdf.save(out)
    with pytest.raises(TextBoxError,match='TEXT_BOX_UNSAFE'):
        perform(out.getvalue(),{'operation':'remove','id':perform(candidate,{'operation':'list'})['boxes'][0]['id']})


@pytest.mark.parametrize('style',[
    {'font_family':'Mono','font_size':17,'bold':True,'character_spacing':2,'alignment':'right'},
    {'font_family':'Serif','font_size':24,'italic':True,'alignment':'center','color':[0.2,0.5,0.8]},
    {'font_family':'Sans','font_size':19,'bold':True,'italic':True,'line_spacing':1.8,'paragraph_spacing':10},
])
def test_font_styles_spacing_alignment_ink_stay_inside_container(style):
    result=perform(source_pdf(),draft(text='jfy A\nB',style=style,rect={'left':20,'top':20,'width':200,'height':160}))
    candidate=output(result)
    assert perform(candidate,{'operation':'list'})['boxes']==result['boxes']
    image,text=image_and_text(candidate)
    assert all(ch in text for ch in 'jfyAB')
    bbox=ImageChops.difference(image,__import__('PIL').Image.new('RGB',image.size,'white')).getbbox()
    assert bbox is not None and bbox[0]>=39 and bbox[1]>=39 and bbox[2]<=441 and bbox[3]<=361
    larger=perform(source_pdf(),draft(text='jfy A\nB',style={**style,'font_size':style['font_size']+5},rect={'left':20,'top':20,'width':200,'height':160}))
    assert larger['layout']['required_height']>result['layout']['required_height']


def test_unbalanced_source_state_refuses_even_overlap_optin():
    with pytest.raises(TextBoxError,match='TEXT_BOX_UNSAFE'):
        perform(source_pdf(b'q 2 0 0 2 0 0 cm'),draft(allow_overlap=True))


def test_source_graphics_state_and_form_image_resources_are_preserved():
    with pikepdf.Pdf.open(io.BytesIO(source_pdf(b'2 0 0 2 0 0 cm 1 0 0 rg /Keep Do'))) as pdf:
        form=pikepdf.Stream(pdf,b'0 0 1 rg 150 100 10 10 re f')
        form.Type=pikepdf.Name.XObject;form.Subtype=pikepdf.Name.Form;form.BBox=[0,0,400,300];form.Resources=pikepdf.Dictionary()
        image=pikepdf.Stream(pdf,b'\xff\x00\x00')
        image.Type=pikepdf.Name.XObject;image.Subtype=pikepdf.Name.Image;image.Width=1;image.Height=1;image.ColorSpace=pikepdf.Name.DeviceRGB;image.BitsPerComponent=8
        pdf.pages[0].Resources=pikepdf.Dictionary(XObject=pikepdf.Dictionary(Keep=form,Image=image))
        out=io.BytesIO();pdf.save(out)
    original=out.getvalue();before,_=image_and_text(original)
    result=perform(original,draft());candidate=output(result);after,_=image_and_text(candidate)
    assert before.crop((500,350,800,600)).tobytes()==after.crop((500,350,800,600)).tobytes()
    with pikepdf.Pdf.open(io.BytesIO(candidate)) as pdf:
        assert not pdf.check_pdf_syntax()
        assert pdf.pages[0].Resources.XObject.Keep.read_bytes()==b'0 0 1 rg 150 100 10 10 re f'
        assert pdf.pages[0].Resources.XObject.Image.read_bytes()==b'\xff\x00\x00'
    removed=output(perform(candidate,{'operation':'remove','id':result['boxes'][0]['id']}))
    assert image_and_text(removed)[0].tobytes()==before.tobytes()


@pytest.mark.parametrize('key',['Encoding','Subtype','BaseFont'])
def test_pdf_primitive_name_string_substitution_never_passes_ownership(key):
    candidate=output(perform(source_pdf(),draft()))
    with pikepdf.Pdf.open(io.BytesIO(candidate)) as pdf:
        font=next(iter(pdf.pages[0].Resources.Font.values()))
        font['/'+key]=pikepdf.String(str(font['/'+key]))
        out=io.BytesIO();pdf.save(out)
    with pytest.raises(TextBoxError,match='TEXT_BOX_UNSAFE'):
        perform(out.getvalue(),{'operation':'list'})


@pytest.mark.parametrize('change',['insert','move','delete','rotate'])
def test_page_operations_keep_owned_boxes_listable_and_removable(change):
    with pikepdf.Pdf.open(io.BytesIO(source_pdf())) as pdf:
        pdf.add_blank_page(page_size=(400,300))
        out=io.BytesIO();pdf.save(out)
    first=perform(out.getvalue(),draft(page_index=1))
    with pikepdf.Pdf.open(io.BytesIO(output(first))) as pdf:
        if change=='insert':
            blank=pdf.add_blank_page(page_size=(400,300));pdf.pages.insert(0,blank);del pdf.pages[-1]
            expected_index=2
        elif change=='move':
            page=pdf.pages[1];pdf.pages.insert(0,page);del pdf.pages[2]
            expected_index=0
        elif change=='delete':
            del pdf.pages[0];expected_index=0
        else:
            pdf.pages[1].Rotate=90;expected_index=1
        out=io.BytesIO();pdf.save(out)
    changed=out.getvalue()
    listed=perform(changed,{'operation':'list'})
    box=listed['boxes'][0]
    assert box['page_index']==expected_index
    if change=='rotate':
        assert box['rotation']==90
        assert box['rect']=={'left':220,'top':20,'width':60,'height':200}
        with pytest.raises(TextBoxError,match='TEXT_BOX_UNSAFE'):
            perform(changed,draft(id=box['id'],page_index=expected_index))
        # An unrelated upright page remains usable while the rotated box is retained.
        assert perform(changed,draft(page_index=0))['ok'] is True
    else:
        assert 'rotation' not in box
        assert perform(changed,draft(id=box['id'],page_index=expected_index,text='Moved'))['ok'] is True
    assert perform(output(perform(changed,{'operation':'remove','id':box['id']})),{'operation':'list'})['boxes']==[]


def test_owned_isolation_is_idempotent_and_preserves_128_source_states():
    original=source_pdf(b'q\n'*128+b'Q\n'*128)
    result=perform(original,draft())
    identifier=result['boxes'][0]['id']
    first=output(result)
    for _ in range(130):
        result=perform(first,draft(id=identifier))
        first=output(result)
    with pikepdf.Pdf.open(io.BytesIO(first)) as pdf:
        assert len(pdf.pages[0].Contents)==4
        assert any(stream.read_bytes()==b'q\n'*128+b'Q\n'*128 for stream in pdf.pages[0].Contents)


def test_output_declares_version_required_by_user_unit():
    source = source_pdf(unit=1)
    assert source.startswith(b'%PDF-1.3')
    with pikepdf.open(io.BytesIO(output(perform(source, draft())))) as pdf:
        assert tuple(map(int, pdf.pdf_version.split('.'))) >= (1, 6)


def test_external_page_wrapper_preserves_text_box_editability():
    first = perform(source_pdf(), draft())
    with pikepdf.open(io.BytesIO(output(first))) as pdf:
        page = pdf.pages[0]
        page.obj.Contents = pikepdf.Array([
            pdf.make_stream(b'q\n'), *page.obj.Contents, pdf.make_stream(b'Q\n'),
            pdf.make_stream(b'q 0 0 1 rg 320 10 30 30 re f Q\n'),
        ])
        buffer = io.BytesIO()
        pdf.save(buffer)
    edited = output(perform(buffer.getvalue(), draft(id=first['boxes'][0]['id'], text='Changed text')))
    assert 'Changed text' in image_and_text(edited)[1]
    assert image_and_text(edited)[0].getpixel((650, 550)) == (0, 0, 255)
    assert len(perform(edited, {'operation': 'list'})['boxes']) == 1


def test_source_appended_after_isolation_retains_existing_drawing_pixels():
    # Original source deliberately leaves a scaled CTM; its restoring Q matters.
    first=perform(source_pdf(b'2 0 0 2 0 0 cm'),draft())
    with pikepdf.Pdf.open(io.BytesIO(output(first))) as pdf:
        pdf.pages[0].obj.Contents=pikepdf.Array([*pdf.pages[0].Contents,pikepdf.Stream(pdf,b'0 0 1 rg 300 10 10 10 re f')])
        out=io.BytesIO();pdf.save(out)
    source=out.getvalue();before,_=image_and_text(source)
    new=perform(source,draft(text='Second',rect={'left':20,'top':100,'width':200,'height':60}))
    candidate=output(new);after,_=image_and_text(candidate)
    assert before.crop((0,0,800,180)).tobytes()==after.crop((0,0,800,180)).tobytes()
    assert before.crop((500,450,800,600)).tobytes()==after.crop((500,450,800,600)).tobytes()
    # The nested proven envelopes themselves are stable on another edit.
    edited=output(perform(candidate,draft(id=new['boxes'][-1]['id'],text='Second',rect={'left':20,'top':100,'width':200,'height':60})))
    with pikepdf.Pdf.open(io.BytesIO(candidate)) as a,pikepdf.Pdf.open(io.BytesIO(edited)) as b:
        assert len(a.pages[0].Contents)==len(b.pages[0].Contents)


@pytest.mark.parametrize('valid_metadata',[True,False])
def test_ordinary_recipe_cannot_edit_managed_text_box(tmp_path,valid_metadata):
    from engine.classify_run import classify_document
    from engine.recipe import RecipeOp,apply_recipe
    candidate=output(perform(source_pdf(),draft()))
    if not valid_metadata:
        with pikepdf.Pdf.open(io.BytesIO(candidate)) as pdf:
            owned=next(s for s in pdf.pages[0].Contents if s.get('/NativeTextBox') is not None)
            owned.NativeTextBox=pikepdf.String('untrusted-marker')
            out=io.BytesIO();pdf.save(out);candidate=out.getvalue()
    source=tmp_path/'managed.pdf';destination=tmp_path/'changed.pdf'
    source.write_bytes(candidate)
    run,_=classify_document(source).runs[0]
    report=apply_recipe(source,(RecipeOp(run.run_id,run.display_text,style={'font_family':'Sans'}),),destination)
    assert not report.ok and report.resolved[0].reason=='managed_text_box'
    assert not destination.exists() and source.read_bytes()==candidate


def test_ordinary_unrelated_source_edit_preserves_box_reopenability(tmp_path):
    from engine.classify_run import classify_document
    from engine.recipe import RecipeOp,apply_recipe
    from tools.build_security_fixtures import text_pdf
    result=perform(text_pdf(b'Hello source'),draft())
    source=tmp_path/'mixed.pdf';destination=tmp_path/'changed.pdf'
    source.write_bytes(output(result))
    run=next(run for run,_ in classify_document(source).runs if run.display_text=='Hello source')
    report=apply_recipe(source,(RecipeOp(run.run_id,'Hallo source'),),destination)
    assert report.ok,report
    assert perform(destination.read_bytes(),{'operation':'list'})['boxes']==result['boxes']


def styled(**kw):
    return draft(text='Hello bold', runs=[{'text': 'Hello ', 'style': {}},
                 {'text': 'bold', 'style': {'bold': True, 'color': [1, 0, 0], 'font_size': 18}}], **kw)


def test_styled_runs_draw_each_run_with_its_own_font_and_colour():
    original = source_pdf()
    data = output(perform(original, styled()))
    _, text = image_and_text(data)
    assert 'Hello bold' in text
    with pikepdf.Pdf.open(io.BytesIO(data)) as pdf:
        page = pdf.pages[0]
        # BaseFont omits the variant, so read the embedded program's own subfamily name.
        from fontTools.ttLib import TTFont
        fonts = [TTFont(io.BytesIO(f.DescendantFonts[0].FontDescriptor.FontFile2.read_bytes()))['name'].getDebugName(2)
                 for f in page.Resources.Font.values()]
        content = b''.join(s.read_bytes() for s in (page.Contents if isinstance(page.Contents, pikepdf.Array) else [page.Contents]))
    assert any('Bold' in f for f in fonts) and any('Bold' not in f for f in fonts)
    assert b'1 0 0 rg' in content and b' 18 Tf' in content


def test_styled_runs_round_trip_through_list():
    original = source_pdf()
    data = output(perform(original, styled()))
    listed = perform(data, {'operation': 'list'})
    assert listed['boxes'][0]['runs'][1]['style']['bold'] is True
    removed = output(perform(data, {'operation': 'remove', 'id': listed['boxes'][0]['id']}))
    assert perform(removed, {'operation': 'list'})['boxes'] == []


def test_styled_runs_wrap_with_per_glyph_advances_and_tallest_line():
    rect = {'left': 20, 'top': 20, 'width': 60, 'height': 200}
    plain = perform(source_pdf(), draft(text='aa bb cc', rect=rect))
    big = perform(source_pdf(), draft(text='aa bb cc', rect=rect, runs=[
        {'text': 'aa ', 'style': {}}, {'text': 'bb cc', 'style': {'font_size': 30}}]))
    assert big['layout']['line_count'] > plain['layout']['line_count']
    assert big['layout']['required_height'] > plain['layout']['required_height']


@pytest.mark.parametrize('runs', [
    [{'text': 'Hello', 'style': {}}],                                   # does not cover text
    [{'text': 'Hello bold', 'style': {'underline': True}}],              # unknown key
    [{'text': '', 'style': {}}, {'text': 'Hello bold', 'style': {}}],    # empty run
    [{'text': 'Hello bold', 'style': {'font_size': 513}}],
    [{'text': 'Hello bold', 'style': {'font_family': 'Comic'}}],
    [{'text': 'Hello bold', 'style': {'color': [1, 0]}}],
    [{'style': {}}, {'text': 'Hello bold', 'style': {}}],
    'Hello bold',
])
def test_styled_runs_refuse_invalid_runs(runs):
    with pytest.raises(TextBoxError, match='INVALID_TEXT_BOX'):
        perform(source_pdf(), draft(text='Hello bold', runs=runs))


def test_styled_runs_refuse_more_than_512_runs():
    perform(source_pdf(), draft(text='x' * 512, rect={'left': 0, 'top': 0, 'width': 400, 'height': 300},
                                runs=[{'text': 'x', 'style': {}}] * 512))
    with pytest.raises(TextBoxError, match='INVALID_TEXT_BOX'):
        perform(source_pdf(), draft(text='x' * 513, runs=[{'text': 'x', 'style': {}}] * 513))


def test_styled_runs_refuse_initial_size():
    with pytest.raises(TextBoxError, match='INVALID_TEXT_BOX'):
        perform(source_pdf(), styled(style={'initial_font_size': 30}))


def test_styled_runs_check_unsupported_text_per_run_font():
    with pytest.raises(TextBoxError, match='TEXT_BOX_UNSUPPORTED_TEXT'):
        perform(source_pdf(), draft(text='Hi😀', runs=[{'text': 'Hi', 'style': {}}, {'text': '😀', 'style': {'bold': True}}]))


def test_box_without_runs_is_unchanged(monkeypatch):
    import secrets
    monkeypatch.setattr(secrets, 'token_hex', lambda n: 'a' * 32)
    original = source_pdf()
    first = output(perform(original, draft()))
    assert first == output(perform(original, draft()))
    with pikepdf.Pdf.open(io.BytesIO(first)) as pdf:
        assert len(pdf.pages[0].Resources.Font) == 1
    assert 'runs' not in perform(first, {'operation': 'list'})['boxes'][0]


def test_replace_source_forwards_runs(tmp_path):
    from engine.source_text_box import prepare_source_text_box
    from tests.test_source_text_box import request, source_pdf as run_source_pdf
    path = tmp_path / 'source.pdf'
    source, ids = run_source_pdf(path)
    payload = request(ids, text='Longer bold', runs=[{'text': 'Longer ', 'style': {}},
                                                     {'text': 'bold', 'style': {'bold': True}}])
    result = prepare_source_text_box(path, source, payload, tmp_path / 'base.pdf')
    assert result['ok'] is True and result['boxes'][0]['runs'][1]['style']['bold'] is True


@pytest.mark.parametrize('text,runs', [
    ('\n', [{'text': '\n', 'style': {}}]),
    ('A\n\nB', [{'text': 'A\n', 'style': {}}, {'text': '\nB', 'style': {'bold': True}}]),
])
def test_styled_runs_handle_newline_only_and_blank_paragraphs(text, runs):
    candidate = output(perform(source_pdf(), draft(text=text, runs=runs)))
    assert perform(candidate, {'operation': 'list'})['boxes'][0]['text'] == text


def test_styled_line_gap_clears_the_larger_line_above():
    import re
    result = perform(source_pdf(), draft(text='gyp\nHHH', auto_expand=True,
        rect={'left': 20, 'top': 20, 'width': 300, 'height': 60},
        runs=[{'text': 'gyp\n', 'style': {'font_size': 48}}, {'text': 'HHH', 'style': {}}]))
    with pikepdf.Pdf.open(io.BytesIO(output(result))) as pdf:
        drawing = next(s for s in pdf.pages[0].Contents if s.get('/NativeTextBox')).read_bytes()
    ys = sorted({-float(y) for y in re.findall(rb' (-?[\d.]+) Tm', drawing)})
    assert len(ys) == 2 and ys[1] - ys[0] >= 48 * 1.2 - 1e-6

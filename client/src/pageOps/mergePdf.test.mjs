import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {createHash} from 'node:crypto';
import {PDFDocument,PDFName,PDFString,PDFHexString,PDFArray,PDFNumber,PDFNull,decodePDFRawStream,degrees} from '@cantoo/pdf-lib';
import {describePage,loadLocalPdf} from './pdfDocument.mjs';

const n=PDFName.of,get=(pdf,dict,key)=>pdf.context.lookup(dict.get(n(key)));
const save=pdf=>pdf.save({updateFieldAppearances:false});
async function base(count=1) {const pdf=await PDFDocument.create();for(let i=0;i<count;i++)pdf.addPage([200+i*10,300+i*20]);return pdf;}
async function merge(...args) {return (await import('./mergePdf.mjs')).mergePdf(...args);}
async function review(...args) {return (await import('./mergePdf.mjs')).inspectPdfImport(...args);}
const hash=bytes=>createHash('sha256').update(bytes).digest('hex');

test('start, middle and end merges preserve imported boxes, rotation and UserUnit by default',async()=>{
  const source=await base(2),target=await base(2);
  source.getPage(0).setMediaBox(-20,-30,500,700);source.getPage(0).setCropBox(10,20,200,300);
  source.getPage(0).setRotation(degrees(90));source.getPage(0).node.set(n('UserUnit'),source.context.obj(2));
  source.getPage(1).setRotation(degrees(270));
  target.catalog.set(n('Lang'),PDFString.of('en-GB'));
  const original=await save(target),imported=await save(source),before=original.slice(),sourceBefore=imported.slice();
  for(const position of [0,1,2]) {
    const result=await merge(original,imported,{position,filename:'contract.pdf'}),out=await loadLocalPdf(result.bytes);
    assert.equal(out.getPageCount(),4);assert.equal(result.selectedPage,position);
    assert.deepEqual(describePage(out,position),describePage(source,0));assert.deepEqual(describePage(out,position+1),describePage(source,1));
    assert.equal(get(out,out.catalog,'Lang').decodeText(),'en-GB');
    assert.ok(result.notices.includes("Keep each imported page's size and rotation."));
    assert.ok(result.notices.includes('No form fields in the imported PDF.'));assert.ok(result.notices.includes('No bookmarks to merge.'));
  }
  assert.deepEqual(original,before);assert.deepEqual(imported,sourceBefore);
});

test('review is serializable data; commit rechecks identity and form collision outcomes',async()=>{
  const source=await base(),target=await base();
  for(const pdf of [source,target]) {const field=pdf.getForm().createTextField('person.name');field.setText('value');field.addToPage(pdf.getPage(0));}
  const original=await save(target),bytes=await save(source),inspection=await review(bytes,{existingBytes:original,filename:'form.pdf'});
  assert.equal(inspection.pageCount,1);assert.equal(inspection.formCount,1);assert.equal(inspection.collisionCount,1);
  assert.equal(inspection.bookmarkCount,0);assert.equal(inspection.signed,false);
  assert.equal(typeof inspection.sourceIdentity,'string');assert.deepEqual(structuredClone(inspection),inspection);
  const result=await merge(original,bytes,{position:1,filename:'form.pdf',sourceIdentity:inspection.sourceIdentity});
  const out=await loadLocalPdf(result.bytes);assert.equal(out.getForm().getTextField('import_1.person.name').getText(),'value');
  assert.ok(result.notices.includes(inspection.notices.find(notice=>notice.includes('duplicate names'))));
  const other=await base(2);await assert.rejects(merge(original,await save(other),{sourceIdentity:inspection.sourceIdentity}),{code:'MERGE_SOURCE_CHANGED'});
});

test('explicit normalization fits rotated cropped physical coordinates and transforms widgets and destinations',async()=>{
  const source=await base(),page=source.getPage(0),ctx=source.context;
  page.setMediaBox(-50,-50,500,500);page.setCropBox(10,20,100,200);page.setRotation(degrees(90));page.node.set(n('UserUnit'),ctx.obj(2));
  page.drawRectangle({x:10,y:20,width:100,height:200});
  const field=source.getForm().createTextField('entry');field.setText('value');field.addToPage(page,{x:20,y:40,width:30,height:10,borderWidth:0});
  const annotation=field.acroField.getWidgets()[0].dict;annotation.set(n('Rect'),ctx.obj([20,40,50,50]));
  const root=ctx.register(ctx.obj({Type:'Outlines'})),item=ctx.register(ctx.obj({Parent:root,Title:PDFString.of('point'),Dest:[page.ref,'XYZ',20,40,2]}));
  ctx.lookup(root).set(n('First'),item);ctx.lookup(root).set(n('Last'),item);ctx.lookup(root).set(n('Count'),ctx.obj(1));source.catalog.set(n('Outlines'),root);
  const original=await save(await base()),bytes=await save(source),result=await merge(original,bytes,{position:1,normalizeTo:{visibleWidth:600,visibleHeight:600},filename:'fit.pdf'}),out=await loadLocalPdf(result.bytes);
  const geometry=describePage(out,1);assert.deepEqual(geometry.mediaBox,{x:0,y:0,width:600,height:600});
  assert.equal(geometry.rotation,0);assert.equal(geometry.userUnit,1);
  // source visible 400×200 fits at 1.5× with 150pt vertical margin: x'=3(y-20), y'=150+3(110-x).
  const widget=out.getForm().getTextField('import_1.entry').acroField.getWidgets()[0];
  assert.deepEqual(get(out,widget.dict,'Rect').asArray().map(v=>v.asNumber()),[60,330,90,420]);
  const outline=get(out,get(out,get(out,out.catalog,'Outlines'),'First'),'First'),dest=get(out,outline,'Dest');
  assert.equal(dest.get(0).toString(),out.getPage(1).ref.toString());assert.deepEqual(dest.asArray().slice(2).map(v=>v.asNumber()),[60,420,4/3]);
  const contents=out.getPage(1).node.Contents().asArray().map(ref=>decodePDFRawStream(out.context.lookup(ref)).decode());
  assert.match(contents.map(bytes=>new TextDecoder().decode(bytes)).join('\n'),/0 -3 3 0 -60 480 cm/);
  assert.match(result.notices.join(' '),/600 × 600 pt/);
  assert.deepEqual(describePage(out,0),describePage(await loadLocalPdf(original),0));
});

test('normalization refusal leaves default-preserving merge available for unsupported annotations',async()=>{
  const source=await base(),ctx=source.context;
  source.getPage(0).node.addAnnot(ctx.register(ctx.obj({Type:'Annot',Subtype:'Line',Rect:[0,0,100,100],L:[0,0,100,100]})));
  const bytes=await save(source),original=await save(await base()),before=bytes.slice();
  await assert.rejects(merge(original,bytes,{normalizeTo:{visibleWidth:200,visibleHeight:300}}),{code:'MERGE_NORMALIZE_UNSUPPORTED'});
  assert.equal((await loadLocalPdf((await merge(original,bytes)).bytes)).getPageCount(),2);assert.deepEqual(bytes,before);
});

test('destination and imported signatures have independent mandatory acknowledgements and retained field structure',async()=>{
  const target=await base(),source=await base();
  for(const pdf of [target,source]) {
    const ctx=pdf.context,signature=ctx.register(ctx.obj({FT:'Sig',T:PDFHexString.fromText('approval'),V:{Type:'Sig',ByteRange:[0,0,0,0],Contents:PDFHexString.of('00')}}));
    pdf.catalog.set(n('AcroForm'),ctx.obj({Fields:[signature],SigFlags:1}));
  }
  const original=await save(target),bytes=await save(source),before=original.slice();
  assert.equal((await review(bytes,{existingBytes:original})).signed,true);
  await assert.rejects(merge(original,bytes),{code:'SIGNATURE_ACK_REQUIRED'});
  await assert.rejects(merge(original,bytes,{acknowledged:true}),{code:'SOURCE_SIGNATURE_ACK_REQUIRED'});
  const result=await merge(original,bytes,{acknowledged:true,sourceAcknowledged:true}),out=await loadLocalPdf(result.bytes);
  assert.equal(out.getForm().getField('import_1.approval').acroField.dict.get(n('FT')),n('Sig'));
  assert.match(result.notices.join(' '),/invalidates.*signatures/);assert.deepEqual(original,before);
});

test('real encrypted inputs verify both passwords, disclose unlocked output and refuse atomically',async()=>{
  const target=await base(),source=await base();target.encrypt({userPassword:'गुप्त🔑'});source.encrypt({userPassword:'páss🔑'});
  const original=await save(target),bytes=await save(source),before=original.slice(),sourceBefore=bytes.slice();
  await assert.rejects(review(bytes,{password:'wrong'}),{code:'PASSWORD_INVALID'});
  await assert.rejects(merge(original,bytes,{password:'गुप्त🔑',sourcePassword:'wrong'}),{code:'PASSWORD_INVALID'});
  await assert.rejects(merge(original,bytes,{password:'wrong',sourcePassword:'páss🔑'}),{code:'PASSWORD_INVALID'});
  const result=await merge(original,bytes,{password:'गुप्त🔑',sourcePassword:'páss🔑'}),out=await loadLocalPdf(result.bytes);
  assert.equal(out.getPageCount(),2);assert.equal(out.context.isDecrypted,false);
  assert.ok(result.notices.some(notice=>notice.code==='ENCRYPTED_COPY_UNLOCKED'));
  assert.deepEqual(original,before);assert.deepEqual(bytes,sourceBefore);
});

test('input sizes, invalid insertion, malformed destinations and unsafe graphs refuse before output',async()=>{
  const original=await save(await base()),source=await base(),bytes=await save(source);
  await assert.rejects(review(new Uint8Array(50*1024*1024+1)),{code:'LOCAL_PDF_TOO_LARGE'});
  await assert.rejects(merge(original,bytes,{position:-1}),{code:'PAGE_INDEX_INVALID'});
  const ctx=source.context;source.catalog.set(n('Names'),ctx.obj({Dests:{Names:[PDFString.of('bad'),[ctx.nextRef(),'Fit']]}}));
  const bad=await save(source),before=bad.slice();await assert.rejects(merge(original,bad),{code:'MERGE_DESTINATION_UNSAFE'});assert.deepEqual(bad,before);
});

test('real visible Arial programs with an identical BaseFont retain distinct hashes and dictionary references',async()=>{
  const specs=[['govdocs1_003_003063.pdf',0,'TT2','8c54d9074cb803ce67f4bc1db58cfcd8defca27d27407a39a5c0f6f48dfe5a5b'],['govdocs1_001_001038.pdf',2,'TT0','674ab0feea74f3f5ae754f3223bde2bfa75473b56cb455172bee5318907d584e']];
  const documents=[];
  for(const [filename,index,key,expected] of specs) {
    const source=await PDFDocument.load(await readFile(new URL(`../../../corpus/public/${filename}`,import.meta.url)));
    const isolated=await PDFDocument.create();isolated.addPage((await isolated.copyPages(source,[index]))[0]);
    const font=get(isolated,isolated.getPage(0).node.Resources(),'Font').lookup(n(key)),descriptor=get(isolated,font,'FontDescriptor');
    font.set(n('BaseFont'),n('ABCDEF+Arial'));descriptor.set(n('FontName'),n('ABCDEF+Arial'));
    const program=get(isolated,descriptor,'FontFile2');assert.equal(hash(decodePDFRawStream(program).decode()),expected);
    documents.push(await save(isolated));
  }
  const out=await loadLocalPdf((await merge(documents[0],documents[1],{position:1})).bytes),refs=[];
  for(const [index,[, ,key,expected]] of specs.entries()) {
    const fonts=get(out,out.getPage(index).node.Resources(),'Font'),ref=fonts.get(n(key)),font=out.context.lookup(ref),descriptor=get(out,font,'FontDescriptor');refs.push(ref.toString());
    assert.equal(get(out,font,'BaseFont'),n('ABCDEF+Arial'));
    assert.equal(hash(decodePDFRawStream(get(out,descriptor,'FontFile2')).decode()),expected);
  }
  assert.notEqual(refs[0],refs[1]);
});

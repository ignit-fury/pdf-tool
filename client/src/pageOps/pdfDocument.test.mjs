import test from 'node:test';
import assert from 'node:assert/strict';
import {PDFDocument, PDFName, PDFNumber, PDFDict, degrees} from '@cantoo/pdf-lib';
import {loadLocalPdf, describePage, inspectLocalPdf, isolatePageResources, transformPages} from './pdfDocument.mjs';

export async function fixture(count=2) {
  const pdf=await PDFDocument.create();
  for(let i=0;i<count;i++) {const p=pdf.addPage([300+i,400]);p.setMediaBox(10,20,300+i,400);}
  return pdf;
}
test('actual AES Unicode password decryption; wrong and missing passwords refuse without changing input',async()=>{
  const pdf=await fixture();pdf.getPage(0).drawText('secret text');
  pdf.encrypt({userPassword:'páss🔑',ownerPassword:'owner'});
  const bytes=await pdf.save(),original=bytes.slice();
  await assert.rejects(loadLocalPdf(bytes),{code:'PASSWORD_REQUIRED'});
  await assert.rejects(loadLocalPdf(bytes,{password:'wrong'}),{code:'PASSWORD_INVALID'});
  const loaded=await loadLocalPdf(bytes,{password:'páss🔑'});
  assert.equal(loaded.getPageCount(),2);
  assert.equal((await inspectLocalPdf(bytes,{password:'páss🔑'})).encrypted,true);
  assert.deepEqual(bytes,original);
});
test('physical effective crop intersection and UserUnit match every quarter rotation',async()=>{
  const pdf=await fixture(1),page=pdf.getPage(0);
  page.setCropBox(-10,30,150,500);page.node.set(PDFName.of('UserUnit'),PDFNumber.of(2));
  for(const rotation of [0,90,180,270]) {
    page.setRotation(degrees(rotation));
    const info=describePage(await loadLocalPdf(await pdf.save()),0);
    assert.deepEqual(info.mediaBox,{x:10,y:20,width:300,height:400});
    assert.equal(info.userUnit,2);assert.equal(info.rotation,rotation);
    assert.equal(info.visibleWidth,rotation%180?780:260);
    assert.equal(info.visibleHeight,rotation%180?260:780);
  }
});
test('signature flags and inherited signed field V detect locally; malformed/cyclic graphs refuse',async()=>{
  const pdf=await fixture(),ctx=pdf.context;
  pdf.catalog.set(PDFName.of('AcroForm'),ctx.obj({SigFlags:1,Fields:[]}));
  assert.equal((await inspectLocalPdf(await pdf.save())).signed,true);
  const child=ctx.obj({V:ctx.obj({Type:'Sig'})}),parent=ctx.obj({FT:'Sig',Kids:[ctx.register(child)]});
  pdf.catalog.set(PDFName.of('AcroForm'),ctx.obj({Fields:[ctx.register(parent)]}));
  assert.equal((await inspectLocalPdf(await pdf.save())).signed,true);
  child.set(PDFName.of('Kids'),ctx.obj([ctx.register(parent)]));
  await assert.rejects(inspectLocalPdf(await pdf.save()),{code:'SIGNATURE_UNKNOWN'});
});
test('resource additions isolate inherited and directly shared mutable dictionaries',async()=>{
  for(const inherited of [true,false]) {
    const pdf=await fixture(),[first,other]=pdf.getPages(),ctx=pdf.context;
    const resources=ctx.obj(Object.fromEntries(['Font','XObject','ExtGState','ColorSpace','Pattern','Shading','Properties'].map(key=>[key,{}])));
    if(inherited) {first.node.delete(PDFName.Resources);other.node.delete(PDFName.Resources);first.node.Parent().set(PDFName.Resources,resources);}
    else {first.node.set(PDFName.Resources,resources);other.node.set(PDFName.Resources,resources);}
    isolatePageResources(first);
    for(const name of ['Font','XObject','ExtGState','ColorSpace','Pattern','Shading','Properties']) {
      first.node.Resources().lookup(PDFName.of(name),PDFDict).set(PDFName.of('Added'),ctx.obj({}));
      assert.equal(other.node.Resources().lookup(PDFName.of(name),PDFDict).has(PDFName.of('Added')),false);
    }
    first.drawText('new font');
    assert.equal(other.node.Resources().lookup(PDFName.Font,PDFDict).keys().length,0);
  }
});
test('blank insertion at either side copies exact origins, effective crop, rotation and UserUnit',async()=>{
  for(const position of ['before','after'])for(const rotation of [0,90,180,270]) {
    const pdf=await fixture(2),page=pdf.getPage(0);page.setCropBox(20,40,100,200);page.setRotation(degrees(rotation));page.node.set(PDFName.of('UserUnit'),PDFNumber.of(2));
    const bytes=await pdf.save(),original=bytes.slice();
    const result=await transformPages(bytes,{type:'insertBlank',adjacentIndex:0,position});
    const out=await loadLocalPdf(result.bytes),index=position==='before'?0:1;
    assert.equal(out.getPageCount(),3);assert.equal(result.selectedPage,index);
    assert.deepEqual(describePage(out,index),describePage(pdf,0));assert.ok(result.notices.length);
    assert.deepEqual(bytes,original);
  }
});
test('move retains physical page refs, inherited attributes, custom catalog and targets; rotation normalizes',async()=>{
  const pdf=await fixture(3),ctx=pdf.context,ref=pdf.getPage(0).ref;
  pdf.catalog.set(PDFName.of('Custom'),ctx.obj({Kept:'yes'}));
  pdf.catalog.set(PDFName.of('OpenAction'),ctx.obj([ref,'Fit']));
  const bytes=await pdf.save();
  const moved=await transformPages(bytes,{type:'move',from:0,to:2});
  const out=await loadLocalPdf(moved.bytes);
  assert.equal(String(out.getPage(2).ref),String(ref));assert.equal(out.getPage(2).getWidth(),300);
  assert.ok(out.catalog.get(PDFName.of('Custom')));
  assert.equal(String(out.catalog.lookup(PDFName.of('OpenAction')).get(0)),String(ref));
  const rotated=await transformPages(moved.bytes,{type:'rotate',index:2,quarterTurns:-5});
  assert.equal((await loadLocalPdf(rotated.bytes)).getPage(2).getRotation().angle,270);
  const noop=await transformPages(bytes,{type:'move',from:1,to:1});assert.equal(noop.noop,true);assert.equal(noop.bytes,bytes);
});
test('deletion prunes only removed widgets/fields and redirects affected outline/name/link targets',async()=>{
  const pdf=await fixture(3),[removed,survivor,last]=pdf.getPages(),ctx=pdf.context,form=pdf.getForm();
  form.createTextField('removed').addToPage(removed);form.createTextField('kept').addToPage(survivor);
  const both=form.createTextField('both');both.addToPage(removed);both.addToPage(last);
  const outline=ctx.obj({Title:'bookmark',Dest:[removed.ref,'Fit']});
  const outlineRef=ctx.register(outline),outlines=ctx.obj({First:outlineRef,Last:outlineRef,Count:1});outline.set(PDFName.of('Parent'),ctx.register(outlines));
  pdf.catalog.set(PDFName.of('Outlines'),outline.get(PDFName.of('Parent')));
  pdf.catalog.set(PDFName.of('Names'),ctx.obj({Dests:{Names:[ctx.obj('old'),ctx.obj([removed.ref,'Fit']),ctx.obj('keep'),ctx.obj([last.ref,'Fit'])]}}));
  const link=ctx.obj({Type:'Annot',Subtype:'Link',Rect:[0,0,10,10],A:{S:'GoTo',D:[removed.ref,'Fit']}});
  survivor.node.addAnnot(ctx.register(link));
  const bytes=await pdf.save(),result=await transformPages(bytes,{type:'delete',index:0}),out=await loadLocalPdf(result.bytes);
  assert.equal(out.getPageCount(),2);assert.equal(result.selectedPage,0);
  assert.deepEqual(out.getForm().getFields().map(field=>field.getName()).sort(),['both','kept']);
  assert.equal(out.getForm().getTextField('both').acroField.getWidgets().length,1);
  assert.equal(String(out.getForm().getTextField('kept').acroField.getWidgets()[0].P()),String(out.getPage(0).ref));
  const dest=out.catalog.lookup(PDFName.of('Outlines')).lookup(PDFName.of('First')).lookup(PDFName.of('Dest'));
  assert.equal(String(dest.get(0)),String(out.getPage(0).ref));assert.ok(result.notices.some(n=>n.code==='DESTINATIONS_REDIRECTED'));
  const names=out.catalog.lookup(PDFName.of('Names')).lookup(PDFName.of('Dests')).lookup(PDFName.of('Names'));
  assert.equal(String(names.lookup(1).get(0)),String(out.getPage(0).ref));assert.equal(String(names.lookup(3).get(0)),String(out.getPage(1).ref));
});
test('final page, unsafe cyclic outlines and unknown signature state refuse atomically; signed gate applies before all mutations',async()=>{
  await assert.rejects(transformPages(await (await fixture(1)).save(),{type:'delete',index:0}),{code:'FINAL_PAGE'});
  const pdf=await fixture(),ctx=pdf.context,outline=ctx.obj({Title:'cycle'}),ref=ctx.register(outline);outline.set(PDFName.of('Next'),ref);
  pdf.catalog.set(PDFName.of('Outlines'),ctx.obj({First:ref,Last:ref,Count:1}));
  const bytes=await pdf.save(),original=bytes.slice();
  await assert.rejects(transformPages(bytes,{type:'delete',index:0}),{code:'CATALOG_UNSAFE'});assert.deepEqual(bytes,original);
  pdf.catalog.delete(PDFName.of('Outlines'));pdf.catalog.set(PDFName.of('AcroForm'),ctx.obj({SigFlags:1,Fields:[]}));
  const signed=await pdf.save();
  for(const command of [{type:'rotate',index:0,quarterTurns:1},{type:'move',from:0,to:1},{type:'delete',index:0},{type:'insertBlank',adjacentIndex:0,position:'after'}])await assert.rejects(transformPages(signed,command),{code:'SIGNATURE_ACK_REQUIRED'});
  assert.ok((await transformPages(signed,{type:'rotate',index:0,quarterTurns:1},{acknowledged:true})).bytes.length);
  pdf.catalog.set(PDFName.of('AcroForm'),ctx.obj({Fields:'invalid'}));
  await assert.rejects(transformPages(await pdf.save(),{type:'rotate',index:0,quarterTurns:1}),{code:'SIGNATURE_UNKNOWN'});
});
test('encrypted rewrite is unlocked, disclosed and capped locally',async()=>{
  const pdf=await fixture();pdf.encrypt({userPassword:'गुप्त🔑'});const bytes=await pdf.save();
  const result=await transformPages(bytes,{type:'rotate',index:1,quarterTurns:1},{password:'गुप्त🔑'});
  assert.equal((await inspectLocalPdf(result.bytes)).encrypted,false);
  assert.ok(result.notices.some(n=>n.code==='ENCRYPTED_COPY_UNLOCKED'));
  await assert.rejects(transformPages(new Uint8Array(50*1024*1024+1),{type:'rotate',index:0,quarterTurns:1}),{code:'LOCAL_PDF_TOO_LARGE'});
});

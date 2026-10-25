import test from 'node:test';
import assert from 'node:assert/strict';
import {PDFDocument, PDFName, PDFNumber, PDFDict, degrees} from '@cantoo/pdf-lib';
import {loadLocalPdf, describePage, inspectLocalPdf, isolatePageResources} from './pdfDocument.mjs';

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

import test from 'node:test';
import assert from 'node:assert/strict';
import {PDFDocument,PDFName,PDFNumber} from '@cantoo/pdf-lib';
import {splitPdf,parsePageGroups,everyNPages} from './split.mjs';
import {inspectLocalPdf} from '../pageOps/pdfDocument.mjs';
async function fixture() {const pdf=await PDFDocument.create();for(let i=0;i<4;i++){const p=pdf.addPage([200+i,300]);p.node.set(PDFName.of('UserUnit'),PDFNumber.of(2));}return pdf.save();}
test('every N and human ranges normalize to ordered zero-based groups',()=>{
  assert.deepEqual(everyNPages(5,2),[[0,1],[2,3],[4]]);assert.deepEqual(parsePageGroups('1-2; 3;4',4),[[0,1],[2],[3]]);
  for(const text of ['1;1','2;1','0','1-5','1;;2','2-1','1,2'])assert.throws(()=>parsePageGroups(text,4));
});
test('split preserves UserUnit and current page contents without changing source',async()=>{
  const bytes=await fixture(),before=bytes.slice(),result=await splitPdf(bytes,[[0,1],[2],[3]]);
  assert.equal(result.files.length,3);assert.equal(result.files[0].filename,'split-0001.pdf');assert.deepEqual(bytes,before);
  const sizes=[];for(const file of result.files){const meta=await inspectLocalPdf(file.bytes);sizes.push(meta.pageCount);assert.equal(meta.pages[0].userUnit,2);}
  assert.deepEqual(sizes,[2,1,1]);assert.equal((await inspectLocalPdf(result.files[1].bytes)).pages[0].mediaBox.width,202);
});
test('split rejects duplicates, unsorted groups, unsafe catalogs, missing signature acknowledgement and budgets',async()=>{
  const bytes=await fixture();
  for(const groups of [[],[[1,0]],[[0],[0]],[[2],[1]],[[4]],Array.from({length:1001},()=>[0])])await assert.rejects(splitPdf(bytes,groups));
  await assert.rejects(splitPdf(bytes,[[0]],{retainedBytes:300*1024*1024}),{code:'EXPORT_LIMIT'});
  const unsafe=await PDFDocument.load(bytes);unsafe.catalog.set(PDFName.of('UnexpectedPageRef'),unsafe.getPage(3).ref);
  await assert.rejects(splitPdf(await unsafe.save(),[[0]]),{code:'CATALOG_UNSAFE'});
  const signed=await PDFDocument.load(bytes);signed.catalog.set(PDFName.of('AcroForm'),signed.context.obj({SigFlags:1}));const source=await signed.save();
  await assert.rejects(splitPdf(source,[[0]]),{code:'SIGNATURE_ACK_REQUIRED'});
  assert.ok((await splitPdf(source,[[0]],{acknowledged:true})).notices.includes('SIGNATURES_INVALIDATED'));
});

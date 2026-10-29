import {execFileSync} from 'node:child_process';
import {existsSync} from 'node:fs';
import {mkdtemp,writeFile,readFile,rm} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {fileURLToPath} from 'node:url';
import {join} from 'node:path';
import {deflateSync} from 'node:zlib';
import test from 'node:test';
import assert from 'node:assert/strict';
import {PDFDocument,PDFArray,PDFName,PDFDict,decodePDFRawStream} from '@cantoo/pdf-lib';
import * as images from './images.mjs';
import {inspectLocalPdf,loadLocalPdf} from './pdfDocument.mjs';
const n=PDFName.of;
const png=Uint8Array.from(Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+a1foAAAAASUVORK5CYII=','base64'));
const rect={left:40,top:50,width:80,height:40};
async function fixture() {const pdf=await PDFDocument.create();const page=pdf.addPage([300,220]);page.drawText('Keep neighboring searchable text',{x:10,y:10,size:9});const foreign=await pdf.embedPng(png);page.drawImage(foreign,{x:200,y:100,width:20,height:20});pdf.addPage([300,220]).drawText('Sibling survives');return pdf.save();}
function streams(pdf,index=0) {const raw=pdf.getPage(index).node.get(n('Contents')),value=pdf.context.lookup(raw);return (value instanceof PDFArray?value.asArray():[raw]).map(ref=>({ref,stream:pdf.context.lookup(ref)}));}
function contents(pdf,index=0) {return streams(pdf,index).map(({stream})=>Buffer.from(decodePDFRawStream(stream).decode()).toString());}
async function inserted() {const bytes=await fixture();const result=await images.writeImage(bytes,png,{destination:'current-page',pageIndex:0,rect});return {bytes,result,id:result.localMetadata.pages[0].managedImages?.[0]?.id};}
test('insertions persist an independently owned native placement alongside foreign images and text',async()=>{
 const {bytes,result,id}=await inserted();assert.equal(typeof id,'string');const info=await inspectLocalPdf(result.bytes);assert.deepEqual(info.pages[0].managedImages,result.localMetadata.pages[0].managedImages);assert.deepEqual(info.pages[0].managedImages[0],{id,rect,rotation:0,pixelWidth:1,pixelHeight:1});
 const before=await loadLocalPdf(bytes),after=await loadLocalPdf(result.bytes);for(const content of contents(before))assert.ok(contents(after).includes(content));assert.deepEqual(contents(after,1),contents(before,1));
 const own=streams(after).filter(({stream})=>stream.dict.has(n('PdfToolImage')));assert.equal(own.length,1);assert.match(Buffer.from(own[0].stream.contents).toString(),/^q\n[\s\S]* Do\nQ\n$/);
});
test('move resize rotate replace and delete survive reopen, keeping unrelated streams and caller bytes',async()=>{
 const {result,id}=await inserted();assert.equal(typeof images.updateManagedImage,'function');let bytes=result.bytes;const initial=bytes.slice(),before=await loadLocalPdf(bytes),untouched=contents(before).filter(s=>!s.includes('/ImageManaged'));
 const next={left:90,top:90,width:70,height:40};const changed=await images.updateManagedImage(bytes,undefined,{pageIndex:0,id,rect:next,rotation:30});assert.deepEqual(bytes,initial);bytes=changed.bytes;
 const metadata=(await inspectLocalPdf(bytes)).pages[0].managedImages[0];assert.deepEqual(metadata.rect,next);assert.equal(metadata.rotation,30);assert.equal(metadata.id,id);
 const replacement=await images.updateManagedImage(bytes,png,{pageIndex:0,id,rect:next,rotation:30});const replaced=await loadLocalPdf(replacement.bytes);for(const content of untouched)assert.ok(contents(replaced).includes(content));assert.deepEqual(contents(replaced,1),contents(before,1));
 const deleted=await images.updateManagedImage(replacement.bytes,undefined,{pageIndex:0,id,remove:true});assert.deepEqual((await inspectLocalPdf(deleted.bytes)).pages[0].managedImages,[]);const after=await loadLocalPdf(deleted.bytes);for(const content of untouched)assert.ok(contents(after).includes(content));assert.deepEqual(contents(after,1),contents(before,1));
});
test('foreign ids and tampered ownership refuse before output; rotation must remain inside page',async()=>{
 const {result,id}=await inserted();assert.equal(typeof images.updateManagedImage,'function');const original=result.bytes.slice();
 await assert.rejects(images.updateManagedImage(result.bytes,undefined,{pageIndex:0,id:'foreign',remove:true}),{code:'IMAGE_MANAGED_UNSUPPORTED'});
 await assert.rejects(images.updateManagedImage(result.bytes,undefined,{pageIndex:0,id,rect:{left:0,top:0,width:80,height:40},rotation:45}),{code:'IMAGE_OUTSIDE_PAGE'});assert.deepEqual(result.bytes,original);
 const pdf=await loadLocalPdf(result.bytes),own=streams(pdf).find(({stream})=>stream.dict.has(n('PdfToolImage')));const bad=pdf.context.stream('q\n1 0 0 1 0 0 cm\n/Foreign Do\nBT (do not erase) Tj ET\nQ\n',Object.fromEntries(own.stream.dict.entries().filter(([key])=>key!==n('Length')).map(([key,val])=>[key.decodeText(),val])));pdf.context.assign(own.ref,bad);const bytes=await pdf.save();
 assert.deepEqual((await inspectLocalPdf(bytes)).pages[0].managedImages,[]);await assert.rejects(images.updateManagedImage(bytes,undefined,{pageIndex:0,id,remove:true}),{code:'IMAGE_OWNERSHIP_INVALID'});
});
test('replacement preserves an unrelated use of the owned XObject resource and shared Contents arrays',async()=>{
 const {result,id}=await inserted(),pdf=await loadLocalPdf(result.bytes),page=pdf.getPage(0),own=streams(pdf).find(({stream})=>stream.dict.has(n('PdfToolImage'))),meta=own.stream.dict.get(n('PdfToolImage')),key=meta.get(n('XObject')),imageRef=meta.get(n('Image'));
 const neighbor=`q\n10 0 0 10 200 10 cm\n/${key.decodeText()} Do\nQ\n`;page.node.addContentStream(pdf.context.register(pdf.context.stream(neighbor)));
 const source=await pdf.save(),before=await loadLocalPdf(source),resourceBefore=before.context.lookup(imageRef).getContents().slice();
 const replaced=await images.updateManagedImage(source,png,{pageIndex:0,id,rect,rotation:0}),after=await loadLocalPdf(replaced.bytes);
 assert.ok(contents(after).includes(neighbor));assert.equal(String(after.getPage(0).node.Resources().lookup(n('XObject'),PDFDict).get(key)),String(imageRef));assert.deepEqual(after.context.lookup(imageRef).getContents(),resourceBefore);
 const shared=await loadLocalPdf(source);shared.getPage(1).node.set(n('Contents'),shared.getPage(0).node.get(n('Contents')));const sharedBytes=await shared.save(),siblingBefore=contents(await loadLocalPdf(sharedBytes),1);
 const added=await images.writeImage(sharedBytes,png,{destination:'current-page',pageIndex:0,rect});assert.deepEqual(contents(await loadLocalPdf(added.bytes),1),siblingBefore);
});
test('duplicated streams and redirected image references are never admitted as owned',async()=>{
 const {result,id}=await inserted();for(const mode of ['duplicate','resource']) {
 const pdf=await loadLocalPdf(result.bytes),page=pdf.getPage(0),own=streams(pdf).find(({stream})=>stream.dict.has(n('PdfToolImage')));
 if(mode==='duplicate')page.node.addContentStream(own.ref);else {const meta=own.stream.dict.get(n('PdfToolImage')),xobjects=page.node.Resources().lookup(n('XObject'),PDFDict),foreign=xobjects.keys().find(key=>key!==meta.get(n('XObject')));xobjects.set(meta.get(n('XObject')),xobjects.get(foreign));}
 const source=await pdf.save();await assert.rejects(images.updateManagedImage(source,undefined,{pageIndex:0,id,remove:true}),{code:'IMAGE_OWNERSHIP_INVALID'});
 }
});
test('managed updates retain password/signature admission and image byte and pixel caps',async()=>{
 const {result,id}=await inserted(),pdf=await loadLocalPdf(result.bytes);pdf.catalog.set(n('AcroForm'),pdf.context.obj({SigFlags:1,Fields:[]}));pdf.encrypt({userPassword:'secret',ownerPassword:'owner'});const bytes=await pdf.save(),options={pageIndex:0,id,remove:true};
 await assert.rejects(images.updateManagedImage(bytes,undefined,options),{code:'PASSWORD_REQUIRED'});await assert.rejects(images.updateManagedImage(bytes,undefined,{...options,password:'wrong'}),{code:'PASSWORD_INVALID'});await assert.rejects(images.updateManagedImage(bytes,undefined,{...options,password:'secret'}),{code:'SIGNATURE_ACK_REQUIRED'});
 const removed=await images.updateManagedImage(bytes,undefined,{...options,password:'secret',acknowledged:true});assert.equal(removed.localMetadata.encrypted,false);assert.ok(removed.notices.some(n=>n.code==='ENCRYPTED_COPY_UNLOCKED'));
 await assert.rejects(images.updateManagedImage(result.bytes,new Uint8Array(images.MAX_IMAGE_PNG_BYTES+1),{pageIndex:0,id,rect}),{code:'IMAGE_PNG_TOO_LARGE'});
 const oversized=png.slice();new DataView(oversized.buffer).setUint32(16,20000);await assert.rejects(images.updateManagedImage(result.bytes,oversized,{pageIndex:0,id,rect}),{code:'IMAGE_DIMENSIONS_EXCEEDED'});
});
test('owned geometry follows page rotation without rewriting image content',async()=>{
 const {result,id}=await inserted(),pdf=await loadLocalPdf(result.bytes),page=pdf.getPage(0);page.node.set(n('Rotate'),pdf.context.obj(90));const rotated=await pdf.save(),info=await inspectLocalPdf(rotated),selected=info.pages[0].managedImages[0];assert.equal(selected.id,id);assert.equal(selected.rotation,90);assert.deepEqual(selected.rect,{left:110,top:60,width:80,height:40});
 const changed=await images.updateManagedImage(rotated,undefined,{pageIndex:0,id,rect:selected.rect,rotation:selected.rotation});const after=await inspectLocalPdf(changed.bytes);assert.deepEqual(after.pages[0].managedImages,[selected]);
});
test('extreme finite rectangles cannot emit nonfinite native transforms',async()=>{
 const {managedImageMatrix}=await import('./managedImages.mjs');const geometry={mediaBox:{x:0,y:0,width:1e308,height:1e308},cropBox:{x:0,y:0,width:1e308,height:1e308},userUnit:1,rotation:0};
 const matrix=managedImageMatrix({left:4e307,top:4e307,width:1e307,height:1e-300},geometry,90);assert.ok(matrix.every(Number.isFinite));
});
test('external-file or extra stream semantics cannot spoof a managed drawing envelope',async()=>{
 const {result,id}=await inserted(),pdf=await loadLocalPdf(result.bytes),own=streams(pdf).find(({stream})=>stream.dict.has(n('PdfToolImage')));own.stream.dict.set(n('F'),pdf.context.obj({Type:'Filespec',F:pdf.context.obj('foreign-content')}));const bytes=await pdf.save();
 assert.deepEqual((await inspectLocalPdf(bytes)).pages[0].managedImages,[]);await assert.rejects(images.updateManagedImage(bytes,undefined,{pageIndex:0,id,remove:true}),{code:'IMAGE_OWNERSHIP_INVALID'});
});
test('current-page insertion persists the requested clockwise rotation',async()=>{
 const bytes=await fixture(),result=await images.writeImage(bytes,png,{destination:'current-page',pageIndex:0,rect,rotation:35});
 const info=await inspectLocalPdf(result.bytes);assert.equal(info.pages[0].managedImages[0].rotation,35);assert.deepEqual(info.pages[0].managedImages[0].rect,rect);assert.equal(result.localMetadata.pages[0].managedImages[0].rotation,35);
});
test('new-page insertion preserves rotation when rotated fitted corners stay inside',async()=>{
 const bytes=await fixture(),result=await images.writeImage(bytes,png,{destination:'new-page',pageIndex:0,position:'after',rotation:180});assert.equal((await inspectLocalPdf(result.bytes)).pages[1].managedImages[0].rotation,180);
 await assert.rejects(images.writeImage(bytes,png,{destination:'new-page',pageIndex:0,position:'after',rotation:45}),{code:'IMAGE_OUTSIDE_PAGE'});
});

const backendRoot=fileURLToPath(new URL('../../../',import.meta.url));
const nativePython=process.env.PDF_TOOL_TEST_PYTHON||join(backendRoot,'.venv/bin/python');
// The Node-only image-builder stage has no backend. The mandatory Python test
// invokes this exact case with its interpreter in the final combined CI image.
test('real native engine text edit keeps compressed managed images editable across runtimes',{skip:!existsSync(nativePython)},async()=>{
 const root=fileURLToPath(new URL('../../../',import.meta.url)),directory=await mkdtemp(join(tmpdir(),'managed-image-engine-'));
 try {
  const {result,id}=await inserted(),source=join(directory,'in.pdf'),output=join(directory,'out.pdf');await writeFile(source,result.bytes);
  const edited=execFileSync(nativePython,['-c',`
import sys
from pathlib import Path
from engine.classify_run import classify_document
from engine.recipe import RecipeOp, apply_recipe
source, output = map(Path, sys.argv[1:])
run = next(r for r, _ in classify_document(source).runs if r.display_text == "Keep neighboring searchable text")
report = apply_recipe(source, (RecipeOp(run.run_id, "Kept neighboring searchable text"),), output)
assert report.ok, report
assert any(r.display_text == "Kept neighboring searchable text" for r, _ in classify_document(output).runs)
print("native text replaced")
`,source,output],{cwd:root,encoding:'utf8'});assert.match(edited,/native text replaced/);
  const bytes=new Uint8Array(await readFile(output)),pdf=await loadLocalPdf(bytes),own=streams(pdf).find(({stream})=>stream.dict.has(n('PdfToolImage')));assert.equal(own.stream.dict.get(n('Filter')),n('FlateDecode'));
  const info=await inspectLocalPdf(bytes);assert.equal(info.pages[0].managedImages[0]?.id,id);
  const changed=await images.updateManagedImage(bytes,undefined,{pageIndex:0,id,rect:{...rect,left:50},rotation:15});assert.equal(changed.localMetadata.pages[0].managedImages[0].rotation,15);
  const removed=await images.updateManagedImage(changed.bytes,undefined,{pageIndex:0,id,remove:true});assert.deepEqual(removed.localMetadata.pages[0].managedImages,[]);
 }finally{await rm(directory,{recursive:true,force:true});}
});
test('compressed ownership rejects decoder parameters, alternate filters, extra content and inflated payloads',async()=>{
 const {result,id}=await inserted();for(const mode of ['parameters','alternate','array','extra','inflated']) {
  const pdf=await loadLocalPdf(result.bytes),own=streams(pdf).find(({stream})=>stream.dict.has(n('PdfToolImage'))),body=mode==='inflated'?Buffer.alloc(2*1024*1024,65):Buffer.concat([own.stream.contents,Buffer.from(mode==='extra'?'BT (foreign text) Tj ET':'')]);
  const replacement=pdf.context.stream(deflateSync(body),{PdfToolImage:own.stream.dict.get(n('PdfToolImage')),Filter:mode==='array'?pdf.context.obj(['FlateDecode']):n(mode==='alternate'?'LZWDecode':'FlateDecode')});
  if(mode==='parameters')replacement.dict.set(n('DecodeParms'),pdf.context.obj({Predictor:1}));pdf.context.assign(own.ref,replacement);const bytes=await pdf.save();
  assert.deepEqual((await inspectLocalPdf(bytes)).pages[0].managedImages,[],mode);await assert.rejects(images.updateManagedImage(bytes,undefined,{pageIndex:0,id,remove:true}),{code:'IMAGE_OWNERSHIP_INVALID'});
 }
});

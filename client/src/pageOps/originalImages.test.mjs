import test from 'node:test';
import assert from 'node:assert/strict';
import {PDFDocument} from '@cantoo/pdf-lib';
import {describePage,loadLocalPdf} from './pdfDocument.mjs';
import {updateManagedImage} from './images.mjs';

const PNG=Uint8Array.from(atob('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=='),c=>c.charCodeAt(0));
async function fixture() {
  const pdf=await PDFDocument.create(),page=pdf.addPage([400,600]),image=await pdf.embedPng(PNG);
  page.drawImage(image,{x:50,y:400,width:200,height:100});
  page.drawImage(image,{x:50,y:100,width:100,height:100});
  return pdf.save();
}
const images=async (bytes,page=0)=>{const pdf=await loadLocalPdf(bytes);return describePage(pdf,page).originalImages;};

test('original images are detected as editable placements',async()=>{
  const list=await images(await fixture());
  assert.deepEqual(list.map(i=>i.id),['oi_0','oi_1']);
  assert.ok(list.every(i=>i.original));
  assert.deepEqual(list[0].rect,{left:50,top:100,width:200,height:100});
});
test('moving and resizing rewrites the placement in place',async()=>{
  const out=await updateManagedImage(await fixture(),undefined,{pageIndex:0,id:'oi_0',rect:{left:20,top:30,width:80,height:40}});
  const list=await images(out.bytes);
  assert.equal(list.length,2);
  const moved=list.find(i=>Math.abs(i.rect.left-20)<1e-3);
  assert.ok(moved);assert.ok(Math.abs(moved.rect.width-80)<1e-3&&Math.abs(moved.rect.height-40)<1e-3&&Math.abs(moved.rect.top-30)<1e-3);
});
test('removing drops only the selected image',async()=>{
  const out=await updateManagedImage(await fixture(),undefined,{pageIndex:0,id:'oi_0',remove:true});
  const list=await images(out.bytes);
  assert.equal(list.length,1);assert.deepEqual(list[0].rect,{left:50,top:400,width:100,height:100});
});
test('replacing keeps position and size',async()=>{
  const out=await updateManagedImage(await fixture(),PNG,{pageIndex:0,id:'oi_1',rect:{left:50,top:400,width:100,height:100}});
  const list=await images(out.bytes);
  assert.equal(list.length,2);
  const again=await updateManagedImage(out.bytes,undefined,{pageIndex:0,id:'oi_1',remove:true});
  assert.equal((await images(again.bytes)).length,1);
});
test('metadata returned after an edit still lists the original images',async()=>{
  const out=await updateManagedImage(await fixture(),undefined,{pageIndex:0,id:'oi_0',rect:{left:20,top:30,width:80,height:40}});
  assert.equal(out.localMetadata.pages[0].originalImages.length,2);
});

test('rotated pages and later pages round-trip an original image edit',async()=>{
  const {degrees}=await import('@cantoo/pdf-lib'),pdf=await PDFDocument.create(),image=await pdf.embedPng(PNG);
  pdf.addPage([400,600]).drawImage(image,{x:10,y:10,width:50,height:50});
  for(const angle of [0,90,180,270]){const page=pdf.addPage([400,600]);page.setRotation(degrees(angle));page.drawImage(image,{x:50,y:400,width:200,height:100});}
  const bytes=await pdf.save();
  for(let index=1;index<=4;index++) {
    const before=(await images(bytes,index))[0],rect={...before.rect,left:before.rect.left+10,top:before.rect.top+5};
    const out=await updateManagedImage(bytes,undefined,{pageIndex:index,id:'oi_0',rect,rotation:before.rotation});
    const after=(await images(out.bytes,index))[0];
    assert.equal(after.rotation,before.rotation);
    for(const key of ['left','top','width','height'])assert.ok(Math.abs(after.rect[key]-rect[key])<1e-3,`page ${index} ${key}`);
    assert.equal((await images(out.bytes,0))[0].rect.width,50);
  }
});

test('encrypted and signed documents keep the password and signature gates for original images',async()=>{
  const pdf=await PDFDocument.load(await fixture()),n=(await import('@cantoo/pdf-lib')).PDFName.of;
  pdf.catalog.set(n('AcroForm'),pdf.context.obj({SigFlags:1,Fields:[]}));pdf.encrypt({userPassword:'secret',ownerPassword:'owner'});
  const bytes=await pdf.save(),options={pageIndex:0,id:'oi_0',rect:{left:20,top:30,width:80,height:40}};
  await assert.rejects(updateManagedImage(bytes,undefined,options),{code:'PASSWORD_REQUIRED'});
  await assert.rejects(updateManagedImage(bytes,undefined,{...options,password:'secret'}),{code:'SIGNATURE_ACK_REQUIRED'});
  const out=await updateManagedImage(bytes,undefined,{...options,password:'secret',acknowledged:true});
  assert.ok(out.notices.some(item=>item.code==='ENCRYPTED_COPY_UNLOCKED'));
  const moved=out.localMetadata.pages[0].originalImages.find(i=>Math.abs(i.rect.left-20)<1e-3);
  assert.ok(moved);
});

import test from 'node:test';
import assert from 'node:assert/strict';
import {deflateSync,inflateSync} from 'node:zlib';
import {readFile} from 'node:fs/promises';
import {PDFDocument,PDFName,PDFNumber,PDFDict,PDFArray,decodePDFRawStream,degrees} from '@cantoo/pdf-lib';
import {decodeLocalImage,writeImage,MAX_IMAGE_BYTES,MAX_IMAGE_PNG_BYTES} from './images.mjs';
import {describePage,loadLocalPdf} from './pdfDocument.mjs';
import {placementMatrix,fitImage} from './imageGeometry.mjs';

const n=PDFName.of;
function chunk(type,data) {
  const body=Buffer.concat([Buffer.from(type),data]),out=Buffer.alloc(data.length+12);out.writeUInt32BE(data.length);body.copy(out,4);
  let crc=0xffffffff;for(const byte of body){crc^=byte;for(let j=0;j<8;j++)crc=(crc>>>1)^((crc&1)?0xedb88320:0);}out.writeUInt32BE((crc^0xffffffff)>>>0,out.length-4);return out;
}
function png(width=2,height=1,rgba=Buffer.from([255,0,0,0,255,0,0,128])) {
  const ihdr=Buffer.alloc(13);ihdr.writeUInt32BE(width);ihdr.writeUInt32BE(height,4);ihdr[8]=8;ihdr[9]=6;
  const rows=[];for(let y=0;y<height;y++)rows.push(Buffer.from([0]),rgba.subarray(y*width*4,(y+1)*width*4));
  return Buffer.concat([Buffer.from([137,80,78,71,13,10,26,10]),chunk('IHDR',ihdr),chunk('IDAT',deflateSync(Buffer.concat(rows))),chunk('IEND',Buffer.alloc(0))]);
}
const orientedJpeg=Buffer.from('/9j/4AAQSkZJRgABAQAAAQABAAD/4QAiRXhpZgAATU0AKgAAAAgAAQESAAMAAAABAAYAAAAAAAD/2wBDAAgGBgcGBQgHBwcJCQgKDBQNDAsLDBkSEw8UHRofHh0aHBwgJC4nICIsIxwcKDcpLDAxNDQ0Hyc5PTgyPC4zNDL/2wBDAQkJCQwLDBgNDRgyIRwhMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjL/wAARCAADAAIDASIAAhEBAxEB/8QAHwAAAQUBAQEBAQEAAAAAAAAAAAECAwQFBgcICQoL/8QAtRAAAgEDAwIEAwUFBAQAAAF9AQIDAAQRBRIhMUEGE1FhByJxFDKBkaEII0KxwRVS0fAkM2JyggkKFhcYGRolJicoKSo0NTY3ODk6Q0RFRkdISUpTVFVWV1hZWmNkZWZnaGlqc3R1dnd4eXqDhIWGh4iJipKTlJWWl5iZmqKjpKWmp6ipqrKztLW2t7i5usLDxMXGx8jJytLT1NXW19jZ2uHi4+Tl5ufo6erx8vP09fb3+Pn6/8QAHwEAAwEBAQEBAQEBAQAAAAAAAAECAwQFBgcICQoL/8QAtREAAgECBAQDBAcFBAQAAQJ3AAECAxEEBSExBhJBUQdhcRMiMoEIFEKRobHBCSMzUvAVYnLRChYkNOEl8RcYGRomJygpKjU2Nzg5OkNERUZHSElKU1RVVldYWVpjZGVmZ2hpanN0dXZ3eHl6goOEhYaHiImKkpOUlZaXmJmaoqOkpaanqKmqsrO0tba3uLm6wsPExcbHyMnK0tPU1dbX2Nna4uPk5ebn6Onq8vP09fb3+Pn6/9oADAMBAAIRAxEAPwDi6KKK+ZP3E//Z','base64');
const webp=Buffer.from('UklGRhwAAABXRUJQVlA4TA8AAAAvAYAAAAcQ/Y/+ByKi/wEA','base64');
const file=(bytes,type='application/octet-stream')=>new Blob([bytes],{type});
function canvasAdapter(width=2,height=1,{encodeError,outputSize}={}) {
  const calls=[],canvas={width,height},pixels=Buffer.alloc(width*height*4);
  const ctx={fillStyle:'',fillRect(...args){calls.push(['white',this.fillStyle,...args]);pixels.fill(255);},drawImage(bitmap,...args){calls.push(['draw',...args]);const rgba=bitmap.rgba;if(rgba)for(let i=0;i<pixels.length;i+=4){const alpha=rgba[i+3]/255;for(let c=0;c<3;c++)pixels[i+c]=Math.round(rgba[i+c]*alpha+255*(1-alpha));pixels[i+3]=255;}}};
  canvas.getContext=()=>ctx;
  canvas.convertToBlob=async options=>{calls.push(['encode',options.type]);if(encodeError)throw Error('private detail');if(outputSize)return {size:outputSize};return file(png(width,height,pixels),'image/png');};
  return {canvas,calls,createCanvas:(w,h)=>{assert.equal(w,width);assert.equal(h,height);return canvas;}};
}
test('local PNG uses magic, white composites pixels, previews flattened canvas, and disposes idempotently',async()=>{
  const a=canvasAdapter(),rgba=Buffer.from([255,0,0,0,255,0,0,128]);let closes=0;
  const result=await decodeLocalImage(file(png(),'image/jpeg'),{createCanvas:a.createCanvas,decodeBitmap:async(blob,options)=>{
    assert.equal(blob.type,'image/png');assert.equal(options.imageOrientation,'from-image');return {width:2,height:1,rgba,close(){closes++;}};
  }});
  assert.deepEqual(a.calls,[['white','#ffffff',0,0,2,1],['draw',0,0],['encode','image/png']]);
  assert.equal(closes,1);assert.equal(result.preview,a.canvas);assert.equal(result.width,2);assert.equal(result.height,1);
  const bytes=Buffer.from(result.pngBytes);let offset=8,data=[];while(offset<bytes.length){const len=bytes.readUInt32BE(offset);if(bytes.toString('ascii',offset+4,offset+8)==='IDAT')data.push(bytes.subarray(offset+8,offset+8+len));offset+=12+len;}
  assert.deepEqual([...inflateSync(Buffer.concat(data))],[0,255,255,255,255,255,127,127,255]);
  result.dispose();result.dispose();assert.equal(a.canvas.width,0);assert.equal(a.canvas.height,0);
});
test('real EXIF orientation-6 JPEG is normalized once by native decoder; WebP and converted PNG share local pipeline',async()=>{
  for(const [bytes,width,height,mime] of [[orientedJpeg,3,2,'image/jpeg'],[webp,2,3,'image/webp'],[png(),2,1,'image/png']]) {
    const a=canvasAdapter(width,height);let decodes=0,closes=0;
    const result=await decodeLocalImage(file(bytes),{createCanvas:a.createCanvas,decodeBitmap:async(blob,options)=>{decodes++;assert.equal(blob.type,mime);assert.equal(options.imageOrientation,'from-image');return {width,height,close(){closes++;}};}});
    assert.equal(decodes,1);assert.equal(closes,1);assert.equal(result.width,width);assert.equal(result.height,height);result.dispose();
  }
});
test('HEIC selection requires explicit conversion and never invokes decoder; unsupported and animated containers refuse',async()=>{
  const heic=Buffer.concat([Buffer.from([0,0,0,24]),Buffer.from('ftypheic'),Buffer.alloc(12)]);
  const animatedPng=Buffer.concat([png().subarray(0,33),chunk('acTL',Buffer.alloc(8)),png().subarray(33)]);
  const animatedWebp=Buffer.concat([Buffer.from('RIFF'),Buffer.from([22,0,0,0]),Buffer.from('WEBPVP8X'),Buffer.from([10,0,0,0]),Buffer.from([2,0,0,0,1,0,0,2,0,0])]);
  for(const [bytes,code] of [[heic,'HEIC_CONVERSION_REQUIRED'],[Buffer.from('<svg/>'),'IMAGE_UNSUPPORTED'],[animatedPng,'IMAGE_ANIMATED'],[animatedWebp,'IMAGE_ANIMATED'],[Buffer.concat([orientedJpeg,orientedJpeg]),'IMAGE_AMBIGUOUS'],[png().subarray(0,30),'IMAGE_INVALID']]) {
    await assert.rejects(decodeLocalImage(file(bytes),{decodeBitmap:()=>{assert.fail('decoder must not allocate');}}),{code});
  }
});
test('input and dimension/pixel budgets reject before native decode; decoded dimensions and PNG budget rechecked',async()=>{
  await assert.rejects(decodeLocalImage({size:MAX_IMAGE_BYTES+1,arrayBuffer(){assert.fail();}}),{code:'IMAGE_TOO_LARGE'});
  for(const [width,height] of [[16385,1],[4001,4000]]) {
    const b=png();b.writeUInt32BE(width,16);b.writeUInt32BE(height,20);
    await assert.rejects(decodeLocalImage(file(b),{decodeBitmap:()=>assert.fail()}),{code:'IMAGE_DIMENSIONS_EXCEEDED'});
  }
  let closes=0;
  await assert.rejects(decodeLocalImage(file(png()),{decodeBitmap:async()=>({width:16385,height:1,close(){closes++;}})}),{code:'IMAGE_DIMENSIONS_EXCEEDED'});
  assert.equal(closes,1);
  const a=canvasAdapter(2,1,{outputSize:MAX_IMAGE_PNG_BYTES+1});
  await assert.rejects(decodeLocalImage(file(png()),{decodeBitmap:async()=>({width:2,height:1,close(){}}),createCanvas:a.createCanvas}),{code:'IMAGE_PNG_TOO_LARGE'});
  assert.equal(a.canvas.width,0);
  await assert.rejects(decodeLocalImage(file(orientedJpeg),{decodeBitmap:async()=>({width:2,height:3,close(){}})}),{code:'IMAGE_ORIENTATION_INVALID'});
});
test('abort releases current and late bitmap/canvas resources, including cancellation after preview',async()=>{
  const early=new AbortController();early.abort();await assert.rejects(decodeLocalImage(file(png()),{signal:early.signal}),{code:'IMAGE_ABORTED'});
  let deliver,closed=0;const controller=new AbortController();
  const pending=decodeLocalImage(file(png()),{signal:controller.signal,decodeBitmap:()=>new Promise(resolve=>{deliver=resolve;})});
  while(!deliver)await new Promise(resolve=>setImmediate(resolve));controller.abort();await assert.rejects(pending,{code:'IMAGE_ABORTED'});
  deliver({width:2,height:1,close(){closed++;}});await new Promise(resolve=>setImmediate(resolve));assert.equal(closed,1);
  const a=canvasAdapter(),c=new AbortController();
  const result=await decodeLocalImage(file(png()),{signal:c.signal,decodeBitmap:async()=>({width:2,height:1,close(){}}),createCanvas:a.createCanvas});
  c.abort();assert.equal(a.canvas.width,0);result.dispose();
  const failed=canvasAdapter(2,1,{encodeError:true});
  await assert.rejects(decodeLocalImage(file(png()),{decodeBitmap:async()=>({width:2,height:1,close(){}}),createCanvas:failed.createCanvas}),{code:'IMAGE_DECODE_FAILED'});assert.equal(failed.canvas.width,0);
});
test('cancel during native encoding releases the canvas promptly; decode/context failures reveal no parser details',async()=>{
  const a=canvasAdapter(),controller=new AbortController();let finishEncode;
  a.canvas.convertToBlob=()=>new Promise(resolve=>{finishEncode=resolve;});
  const pending=decodeLocalImage(file(png()),{signal:controller.signal,decodeBitmap:async()=>({width:2,height:1,close(){}}),createCanvas:a.createCanvas});
  while(!finishEncode)await new Promise(resolve=>setImmediate(resolve));controller.abort();await assert.rejects(pending,{code:'IMAGE_ABORTED'});assert.equal(a.canvas.width,0);finishEncode(file(png()));
  await assert.rejects(decodeLocalImage(file(png()),{decodeBitmap:async()=>{throw Error('private parser trace');}}),{code:'IMAGE_DECODE_FAILED',message:'IMAGE_DECODE_FAILED'});
  let closes=0;const badCanvas={width:2,height:1,getContext(){return null;}};
  await assert.rejects(decodeLocalImage(file(png()),{decodeBitmap:async()=>({width:2,height:1,close(){closes++;}}),createCanvas:()=>badCanvas}),{code:'IMAGE_DECODE_FAILED'});assert.equal(closes,1);assert.equal(badCanvas.width,0);
});
function content(pdf,page) {const raw=page.node.get(n('Contents'));if(!raw)return [];const value=pdf.context.lookup(raw);return (value instanceof PDFArray?value.asArray():[raw]).map(ref=>Buffer.from(decodePDFRawStream(pdf.context.lookup(ref)).decode()).toString());}
async function pdfFixture(rotation=0) {
  const pdf=await PDFDocument.create(),first=pdf.addPage([300,220]),other=pdf.addPage([300,220]);
  first.setMediaBox(-30,10,300,220);first.setCropBox(20,30,200,160);first.setRotation(degrees(rotation));first.node.set(n('UserUnit'),PDFNumber.of(2));
  first.drawRectangle({x:30,y:40,width:20,height:10});other.drawRectangle({x:70,y:80,width:10,height:20});
  const parent=first.node.Parent(),shared=first.node.Resources();parent.set(n('Resources'),shared);first.node.delete(n('Resources'));other.node.delete(n('Resources'));
  const annot=pdf.context.register(pdf.context.obj({Type:'Annot',Subtype:'Text',Rect:[20,30,30,40],Contents:'keep'}));first.node.addAnnot(annot);
  return pdf;
}
for(const rotation of [0,90,180,270])test(`serialized current-page image has predicted ${rotation} degree matrix; sibling and prior operators survive`,async()=>{
  const pdf=await pdfFixture(rotation),bytes=await pdf.save(),original=bytes.slice(),before=await loadLocalPdf(bytes),beforeContent=content(before,before.getPage(0)),siblingContent=content(before,before.getPage(1)),siblingResources=before.getPage(1).node.Resources().toString();
  const rect={left:20,top:40,width:100,height:60};const result=await writeImage(bytes,png(),{destination:'current-page',pageIndex:0,rect});
  const out=await loadLocalPdf(result.bytes),[page,sibling]=out.getPages(),streams=content(out,page);
  for(const operators of beforeContent)assert.ok(streams.includes(operators));
  assert.deepEqual(content(out,sibling),siblingContent);assert.equal(sibling.node.Resources().toString(),siblingResources);
  assert.equal(page.node.lookup(n('Annots'),PDFArray).size(),1);assert.equal(page.node.Resources().lookup(n('XObject'),PDFDict).keys().length,1);
  const images=page.node.Resources().lookup(n('XObject'),PDFDict);const image=out.context.lookup(images.get(images.keys()[0]));assert.equal(image.dict.get(n('Subtype')),n('Image'));assert.equal(image.dict.get(n('Width')).asNumber(),2);
  assert.ok(streams.some(stream=>stream.includes(placementMatrix(rect,describePage(before,0)).join(' ')+' cm')&&/\/Image[^\s]* Do/.test(stream)));
  assert.deepEqual(result.localMetadata.pages,out.getPages().map((_,i)=>describePage(out,i)));assert.equal(result.selectedPage,0);assert.deepEqual(bytes,original);
});
test('new image pages inherit geometry and fit centered; signed gate and decrypted output metadata are explicit',async()=>{
  for(const position of ['before','after']) {
    const pdf=await pdfFixture(90),bytes=await pdf.save(),result=await writeImage(bytes,png(),{destination:'new-page',pageIndex:0,position});
    const out=await loadLocalPdf(result.bytes),index=position==='before'?0:1;assert.equal(out.getPageCount(),3);assert.equal(result.selectedPage,index);assert.deepEqual(describePage(out,index),describePage(pdf,0));
    assert.ok(content(out,out.getPage(index)).some(s=>s.includes(placementMatrix(fitImage({width:2,height:1},describePage(out,index)),describePage(out,index)).join(' ')+' cm')));
  }
  const pdf=await pdfFixture();pdf.catalog.set(n('AcroForm'),pdf.context.obj({SigFlags:1,Fields:[]}));pdf.encrypt({userPassword:'páss🔑',ownerPassword:'owner'});const bytes=await pdf.save();
  await assert.rejects(writeImage(bytes,png(),{destination:'current-page',pageIndex:0,rect:{left:0,top:0,width:10,height:10}}),{code:'PASSWORD_REQUIRED'});
  await assert.rejects(writeImage(bytes,png(),{password:'páss🔑',destination:'current-page',pageIndex:0,rect:{left:0,top:0,width:10,height:10}}),{code:'SIGNATURE_ACK_REQUIRED'});
  const result=await writeImage(bytes,png(),{password:'páss🔑',acknowledged:true,destination:'current-page',pageIndex:0,rect:{left:0,top:0,width:10,height:10}});
  assert.equal(result.localMetadata.signed,true);assert.equal(result.localMetadata.encrypted,false);assert.ok(result.notices.some(n=>n.code==='ENCRYPTED_COPY_UNLOCKED'));await loadLocalPdf(result.bytes);
});
test('image failures return no output and source buffers remain immutable; modules have no network path',async()=>{
  const pdf=await pdfFixture(),bytes=await pdf.save(),original=bytes.slice();
  for(const options of [{destination:'current-page',pageIndex:8,rect:{}},{destination:'current-page',pageIndex:0,rect:{left:-1,top:0,width:2,height:1}},{destination:'new-page',pageIndex:0,position:'bad'},{destination:'bad',pageIndex:0}])await assert.rejects(writeImage(bytes,png(),options));
  await assert.rejects(writeImage(bytes,new Uint8Array([1,2]),{destination:'new-page',pageIndex:0,position:'after'}));assert.deepEqual(bytes,original);
  for(const path of ['images.mjs','imageGeometry.mjs'])assert.doesNotMatch(await readFile(new URL(path,import.meta.url),'utf8'),/\bfetch\s*\(|XMLHttpRequest|ignoreEncryption/);
});
test('existing AcroForm appearance streams and their references survive image save exactly',async()=>{
  const pdf=await pdfFixture(),page=pdf.getPage(0),form=pdf.getForm(),field=form.createTextField('preserved');field.setText('retained');field.addToPage(page,{x:30,y:40,width:70,height:20});
  const bytes=await pdf.save(),before=await loadLocalPdf(bytes);
  const appearances=doc=>doc.getForm().getTextField('preserved').acroField.getWidgets().map(widget=>{const raw=widget.dict.lookup(n('AP'),PDFDict).get(n('N'));return {ref:String(raw),bytes:Buffer.from(doc.context.lookup(raw).getContents()).toString('hex')};});
  const expected=appearances(before),result=await writeImage(bytes,png(),{destination:'current-page',pageIndex:0,rect:{left:10,top:10,width:20,height:10}}),out=await loadLocalPdf(result.bytes);
  assert.deepEqual(appearances(out),expected);assert.equal(out.getForm().getTextField('preserved').getText(),'retained');
});
test('real 600 by 782 PNG fits and serializes on a new Letter image page',async()=>{
  const pdf=await PDFDocument.create();pdf.addPage([612,792]);
  const rgba=Buffer.alloc(600*782*4,255),source=png(600,782,rgba);
  const result=await writeImage(await pdf.save(),source,{destination:'new-page',pageIndex:0,position:'after'}),out=await loadLocalPdf(result.bytes),page=out.getPage(1);
  assert.equal(result.selectedPage,1);assert.equal(out.getPageCount(),2);
  const images=page.node.Resources().lookup(n('XObject'),PDFDict),image=out.context.lookup(images.get(images.keys()[0]));
  assert.equal(image.dict.get(n('Width')).asNumber(),600);assert.equal(image.dict.get(n('Height')).asNumber(),782);
  const rect=fitImage({width:600,height:782},describePage(out,1));assert.equal(rect.top,0);assert.equal(rect.height,792);
  assert.ok(content(out,page).some(s=>s.includes(placementMatrix(rect,describePage(out,1)).join(' ')+' cm')));
});

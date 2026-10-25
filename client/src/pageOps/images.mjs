import {PDFName,PDFNumber,degrees} from '@cantoo/pdf-lib';
import {loadLocalPdf,describePage,isolatePageResources,inspectSignatures,MAX_LOCAL_PDF_BYTES,pdfError} from './pdfDocument.mjs';
import {fitImage,placementMatrix} from './imageGeometry.mjs';

export const MAX_IMAGE_BYTES=20*1024*1024;
export const MAX_IMAGE_PIXELS=16000000;
export const MAX_IMAGE_DIMENSION=16384;
export const MAX_IMAGE_PNG_BYTES=64*1024*1024;
export const IMAGE_ERROR_CODES=Object.freeze(['HEIC_CONVERSION_REQUIRED','IMAGE_UNSUPPORTED','IMAGE_INVALID','IMAGE_ANIMATED','IMAGE_AMBIGUOUS','IMAGE_TOO_LARGE','IMAGE_DIMENSIONS_EXCEEDED','IMAGE_PNG_TOO_LARGE','IMAGE_ORIENTATION_INVALID','IMAGE_ABORTED','IMAGE_DECODE_FAILED','IMAGE_RECT_INVALID','IMAGE_OUTSIDE_PAGE','IMAGE_SIZE_INVALID','IMAGE_ASPECT_INVALID']);
const refuse=code=>{throw pdfError(code);};
const text=(bytes,start,length)=>String.fromCharCode(...bytes.subarray(start,start+length));
function dimensions(width,height) {
  if(!Number.isInteger(width)||!Number.isInteger(height)||width<=0||height<=0)refuse('IMAGE_INVALID');
  if(width>MAX_IMAGE_DIMENSION||height>MAX_IMAGE_DIMENSION||width*height>MAX_IMAGE_PIXELS)refuse('IMAGE_DIMENSIONS_EXCEEDED');
}
/** Read orientation, never rotate pixels here. Native from-image applies it once. */
function orientation(bytes) {
  if(text(bytes,0,6)==='Exif\0\0')bytes=bytes.subarray(6);
  if(bytes.length<8)refuse('IMAGE_INVALID');
  const little=text(bytes,0,2)==='II';
  if(!little&&text(bytes,0,2)!=='MM')refuse('IMAGE_INVALID');
  const view=new DataView(bytes.buffer,bytes.byteOffset,bytes.byteLength);
  const u16=at=>{if(at<0||at+2>bytes.length)refuse('IMAGE_INVALID');return view.getUint16(at,little);};
  const u32=at=>{if(at<0||at+4>bytes.length)refuse('IMAGE_INVALID');return view.getUint32(at,little);};
  if(u16(2)!==42)refuse('IMAGE_INVALID');
  const start=u32(4),count=u16(start);if(start+2+count*12+4>bytes.length)refuse('IMAGE_INVALID');
  let found;
  for(let i=0;i<count;i++) {
    const at=start+2+i*12;
    if(u16(at)===0x112) {
      if(found!==undefined||u16(at+2)!==3||u32(at+4)!==1)refuse('IMAGE_AMBIGUOUS');
      found=u16(at+8);if(found<1||found>8)refuse('IMAGE_INVALID');
    }
  }
  return found??1;
}
/** Bounded structural preflight: dimensions before native allocation, one image
 * only, and explicit animation/ambiguous-container refusals. Native decoder
 * remains responsible for compressed-pixel validity and PNG CRC verification. */
function inspectImage(bytes) {
  if(!(bytes instanceof Uint8Array))refuse('IMAGE_INVALID');
  const view=new DataView(bytes.buffer,bytes.byteOffset,bytes.byteLength);
  const u32=(at,little=false)=>{if(at+4>bytes.length)refuse('IMAGE_INVALID');return view.getUint32(at,little);};
  let width,height,orient=1,mime;
  if(bytes.length>=12&&text(bytes,4,4)==='ftyp') {
    const end=Math.min(u32(0),bytes.length);
    for(let at=8;at+4<=end;at+=4)if(at!==12&&/^(hei[cxms]|hev[cxms]|mif1|msf1)$/.test(text(bytes,at,4)))refuse('HEIC_CONVERSION_REQUIRED');
    refuse('IMAGE_UNSUPPORTED');
  }
  if(text(bytes,0,8)==='\x89PNG\r\n\x1a\n') {
    mime='image/png';let at=8,header=false,data=false,end=false,exif=false,afterData=false;
    while(at<bytes.length) {
      const length=u32(at),kind=text(bytes,at+4,4),next=at+12+length;if(next>bytes.length)refuse('IMAGE_INVALID');
      if(['acTL','fcTL','fdAT'].includes(kind))refuse('IMAGE_ANIMATED');
      if(!header&&kind!=='IHDR')refuse('IMAGE_INVALID');
      if(kind==='IHDR') {
        if(header||length!==13)refuse('IMAGE_AMBIGUOUS');header=true;width=u32(at+8);height=u32(at+12);dimensions(width,height);
      }else if(kind==='IDAT') {if(afterData)refuse('IMAGE_AMBIGUOUS');data=true;}
      else if(data)afterData=true;
      if(kind==='eXIf') {if(exif)refuse('IMAGE_AMBIGUOUS');orient=orientation(bytes.subarray(at+8,at+8+length));exif=true;}
      if(kind==='IEND') {if(length||!data)refuse('IMAGE_INVALID');end=true;if(next!==bytes.length)refuse('IMAGE_AMBIGUOUS');break;}
      at=next;
    }
    if(!end)refuse('IMAGE_INVALID');
  }else if(text(bytes,0,4)==='RIFF'&&text(bytes,8,4)==='WEBP') {
    mime='image/webp';if(u32(4,true)+8!==bytes.length)refuse('IMAGE_AMBIGUOUS');
    let at=12,frames=0,extended=false,exif=false,frameWidth,frameHeight;
    while(at<bytes.length) {
      const kind=text(bytes,at,4),length=u32(at+4,true),start=at+8,next=start+length+(length%2);if(next>bytes.length)refuse('IMAGE_INVALID');
      if(kind==='ANIM'||kind==='ANMF')refuse('IMAGE_ANIMATED');
      if(kind==='VP8X') {
        if(extended||at!==12||length!==10)refuse('IMAGE_AMBIGUOUS');extended=true;
        if(bytes[start]&2)refuse('IMAGE_ANIMATED');
        width=1+bytes[start+4]+(bytes[start+5]<<8)+(bytes[start+6]<<16);height=1+bytes[start+7]+(bytes[start+8]<<8)+(bytes[start+9]<<16);dimensions(width,height);
      }
      if(kind==='VP8 '||kind==='VP8L') {
        if(++frames!==1)refuse('IMAGE_AMBIGUOUS');
        if(kind==='VP8L') {
          if(length<5||bytes[start]!==0x2f)refuse('IMAGE_INVALID');
          const bits=u32(start+1,true);frameWidth=(bits&0x3fff)+1;frameHeight=((bits>>>14)&0x3fff)+1;
        }else {
          if(length<10||text(bytes,start+3,3)!=='\x9d\x01\x2a')refuse('IMAGE_INVALID');
          frameWidth=(bytes[start+6]+(bytes[start+7]<<8))&0x3fff;frameHeight=(bytes[start+8]+(bytes[start+9]<<8))&0x3fff;
        }
        dimensions(frameWidth,frameHeight);
      }
      if(kind==='EXIF') {if(exif)refuse('IMAGE_AMBIGUOUS');orient=orientation(bytes.subarray(start,start+length));exif=true;}
      at=next;
    }
    if(frames!==1)refuse('IMAGE_INVALID');
    if(extended&&(frameWidth!==width||frameHeight!==height))refuse('IMAGE_AMBIGUOUS');
    width=frameWidth;height=frameHeight;
  }else if(bytes[0]===0xff&&bytes[1]===0xd8) {
    mime='image/jpeg';let at=2,frames=0,ended=false,scanned=false,exif=false;
    while(at<bytes.length) {
      if(bytes[at++]!==0xff)refuse('IMAGE_INVALID');
      while(bytes[at]===0xff)at++;
      const marker=bytes[at++];
      if(marker===0xd9){ended=true;if(at!==bytes.length)refuse('IMAGE_AMBIGUOUS');break;}
      if(marker===0xd8)refuse('IMAGE_AMBIGUOUS');
      if(at+2>bytes.length)refuse('IMAGE_INVALID');
      const length=(bytes[at]<<8)|bytes[at+1],end=at+length;if(length<2||end>bytes.length)refuse('IMAGE_INVALID');
      if(marker===0xe2&&text(bytes,at+2,4)==='MPF\0')refuse('IMAGE_AMBIGUOUS');
      if(marker===0xe1&&text(bytes,at+2,6)==='Exif\0\0') {if(exif)refuse('IMAGE_AMBIGUOUS');orient=orientation(bytes.subarray(at+2,end));exif=true;}
      if(marker>=0xc0&&marker<=0xcf&&![0xc4,0xc8,0xcc].includes(marker)) {
        if(++frames!==1)refuse('IMAGE_AMBIGUOUS');if(length<8)refuse('IMAGE_INVALID');
        height=(bytes[at+3]<<8)|bytes[at+4];width=(bytes[at+5]<<8)|bytes[at+6];dimensions(width,height);
      }
      at=end;
      if(marker===0xda) {
        scanned=true;
        // Entropy bytes may escape FF or use restart markers. Progressive JPEG
        // can return to the marker loop for another SOS, but never another SOF.
        while(at<bytes.length) {
          if(bytes[at]!==0xff){at++;continue;}
          let next=at+1;while(bytes[next]===0xff)next++;
          if(bytes[next]===0||bytes[next]>=0xd0&&bytes[next]<=0xd7){at=next+1;continue;}
          break;
        }
      }
    }
    if(!ended||frames!==1||!scanned)refuse('IMAGE_INVALID');
  }else refuse('IMAGE_UNSUPPORTED');
  dimensions(width,height);
  return {mime,width:orient>=5?height:width,height:orient>=5?width:height,orientation:orient};
}
function browserCanvas(width,height) {
  if(typeof OffscreenCanvas!=='undefined')return new OffscreenCanvas(width,height);
  if(typeof document==='undefined')refuse('IMAGE_DECODE_FAILED');
  const canvas=document.createElement('canvas');canvas.width=width;canvas.height=height;return canvas;
}
function encodeCanvas(canvas) {
  if(canvas.convertToBlob)return canvas.convertToBlob({type:'image/png'});
  return new Promise((resolve,reject)=>canvas.toBlob(blob=>blob?resolve(blob):reject(pdfError('IMAGE_DECODE_FAILED')),'image/png'));
}
function checkAbort(signal) {if(signal?.aborted)refuse('IMAGE_ABORTED');}
/** Native operations cannot be forcibly interrupted. Reject promptly, and close
 * late bitmap results. No object URLs are allocated. Caller aborts on close/stale
 * and calls dispose when replacing a successful draft. */
function cancellable(promise,signal,lateDispose=()=>{}) {
  return new Promise((resolve,reject)=>{
    const abort=()=>reject(pdfError('IMAGE_ABORTED'));
    signal?.addEventListener('abort',abort,{once:true});
    Promise.resolve(promise).then(value=>{signal?.removeEventListener('abort',abort);if(signal?.aborted){lateDispose(value);reject(pdfError('IMAGE_ABORTED'));}else resolve(value);},error=>{signal?.removeEventListener('abort',abort);reject(error);});
    if(signal?.aborted)abort();
  });
}
/** Local PNG/JPEG/WebP decode, exactly-once native EXIF normalization and white
 * compositing. preview is the actual flattened canvas, owned until dispose/abort.
 * Caps limit admitted dimensions/bytes, not the native decoder's total heap. */
export async function decodeLocalImage(file,{signal,decodeBitmap=(blob,options)=>globalThis.createImageBitmap(blob,options),createCanvas=browserCanvas}={}) {
  let bitmap,canvas,disposed=false;
  const dispose=()=>{if(disposed)return;disposed=true;signal?.removeEventListener('abort',dispose);try{bitmap?.close();}catch{}bitmap=undefined;if(canvas){canvas.width=0;canvas.height=0;}};
  try {
    checkAbort(signal);
    if(!file||!Number.isFinite(file.size)||file.size<=0||typeof file.arrayBuffer!=='function')refuse('IMAGE_INVALID');
    if(file.size>MAX_IMAGE_BYTES)refuse('IMAGE_TOO_LARGE');
    const input=await cancellable(file.arrayBuffer(),signal);checkAbort(signal);
    if(input.byteLength>MAX_IMAGE_BYTES)refuse('IMAGE_TOO_LARGE');
    const info=inspectImage(new Uint8Array(input));
    bitmap=await cancellable(decodeBitmap(new Blob([input],{type:info.mime}),{imageOrientation:'from-image'}),signal,value=>value?.close());
    checkAbort(signal);dimensions(bitmap?.width,bitmap?.height);
    if(bitmap.width!==info.width||bitmap.height!==info.height)refuse('IMAGE_ORIENTATION_INVALID');
    canvas=createCanvas(bitmap.width,bitmap.height);const context=canvas.getContext('2d');if(!context)refuse('IMAGE_DECODE_FAILED');
    const {width,height}=bitmap;context.fillStyle='#ffffff';context.fillRect(0,0,width,height);context.drawImage(bitmap,0,0);bitmap.close();bitmap=undefined;
    const blob=await cancellable(encodeCanvas(canvas),signal);checkAbort(signal);
    if(!blob||blob.size>MAX_IMAGE_PNG_BYTES)refuse('IMAGE_PNG_TOO_LARGE');
    const pngBytes=new Uint8Array(await cancellable(blob.arrayBuffer(),signal));checkAbort(signal);
    if(pngBytes.byteLength>MAX_IMAGE_PNG_BYTES)refuse('IMAGE_PNG_TOO_LARGE');
    const output=inspectImage(pngBytes);if(output.mime!=='image/png'||output.orientation!==1||output.width!==width||output.height!==height)refuse('IMAGE_DECODE_FAILED');
    signal?.addEventListener('abort',dispose,{once:true});checkAbort(signal);
    return {pngBytes,width,height,preview:canvas,dispose};
  }catch(error) {dispose();if(IMAGE_ERROR_CODES.includes(error.code))throw error;refuse('IMAGE_DECODE_FAILED');}
}
/** Pure byte mutation for the module worker (UI transaction owns publication and
 * acknowledgement). Geometry is read afresh; never trust draft page metadata. */
export async function writeImage(bytes,pngBytes,{password,destination,pageIndex,position='after',rect,acknowledged=false}={}) {
  const png=pngBytes instanceof ArrayBuffer?new Uint8Array(pngBytes):pngBytes;
  if(!(png instanceof Uint8Array))refuse('IMAGE_INVALID');if(png.byteLength>MAX_IMAGE_PNG_BYTES)refuse('IMAGE_PNG_TOO_LARGE');
  const info=inspectImage(png);if(info.mime!=='image/png'||info.orientation!==1)refuse('IMAGE_INVALID');
  const pdf=await loadLocalPdf(bytes,{password}),signed=inspectSignatures(pdf),encrypted=!!(pdf.isEncrypted||pdf.context.isDecrypted),notices=[];
  if(signed&&!acknowledged)refuse('SIGNATURE_ACK_REQUIRED');
  const adjacent=describePage(pdf,pageIndex);let selectedPage=pageIndex,page;
  if(destination==='new-page') {
    if(!['before','after'].includes(position))refuse('PAGE_COMMAND_INVALID');
    selectedPage=pageIndex+(position==='after'?1:0);
    page=pdf.insertPage(selectedPage,[adjacent.mediaBox.width,adjacent.mediaBox.height]);
    const m=adjacent.mediaBox,c=adjacent.cropBox;page.setMediaBox(m.x,m.y,m.width,m.height);page.setCropBox(c.x,c.y,c.width,c.height);page.setRotation(degrees(adjacent.rotation));page.node.set(PDFName.of('UserUnit'),PDFNumber.of(adjacent.userUnit));
    rect=fitImage(info,describePage(pdf,selectedPage));notices.push({code:'IMAGE_PAGE_INHERITED',adjacentIndex:pageIndex,...describePage(pdf,selectedPage)});
  }else if(destination==='current-page')page=pdf.getPage(pageIndex);
  else refuse('PAGE_COMMAND_INVALID');
  const matrix=placementMatrix(rect,describePage(pdf,selectedPage));
  isolatePageResources(page);
  try {const image=await pdf.embedPng(png);page.drawImage(image,{x:0,y:0,width:1,height:1,matrix});}
  catch(error){if(error.code)throw error;refuse('IMAGE_INVALID');}
  if(encrypted)notices.push({code:'ENCRYPTED_COPY_UNLOCKED'});
  const output=await pdf.save({updateFieldAppearances:false});if(output.byteLength>MAX_LOCAL_PDF_BYTES)refuse('LOCAL_PDF_TOO_LARGE');
  return {bytes:output,selectedPage,notices,localMetadata:{pageCount:pdf.getPageCount(),pages:pdf.getPages().map((_,i)=>describePage(pdf,i)),signed,encrypted:false}};
}

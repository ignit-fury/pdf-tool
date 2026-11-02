import {PDFName,PDFNumber,PDFDict,PDFArray,PDFRef,PDFRawStream,decodePDFRawStream} from '@cantoo/pdf-lib';
import {visibleRect} from './imageGeometry.mjs';
import {managedImageMatrix} from './managedImages.mjs';
const n=PDFName.of;
const MAX_BYTES=8*1024*1024,MAX_IMAGES=200,MAX_STACK=256,TOLERANCE=1e-3;
const WHITE=new Set([0,9,10,12,13,32]),DELIM=new Set('()<>[]{}/%'.split('').map(c=>c.charCodeAt(0)));
const isNumber=word=>/^[+-]?(\d+\.?\d*|\.\d+)$/.test(word);
const multiply=(m,k)=>[m[0]*k[0]+m[1]*k[2],m[0]*k[1]+m[1]*k[3],m[2]*k[0]+m[3]*k[2],m[2]*k[1]+m[3]*k[3],m[4]*k[0]+m[5]*k[2]+k[4],m[4]*k[1]+m[5]*k[3]+k[5]];
function invert([a,b,c,d,e,f]) {const det=a*d-b*c;if(!Number.isFinite(det)||Math.abs(det)<1e-12)return null;return [d/det,-b/det,-c/det,a/det,(c*f-d*e)/det,(b*e-a*f)/det];}
const fmt=v=>(Object.is(v,-0)?0:v).toFixed(6).replace(/\.?0+$/,'')||'0';
function contents(page) {const raw=page.node.get(n('Contents'));if(!raw)return [];const value=page.doc.context.lookup(raw);return value instanceof PDFArray?value.asArray():[raw];}
function decodedName(bytes,start,end) {let out='';for(let i=start;i<end;i++){if(bytes[i]===0x23&&i+2<end&&/^[0-9a-fA-F]{2}$/.test(String.fromCharCode(bytes[i+1],bytes[i+2]))){out+=String.fromCharCode(parseInt(String.fromCharCode(bytes[i+1],bytes[i+2]),16));i+=2;}else out+=String.fromCharCode(bytes[i]);}return out;}

/** Minimal content-stream walk that tracks only q/Q/cm/clip so each `Do` gets its
 * exact CTM. Inline images are skipped; anything unparseable is simply not found. */
function scan(page) {
  const context=page.doc.context,refs=contents(page),buffers=[],owned=[];let total=0;
  for(const ref of refs) {
    const stream=context.lookup(ref);let bytes;
    // Streams this module wrote earlier in the same document are not yet encoded raw streams.
    try{bytes=stream instanceof PDFRawStream?decodePDFRawStream(stream).decode():stream.getUnencodedContents();}catch{return null;}
    total+=bytes.length;if(total>MAX_BYTES)return null;
    buffers.push(bytes);owned.push(!!stream.dict?.has(n("PdfToolImage")));
  }
  const found=[],stack=[];let ctm=[1,0,0,1,0,0],clip=false,nums=[],nameToken=null;
  for(let b=0;b<buffers.length;b++) {
    const bytes=buffers[b],end=bytes.length;let i=0;
    while(i<end) {
      const c=bytes[i];
      if(WHITE.has(c)){i++;continue;}
      if(c===0x25){while(i<end&&bytes[i]!==10&&bytes[i]!==13)i++;continue;}
      if(c===0x28){let depth=0;do{if(bytes[i]===0x5c)i++;else if(bytes[i]===0x28)depth++;else if(bytes[i]===0x29)depth--;i++;}while(depth>0&&i<end);continue;}
      if(c===0x3c){if(bytes[i+1]===0x3c){i+=2;continue;}while(i<end&&bytes[i]!==0x3e)i++;i++;continue;}
      if(DELIM.has(c)&&c!==0x2f){i++;continue;}
      const start=i;i++;
      while(i<end&&!WHITE.has(bytes[i])&&!DELIM.has(bytes[i]))i++;
      if(c===0x2f){nameToken={text:decodedName(bytes,start+1,i),start,end:i};continue;}
      if(i-start>32){nums=[];nameToken=null;continue;} // no operator or number is this long
      const word=String.fromCharCode(...bytes.subarray(start,i));
      if(isNumber(word)){nums.push(parseFloat(word));if(nums.length>6)nums.shift();continue;}
      switch(word) {
        case 'q':if(stack.length>=MAX_STACK)return null;stack.push({ctm,clip});break;
        case 'Q':if(stack.length){({ctm,clip}=stack.pop());}break;
        case 'cm':if(nums.length===6)ctm=multiply(nums,ctm);break;
        case 'W':case 'W*':clip=true;break;
        case 'BI': {let j=i;while(j<end&&!(WHITE.has(bytes[j])&&bytes[j+1]===0x45&&bytes[j+2]===0x49&&(j+3>=end||WHITE.has(bytes[j+3]))))j++;i=Math.min(end,j+3);break;}
        case 'Do':if(nameToken&&!owned[b]&&found.length<MAX_IMAGES)found.push({name:nameToken.text,nameStart:nameToken.start,nameEnd:nameToken.end,start:nameToken.start,end:i,buffer:b,ctm,clipped:clip});break;
      }
      nums=[];nameToken=null;
    }
  }
  return {refs,buffers,found};
}
function imageDict(page,name) {
  const xobjects=page.node.Resources()?.lookupMaybe(n('XObject'),PDFDict),raw=xobjects?.get(n(name)),stream=raw&&page.doc.context.lookup(raw);
  if(!(stream instanceof PDFRawStream)||stream.dict.get(n('Subtype'))!==n('Image'))return null;
  const width=stream.dict.get(n('Width'))?.asNumber?.(),height=stream.dict.get(n('Height'))?.asNumber?.();
  return Number.isInteger(width)&&Number.isInteger(height)&&width>0&&height>0?{width,height}:null;
}
function describe(page,item,geometry) {
  const size=imageDict(page,item.name);if(!size||item.clipped)return null;
  const [a,b,c,d,e,f]=item.ctm,corners=[[e,f],[e+a,f+b],[e+c,f+d],[e+a+c,f+b+d]];
  const matches=(expected)=>expected.every((v,k)=>Math.abs(v-item.ctm[k])<=TOLERANCE*Math.max(1,Math.abs(v)));
  try {
    const box=visibleRect(corners,geometry),cx=box.left+box.width/2,cy=box.top+box.height/2;
    // A quarter-turn image (or any image on a rotated page) is the same upright rect, rotated.
    for(const rotation of [0,90,180,270]) {
      const [w,h]=rotation%180?[box.height,box.width]:[box.width,box.height],rect={left:cx-w/2,top:cy-h/2,width:w,height:h};
      try{if(matches(managedImageMatrix(rect,geometry,rotation)))return {rect,rotation,pixelWidth:size.width,pixelHeight:size.height};}catch{}
    }
    return null;
  }catch{return null;}
}
/** Unclipped, on-page image placements (rotation a multiple of 90°) in the page's own
 * content streams. Images inside forms, mirrored, skewed or clipped ones are not offered. */
export function readOriginalImages(page,geometry) {
  const result=scan(page);if(!result)return [];
  return result.found.flatMap(item=>{const info=describe(page,item,geometry);return info?[item]:[]}).map((item,ordinal)=>({id:`oi_${ordinal}`,original:true,...describe(page,item,geometry)}));
}
/** Rewrite one placement in place so z-order, text and every other stream stay put.
 * `key` is the XObject to draw (the original, or a freshly added replacement). */
export function rewriteOriginalImage(page,id,geometry,{rect,rotation=0,remove=false,key}) {
  const result=scan(page),fail=code=>{throw Object.assign(new Error(code),{code});};
  if(!result)fail('IMAGE_OWNERSHIP_INVALID');
  const items=result.found.filter(item=>describe(page,item,geometry)),item=items[Number(/^oi_(\d+)$/.exec(id)?.[1])];
  if(!item)fail('IMAGE_MANAGED_UNSUPPORTED');
  const bytes=result.buffers[item.buffer],original=new TextDecoder('latin1').decode(bytes.subarray(item.nameStart,item.nameEnd));
  let replacement=' ';
  if(!remove) {
    const inverse=invert(item.ctm);if(!inverse)fail('IMAGE_RECT_INVALID');
    const relative=multiply(managedImageMatrix(rect,geometry,rotation),inverse);
    replacement=`q ${relative.map(fmt).join(' ')} cm ${key?`/${key}`:original} Do Q`;
  }
  const text=new TextEncoder(),tail=text.encode(replacement),next=new Uint8Array(item.start+tail.length+bytes.length-item.end);next.set(bytes.subarray(0,item.start));next.set(tail,item.start);next.set(bytes.subarray(item.end),item.start+tail.length);
  const context=page.doc.context,stream=context.register(context.flateStream(next)),refs=result.refs.map((ref,index)=>index===item.buffer?stream:ref);
  page.node.set(n('Contents'),context.obj(refs));
  return item.name;
}

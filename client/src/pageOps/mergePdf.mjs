import {PDFObjectCopier,PDFPage,PDFName,PDFDict,PDFArray,PDFNumber,PDFNull,PDFStream,PDFString} from '@cantoo/pdf-lib';
import {loadLocalPdf,describePage,inspectSignatures,isolatePageResources,pdfError,MAX_LOCAL_PDF_BYTES} from './pdfDocument.mjs';
import {preflightMergeGraph,importMergeGraph} from './mergeGraph.mjs';

const n=PDFName.of,fail=code=>{throw pdfError(code);};
const get=(pdf,dict,key)=>pdf.context.lookup(dict.get(n(key)));
const isEncrypted=pdf=>!!(pdf.isEncrypted||pdf.context.isDecrypted);
async function identity(bytes) {
  const input=bytes instanceof Uint8Array?bytes:new Uint8Array(bytes);
  const digest=await globalThis.crypto.subtle.digest('SHA-256',input);
  return Array.from(new Uint8Array(digest),value=>value.toString(16).padStart(2,'0')).join('');
}
const geometries=pdf=>pdf.getPages().map((_,index)=>describePage(pdf,index));

/** Serializable review only; mutable PDF objects never leave this operation. */
export async function inspectPdfImport(bytes,{password,existingBytes,existingPassword,filename='import.pdf'}={}) {
  const source=await loadLocalPdf(bytes,{password}),destination=existingBytes?await loadLocalPdf(existingBytes,{password:existingPassword}):undefined;
  const signed=inspectSignatures(source),existingSigned=destination?inspectSignatures(destination):false;
  const graph=preflightMergeGraph(source,{destination,filename}),pages=geometries(source);
  if(!pages.length)fail('MERGE_EMPTY_SOURCE');
  const notices=[...graph.notices,"Keep each imported page's size and rotation."];
  if(signed)notices.push('Merging this PDF invalidates its signatures.');
  return {pageCount:pages.length,pages,signed,existingSigned,encrypted:isEncrypted(source),formCount:graph.formCount,collisionCount:graph.collisionCount,prefix:graph.prefix,bookmarkCount:graph.bookmarkCount,notices,sourceIdentity:await identity(bytes)};
}

function visibleBox(geometry) {
  const media=geometry.mediaBox,crop=geometry.cropBox,x=Math.max(media.x,crop.x),y=Math.max(media.y,crop.y);
  const width=Math.min(media.x+media.width,crop.x+crop.width)-x,height=Math.min(media.y+media.height,crop.y+crop.height)-y;
  return width>0&&height>0?{x,y,width,height}:media;
}
function fitTransform(geometry,target) {
  const width=target.visibleWidth,height=target.visibleHeight;
  if(!Number.isFinite(width)||!Number.isFinite(height)||width<=0||height<=0)fail('PAGE_GEOMETRY_INVALID');
  const fitScale=Math.min(width/geometry.visibleWidth,height/geometry.visibleHeight),scale=fitScale*geometry.userUnit;
  const tx=(width-fitScale*geometry.visibleWidth)/2,ty=(height-fitScale*geometry.visibleHeight)/2,box=visibleBox(geometry),{x,y}=box;
  const matrices={0:[scale,0,0,scale,tx-scale*x,ty-scale*y],90:[0,-scale,scale,0,tx-scale*y,ty+scale*(x+box.width)],180:[-scale,0,0,-scale,tx+scale*(x+box.width),ty+scale*(y+box.height)],270:[0,scale,-scale,0,tx+scale*(y+box.height),ty-scale*x]};
  const matrix=matrices[geometry.rotation];
  if(!matrix.every(Number.isFinite)||!Number.isFinite(fitScale)||fitScale<=0)fail('PAGE_GEOMETRY_INVALID');
  return {matrix,fitScale,scale,width,height,box,rotation:geometry.rotation};
}
const point=([a,b,c,d,e,f],x,y)=>[a*x+c*y+e,b*x+d*y+f];
const bounds=(matrix,[x0,y0,x1,y1])=>{
  const points=[point(matrix,x0,y0),point(matrix,x0,y1),point(matrix,x1,y0),point(matrix,x1,y1)];
  if(!points.flat().every(Number.isFinite))fail('MERGE_NORMALIZE_UNSUPPORTED');
  return [Math.min(...points.map(p=>p[0])),Math.min(...points.map(p=>p[1])),Math.max(...points.map(p=>p[0])),Math.max(...points.map(p=>p[1]))];
};
function numbers(pdf,value,count) {
  if(!(value instanceof PDFArray)||count!==undefined&&value.size()!==count)fail('MERGE_NORMALIZE_UNSUPPORTED');
  return value.asArray().map(raw=>{const number=pdf.context.lookup(raw);if(!(number instanceof PDFNumber)||!Number.isFinite(number.asNumber()))fail('MERGE_NORMALIZE_UNSUPPORTED');return number.asNumber();});
}
function rotateAppearance(pdf,raw,rotation) {
  const value=pdf.context.lookup(raw),ctx=pdf.context;
  if(value instanceof PDFStream) {
    const stream=value.clone(ctx),matrix=stream.dict.has(n('Matrix'))?numbers(pdf,get(pdf,stream.dict,'Matrix'),6):[1,0,0,1,0,0];
    numbers(pdf,get(pdf,stream.dict,'BBox'),4);
    const rotate={0:[1,0,0,1,0,0],90:[0,-1,1,0,0,0],180:[-1,0,0,-1,0,0],270:[0,1,-1,0,0,0]}[rotation];
    const [a,b,c,d,e,f]=matrix,[r,s,t,u]=rotate;
    stream.dict.set(n('Matrix'),ctx.obj([r*a+t*b,s*a+u*b,r*c+t*d,s*c+u*d,r*e+t*f,s*e+u*f]));
    return ctx.register(stream);
  }
  if(!(value instanceof PDFDict))fail('MERGE_NORMALIZE_UNSUPPORTED');
  const result=value.clone(ctx);for(const [key,child] of result.entries())result.set(key,rotateAppearance(pdf,child,rotation));return result;
}
function normalizePage(pdf,page,transform) {
  const ctx=pdf.context,{matrix,width,height,box,rotation,scale}=transform;
  for(const key of ['VP','Measure'])if(page.node.has(n(key)))fail('MERGE_NORMALIZE_UNSUPPORTED');
  for(const raw of page.node.Annots()?.asArray()??[]) {
    const annot=ctx.lookup(raw);if(!(annot instanceof PDFDict))fail('MERGE_NORMALIZE_UNSUPPORTED');
    const type=get(pdf,annot,'Subtype');
    if(!['Link','Widget'].some(value=>type===n(value)))fail('MERGE_NORMALIZE_UNSUPPORTED');
    for(const key of ['Popup','IRT','RD','Measure','CL','L','Vertices','InkList'])if(annot.has(n(key)))fail('MERGE_NORMALIZE_UNSUPPORTED');
    const flags=get(pdf,annot,'F');if(flags&&(!(flags instanceof PDFNumber)||(flags.asNumber()&24)))fail('MERGE_NORMALIZE_UNSUPPORTED');
    annot.set(n('Rect'),ctx.obj(bounds(matrix,numbers(pdf,get(pdf,annot,'Rect'),4))));
    if(annot.has(n('QuadPoints'))) {
      const coordinates=numbers(pdf,get(pdf,annot,'QuadPoints'));if(coordinates.length%8)fail('MERGE_NORMALIZE_UNSUPPORTED');
      const result=[];for(let i=0;i<coordinates.length;i+=2)result.push(...point(matrix,coordinates[i],coordinates[i+1]));annot.set(n('QuadPoints'),ctx.obj(result));
    }
    if(annot.has(n('Border'))) {
      const border=get(pdf,annot,'Border');if(!(border instanceof PDFArray)||![3,4].includes(border.size()))fail('MERGE_NORMALIZE_UNSUPPORTED');
      const first=numbers(pdf,ctx.obj(border.asArray().slice(0,3)),3).map(value=>value*scale);
      if(rotation%180)[first[0],first[1]]=[first[1],first[0]];
      if(border.size()===4)first.push(ctx.obj(numbers(pdf,ctx.lookup(border.get(3))).map(value=>value*scale)));
      annot.set(n('Border'),ctx.obj(first));
    }
    if(annot.has(n('BS'))) {
      const old=get(pdf,annot,'BS');if(!(old instanceof PDFDict))fail('MERGE_NORMALIZE_UNSUPPORTED');
      const style=old.clone(ctx),line=get(pdf,style,'W');if(line) {if(!(line instanceof PDFNumber))fail('MERGE_NORMALIZE_UNSUPPORTED');style.set(n('W'),ctx.obj(line.asNumber()*scale));}
      if(style.has(n('D')))style.set(n('D'),ctx.obj(numbers(pdf,get(pdf,style,'D')).map(value=>value*scale)));annot.set(n('BS'),style);
    }
    if(annot.has(n('AP')))annot.set(n('AP'),rotateAppearance(pdf,annot.get(n('AP')),rotation));
    if(type===n('Widget')) {
      const old=get(pdf,annot,'MK'),mk=old instanceof PDFDict?old.clone(ctx):ctx.obj({});
      const angle=get(pdf,mk,'R')?.asNumber()??0;if(!Number.isInteger(angle/90))fail('MERGE_NORMALIZE_UNSUPPORTED');
      mk.set(n('R'),ctx.obj(((angle-rotation)%360+360)%360));annot.set(n('MK'),mk);
    }
  }
  isolatePageResources(page);
  const original=page.node.Contents(),contents=original instanceof PDFArray?original.asArray():original?[page.node.get(n('Contents'))]:[];
  const numeric=value=>PDFNumber.of(Object.is(value,-0)?0:value).toString();
  const start=ctx.register(ctx.stream(`q\n${matrix.map(numeric).join(' ')} cm\n${[box.x,box.y,box.width,box.height].map(numeric).join(' ')} re W n\n`));
  const end=ctx.register(ctx.stream('\nQ\n'));page.node.set(n('Contents'),ctx.obj([start,...contents,end]));
  for(const key of ['BleedBox','TrimBox','ArtBox'])if(page.node.has(n(key))) {
    const transformed=bounds(matrix,numbers(pdf,get(pdf,page.node,key),4));
    const clipped=[Math.max(0,transformed[0]),Math.max(0,transformed[1]),Math.min(width,transformed[2]),Math.min(height,transformed[3])];
    if(clipped[2]<=clipped[0]||clipped[3]<=clipped[1])fail('MERGE_NORMALIZE_UNSUPPORTED');page.node.set(n(key),ctx.obj(clipped));
  }
  page.setMediaBox(0,0,width,height);page.setCropBox(0,0,width,height);page.node.set(n('Rotate'),ctx.obj(0));page.node.set(n('UserUnit'),ctx.obj(1));
}
function normalizeDestinations(source,copier,graph,transforms) {
  const all=[...graph.destinations.named.values()].map(value=>graph.destinations.destination(value));
  all.push(...graph.destinations.targets.map(target=>target.target));
  const outlines=items=>{for(const item of items) {if(item.target)all.push(item.target);outlines(item.children);}};outlines(graph.outlines);
  const seen=new Set();
  for(const original of all) {
    if(seen.has(original))continue;seen.add(original);
    const transform=transforms.get(original.get(0).toString()),array=copier.copy(original),mode=source.context.lookup(original.get(1)).decodeText();
    const values=original.asArray().slice(2).map(raw=>{const value=source.context.lookup(raw);if(value===PDFNull)return null;if(!(value instanceof PDFNumber)||!Number.isFinite(value.asNumber()))fail('MERGE_NORMALIZE_UNSUPPORTED');return value.asNumber();});
    const {matrix,rotation}=transform,[a,b,c,d,e,f]=matrix;
    let next=values,newMode=mode;
    if(mode==='XYZ') {
      const [x,y,zoom]=values;
      next=rotation%180?[y===null?null:c*y+e,x===null?null:b*x+f,zoom===null||zoom===0?zoom:zoom/transform.fitScale]:[x===null?null:a*x+e,y===null?null:d*y+f,zoom===null||zoom===0?zoom:zoom/transform.fitScale];
    }else if(mode==='FitR') {
      if(values.includes(null))fail('MERGE_NORMALIZE_UNSUPPORTED');next=bounds(matrix,values);
    }else if(['FitH','FitBH'].includes(mode)) {
      next=[values[0]===null?null:rotation%180?c*values[0]+e:d*values[0]+f];if(rotation%180)newMode=mode==='FitH'?'FitV':'FitBV';
    }else if(['FitV','FitBV'].includes(mode)) {
      next=[values[0]===null?null:rotation%180?b*values[0]+f:a*values[0]+e];if(rotation%180)newMode=mode==='FitV'?'FitH':'FitBH';
    }
    array.set(1,n(newMode));next.forEach((value,index)=>array.set(index+2,value===null?PDFNull:PDFNumber.of(value)));
  }
}

function scaleFieldDefaults(destination,copier,graph,transforms) {
  const scales=new Map(graph.forms.fields.map(entry=>[entry.field,new Set()]));
  // Postorder aggregation is linear in fields; shared widgets cannot quietly
  // receive incompatible fixed font sizes after different page-fit transforms.
  for(const entry of [...graph.forms.fields].reverse()) {
    const values=scales.get(entry.field);
    if(entry.pageRef)values.add(transforms.get(entry.pageRef.toString()).scale);
    if(entry.parent)for(const value of values)scales.get(entry.parent).add(value);
  }
  for(const entry of graph.forms.fields) {
    const field=copier.copy(entry.field),da=get(destination,field,'DA');if(!da)continue;
    const tokens=da.decodeText().split(/\s+/),values=scales.get(entry.field);
    for(let i=0;i<tokens.length;i++)if(tokens[i]==='Tf') {
      const size=Number(tokens[i-1]);if(size===0)continue;
      if(values.size>1)fail('MERGE_NORMALIZE_UNSUPPORTED');
      if(values.size)tokens[i-1]=PDFNumber.of(size*[...values][0]).toString();
    }
    field.set(n('DA'),PDFString.of(tokens.join(' ')));
  }
}

/** Atomic local merge: load fresh bytes, recheck all gates, copy refs first, save once. */
export async function mergePdf(destinationBytes,sourceBytes,{password,sourcePassword,filename='import.pdf',position,normalizeTo=null,acknowledged=false,sourceAcknowledged=false,sourceIdentity}={}) {
  const destination=await loadLocalPdf(destinationBytes,{password}),source=await loadLocalPdf(sourceBytes,{password:sourcePassword});
  const signed=inspectSignatures(destination),sourceSigned=inspectSignatures(source);
  if(signed&&!acknowledged)fail('SIGNATURE_ACK_REQUIRED');if(sourceSigned&&!sourceAcknowledged)fail('SOURCE_SIGNATURE_ACK_REQUIRED');
  if(sourceIdentity!==undefined&&sourceIdentity!==await identity(sourceBytes))fail('MERGE_SOURCE_CHANGED');
  position??=destination.getPageCount();if(!Number.isInteger(position)||position<0||position>destination.getPageCount())fail('PAGE_INDEX_INVALID');
  const pages=geometries(source);if(!pages.length)fail('MERGE_EMPTY_SOURCE');geometries(destination);
  const graph=preflightMergeGraph(source,{destination,filename}),copier=PDFObjectCopier.for(source.context,destination.context),pageMap=new Map();
  for(const page of source.getPages())pageMap.set(page.ref,copier.copy(page.ref));
  const imported=[...pageMap.values()].map(ref=>PDFPage.of(destination.context.lookup(ref),ref,destination));
  imported.forEach((page,index)=>destination.insertPage(position+index,page));
  importMergeGraph({source,destination,copier,pageMap,prefix:graph.prefix,preflight:graph,filename});
  const notices=[...graph.notices];
  if(normalizeTo!==null) {
    const transforms=new Map();
    imported.forEach((page,index)=>{const transform=fitTransform(pages[index],normalizeTo);transforms.set(source.getPage(index).ref.toString(),transform);normalizePage(destination,page,transform);});
    scaleFieldDefaults(destination,copier,graph,transforms);
    normalizeDestinations(source,copier,graph,transforms);
    notices.push(`Imported pages will be resized to ${normalizeTo.visibleWidth} × ${normalizeTo.visibleHeight} pt. Check the preview before adding them.`);
  }else notices.push("Keep each imported page's size and rotation.");
  if(signed)notices.push('Editing this PDF invalidates its signatures.');if(sourceSigned)notices.push('Merging this PDF invalidates its signatures.');
  if(isEncrypted(destination)||isEncrypted(source))notices.push({code:'ENCRYPTED_COPY_UNLOCKED'});
  const bytes=await destination.save({updateFieldAppearances:false});if(bytes.byteLength>MAX_LOCAL_PDF_BYTES)fail('LOCAL_PDF_TOO_LARGE');
  return {bytes,selectedPage:position,notices,localMetadata:{pageCount:destination.getPageCount(),pages:geometries(destination),signed:signed||sourceSigned,encrypted:false}};
}

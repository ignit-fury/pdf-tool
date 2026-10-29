import {PDFName,PDFNumber,PDFDict,PDFArray,PDFRef,PDFRawStream,decodePDFRawStream} from '@cantoo/pdf-lib';
import {placementMatrix} from './imageGeometry.mjs';
const n=PDFName.of;
const fail=code=>{throw Object.assign(new Error(code),{code});};
const invalid=()=>fail('IMAGE_OWNERSHIP_INVALID');
const number=value=>PDFNumber.of(Object.is(value,-0)?0:value).toString();
const geometryValues=g=>[...['mediaBox','cropBox'].flatMap(key=>['x','y','width','height'].map(field=>g[key][field])),g.userUnit,g.rotation];
function geometryFrom(values) {if(values.length!==10||!values.every(Number.isFinite))invalid();const [x,y,width,height,cx,cy,cw,ch,userUnit,rotation]=values;return {mediaBox:{x,y,width,height},cropBox:{x:cx,y:cy,width:cw,height:ch},userUnit,rotation};}
function readNumbers(value,length) {if(!(value instanceof PDFArray)||value.size()!==length)invalid();return value.asArray().map(v=>{if(!(v instanceof PDFNumber)||!Number.isFinite(v.asNumber()))invalid();return v.asNumber();});}
function normalizeRotation(rotation) {if(!Number.isFinite(rotation)||Math.abs(rotation)>360000)fail('IMAGE_ROTATION_INVALID');return ((rotation%360)+360)%360;}
/** Clockwise physical rotation about the unrotated rectangle's center. */
export function managedImageMatrix(rect,geometry,rotation=0) {
 const angle=normalizeRotation(rotation)*Math.PI/180,c=Math.cos(angle),s=Math.sin(angle),{left,top,width:w,height:h}=rect??{};
 if(![left,top,w,h].every(Number.isFinite)||w<=0||h<=0)fail('IMAGE_RECT_INVALID');
 const cx=left+w/2,cy=top+h/2;
 // Check every rotated corner against the visible physical page bounds.
 const m=geometry.mediaBox,k=geometry.cropBox;let pw=Math.min(m.x+m.width,k.x+k.width)-Math.max(m.x,k.x),ph=Math.min(m.y+m.height,k.y+k.height)-Math.max(m.y,k.y);if(pw<=0||ph<=0){pw=m.width;ph=m.height;}pw*=geometry.userUnit;ph*=geometry.userUnit;if(geometry.rotation%180)[pw,ph]=[ph,pw];
 const epsilon=16*Number.EPSILON*Math.max(pw,ph);
 for(const x of [-w/2,w/2])for(const y of [-h/2,h/2]){const px=cx+x*c-y*s,py=cy+x*s+y*c;if(px< -epsilon||py< -epsilon||px>pw+epsilon||py>ph+epsilon)fail('IMAGE_OUTSIDE_PAGE');}
 if(normalizeRotation(rotation)===0)return placementMatrix(rect,geometry);
 const full=placementMatrix({left:0,top:0,width:pw,height:ph},geometry),rx=full[0]/pw,ry=full[1]/pw,ux=full[2]/ph,uy=full[3]/ph;
 const a=rx*w,b=ry*w,d=ux*h,e=uy*h,tx=full[4]+rx*left+ux*(ph-top-h),ty=full[5]+ry*left+uy*(ph-top-h);
 const A=(rx*c-ux*s)*w,B=(ry*c-uy*s)*w,D=(rx*s+ux*c)*h,E=(ry*s+uy*c)*h;
 const matrix=[A,B,D,E,tx+(a+d-A-D)/2,ty+(b+e-B-E)/2].map(v=>Object.is(v,-0)?0:v);
 if(!matrix.every(Number.isFinite))fail('IMAGE_RECT_INVALID');return matrix;
}
function canonical(rect,rotation,geometry,key) {const body=`q\n${managedImageMatrix(rect,geometry,rotation).map(number).join(' ')} cm\n/${key.decodeText()} Do\nQ\n`;if(body.length>4096)fail('IMAGE_RECT_INVALID');return body;}
function contents(page) {const raw=page.node.get(n('Contents'));if(!raw)return [];const value=page.doc.context.lookup(raw);if(value instanceof PDFArray){if(value.size()>100000)invalid();return value.asArray();}return [raw];}
function ownership(page,ref) {
 const context=page.doc.context,stream=context.lookup(ref),meta=stream?.dict?.get(n('PdfToolImage'));if(!meta)return undefined;
 if(!(ref instanceof PDFRef)||!(stream instanceof PDFRawStream)||stream.dict.keys().some(key=>key!==n('Length')&&key!==n('PdfToolImage')&&key!==n('Filter'))||stream.contents.length>4096||!(meta instanceof PDFDict))invalid();
 const filter=stream.dict.get(n('Filter'));if(filter&&filter!==n('FlateDecode'))invalid();
 const id=meta.get(n('Id'));if(!(id instanceof PDFName)||!/^mi_[a-zA-Z0-9_-]{8,80}$/.test(id.decodeText())||meta.get(n('Version'))?.asNumber?.()!==1)invalid();
 const values=readNumbers(meta.get(n('Rect')),4),rect=Object.fromEntries(['left','top','width','height'].map((key,i)=>[key,values[i]]));const rotation=meta.get(n('Rotation'))?.asNumber?.();if(normalizeRotation(rotation)!==rotation)invalid();const geometry=geometryFrom(readNumbers(meta.get(n('Geometry')),10));
 const key=meta.get(n('XObject')),imageRef=meta.get(n('Image'));if(!(key instanceof PDFName)||!new RegExp(`^ImageManaged${id.decodeText()}_[a-zA-Z0-9_-]{8,80}$`).test(key.decodeText())||!(imageRef instanceof PDFRef))invalid();
 const resources=page.node.Resources(),xobjects=resources?.lookupMaybe(n('XObject'),PDFDict),actual=xobjects?.get(key);if(!(actual instanceof PDFRef)||String(actual)!==String(imageRef))invalid();
 const image=context.lookup(imageRef);if(!(image instanceof PDFRawStream)||image.dict.get(n('Subtype'))!==n('Image'))invalid();
 const pixelWidth=image.dict.get(n('Width'))?.asNumber?.(),pixelHeight=image.dict.get(n('Height'))?.asNumber?.();if(![pixelWidth,pixelHeight].every(v=>Number.isInteger(v)&&v>0&&v<=16384)||pixelWidth*pixelHeight>16000000)invalid();
 const expected=canonical(rect,rotation,geometry,key);let decoded=stream.contents;
 if(filter) {
   const decoder=decodePDFRawStream(stream),reserve=decoder.ensureBuffer.bind(decoder);
   // Flate readBlock can expand a whole block even for getBytes(n). Bound its
   // allocator before decoding; the pinned decoder rounds this to at most 8 KiB.
   // This also refuses oversized stored blocks and compressed expansion bombs.
   decoder.ensureBuffer=size=>{if(size>8192)invalid();return reserve(size);};
   decoded=decoder.getBytes(expected.length+1);
 }
 if(decoded.length!==expected.length||decoded.some((v,i)=>v!==expected.charCodeAt(i)))invalid();
 return {id:id.decodeText(),rect,rotation,pixelWidth,pixelHeight,ref,key,imageRef,geometry};
}
function present(record,current) {
 const prior=record.geometry,old=geometryValues(prior),now=geometryValues(current);if(old.slice(0,9).some((v,i)=>v!==now[i]))invalid();
 const delta=((current.rotation-prior.rotation)%360+360)%360;let rect={...record.rect},rotation=record.rotation;
 if(delta){const unit=prior.userUnit,m=prior.mediaBox,c=prior.cropBox;let w=Math.min(m.x+m.width,c.x+c.width)-Math.max(m.x,c.x),h=Math.min(m.y+m.height,c.y+c.height)-Math.max(m.y,c.y);if(w<=0||h<=0){w=m.width;h=m.height;}w*=unit;h*=unit;if(prior.rotation%180)[w,h]=[h,w];const x=rect.left+rect.width/2,y=rect.top+rect.height/2;const center=delta===90?[h-y,x]:delta===180?[w-x,h-y]:[y,w-x];rect.left=center[0]-rect.width/2;rect.top=center[1]-rect.height/2;rotation=(rotation+delta)%360;}
 return {id:record.id,rect,rotation,pixelWidth:record.pixelWidth,pixelHeight:record.pixelHeight};
}
/** Only exact standalone owned drawing streams are offered for editing. Foreign
 * and damaged streams remain untouched and do not prevent ordinary PDF viewing. */
export function readManagedImages(page,geometry) {
 let refs;try{refs=contents(page);}catch{return [];}
 const records=[],counts=new Map();for(const ref of refs){try{const record=ownership(page,ref);if(record){records.push(record);counts.set(record.id,(counts.get(record.id)??0)+1);}}catch{}}
 return records.filter(r=>counts.get(r.id)===1).flatMap(record=>{try{return [present(record,geometry)];}catch{return [];}});
}
export function findManagedImage(page,id,geometry) {
 if(typeof id!=='string')fail('IMAGE_MANAGED_UNSUPPORTED');const matches=[];
 for(const ref of contents(page)){const meta=page.doc.context.lookup(ref)?.dict?.get(n('PdfToolImage'));if(meta instanceof PDFDict&&meta.get(n('Id'))?.decodeText?.()===id){let record;try{record=ownership(page,ref);present(record,geometry);}catch{invalid();}matches.push(record);}}
 if(matches.length>1)invalid();if(!matches.length)fail('IMAGE_MANAGED_UNSUPPORTED');return matches[0];
}
/** Caller isolates resources and embeds replacement pixels before attachment.
 * Never rewrite/delete an old XObject: it may be shared by unrelated streams. */
export function attachManagedImage(pdf,page,image,rect,geometry,{id=`mi_${globalThis.crypto.randomUUID()}`,rotation=0,replace}={}) {
 rotation=normalizeRotation(rotation);const key=n(`ImageManaged${id}_${globalThis.crypto.randomUUID()}`),body=canonical(rect,rotation,geometry,key),context=pdf.context;
 const meta=context.obj({Version:1,Id:n(id),Rect:[rect.left,rect.top,rect.width,rect.height],Rotation:rotation,Geometry:geometryValues(geometry),XObject:key,Image:image.ref});
 page.node.setXObject(key,image.ref);
 const stream=context.register(context.stream(body,{PdfToolImage:meta}));
 const refs=contents(page);if(replace){const next=refs.map(ref=>String(ref)===String(replace.ref)?stream:ref);page.node.set(n('Contents'),context.obj(next));}else{page.node.set(n('Contents'),context.obj(refs));page.node.normalize();page.node.addContentStream(stream);}
 return id;
}
export function removeManagedImage(page,record) {page.node.set(n('Contents'),page.doc.context.obj(contents(page).filter(ref=>String(ref)!==String(record.ref))));}

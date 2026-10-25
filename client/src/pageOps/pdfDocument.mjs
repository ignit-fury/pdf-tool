import {PDFDocument, PDFName, PDFDict, PDFArray, PDFNumber, PDFRef, PDFNull, degrees} from '@cantoo/pdf-lib';

export const MAX_LOCAL_PDF_BYTES=50*1024*1024;
export const GRAPH_MAX_DEPTH=64;
export const GRAPH_MAX_NODES=100000;
const name=value=>PDFName.of(value);
export function pdfError(code) {return Object.assign(new Error(code),{code});}
function refuse(code) {throw pdfError(code);}
function checkBytes(bytes) {
  if(!(bytes instanceof Uint8Array)&&!(bytes instanceof ArrayBuffer))refuse('PDF_INPUT_INVALID');
  if(bytes.byteLength>MAX_LOCAL_PDF_BYTES)refuse('LOCAL_PDF_TOO_LARGE');
}
/** Actual password decryption. Inputs remain caller-owned and must be immutable. */
export async function loadLocalPdf(bytes,{password}={}) {
  checkBytes(bytes);
  try {return await PDFDocument.load(bytes,{password,updateMetadata:false});}
  catch(error) {
    if(error.name==='EncryptedPDFError'||/encrypted/i.test(error.message))refuse('PASSWORD_REQUIRED');
    if(/password/i.test(error.name+' '+error.message))refuse(password===undefined?'PASSWORD_REQUIRED':'PASSWORD_INVALID');
    refuse('PDF_INVALID');
  }
}
function pageAt(pdf,index) {
  if(!Number.isInteger(index)||index<0||index>=pdf.getPageCount())refuse('PAGE_INDEX_INVALID');
  return pdf.getPage(index);
}
/** Raw boxes plus pdf.js scale-1 visible physical dimensions (crop ∩ media × UserUnit). */
export function describePage(pdf,index) {
  const page=pageAt(pdf,index),mediaBox=page.getMediaBox(),cropBox=page.getCropBox();
  const unit=page.node.lookupMaybe(name('UserUnit'),PDFNumber)?.asNumber()??1;
  const angle=page.getRotation().angle,rotation=((angle%360)+360)%360;
  for(const box of [mediaBox,cropBox])if(!Object.values(box).every(Number.isFinite)||box.width<=0||box.height<=0)refuse('PAGE_GEOMETRY_INVALID');
  if(!Number.isFinite(unit)||unit<=0||!Number.isInteger(rotation/90))refuse('PAGE_GEOMETRY_INVALID');
  const width=Math.max(0,Math.min(mediaBox.x+mediaBox.width,cropBox.x+cropBox.width)-Math.max(mediaBox.x,cropBox.x));
  const height=Math.max(0,Math.min(mediaBox.y+mediaBox.height,cropBox.y+cropBox.height)-Math.max(mediaBox.y,cropBox.y));
  // pdf.js falls back to MediaBox for a disjoint/empty crop.
  const w=(width&&height?width:mediaBox.width)*unit,h=(width&&height?height:mediaBox.height)*unit;
  return {mediaBox,cropBox,userUnit:unit,rotation,visibleWidth:rotation%180?h:w,visibleHeight:rotation%180?w:h};
}
/** Bounded field-tree traversal; malformed, repeated or cyclic field identities fail closed. */
export function inspectSignatures(pdf) {
  try {
    const raw=pdf.catalog.get(name('AcroForm'));
    if(!raw)return false;
    const form=pdf.context.lookup(raw);
    if(!(form instanceof PDFDict))refuse('SIGNATURE_UNKNOWN');
    const flags=form.get(name('SigFlags'));
    if(flags&&!(pdf.context.lookup(flags) instanceof PDFNumber))refuse('SIGNATURE_UNKNOWN');
    let signed=!!((flags?pdf.context.lookup(flags).asNumber():0)&1),nodes=0;
    const seen=new Set();
    const visit=(rawField,inheritedType,depth)=>{
      if(depth>GRAPH_MAX_DEPTH||++nodes>GRAPH_MAX_NODES)refuse('SIGNATURE_UNKNOWN');
      const field=pdf.context.lookup(rawField);
      if(!(field instanceof PDFDict)||seen.has(field))refuse('SIGNATURE_UNKNOWN');
      seen.add(field);
      const ft=field.get(name('FT'))?pdf.context.lookup(field.get(name('FT'))):inheritedType;
      if(ft&&!(ft instanceof PDFName))refuse('SIGNATURE_UNKNOWN');
      const value=field.get(name('V'));
      if(ft===name('Sig')&&value&&pdf.context.lookup(value)!==PDFNull) {
        if(!(pdf.context.lookup(value) instanceof PDFDict))refuse('SIGNATURE_UNKNOWN');
        signed=true;
      }
      const kids=field.get(name('Kids'));
      if(kids) {
        const array=pdf.context.lookup(kids);
        if(!(array instanceof PDFArray))refuse('SIGNATURE_UNKNOWN');
        for(const item of array.asArray())visit(item,ft,depth+1);
      }
    };
    const fields=form.get(name('Fields'));
    if(fields) {
      const array=pdf.context.lookup(fields);
      if(!(array instanceof PDFArray))refuse('SIGNATURE_UNKNOWN');
      for(const field of array.asArray())visit(field,undefined,0);
    }
    return signed;
  }catch(error) {if(error.code==='SIGNATURE_UNKNOWN')throw error;refuse('SIGNATURE_UNKNOWN');}
}
/** Local-only metadata, including encryption on original input even after successful decryption. */
export async function inspectLocalPdf(bytes,options={}) {
  const pdf=await loadLocalPdf(bytes,options);
  return {pageCount:pdf.getPageCount(),pages:pdf.getPages().map((_,index)=>describePage(pdf,index)),signed:inspectSignatures(pdf),encrypted:!!(pdf.isEncrypted||pdf.context.isDecrypted)};
}
/** Clone resolved mutable resource dictionaries; referenced streams stay immutable/shared. */
export function isolatePageResources(page) {
  const context=page.doc.context,resources=page.node.Resources();
  const clone=resources?resources.clone(context):context.obj({});
  for(const key of ['Font','XObject','ExtGState','ColorSpace','Pattern','Shading','Properties']) {
    const raw=clone.get(name(key));
    if(raw) {
      const dict=context.lookup(raw);
      if(!(dict instanceof PDFDict))refuse('RESOURCES_UNSAFE');
      clone.set(name(key),dict.clone(context));
    }
  }
  page.node.set(PDFName.Resources,clone);
}

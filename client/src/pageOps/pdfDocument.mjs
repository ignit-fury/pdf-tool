import {readManagedImages} from './managedImages.mjs';
import {PDFDocument, PDFName, PDFDict, PDFArray, PDFNumber, PDFRef, PDFNull, PDFString, PDFHexString, PDFParser, PDFStream, PDFRawStream, PDFInvalidObject, degrees} from '@cantoo/pdf-lib';
import {MAX_EXPORT_BYTES,admitExport} from '../exports/zip.mjs';

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
  try {
    const pdf=await PDFDocument.load(bytes,{password,updateMetadata:false});
    const invalid=pdf.context.enumerateIndirectObjects().filter(([,object])=>object instanceof PDFInvalidObject);
    if(invalid.length) {
      if(!pdf.context.isDecrypted)refuse('PDF_INVALID');
      // Cantoo 2.9.1 decrypts an unencrypted XRef stream into PDFInvalidObject.
      // Verify identity against the original parser context; never copy the obsolete
      // /Encrypt trailer into an unlocked output. All content objects must decrypt.
      const source=await PDFParser.forBytesWithOptions(bytes instanceof Uint8Array?bytes:new Uint8Array(bytes),100,false,false).parseDocument();
      for(const [ref] of invalid) {
        const original=source.lookup(ref);
        if(!(original instanceof PDFRawStream)||original.dict.get(name('Type'))!==name('XRef'))refuse('PDF_INVALID');
        pdf.context.delete(ref);
      }
    }
    return pdf;
  }
  catch(error) {
    if(error.code)throw error;
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
  if(!Number.isFinite(unit)||unit<=0||unit>75000||!Number.isInteger(rotation/90))refuse('PAGE_GEOMETRY_INVALID');
  const width=Math.max(0,Math.min(mediaBox.x+mediaBox.width,cropBox.x+cropBox.width)-Math.max(mediaBox.x,cropBox.x));
  const height=Math.max(0,Math.min(mediaBox.y+mediaBox.height,cropBox.y+cropBox.height)-Math.max(mediaBox.y,cropBox.y));
  // pdf.js falls back to MediaBox for a disjoint/empty crop.
  const w=(width&&height?width:mediaBox.width)*unit,h=(width&&height?height:mediaBox.height)*unit;
  if(!Number.isFinite(w)||!Number.isFinite(h)||w<=0||h<=0)refuse('PAGE_GEOMETRY_INVALID');
  const geometry={mediaBox,cropBox,userUnit:unit,rotation,visibleWidth:rotation%180?h:w,visibleHeight:rotation%180?w:h};
  return {...geometry,managedImages:readManagedImages(page,geometry)};
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
    const visit=(rawField,inheritedType,depth,parent)=>{
      if(depth>GRAPH_MAX_DEPTH||++nodes>GRAPH_MAX_NODES)refuse('SIGNATURE_UNKNOWN');
      const field=pdf.context.lookup(rawField);
      if(!(field instanceof PDFDict)||seen.has(field))refuse('SIGNATURE_UNKNOWN');
      seen.add(field);
      if(field.has(name('Parent'))&&pdf.context.lookup(field.get(name('Parent')))!==parent)refuse('SIGNATURE_UNKNOWN');
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
        for(const item of array.asArray())visit(item,ft,depth+1,field);
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

/** Preflight supported deletion graphs into deferred edits. Unknown destination/action,
 * field/name/outline cycles or bounds violations refuse before any edits are applied.
 * Destinations targeting the deleted page redirect to the nearest surviving page.
 * Surviving outlines keep topology/counts and surviving fields keep original references. */
function planDeletion(pdf,index) {
  const ctx=pdf.context,pages=pdf.getPages(),removed=pages[index],replacement=pages[index+1]??pages[index-1];
  const edits=[],removedFields=new Set(),seen=new Set(),destinationArrays=new Set();let count=0,redirects=0,widgets=0;
  const bad=()=>refuse('CATALOG_UNSAFE');
  const resolve=raw=>{const value=ctx.lookup(raw);if(raw&&!value)bad();return value;};
  const tick=depth=>{if(depth>GRAPH_MAX_DEPTH||++count>GRAPH_MAX_NODES)bad();};
  const dict=raw=>{const value=resolve(raw);if(!(value instanceof PDFDict))bad();return value;};
  const array=raw=>{const value=resolve(raw);if(!(value instanceof PDFArray))bad();return value;};
  const refEqual=(a,b)=>a===b||a instanceof PDFRef&&b instanceof PDFRef&&String(a)===String(b);
  const destination=(raw,depth=0)=>{
    tick(depth);const value=resolve(raw);
    if(value instanceof PDFName||value instanceof PDFString||value instanceof PDFHexString)return; // named target resolved below
    if(value instanceof PDFDict) {const d=value.get(name('D'));if(!d)bad();destination(d,depth+1);return;}
    if(!(value instanceof PDFArray)||value.size()<2)bad();
    destinationArrays.add(value);
    const target=value.get(0);
    if(!(target instanceof PDFRef)||!pages.some(p=>refEqual(p.ref,target)))bad();
    if(!(value.lookup(1) instanceof PDFName))bad();
    if(refEqual(target,removed.ref)){edits.push(()=>value.set(0,replacement.ref));redirects++;}
  };
  const action=raw=>{
    const value=dict(raw),kind=value.lookupMaybe(name('S'),PDFName);
    if(value.has(name('Next'))||kind===name('JavaScript'))bad();
    if(kind===name('GoTo')) {if(!value.has(name('D')))bad();destination(value.get(name('D')));}
    else if(!['URI','GoToR','Launch','Named'].some(item=>kind===name(item)))bad();
  };
  const targetIn=dict=>{if(dict.has(name('Dest')))destination(dict.get(name('Dest')));if(dict.has(name('A')))action(dict.get(name('A')));if(dict.has(name('AA')))bad();};
  // All explicit catalog OpenAction destinations and supported actions remain attached.
  if(pdf.catalog.has(name('OpenAction'))) {
    const raw=pdf.catalog.get(name('OpenAction')),value=resolve(raw);
    if(value instanceof PDFDict)action(raw);else destination(raw);
  }
  if(pdf.catalog.has(name('AA')))bad();
  const removedAnnots=new Set();
  const annotationOwners=new Map();
  for(const page of pages) {
    const raw=page.node.get(name('Annots'));if(!raw)continue;
    for(const annotRef of array(raw).asArray()) {
      tick(0);const annot=dict(annotRef);
      if(annotationOwners.has(annot))bad();annotationOwners.set(annot,page.ref);
      const owner=annot.get(name('P'));if(owner&&!refEqual(owner,page.ref))bad();
      if(page===removed)removedAnnots.add(annot);
      else targetIn(annot);
    }
  }
  if(pdf.catalog.has(name('AcroForm'))) {
    const form=dict(pdf.catalog.get(name('AcroForm')));
    if(form.has(name('XFA'))||form.has(name('AA')))bad();
    const visitField=(raw,depth,parent)=>{
      tick(depth);const field=dict(raw);if(seen.has(field))bad();seen.add(field);
      if(field.has(name('AA'))||field.has(name('A')))bad();
      if(parent&&field.has(name('Parent'))&&resolve(field.get(name('Parent')))!==parent)bad();
      const subtype=field.lookupMaybe(name('Subtype'),PDFName),isWidget=subtype===name('Widget');
      const pageRef=field.get(name('P')),owner=annotationOwners.get(field);
      if(isWidget) {
        if(pageRef&&owner&&!refEqual(pageRef,owner))bad();
        if(!pageRef&&!owner)bad();
        if(removedAnnots.has(field)||refEqual(pageRef,removed.ref)) {
          removedFields.add(field);widgets++;return false;
        }
        if(pageRef&&!pages.some(p=>refEqual(p.ref,pageRef)))bad();
      }
      if(field.has(name('Kids'))) {
        const kids=array(field.get(name('Kids'))),retained=kids.asArray().filter(child=>visitField(child,depth+1,field));
        if(!retained.length){removedFields.add(field);return false;}
        if(retained.length!==kids.size())edits.push(()=>field.set(name('Kids'),ctx.obj(retained)));
      }
      return true;
    };
    if(form.has(name('Fields'))) {
      const fields=array(form.get(name('Fields'))),retained=fields.asArray().filter(raw=>visitField(raw,0,null));
      if(retained.length!==fields.size())edits.push(()=>form.set(name('Fields'),ctx.obj(retained)));
    }
    if(form.has(name('CO'))) {
      const order=array(form.get(name('CO'))),retained=order.asArray().filter(raw=>!removedFields.has(resolve(raw)));
      if(retained.length!==order.size())edits.push(()=>form.set(name('CO'),ctx.obj(retained)));
    }
  }
  const outlines=pdf.catalog.get(name('Outlines'));
  if(outlines) {
    const root=dict(outlines),outlineSeen=new Set();
    const walk=(raw,parent,depth)=>{
      let previous;
      while(raw) {
        tick(depth);const item=dict(raw);if(outlineSeen.has(item))bad();outlineSeen.add(item);
        if(resolve(item.get(name('Parent')))!==parent)bad();
        if(previous&&resolve(item.get(name('Prev')))!==previous)bad();
        if(!previous&&item.has(name('Prev')))bad();
        targetIn(item);
        if(item.has(name('First')))walk(item.get(name('First')),item,depth+1);
        if(item.has(name('Last'))&&!outlineSeen.has(resolve(item.get(name('Last')))))bad();
        previous=item;raw=item.get(name('Next'));
      }
      if(parent.has(name('Last'))&&resolve(parent.get(name('Last')))!==previous)bad();
    };
    if(root.has(name('First')))walk(root.get(name('First')),root,0);
    else if(root.has(name('Last')))bad();
  }
  const oldDests=pdf.catalog.get(name('Dests'));
  if(oldDests)for(const [,dest] of dict(oldDests).entries())destination(dest);
  const names=pdf.catalog.get(name('Names'));
  if(names) {
    const root=dict(names);if(root.has(name('JavaScript')))bad();
    if(root.has(name('Dests'))) {
      const visited=new Set();
      const walk=(raw,depth)=>{
        tick(depth);const node=dict(raw);if(visited.has(node))bad();visited.add(node);
        if(node.has(name('Kids'))&&node.has(name('Names')))bad();
        if(node.has(name('Kids')))for(const child of array(node.get(name('Kids'))).asArray())walk(child,depth+1);
        if(node.has(name('Names'))) {
          const entries=array(node.get(name('Names')));if(entries.size()%2)bad();
          for(let i=1;i<entries.size();i+=2)destination(entries.get(i),depth+1);
        }
      };walk(root.get(name('Dests')),0);
    }
  }
  // Scan remaining catalog graph for unknown references to the removed page. Ordinary
  // backreferences are visited once; only recognized destination-array/widget uses may remain.
  const graphSeen=new Set();
  const scan=(raw,depth,parent,key)=>{
    tick(depth);
    if(refEqual(raw,removed.ref)) {
      const allowed=parent===removed.node||destinationArrays.has(parent)&&key===0||
        parent instanceof PDFDict&&key===name('P')&&removedFields.has(parent)||
        parent instanceof PDFArray&&pages.some(page=>page.node.Parent()?.get(name('Kids'))===parent||resolve(page.node.Parent()?.get(name('Kids')))===parent);
      if(!allowed)bad();return;
    }
    const value=resolve(raw);if(!(value instanceof PDFDict)&&!(value instanceof PDFArray)&&!(value instanceof PDFStream)||graphSeen.has(value))return;
    graphSeen.add(value);
    if(value instanceof PDFStream)scan(value.dict,depth+1,value,'dict');
    else if(value instanceof PDFArray)value.asArray().forEach((child,i)=>scan(child,depth+1,value,i));
    else for(const [k,child] of value.entries())scan(child,depth+1,value,k);
  };
  scan(pdf.catalog,0);
  return {apply:()=>edits.forEach(edit=>edit()),notices:[...(redirects?[{code:'DESTINATIONS_REDIRECTED',count:redirects}]:[]),...(widgets?[{code:'FORM_WIDGETS_REMOVED',count:widgets}]:[])]};
}

/** Same-document structural transforms; browser callers invoke in a module worker only.
 * command.type: insertBlank {adjacentIndex,position:'before'|'after'}, move {from,to},
 * rotate {index,quarterTurns}, delete {index}. All indices are zero-based.
 * Outputs are fresh unlocked bytes. Identity move/rotation returns noop without a save. */
export async function transformPages(bytes,command,{password,acknowledged=false}={}) {
  const pdf=await loadLocalPdf(bytes,{password});
  const signed=inspectSignatures(pdf),encrypted=!!(pdf.isEncrypted||pdf.context.isDecrypted),notices=[];
  if(signed&&!acknowledged)refuse('SIGNATURE_ACK_REQUIRED');
  let selectedPage;
  switch(command?.type) {
    case 'insertBlank': {
      const adjacent=describePage(pdf,command.adjacentIndex);
      if(!['before','after'].includes(command.position))refuse('PAGE_COMMAND_INVALID');
      selectedPage=command.adjacentIndex+(command.position==='after'?1:0);
      const page=pdf.insertPage(selectedPage,[adjacent.mediaBox.width,adjacent.mediaBox.height]),box=adjacent.mediaBox,crop=adjacent.cropBox;
      page.setMediaBox(box.x,box.y,box.width,box.height);
      const x=Math.max(box.x,crop.x),y=Math.max(box.y,crop.y),right=Math.min(box.x+box.width,crop.x+crop.width),top=Math.min(box.y+box.height,crop.y+crop.height);
      if(right>x&&top>y)page.setCropBox(x,y,right-x,top-y);else page.setCropBox(box.x,box.y,box.width,box.height);
      page.setRotation(degrees(adjacent.rotation));page.node.set(name('UserUnit'),PDFNumber.of(adjacent.userUnit));
      notices.push({code:'BLANK_INHERITED',adjacentIndex:command.adjacentIndex,...describePage(pdf,selectedPage)});break;
    }
    case 'move': {
      const page=pageAt(pdf,command.from);pageAt(pdf,command.to);selectedPage=command.to;
      if(command.from===command.to)return {bytes,selectedPage,notices:[],noop:true};
      // Materialize inherited attributes before reparenting across a page-tree branch.
      for(const key of ['Resources','MediaBox','CropBox','Rotate']) {
        const value=page.node.getInheritableAttribute(name(key));if(value)page.node.set(name(key),value);
      }
      pdf.removePage(command.from);pdf.context.assign(page.ref,page.node);pdf.insertPage(command.to,page);break;
    }
    case 'rotate': {
      const page=pageAt(pdf,command.index);selectedPage=command.index;
      if(!Number.isInteger(command.quarterTurns))refuse('PAGE_COMMAND_INVALID');
      if(command.quarterTurns%4===0)return {bytes,selectedPage,notices:[],noop:true};
      const angle=describePage(pdf,command.index).rotation;
      page.setRotation(degrees(((angle+command.quarterTurns*90)%360+360)%360));break;
    }
    case 'delete': {
      pageAt(pdf,command.index);if(pdf.getPageCount()===1)refuse('FINAL_PAGE');
      let deletion;
      try{deletion=planDeletion(pdf,command.index);}catch(error){if(error.code==='CATALOG_UNSAFE')throw error;refuse('CATALOG_UNSAFE');}
      deletion.apply();notices.push(...deletion.notices);pdf.removePage(command.index);selectedPage=Math.min(command.index,pdf.getPageCount()-1);break;
    }
    default:refuse('PAGE_COMMAND_INVALID');
  }
  if(encrypted)notices.push({code:'ENCRYPTED_COPY_UNLOCKED'});
  const output=await pdf.save({updateFieldAppearances:false});checkBytes(output);
  return {bytes:output,selectedPage,notices,localMetadata:{pageCount:pdf.getPageCount(),pages:pdf.getPages().map((_,i)=>describePage(pdf,i)),signed,encrypted:false}};
}

export function validateSubsetGroups(groups,pageCount) {
  if(!Array.isArray(groups)||!groups.length||groups.length>1000)refuse('EXPORT_OPTIONS_INVALID');
  let previous=-1;
  for(const group of groups) {
    if(!Array.isArray(group)||!group.length)refuse('EXPORT_OPTIONS_INVALID');
    for(const index of group) {
      if(!Number.isInteger(index)||index<=previous||index>=pageCount)refuse('EXPORT_OPTIONS_INVALID');
      previous=index;
    }
  }
}
/** Each subset owns an independent parsed source, reuses deletion graph planning and saves
 * once. Atomic aggregate refusal: no output is published until every group succeeds. */
export async function subsetPages(bytes,groups,{password,acknowledged=false,retainedBytes=0}={}) {
  checkBytes(bytes);validateSubsetGroups(groups,Number.MAX_SAFE_INTEGER);
  const sourceSize=bytes instanceof Uint8Array?bytes.buffer.byteLength:bytes.byteLength;
  admitExport(retainedBytes,sourceSize*2+MAX_EXPORT_BYTES*3);
  const files=[],notices=new Set();let total=0;
  for(const [ordinal,group] of groups.entries()) {
    const pdf=await loadLocalPdf(bytes,{password});validateSubsetGroups(groups,pdf.getPageCount());
    const signed=inspectSignatures(pdf),encrypted=!!(pdf.isEncrypted||pdf.context.isDecrypted),localNotices=[];
    if(signed&&!acknowledged)refuse('SIGNATURE_ACK_REQUIRED');
    const retained=new Set(group);
    for(let index=pdf.getPageCount()-1;index>=0;index--)if(!retained.has(index)) {
      let deletion;
      try{deletion=planDeletion(pdf,index);}catch(error){if(error.code==='CATALOG_UNSAFE')throw error;refuse('CATALOG_UNSAFE');}
      deletion.apply();localNotices.push(...deletion.notices);pdf.removePage(index);
    }
    if(signed){notices.add('SIGNATURES_INVALIDATED');localNotices.push('SIGNATURES_INVALIDATED');}
    if(encrypted){notices.add('UNLOCKED_COPY');localNotices.push('UNLOCKED_COPY');}
    admitExport(retainedBytes,sourceSize*2+total*3+MAX_EXPORT_BYTES);
    const output=await pdf.save({updateFieldAppearances:false});total+=output.byteLength;
    if(total>MAX_EXPORT_BYTES)refuse('EXPORT_LIMIT');
    admitExport(retainedBytes,sourceSize*2+total*3);
    files.push({bytes:output,filename:`split-${String(ordinal+1).padStart(4,'0')}.pdf`,mediaType:'application/pdf',notices:localNotices});
  }
  return {files,notices:[...notices]};
}

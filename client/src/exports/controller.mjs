import {passwordHeaders} from '../session.mjs';
import {renderPageImages} from './images.mjs';
import {createStoredZip,MAX_EXPORT_BYTES,admitExport,exportError} from './zip.mjs';

export const NOTICE_TEXT={
  NO_SIZE_REDUCTION:'No size reduction was achieved. The original bytes are retained for lossless compression.',
  IMAGES_SKIPPED:'Unsupported images were retained without changes.',
  UNLOCKED_COPY:'This export is an unlocked copy. Your open document keeps its original protection.',
  SIGNATURES_INVALIDATED:'Rewriting this copy invalidates its digital signatures.',
  ANNOTATIONS_FLATTENED:'Annotation appearances are now page content; supported fields are no longer interactive.',
  NO_EXTRACTABLE_TEXT:'No extractable text was found. Scanned pages need OCR, which is not included.',
  PDFA_METADATA_ADDED:'Archival PDF/A-2b identification metadata was added.',
  PDFA_OUTPUT_INTENT_ADDED:'An sRGB output profile was added for supported RGB and gray content.',
  PDFA_RESOURCES_NORMALIZED:'Page resources were made explicit for archival output.',
  DOCX_SIGNATURES_NOT_PRESERVED:'Digital signatures are not carried into Word.',
  DESTINATIONS_REDIRECTED:'Destinations to removed pages were redirected to a retained page.',
  FORM_WIDGETS_REMOVED:'Form widgets on excluded pages were removed.',
};
const serverNotices=new Set(['NO_SIZE_REDUCTION','IMAGES_SKIPPED','UNLOCKED_COPY','SIGNATURES_INVALIDATED','ANNOTATIONS_FLATTENED','NO_EXTRACTABLE_TEXT','PDFA_METADATA_ADDED','PDFA_OUTPUT_INTENT_ADDED','PDFA_RESOURCES_NORMALIZED','DOCX_SIGNATURES_NOT_PRESERVED']);
const formats={compress:['application/pdf','compressed.pdf'],flatten:['application/pdf','flattened.pdf'],text:['text/plain','document.txt'],markdown:['text/markdown','document.md'],html:['text/html','document.html'],pdfa:['application/pdf','archival.pdf'],docx:['application/vnd.openxmlformats-officedocument.wordprocessingml.document','document.docx']};
const abortError=()=>new DOMException('Export cancelled or document changed','AbortError');
const fail=()=>{throw exportError('EXPORT_RESPONSE_INVALID');};
export function explainExportError(error) {
  if(['DOCX_REVIEW_REQUIRED','DOCX_REVIEW_MISMATCH'].includes(error?.code))return 'Review this document again before converting to DOCX. The document or its analysis has changed.';
  if(error?.code==='DOCX_UNAVAILABLE')return 'DOCX is unavailable. Other export formats are still available.';
  if(error?.code==='DOCX_UNSUPPORTED')return 'This document contains text that cannot be represented safely in DOCX. Try a text export or another document.';
  if(error?.code==='PDFA_UNSUPPORTED') {
    const reasons={'font-missing':'A required font is not embedded.','font-unsupported':'This document uses an unsupported font format.','font-invalid':'An embedded font cannot be used safely.','color-unsupported':'This document uses unsupported color features.','content-unsupported':'This document contains unsupported content.','structure-unsupported':'This document uses unsupported PDF structures.','metadata-unsupported':'This document contains unsupported metadata.','pdf-version':'This PDF version is not supported for archival conversion.','limit':'This document exceeds the archival conversion limits.'};
    const reason=Object.hasOwn(reasons,error.detail?.reason_id)?reasons[error.detail.reason_id]:reasons['content-unsupported'];
    return `This PDF cannot be converted safely to PDF/A-2b. ${reason} Download the current PDF or try another document.`;
  }
  const messages={EXPORT_OPTIONS_INVALID:'Check the page ranges, format and DPI before trying again.',EXPORT_LIMIT:'This export exceeds the browser or output limit. Choose fewer pages, lower DPI or a smaller PDF.',TRANSIENT_LIMIT:'This export exceeds the browser memory limit. Download the current PDF and reopen it to release Undo memory.',LOCAL_PDF_TOO_LARGE:'Local exports support PDFs up to 50 MiB.',FLATTEN_APPEARANCE_REQUIRED:'Some annotations lack usable appearances. This PDF cannot be flattened safely.',EXPORT_UNSUPPORTED:'This document uses content that cannot be exported safely in this format.',EXPORT_RESPONSE_INVALID:'The export response was invalid. No download was prepared.',SIGNATURE_ACK_REQUIRED:'Acknowledge the signature warning before rewriting a signed PDF.',SIGNATURE_UNKNOWN:'Document signatures could not be checked safely.',CATALOG_UNSAFE:'This PDF contains page links or forms that cannot be split safely.',PASSWORD_REQUIRED:'A password is required to export this PDF.',PASSWORD_INVALID:'The document password was not accepted.',PDF_JOB_TIMEOUT:'The export took too long. Try fewer pages or a smaller document.',WORKER_TIMEOUT:'The export took too long. Try a smaller document.',WORKER_BUSY:'The server is busy. Try the export again shortly.'};
  const aliases={PASSWORD_INCORRECT:'PASSWORD_INVALID',SIGNATURE_ACKNOWLEDGEMENT_REQUIRED:'SIGNATURE_ACK_REQUIRED'};
  return messages[aliases[error?.code]||error?.code]||'This export could not be completed. Your current document and Undo history are unchanged.';
}
export function validateServerExport(data,format,beforeBytes,{retainedBytes=0}={}) {
  const spec=formats[format];
  if(!spec||!data||typeof data!=='object'||Array.isArray(data)||Object.keys(data).sort().join(',')!=='after_bytes,before_bytes,changed_images,data,filename,location,media_type,notices')fail();
  if(data.location!=='server'||data.media_type!==spec[0]||data.filename!==spec[1]||data.before_bytes!==beforeBytes||!Number.isSafeInteger(data.after_bytes)||data.after_bytes<0||data.after_bytes>MAX_EXPORT_BYTES||!Number.isSafeInteger(data.changed_images)||data.changed_images<0||!Array.isArray(data.notices)||data.notices.length>20||data.notices.some(n=>!serverNotices.has(n)))fail();
  const size=data.after_bytes;
  if(['pdfa','docx'].includes(format)&&data.changed_images!==0)fail();
  if(typeof data.data!=='string'||data.data.length!==4*Math.ceil(size/3)||/[^A-Za-z0-9+/=]/.test(data.data))fail();
  const alphabet='ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/';
  if(size%3===1&&(!data.data.endsWith('==')||(alphabet.indexOf(data.data.at(-3))&15)!==0)||size%3===2&&(!data.data.endsWith('=')||(alphabet.indexOf(data.data.at(-2))&3)!==0)||size%3===0&&data.data.includes('='))fail();
  // JSON UTF-16 base64 + atob string + decoded array + download Blob backing store.
  admitExport(retainedBytes,data.data.length*2+size*4);
  let decoded;try{decoded=atob(data.data);}catch{fail();}
  if(decoded.length!==size)fail();
  const bytes=Uint8Array.from(decoded,c=>c.charCodeAt(0));
  if(spec[0]==='application/pdf') {if(size<5||String.fromCharCode(...bytes.subarray(0,5))!=='%PDF-')fail();}
  else if(format==='docx'){if(size<4||bytes[0]!==80||bytes[1]!==75||bytes[2]!==3||bytes[3]!==4)fail();}
  else {try{new TextDecoder('utf-8',{fatal:true}).decode(bytes);}catch{fail();}}
  return {files:[{bytes,filename:spec[1],mediaType:spec[0],notices:data.notices}],notices:data.notices,beforeBytes,afterBytes:size,changedImages:data.changed_images,location:'server'};
}
const factCodes=new Set(['COLUMN_LAYOUT','AMBIGUOUS_TABLE','UNSUPPORTED_DIRECTION','IMAGE_UNSUPPORTED','NO_EXTRACTABLE_TEXT','TABLES_FLATTENED','ANNOTATIONS_OMITTED']);
export function validateDocxReview(data) {
  if(!data||Object.keys(data).sort().join(',')!=='location,policy_version,review,snapshot_sha256,source_sha256'||data.location!=='server'||data.policy_version!==1||typeof data.source_sha256!=='string'||typeof data.snapshot_sha256!=='string'||!/^[0-9a-f]{64}$/.test(data.source_sha256)||!/^[0-9a-f]{64}$/.test(data.snapshot_sha256))fail();
  const r=data.review;
  if(!r||Object.keys(r).sort().join(',')!=='facts,has_text,images_complete,page_count,schema_version,supported_ruled_tables'||r.schema_version!==1||!Number.isSafeInteger(r.page_count)||r.page_count<1||r.page_count>2000||typeof r.has_text!=='boolean'||typeof r.images_complete!=='boolean'||!Number.isSafeInteger(r.supported_ruled_tables)||r.supported_ruled_tables<0||r.supported_ruled_tables>r.page_count||!Array.isArray(r.facts)||r.facts.length>factCodes.size)fail();
  const seen=new Set();
  for(const f of r.facts){if(!f||Object.keys(f).sort().join(',')!=='code,count,pages'||!factCodes.has(f.code)||seen.has(f.code)||!Array.isArray(f.pages)||!f.pages.length||f.pages.length>r.page_count||f.pages.some((p,i)=>!Number.isSafeInteger(p)||p<0||p>=r.page_count||(i>0&&p<=f.pages[i-1]))||(f.count!==null&&(!Number.isSafeInteger(f.count)||f.count<1)))fail();seen.add(f.code);}
  if(!r.images_complete&&!seen.has('IMAGE_UNSUPPORTED')||r.images_complete&&seen.has('IMAGE_UNSUPPORTED'))fail();
  const empty=r.facts.find(f=>f.code==='NO_EXTRACTABLE_TEXT');
  if(!r.has_text&&(!empty||empty.pages.length!==r.page_count||empty.count!==r.page_count)||r.has_text&&empty?.pages.length===r.page_count)fail();
  return structuredClone(data);
}
export function describeDocxFact(fact) {
  const pages=Array.isArray(fact.pages)?fact.pages:[],where=`${pages.length} page${pages.length===1?'':'s'} (${pages.slice(0,8).map(p=>p+1).join(', ')}${pages.length>8?`, and ${pages.length-8} more`:''})`;
  const descriptions={COLUMN_LAYOUT:`Column-like layout on ${where} will become plain paragraphs in page-position order.`,AMBIGUOUS_TABLE:`Ambiguous table-like layout on ${where} will become plain paragraphs.`,UNSUPPORTED_DIRECTION:`Unsupported text directions on ${where} will become plain paragraphs.`,IMAGE_UNSUPPORTED:fact.count===null?`Image coverage is incomplete on ${where}. Some graphics may be omitted.`:`${fact.count} unsupported image${fact.count===1?'':'s'} will be omitted on ${where}.`,NO_EXTRACTABLE_TEXT:`No extractable text on ${where}. Supported images are retained; no OCR is performed.`,TABLES_FLATTENED:`${fact.count} ruled table${fact.count===1?'':'s'} will become paragraphs because of unsupported layout on ${where}.`,ANNOTATIONS_OMITTED:`${fact.count} annotation${fact.count===1?'':'s'} will not be carried into Word on ${where}.`};
  return Object.hasOwn(descriptions,fact.code)?descriptions[fact.code]:'Review this document before conversion.';
}
function validateLocal(result) {
  if(!result||!Array.isArray(result.files)||!result.files.length||result.files.length>1000)fail();
  let size=0;const names=new Set();
  for(const file of result.files) {
    if(!(file.bytes instanceof Uint8Array)||!file.bytes.length||typeof file.filename!=='string'||!/^\w[\w.-]*\.(?:png|jpg|pdf)$/.test(file.filename)||file.filename.length>100||file.filename.includes('..')||names.has(file.filename)||!['image/png','image/jpeg','application/pdf'].includes(file.mediaType))fail();
    names.add(file.filename);size+=file.bytes.byteLength;if(size>MAX_EXPORT_BYTES)throw exportError('EXPORT_LIMIT');
  }
  return size;
}
/** Orchestration owns results, cancellation and URLs; it has no editor/history writer.
 * getCurrent returns {session,bytes,version,retainedBytes}; sourceBytes is never used. */
export function createExportController({getCurrent,request,runSplit,renderImages=renderPageImages,createUrl=blob=>URL.createObjectURL(blob),revokeUrl=url=>URL.revokeObjectURL(url),onState=()=>{}}) {
  let generation=0,active=null,result=null,review=null;const urls=new Set();
  const release=()=>{for(const url of urls)revokeUrl(url);urls.clear();result=null;};
  const invalidate=()=>{generation++;active?.abort();active=null;review=null;release();onState({status:'idle',result:null});};
  const currentReview=options=>{const now=getCurrent();return review&&review.capture.session===now.session&&review.capture.bytes===now.bytes&&review.capture.version===now.version&&!now.session?.controller?.signal?.aborted&&JSON.stringify(review.options)===JSON.stringify(options);};
  const api={
    get result(){return result;},invalidate,cancel:invalidate,dispose:invalidate,
    async reviewDocx(options) {
      options=structuredClone(options);invalidate();
      const token=generation,capture={...getCurrent()},bytes=capture.bytes,controller=new AbortController();active=controller;
      const valid=()=>{const now=getCurrent();return token===generation&&!controller.signal.aborted&&now.session===capture.session&&now.bytes===bytes&&now.version===capture.version;};
      const check=()=>{if(!valid())throw abortError();};
      const parentSignal=capture.session?.controller?.signal,abort=()=>controller.abort();parentSignal?.addEventListener('abort',abort,{once:true});if(parentSignal?.aborted)abort();
      try {
        if(options.format!=='docx'||options.downsample||!(bytes instanceof Uint8Array)||!bytes.length)throw exportError('EXPORT_OPTIONS_INVALID');
        check();admitExport(capture.retainedBytes??bytes.buffer.byteLength,bytes.buffer.byteLength*2+1024*1024);onState({status:'reviewing',result:null});
        const response=await request('/exports?operation=docx-review',{method:'POST',body:bytes,signal:controller.signal,headers:{'Content-Type':'application/pdf',...passwordHeaders(capture.session.password)}});
        check();const data=validateDocxReview(response),digest=await crypto.subtle.digest('SHA-256',bytes);check();
        if(Array.from(new Uint8Array(digest),n=>n.toString(16).padStart(2,'0')).join('')!==data.source_sha256)fail();
        review={capture,options,data:structuredClone(data)};onState({status:'review-ready',review:data,result:null});return data;
      }catch(error){if(token===generation){review=null;release();onState({status:error.name==='AbortError'?'idle':'error',error,result:null});}throw error;}
      finally{parentSignal?.removeEventListener('abort',abort);if(active===controller)active=null;}
    },
    async convertDocx(options) {return api.prepare(options);},
    async prepare(options,{pdf}={}) {
      options=structuredClone(options);
      const approved=options.format==='docx'?review:null;
      if(options.format==='docx'&&!currentReview(options)){invalidate();const error=exportError('DOCX_REVIEW_REQUIRED');onState({status:'error',error,result:null});throw error;}
      invalidate();const token=generation,capture={...getCurrent()},bytes=capture?.bytes;
      if(!(bytes instanceof Uint8Array)||!bytes.length)throw exportError('EXPORT_OPTIONS_INVALID');
      const controller=new AbortController();active=controller;const {signal}=controller;
      const valid=()=>{const now=getCurrent();return token===generation&&!signal.aborted&&now?.session===capture.session&&now?.bytes===bytes&&now?.version===capture.version;};
      const check=()=>{if(!valid())throw abortError();};
      const parentSignal=capture.session?.controller?.signal,abort=()=>controller.abort();parentSignal?.addEventListener('abort',abort,{once:true});
      if(parentSignal?.aborted)controller.abort();
      const retainedBytes=capture.retainedBytes??bytes.buffer.byteLength;
      const publish=state=>{if(valid())onState(state);};
      try {
        check();admitExport(retainedBytes,bytes.buffer.byteLength*2+MAX_EXPORT_BYTES*2);publish({status:options.format==='docx'?'converting':'working',result:null});
        let prepared;
        if(['png','jpeg'].includes(options.format))prepared=await renderImages({pdf,pages:options.pages,format:options.format,dpi:options.dpi,signal,retainedBytes,onProgress:progress=>publish({status:'working',progress,result:null})});
        else if(options.format==='split')prepared=await runSplit(bytes,options.groups,{password:capture.session.password,acknowledged:!!options.acknowledged,retainedBytes,signal});
        else if(formats[options.format]) {
          if(options.downsample&&options.format!=='compress')throw exportError('EXPORT_OPTIONS_INVALID');
          const query=new URLSearchParams({operation:options.format,downsample:String(!!options.downsample),acknowledge_signature:String(!!options.acknowledged)});
          const headers={'Content-Type':'application/pdf',...passwordHeaders(capture.session.password)};
          if(options.format==='docx'){const {source_sha256,snapshot_sha256,policy_version}=approved.data;headers['X-DOCX-Review']=JSON.stringify({source_sha256,snapshot_sha256,policy_version});}
          const response=await request(`/exports?${query}`,{method:'POST',body:bytes,signal,headers});
          check();prepared=validateServerExport(response,options.format,bytes.byteLength,{retainedBytes});
        }else throw exportError('EXPORT_OPTIONS_INVALID');
        check();const total=formats[options.format]?prepared.afterBytes:validateLocal(prepared);
        admitExport(retainedBytes,total*4);
        const location=formats[options.format]?'server':'browser';
        const archive=options.archive||prepared.files.length>1?{bytes:createStoredZip(prepared.files,{retainedBytes}),filename:'export-pages.zip',mediaType:'application/zip'}:null;
        const link=file=>{check();const url=createUrl(new Blob([file.bytes],{type:file.mediaType}));urls.add(url);return {...file,url};};
        result={...prepared,location,beforeBytes:bytes.byteLength,afterBytes:total,files:prepared.files.map(link),archive:archive?link(archive):null,options:structuredClone(options)};
        publish({status:'ready',result});return result;
      }catch(error){if(token===generation){release();onState({status:error.name==='AbortError'?'idle':'error',error,result:null});}throw error;}
      finally {parentSignal?.removeEventListener('abort',abort);if(active===controller)active=null;}
    },
  };
  return api;
}

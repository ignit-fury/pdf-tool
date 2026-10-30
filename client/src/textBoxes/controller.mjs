import {passwordHeaders,withSourceRetry} from '../session.mjs';
import {admitExport,MAX_EXPORT_BYTES} from '../exports/zip.mjs';

const abort=()=>new DOMException('Text box preview canceled or document changed','AbortError');
const fail=()=>{throw Object.assign(new Error('Invalid text box response'),{code:'TEXT_BOX_RESPONSE_INVALID'});};
const keys=(value,expected)=>value&&typeof value==='object'&&!Array.isArray(value)&&Object.keys(value).sort().join(',')===[...expected].sort().join(',');
const finite=(v,lo,hi)=>typeof v==='number'&&Number.isFinite(v)&&v>=lo&&v<=hi;
const styleKeys=['font_family','font_size','bold','italic','color','character_spacing','line_spacing','paragraph_spacing','alignment'];
export function validateBoxes(boxes){
  if(!Array.isArray(boxes)||boxes.length>200)fail();
  const ids=new Set();
  for(const box of boxes){
    if(!keys(box,['id','page_index','rect','text','style',...(Object.hasOwn(box,'rotation')?['rotation']:[])])||Object.hasOwn(box,'rotation')&&![90,180,270].includes(box.rotation)||typeof box.id!=='string'||!/^[0-9a-f]{32}$/.test(box.id)||ids.has(box.id)||!Number.isSafeInteger(box.page_index)||box.page_index<0||box.page_index>=2048||typeof box.text!=='string'||!box.text.length||Array.from(box.text).length>10000)fail();
    ids.add(box.id);const r=box.rect,s=box.style;
    if(!keys(r,['left','top','width','height'])||!Object.entries(r).every(([k,v])=>finite(v,['left','top'].includes(k)?0:.01,144000)))fail();
    if(!keys(s,[...styleKeys,...(Object.hasOwn(s,'initial_font_size')?['initial_font_size']:[])])||!['Sans','Serif','Mono'].includes(s.font_family)||!['left','center','right'].includes(s.alignment)||typeof s.bold!=='boolean'||typeof s.italic!=='boolean'||!Array.isArray(s.color)||s.color.length!==3||!s.color.every(v=>finite(v,0,1))||!finite(s.font_size,1,512)||Object.hasOwn(s,'initial_font_size')&&!finite(s.initial_font_size,1,512)||!finite(s.character_spacing,0,10)||!finite(s.line_spacing,1,3)||!finite(s.paragraph_spacing,0,144))fail();
  }
  return structuredClone(boxes);
}
function decodePdf(encoded,retainedBytes){
  if(typeof encoded!=='string'||encoded.length%4||encoded.length>4*Math.ceil(MAX_EXPORT_BYTES/3)||/[^A-Za-z0-9+/=]/.test(encoded))fail();
  const size=encoded.length/4*3-(encoded.endsWith('==')?2:encoded.endsWith('=')?1:0);
  if(size<5||size>MAX_EXPORT_BYTES)fail();
  admitExport(retainedBytes,encoded.length*2+size*4);
  let raw;try{raw=atob(encoded);}catch{fail();}
  if(raw.length!==size||raw.slice(0,5)!=='%PDF-')fail();
  return Uint8Array.from(raw,c=>c.charCodeAt(0));
}
const digest=async bytes=>Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',bytes)),v=>v.toString(16).padStart(2,'0')).join('');

/** Separate preview cache. Source conversion uploads baseline + recipe; publication
 * always stays bound to current working bytes. Never mutates source/job/recipe. */
export function createTextBoxController({getCurrent,request,prepare,onState=()=>{}}){
  let generation=0,active=null,previewResult=null,cache=null,retiredBytes=0;
  const pendingBytes=new Map(),pendingTotal=()=>[...pendingBytes.values()].reduce((sum,size)=>sum+size,0);
  const matches=capture=>{const now=getCurrent();return now.session===capture.session&&now.bytes===capture.bytes&&now.version===capture.version&&!capture.session?.controller?.signal.aborted;};
  const dispose=prepared=>{if(!prepared)return;const count=(prepared.bytes?.buffer.byteLength||0)*2;retiredBytes+=count;let closed;try{closed=prepared.dispose?.();}catch{}Promise.resolve(closed).catch(()=>{}).finally(()=>{retiredBytes-=count;});};
  const invalidate=()=>{generation++;active?.abort();active=null;if(previewResult)dispose(previewResult.prepared);previewResult=null;onState({status:'idle'});};
  async function perform(payload,acknowledged=false){
    payload=structuredClone(payload);invalidate();
    const token=generation,capture={...getCurrent()},controller=new AbortController();active=controller;
    const valid=()=>token===generation&&!controller.signal.aborted&&matches(capture);
    const check=()=>{if(!valid())throw abort();};
    const parent=capture.session?.controller?.signal,cancel=()=>controller.abort();parent?.addEventListener('abort',cancel,{once:true});if(parent?.aborted)cancel();
    let prepared;
    try{
      check();if(!(capture.bytes instanceof Uint8Array)||!capture.bytes.length||capture.bytes.byteLength>50*1024*1024)throw Object.assign(new Error(),{code:'INVALID_TEXT_BOX'});
      const sourceBytes=payload.operation==='replace-source'?capture.session.sourceBytes:capture.bytes;
      if(!(sourceBytes instanceof Uint8Array)||!sourceBytes.length||sourceBytes.byteLength>50*1024*1024)throw Object.assign(new Error(),{code:'INVALID_TEXT_BOX'});
      admitExport(capture.retainedBytes||0,sourceBytes.buffer.byteLength*2+retiredBytes+1024*1024);
      onState({status:payload.operation==='list'?'listing':'preparing'});
      const cached=cache&&matches(cache.capture)&&cache.sourceBytes===sourceBytes;
      const hash=cached?cache.hash:await digest(sourceBytes);check();
      const context={controller,sourceBytes,password:capture.session.password,jobId:cached?cache.jobId:null};
      const upload=async(bytes,password)=>{
        const result=await request('/upload',{method:'POST',body:bytes,signal:controller.signal,headers:{'Content-Type':'application/pdf',...passwordHeaders(password)}});check();
        if(!result||result.source_hash!==hash||typeof result.job_id!=='string'||!result.job_id.length||result.job_id.length>256)fail();return result;
      };
      const response=await withSourceRetry(context,job=>request(`/jobs/${encodeURIComponent(job)}/text-box?acknowledge_signature=${!!acknowledged}`,{method:'POST',body:JSON.stringify(payload),signal:controller.signal,headers:{'Content-Type':'application/json',...passwordHeaders(context.password)}}),upload);
      check();cache={capture,hash,jobId:context.jobId,sourceBytes};
      if(!response||response.location!=='server'||response.source_hash!==hash||typeof response.ok!=='boolean')fail();
      if(payload.operation==='list'){
        if(!keys(response,['ok','source_hash','boxes','location'])||!response.ok)fail();
        const boxes=validateBoxes(response.boxes);onState({status:'listed',boxes});return boxes;
      }
      if(!response.ok){
        if(!keys(response,['ok','source_hash','code','required_height','available_height','location'])||response.code!=='TEXT_BOX_OVERFLOW'||!finite(response.required_height,.01,100000000)||!finite(response.available_height,.01,144000)||response.required_height<=response.available_height)fail();
        const result={...response};onState({status:'overflow',...result});return result;
      }
      if(!keys(response,['ok','source_hash','pdf','page_index','boxes','layout','notices','location'])||!Number.isSafeInteger(response.page_index)||response.page_index<0||response.page_index>=2048||!Array.isArray(response.notices)||response.notices.length>2||response.notices.some(n=>!['UNLOCKED_COPY','SIGNATURES_INVALIDATED'].includes(n)))fail();
      const boxes=validateBoxes(response.boxes),layout=response.layout;
      if(payload.operation!=='remove'&&(!keys(layout,['required_height','available_height','line_count'])||!finite(layout.required_height,.01,144000)||!finite(layout.available_height,.01,144000)||layout.required_height>layout.available_height+.000001||!Number.isSafeInteger(layout.line_count)||layout.line_count<1||layout.line_count>10000))fail();
      if(payload.operation==='remove'&&layout!==null)fail();
      const bytes=decodePdf(response.pdf,(capture.retainedBytes||0)+retiredBytes);check();pendingBytes.set(token,bytes.buffer.byteLength*2);
      prepared=await prepare(bytes,valid);check();
      if(!prepared||prepared.bytes!==bytes||!prepared.document)fail();
      previewResult={capture,key:JSON.stringify(payload),prepared,page_index:response.page_index,boxes,layout,notices:response.notices};
      prepared=null;onState({status:'ready',preview:previewResult});return previewResult;
    }catch(error){if(prepared)dispose(prepared);if(token===generation)onState({status:error.name==='AbortError'?'idle':'error',error});throw error;}
    finally{pendingBytes.delete(token);parent?.removeEventListener('abort',cancel);if(active===controller)active=null;}
  }
  return {invalidate,cancel:invalidate,dispose(){invalidate();cache=null;},
    get previewResult(){return previewResult;},get retainedBytes(){return retiredBytes+pendingTotal()+(previewResult?.prepared.bytes.buffer.byteLength||0)*2;},
    list(){return perform({operation:'list'});},preview(payload,{acknowledged=false}={}){return perform(payload,acknowledged);},
    take(payload){if(!previewResult)return null;if(!matches(previewResult.capture)||previewResult.key!==JSON.stringify(payload)){invalidate();return null;}const result=previewResult;previewResult=null;generation++;onState({status:'idle'});return result;}
  };
}

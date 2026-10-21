export function upsertOperation(recipe, operation) {
  return recipe.some(item => item.run_id === operation.run_id) ? recipe.map(item => item.run_id === operation.run_id ? operation : item) : [...recipe, operation];
}
export function commitRecipe(state, recipe) {return {recipe, history: [...state.history, state.recipe]};}
export function previousRecipe(state) {return state.history.length ? {recipe: state.history.at(-1), history: state.history.slice(0,-1)} : state;}
export function operationLocation(operations) {return operations.length ? 'server' : 'local';}
export function passwordHeaders(password) {
  return password ? {'X-PDF-Password-B64': btoa(Array.from(new TextEncoder().encode(password), byte=>String.fromCharCode(byte)).join(''))} : {};
}
export async function withSourceRetry(session, operation, upload) {
  try {return await operation(session.jobId);}
  catch (error) {
    if (error.status !== 409 || error.code !== 'SOURCE_MISSING') throw error;
    if (!session.restoring) session.restoring = upload(session.original,session.password).then(result => {session.jobId=result.job_id;}).finally(()=>{session.restoring=null;});
    await session.restoring;
    return operation(session.jobId);
  }
}
export function viewportBox(box, viewport) {
  const points=[[box[0],box[1]],[box[2],box[1]],[box[2],box[3]],[box[0],box[3]]].map(([x,y])=>viewport.convertToViewportPoint(x,y));
  const xs=points.map(p=>p[0]),ys=points.map(p=>p[1]),left=Math.min(...xs),top=Math.min(...ys);
  return {left,top,width:Math.max(...xs)-left,height:Math.max(...ys)-top};
}
export function decodePdf(encoded) {return Uint8Array.from(atob(encoded),char=>char.charCodeAt(0));}
export async function disposeDocument(document) {
  // pdf.js 6 exposes disposal on the loading task, not PDFDocumentProxy.
  // Cleanup of a superseded viewer must never roll back a successful edit.
  try {await document?.loadingTask?.destroy();} catch {}
}
export function explainReason(reason) {
  if(reason==='stateful_text_showing_unsupported')return 'This text uses line or spacing operators that cannot be safely rewritten yet.';
  if(reason==='multi_character_shaping_unsupported'||reason==='ambiguous_glyph_unicode_mapping')return 'This replacement cannot preserve exact searchable text with the available font. Try a simpler spelling or a different text run.';
  const explanations={overflow:'The replacement does not fit. Try shorter text.',fit_overflow:'The replacement does not fit. Try shorter text.',font_size_change_unsupported:'Font-size changes are not supported. Edits must fit the original width.',font_size_unsupported:'Font-size changes are not supported. Edits must fit the original width.',run_id_not_found:'The original text address could not be resolved.','right-to-left text':'Right-to-left text cannot be safely rewritten yet.',Type3:'This Type 3 font cannot be safely rewritten.'};
  return explanations[reason] || reason || 'This text cannot be safely rewritten.';
}

export function explainBucket(bucket) {
  return {editable:'Editable text',mixed_degraded:'Some text locked',scan_no_text:'Scanned page',ocr_scan:'Searchable scan',vector_outlined:'Outlined text',empty:'Empty page'}[bucket] || bucket;
}

export function createRequestQueue({limit=2,signal}={}) {
  let active=0;
  const pending=[];
  const pump=()=>{
    pending.sort((a,b)=>a.priority-b.priority);
    while(active<limit&&pending.length){
      const item=pending.shift();
      if(signal?.aborted){item.reject(new DOMException('Document closed','AbortError'));continue;}
      active++;
      Promise.resolve().then(item.operation).then(item.resolve,item.reject).finally(()=>{active--;pump();});
    }
  };
  signal?.addEventListener('abort',()=>{for(const item of pending.splice(0))item.reject(new DOMException('Document closed','AbortError'));},{once:true});
  return {run(operation,priority=10){
    let item;
    const promise=new Promise((resolve,reject)=>{item={operation,priority,resolve,reject};pending.push(item);});
    promise.promote=value=>{item.priority=Math.min(item.priority,value);};
    queueMicrotask(pump);
    return promise;
  }};
}

export async function retryWorkerBusy(operation,{signal,delays=[200,500,1000]}={}) {
  for(let attempt=0;;attempt++){
    if(signal?.aborted)throw new DOMException('Document closed','AbortError');
    try{return await operation();}
    catch(error){
      if(error.status!==429||attempt>=delays.length)throw error;
      await new Promise((resolve,reject)=>{
        const cancel=()=>{clearTimeout(timer);reject(new DOMException('Document closed','AbortError'));};
        const timer=setTimeout(()=>{signal?.removeEventListener('abort',cancel);resolve();},delays[attempt]);
        signal?.addEventListener('abort',cancel,{once:true});
      });
    }
  }
}

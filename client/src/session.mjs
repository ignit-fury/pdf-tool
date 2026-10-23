export function upsertOperation(recipe, operation) {
  return recipe.some(item => item.run_id === operation.run_id) ? recipe.map(item => item.run_id === operation.run_id ? operation : item) : [...recipe, operation];
}
export function commitRecipe(state, recipe) {return {recipe, history: [...state.history, state.recipe]};}
export function previousRecipe(state) {return state.history.length ? {recipe: state.history.at(-1), history: state.history.slice(0,-1)} : state;}
export function operationLocation(operations) {return operations.length ? 'server' : 'local';}
export function passwordHeaders(password) {
  return password ? {'X-PDF-Password-B64': btoa(Array.from(new TextEncoder().encode(password), byte=>String.fromCharCode(byte)).join(''))} : {};
}
export function chooseFontFamily(style, family) {
  const next = {...style};
  if(family)next.font_family=family;else delete next.font_family;
  return next;
}
export function needsFontChoice(run, style) {
  return run?.state!=='not_editable'&&(run?.state==='editable_substitution'||run?.suggested_font_family===null)&&!run?.suggested_font_family&&!style.font_family;
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
  if(reason==='normalization_boundary_unreplaceable')return 'This match covers only part of a character or combined character. Search for the complete character to replace it safely.';
  const widthError=/^delta (-?\d+(?:\.\d+)?)pt exceeds/.exec(reason||'');
  if(widthError)return Number(widthError[1])>0?'The replacement is too wide for this text area. Try shorter text or another replacement font.':'The replacement is shorter than the original text. Preview again with the updated editor.';
  if(reason?.startsWith('no mapping table entry for BaseFont'))return 'No automatic match for this font. Choose a replacement font, then preview again.';
  if(reason==='stateful_text_showing_unsupported')return 'This text uses line or spacing operators that cannot be safely rewritten yet.';
  if(reason==='part_boundary_truncated')return 'This text crosses PDF content-stream boundaries that cannot be safely rewritten yet. Try another text run.';
  if(reason==='operator_shared_by_multiple_runs')return 'This text shares a PDF instruction with other text. Editing it separately could change nearby text. Try another text run.';
  if(reason==='stale_run_index'||reason==='correlation_failed')return 'The text could not be matched safely to its PDF instructions. Try another text run.';
  if(reason==='resolution_failed')return 'This font could not be prepared for editing. Try a replacement font or another text run.';
  if(reason==='matrix_shift_detected'||reason==='text_matrix_shifted_after_edit')return 'This edit would move nearby text, so it was refused. Try another replacement or text run.';
  if(reason==='multi_character_shaping_unsupported'||reason==='ambiguous_glyph_unicode_mapping')return 'This replacement cannot preserve exact searchable text with the available font. Try a simpler spelling or a different text run.';
  const explanations={overflow:'The replacement does not fit. Try shorter text.',fit_overflow:'The replacement does not fit. Try shorter text.',font_size_change_unsupported:'Font-size changes are not supported. Edits must fit the original width.',font_size_unsupported:'Font-size changes are not supported. Edits must fit the original width.',run_id_not_found:'The original text address could not be resolved.','right-to-left text':'Right-to-left text cannot be safely rewritten yet.',Type3:'This Type 3 font cannot be safely rewritten.'};
  return explanations[reason] || 'This text cannot be safely rewritten.';
}
export function refusalCode(reason) {
  return /^[a-z][a-z0-9_]*$/.test(reason||'')&&explainReason(reason)!==reason?reason:null;
}
export function explainFit(strategy) {
  return {trailing_kern:'Fits at the original font size',inter_word_kern:'Fits with adjusted word spacing',tz:'Fits with slight horizontal compression'}[strategy]||'Text fits';
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

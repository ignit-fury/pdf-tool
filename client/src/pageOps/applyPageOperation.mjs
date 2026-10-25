const refused=admission=>({status:'refused',code:admission?.code??'MEMORY_REFUSED'});
/** Caller owns the one mutation lock and an immutable complete snapshot. admit is called
 * with {snapshot,candidateBytes,temporaryBytes,stage}; close/duplicate ownership isCurrent
 * must become false. commit(prepared,next,snapshot) must publish synchronously and not throw.
 * No state/history is mutated here; Undo uses admission + preparation before caller pops. */
export async function applyPageOperation({snapshot,transform,prepare,isCurrent,admit,commit}) {
  let prepared;
  const fresh=()=>isCurrent()===true;
  const dispose=async()=>{try{await prepared?.dispose?.();}catch{}};
  try {
    if(!fresh())return {status:'stale'};
    if(typeof snapshot.localMetadata?.signed!=='boolean')return {status:'refused',code:'SIGNATURE_UNKNOWN'};
    if(snapshot.localMetadata?.signed&&!snapshot.acknowledged)return {status:'refused',code:'SIGNATURE_ACK_REQUIRED'};
    // Preflight known disposable worker/output copies before transform allocates them.
    let admission=await admit({snapshot,candidateBytes:snapshot.bytes,temporaryBytes:snapshot.bytes.byteLength,stage:'before-transform'});
    if(!fresh())return {status:'stale'};
    if(admission?.ok!==true)return refused(admission);
    const result=await transform(snapshot);
    if(!fresh())return {status:'stale'};
    if(result?.noop)return {status:'refused',code:'NO_CHANGE',noop:true};
    if(!(result?.bytes instanceof Uint8Array))return {status:'refused',code:result?.code??'PDF_RESULT_INVALID'};
    admission=await admit({snapshot,candidateBytes:result.bytes,temporaryBytes:result.bytes.byteLength,stage:'before-prepare'});
    if(!fresh())return {status:'stale'};
    if(admission?.ok!==true)return refused(admission);
    prepared=await prepare(result.bytes,result);
    if(!fresh()){await dispose();return {status:'stale'};}
    if(!prepared)throw new Error('PDF_PREPARATION_FAILED');
    admission=await admit({snapshot,candidateBytes:result.bytes,temporaryBytes:prepared.bytes?[prepared.bytes]:0,stage:'after-prepare'});
    if(!fresh()){await dispose();return {status:'stale'};}
    if(admission?.ok!==true){await dispose();return refused(admission);}
    const next={...snapshot,bytes:result.bytes,sourceBytes:result.bytes,password:undefined,recipe:[],selectedPage:result.selectedPage??snapshot.selectedPage,selection:null,
      localMetadata:result.localMetadata??prepared.localMetadata??null,analysis:{enabled:false,sourceIdentity:null,meta:null,index:null},findState:null,
      acknowledged:result.localMetadata?.signed===true&&(result.acknowledged===true||snapshot.localMetadata.signed===true&&snapshot.acknowledged===true),action:result.action??'page'};
    commit(prepared,next,snapshot);
    return {status:'applied',next,notices:result.notices??[]};
  }catch(error) {await dispose();return fresh()?{status:error?.code?'refused':'failed',error,code:error?.code}:{status:'stale'};}
}

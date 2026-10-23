function immutable(value){
  if(value&&typeof value==='object'){for(const child of Object.values(value))immutable(child);Object.freeze(value);}
  return value;
}

// Each failed actual rewrite can identify a further unsafe proposed run. Only a
// strictly smaller candidate can be retried; earlier committed operations survive.
export async function previewReplacement({buildCandidate,requestPreview,isCurrent=()=>true,key}){
  const refused=new Set(),refusals={};
  const check=()=>{if(!isCurrent())throw new DOMException('Preview changed','AbortError');};
  for(;;){
    check();
    const candidate=buildCandidate(refused);
    if(!candidate.changes.length||!candidate.selectedCount){
      return immutable(structuredClone({...candidate,key,refusals,result:{ok:false,resolved:[],pdf:null}}));
    }
    // Freeze the exact serialized candidate before awaiting external work.
    const recipe=immutable(structuredClone(candidate.recipe));
    const result=await requestPreview(recipe);
    check();
    if(result.error)throw new Error(`Could not preview replacements (${result.error}).`);
    if(result.ok===true){
      const rows=result.resolved||[];
      if(rows.length!==recipe.length||recipe.some(op=>!rows.some(row=>row.run_id===op.run_id&&row.ok===true))){
        throw new Error('Could not verify the complete replacement preview.');
      }
      return immutable(structuredClone({...candidate,recipe,key,refusals,result}));
    }
    const failures=(result.resolved||[]).filter(row=>row.ok===false);
    if(failures.some(row=>['run_id_not_found','source_hash_mismatch','source_mismatch'].includes(row.reason))){
      const error=new Error('This preview no longer matches the document. Refresh the index and preview again.');
      error.code='SOURCE_MISMATCH';throw error;
    }
    if(!failures.length)throw new Error('Could not preview replacements. Your PDF is unchanged.');
    const proposed=new Set(candidate.changes.map(change=>change.runId));
    if(failures.some(row=>!proposed.has(row.run_id))){
      throw new Error('A previous edit could not be validated. Your PDF is unchanged. Undo or review that edit before replacing.');
    }
    const before=refused.size;
    for(const row of failures){refused.add(row.run_id);refusals[row.run_id]=row.reason||'replacement_refused';}
    if(refused.size===before)throw new Error('Could not complete the replacement preview.');
  }
}

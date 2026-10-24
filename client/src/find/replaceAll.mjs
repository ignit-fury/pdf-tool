function freeze(value){
  if(value&&typeof value==='object'){for(const child of Object.values(value))freeze(child);Object.freeze(value);}
  return value;
}

/** The caller owns the shared mutation lock. loadOutput prepares without publishing;
 * commit synchronously publishes that prepared output and one history entry. */
export async function applyReviewedReplacement({review,currentKey,isCurrent=()=>true,acknowledged=false,signed=false,requestApply,loadOutput,commit}){
  const key=()=>typeof currentKey==='function'?currentKey():currentKey;
  const fresh=()=>isCurrent()&&review?.key===key();
  if(!fresh())return {status:'stale'};
  if(signed&&!acknowledged)return {status:'blocked',reason:'signature'};
  const rows=review?.result?.resolved||[],recipe=review?.recipe;
  if(review?.result?.ok!==true||!Array.isArray(recipe)||!recipe.length||!(review.selectedCount>0)||!review.changedPages?.length||
    rows.length!==recipe.length||new Set(recipe.map(op=>op.run_id)).size!==recipe.length||
    recipe.some(op=>rows.filter(row=>row.run_id===op.run_id&&row.ok===true).length!==1))return {status:'blocked',reason:'preview'};
  // Capture plain immutable data, even if a caller supplied a mutable review.
  const accepted=freeze(structuredClone({recipe,selectedCount:review.selectedCount,changedPages:review.changedPages}));
  let output;
  try{
    const result=await requestApply(accepted.recipe);
    if(!fresh())return {status:'stale'};
    if(result?.ok!==true||!result.pdf)return {status:'refused',result};
    output=await loadOutput(result.pdf);
    if(!fresh()){await output?.dispose?.();return {status:'stale'};}
    if(!output)throw new Error('The edited PDF could not be prepared.');
    commit(output,accepted.recipe);
    return {status:'applied',selectedCount:accepted.selectedCount,changedPages:accepted.changedPages};
  }catch(error){
    await output?.dispose?.();
    return fresh()?{status:'failed',error}:{status:'stale'};
  }
}

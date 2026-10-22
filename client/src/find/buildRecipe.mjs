import {upsertOperation} from '../session.mjs';

export function assertRecipeLimits(recipe){
  if(recipe.length>50000||recipe.some(op=>Array.from(op.new_text).length>10000)||new TextEncoder().encode(JSON.stringify(recipe)).length>1024*1024){
    const error=new Error('This replacement exceeds the document edit limit. Exclude some matches or use shorter replacement text, then preview again.');
    error.code='RECIPE_TOO_LARGE';throw error;
  }
}

/** Collapse selected source spans into ordinary overrides of immutable run IDs. */
export function buildReplacementRecipe({pages,recipe=[],matches,excludedIds=new Set(),replacement,fontFamily='',refusedRunIds=new Set()}){
  const entries=pages instanceof Map?[...pages.values()]:Object.values(pages);
  const runs=new Map(entries.flatMap(value=>Array.isArray(value)?value:value?.runs||[]).map(run=>[run.run_id,run]));
  const prior=new Map(recipe.map(op=>[op.run_id,op])),groups=new Map();
  let unchangedCount=0;
  for(const match of matches){
    if(!match.replaceable||excludedIds.has(match.id)||refusedRunIds.has(match.runId))continue;
    if(match.text===replacement){unchangedCount++;continue;}
    if(!groups.has(match.runId))groups.set(match.runId,[]);
    groups.get(match.runId).push(match);
  }
  let candidate=recipe;const changes=[];
  for(const [runId,occurrences] of groups){
    const run=runs.get(runId),existing=prior.get(runId);
    if(!run)throw new Error('This preview no longer matches the document. Refresh the index and preview again.');
    const before=existing?.new_text??run.text;
    const ordered=[...occurrences].sort((a,b)=>a.start-b.start);
    let last=0;
    for(const match of ordered){
      if(match.start<last||match.start<0||match.end>before.length||before.slice(match.start,match.end)!==match.text)throw new Error('This preview no longer matches the document. Refresh the index and preview again.');
      last=match.end;
    }
    let after=before;
    for(const match of ordered.toReversed())after=after.slice(0,match.start)+replacement+after.slice(match.end);
    if(after===before){unchangedCount+=occurrences.length;continue;}
    // An existing per-run font choice is intentional. The batch choice only
    // supplies missing substitution/font recovery, never blanket restyling.
    const style={...existing?.style};
    const needsFallback=run.state==='editable_substitution'||run.suggested_font_family===null||run.reason?.startsWith('no mapping table entry for BaseFont');
    if(fontFamily&&needsFallback&&!style.font_family)style.font_family=fontFamily;
    const operation={run_id:runId,new_text:after};
    if(Object.keys(style).length)operation.style=style;
    candidate=upsertOperation(candidate,operation);
    changes.push({runId,page:ordered[0].page,before,after,matchIds:ordered.map(match=>match.id)});
  }
  assertRecipeLimits(candidate);
  return {recipe:candidate,changes,selectedCount:changes.reduce((sum,change)=>sum+change.matchIds.length,0),changedPages:[...new Set(changes.map(change=>change.page))].sort((a,b)=>a-b),unchangedCount};
}

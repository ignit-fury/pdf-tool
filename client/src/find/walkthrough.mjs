import {sourceRunForMatch} from './search.mjs';

export function matchesForScope(matches,activeId,scope='all') {
  return scope==='one'?matches.filter(match=>match.id===activeId):matches;
}
export function beginWalkthrough(review,matches,pages,reducedMotion=false) {
  const accepted=new Set((review.changes||[]).flatMap(change=>change.matchIds));
  const changes=new Map((review.changes||[]).map(change=>[change.runId,change]));
  const targets=matches.filter(match=>accepted.has(match.id)).map(match=>{
    const change=changes.get(match.runId),span=change?.spans?.find(value=>value.matchId===match.id);
    return {...match,...(span?{start:span.start,end:span.end,sourceText:change.after,text:change.after.slice(span.start,span.end),removed:span.start===span.end}:{}),box:sourceRunForMatch(pages,match)?.box};
  }).filter(match=>Array.isArray(match.box));
  return {targets,position:0,status:!targets.length?'complete':reducedMotion?'paused':'playing'};
}
export function stepWalkthrough(state,action) {
  if(!state)return state;
  if(action==='stop')return {...state,status:'stopped'};
  if(action==='pause')return {...state,status:'paused'};
  if(action==='resume')return state.position<state.targets.length?{...state,status:'playing'}:state;
  if(action==='tick'&&state.status!=='playing')return state;
  if(['next','tick'].includes(action))return {...state,position:Math.min(state.position+1,state.targets.length),status:state.position+1>=state.targets.length?'complete':state.status};
  return state;
}

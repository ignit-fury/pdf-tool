import {HIGHLIGHT_LIMITS,projectedCandidates,chooseCandidate} from './highlight.mjs';

/** Current PDF.js text only; no DOM mutation, canvas writes, selection or retained nodes. */
export function measureHighlight(container,paper,expected,target){
  const fallback=reason=>({quality:target.removed?'removed':'approximate',reason,rects:[expected]});
  if(target.removed)return fallback('removed');
  if(!container||!paper)return fallback('unavailable');
  const nodes=[],strings=[],walker=container.ownerDocument.createTreeWalker(container,4);let node,total=0,visited=0;
  while((node=walker.nextNode())){
    if(++visited>HIGHLIGHT_LIMITS.nodes)return fallback('limit');
    if(!node.data.length)continue;
    const start=total;total+=node.data.length;if(total>HIGHLIGHT_LIMITS.visible)return fallback('limit');
    nodes.push({node,start,end:total});strings.push(node.data);
  }
  const projected=projectedCandidates(strings.join(''),target.sourceText,target.start,target.end);
  if(projected.reason)return fallback(projected.reason);
  const origin=paper.getBoundingClientRect();
  function measure(start,end){
    const a=nodes.find(n=>n.end>start),b=nodes.find(n=>n.end>=end);
    if(!a||!b||end<=start)return null;
    const range=container.ownerDocument.createRange();
    range.setStart(a.node,start-a.start);range.setEnd(b.node,end-b.start);
    const raw=range.getClientRects();if(raw.length>HIGHLIGHT_LIMITS.rects*4)return null;
    const rects=[];
    for(const r of raw){
      const value={left:r.left-origin.left,top:r.top-origin.top,width:r.width,height:r.height};
      if(!Object.values(value).every(Number.isFinite)||value.width<=0||value.height<=0)continue;
      if(value.left<-2||value.top<-2||value.left+value.width>origin.width+2||value.top+value.height>origin.height+2)return null;
      if(!rects.some(p=>Object.keys(value).every(k=>Math.abs(p[k]-value[k])<.1)))rects.push(value);
      if(rects.length>HIGHLIGHT_LIMITS.rects)return null;
    }
    return rects.length?rects:null;
  }
  const measured=projected.candidates.map(c=>({runRects:measure(c.runStart,c.runEnd),rects:measure(c.start,c.end)}));
  const chosen=chooseCandidate(measured,expected);
  return chosen.reason?fallback(chosen.reason):{quality:'precise',reason:null,rects:chosen.rects};
}

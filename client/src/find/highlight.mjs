import {projectText} from './search.mjs';
import unicode from '../../../engine/data/search-unicode-15.1.json' with {type:'json'};

export const HIGHLIGHT_LIMITS=Object.freeze({visible:100000,source:20000,nodes:10000,candidates:64,rects:64,combining:64});
const failed=reason=>({candidates:[],reason});
const withinProjectionBudget=text=>{
  let size=0,marks=0;
  for(const char of text){
    const parts=unicode.nfkd[char.codePointAt(0)]||char;size+=parts.length;if(size>HIGHLIGHT_LIMITS.visible)return false;
    for(const part of parts){marks=unicode.combining[part.codePointAt(0)]?marks+1:0;if(marks>HIGHLIGHT_LIMITS.combining)return false;}
  }
  return true;
};
function sourceRange(projection,start,end){
  let from=-1,to=-1;
  for(let i=0;i<projection.spans.length;i++){
    const [a,b]=projection.spans[i];if(b<=start||a>=end)continue;
    if(a<start||b>end)return null;if(from<0)from=i;to=i+1;
  }
  if(from<0)return null;
  for(let i=from;i<to;i++){const [a,b]=projection.spans[i];if(a<start||b>end)return null;}
  return [from,to];
}
function closedRange(projection,from,to){
  let start=Infinity,end=-1;
  for(let i=from;i<to;i++){const [a,b]=projection.spans[i];start=Math.min(start,a);end=Math.max(end,b);}
  for(let i=0;i<projection.spans.length;i++)if(i<from||i>=to){const [a,b]=projection.spans[i];if(a<end&&b>start)return null;}
  return [start,end];
}
/** Exact canonical text equivalence, not fuzzy search or width interpolation. */
export function projectedCandidates(visible,source,start,end){
  if(typeof visible!=='string'||typeof source!=='string')return failed('unmapped');
  if(visible.length>HIGHLIGHT_LIMITS.visible||source.length>HIGHLIGHT_LIMITS.source||!withinProjectionBudget(visible)||!withinProjectionBudget(source))return failed('limit');
  if(!Number.isSafeInteger(start)||!Number.isSafeInteger(end)||start<0||end<start||end>source.length)return failed('unmapped');
  if(start===end)return failed('empty');
  const run=projectText(source,{matchCase:true}),page=projectText(visible,{matchCase:true}),selected=sourceRange(run,start,end);
  if(!run.text||!selected)return failed('unmapped');
  const candidates=[];let attempts=0;
  for(let offset=0;;){
    const at=page.text.indexOf(run.text,offset);if(at<0)break;offset=at+1;
    if(++attempts>HIGHLIGHT_LIMITS.candidates)return failed('limit');
    const full=closedRange(page,at,at+run.text.length),part=closedRange(page,at+selected[0],at+selected[1]);
    if(full&&part)candidates.push({start:part[0],end:part[1],runStart:full[0],runEnd:full[1]});
  }
  return {candidates,reason:candidates.length?null:'unmapped'};
}
const validRect=r=>r&&[r.left,r.top,r.width,r.height].every(Number.isFinite)&&r.width>0&&r.height>0;
export function rectUnion(rects){
  if(!rects.length||rects.length>HIGHLIGHT_LIMITS.rects||!rects.every(validRect))return null;
  const left=Math.min(...rects.map(r=>r.left)),top=Math.min(...rects.map(r=>r.top));
  return {left,top,width:Math.max(...rects.map(r=>r.left+r.width))-left,height:Math.max(...rects.map(r=>r.top+r.height))-top};
}
export function chooseCandidate(candidates,expected){
  if(!validRect(expected))return {reason:'unmapped',rects:[]};
  const overlaps=actual=>{
    const width=Math.max(0,Math.min(actual.left+actual.width,expected.left+expected.width)-Math.max(actual.left,expected.left));
    const height=Math.max(0,Math.min(actual.top+actual.height,expected.top+expected.height)-Math.max(actual.top,expected.top));
    return width*height>=.5*Math.min(actual.width*actual.height,expected.width*expected.height);
  };
  const eligible=candidates.filter(c=>{
    const actual=rectUnion(c.runRects||[]);if(!actual||!rectUnion(c.rects||[]))return false;
    // An enclosing union can cover empty space between unrelated text nodes.
    // Every constituent must agree with the original run, not only the union.
    return overlaps(actual)&&c.runRects.every(overlaps)&&c.rects.every(overlaps);
  });
  return eligible.length===1?{reason:null,rects:eligible[0].rects}:{reason:eligible.length?'ambiguous':'unmapped',rects:[]};
}
export const highlightKey=target=>JSON.stringify([target.id,target.sourceText,target.start,target.end,target.box,target.removed===true]);
export const highlightMessage=result=>result?.quality==='precise'?'Matching text highlighted.':result?.quality==='removed'?'Text removed — showing its original text area.':result?.quality==='approximate'?'Approximate text area — exact text-layer mapping is unavailable.':'Locating matching text…';

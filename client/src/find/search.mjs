import data from '../../../engine/data/search-unicode-15.1.json' with {type:'json'};

export const SEARCH_VERSION=data.version;
const pageRuns=value=>Array.isArray(value)?value:value?.runs||[];
export function sourceRunForMatch(pages,match){
  const value=pages instanceof Map?(pages.get(match.page)??pages.get(String(match.page))):pages?.[match.page];
  const run=pageRuns(value)[match.runOrder];
  return run?.run_id===match.runId?run:null;
}
const ccc=char=>data.combining[char.codePointAt(0)]||0;
function decompose(items){
  const ordered=[];
  for(const [char,start,end] of items){
    for(const part of data.nfkd[char.codePointAt(0)]||char){
      const item=[part,start,end],rank=ccc(part);let index=ordered.length;
      if(rank)while(index&&ccc(ordered[index-1][0])>rank)index--;
      ordered.splice(index,0,item);
    }
  }
  return ordered;
}
export function projectText(text,{matchCase=false}={}){
  let offset=0;
  let items=decompose(Array.from(text,char=>{const start=offset;offset+=char.length;return [char,start,offset];}));
  if(!matchCase)items=decompose(items.flatMap(([char,start,end])=>Array.from(data.casefold[char.codePointAt(0)]||char,part=>[part,start,end])));
  return {text:items.map(item=>item[0]).join(''),spans:items.flatMap(([char,start,end])=>Array.from({length:char.length},()=>[start,end]))};
}
export function projectSearchText(text){return {version:SEARCH_VERSION,sensitive:projectText(text,{matchCase:true}),folded:projectText(text)};}

function boundaries(text,granularity,segmenters){
  if(typeof Intl.Segmenter!=='function')return null;
  if(!segmenters.has(granularity))segmenters.set(granularity,new Intl.Segmenter('en',{granularity}));
  return new Set([0,text.length,...Array.from(segmenters.get(granularity).segment(text),part=>part.index)]);
}
function inverseSpans(projection){
  const inverse=new Map();
  projection.spans.forEach(([start,end],index)=>{
    for(let offset=start;offset<end;offset++){
      const range=inverse.get(offset);
      if(range)range[1]=index;else inverse.set(offset,[index,index]);
    }
  });
  return inverse;
}
function sourceSpan(projection,from,to,graphemes,inverse){
  let start=Infinity,end=0;
  for(let index=from;index<to;index++){const [a,b]=projection.spans[index];start=Math.min(start,a);end=Math.max(end,b);}
  let closed=true;
  for(let offset=start;offset<end;offset++){
    const range=inverse.get(offset);
    if(!range||range[0]<from||range[1]>=to){closed=false;break;}
  }
  return {start,end,safe:closed&&Boolean(graphemes?.has(start)&&graphemes?.has(end))};
}

export function findMatches(pages,query,{matchCase=false,wholeWords=false,recipe=[]}={}){
  const needle=projectText(query,{matchCase}).text;
  if(!needle)return [];
  if(wholeWords&&typeof Intl.Segmenter!=='function')throw new Error('Unicode whole-word search requires Intl.Segmenter. Turn off Whole words only.');
  const overrides=new Map(recipe.map(op=>[op.run_id,op])),results=[];
  const segmenters=new Map();
  const entries=pages instanceof Map?[...pages.entries()]:Object.entries(pages);
  entries.sort((a,b)=>Number(a[0])-Number(b[0]));
  const addresses=new Map();
  for(const [,value] of entries)for(const run of pageRuns(value))addresses.set(run.run_id,(addresses.get(run.run_id)||0)+1);
  for(const [pageKey,value] of entries){
    const runs=pageRuns(value);
    runs.forEach((run,runOrder)=>{
      const effective=overrides.get(run.run_id)?.new_text??run.text;
      const cached=effective===run.text&&run.search?.version===SEARCH_VERSION?run.search:null;
      const projection=cached?.[matchCase?'sensitive':'folded']||projectText(effective,{matchCase});
      // Most runs do not match. Build provenance and Unicode boundaries only
      // when a candidate exists; these checks still guard every returned match.
      const first=projection.text.indexOf(needle);
      if(first<0)return;
      const graphemes=boundaries(effective,'grapheme',segmenters),words=wholeWords?boundaries(projection.text,'word',segmenters):null,inverse=inverseSpans(projection);
      for(let from=first;;){
        const normalizedStart=projection.text.indexOf(needle,from);
        if(normalizedStart<0)break;
        const normalizedEnd=normalizedStart+needle.length;from=normalizedEnd;
        if(wholeWords&&!(words.has(normalizedStart)&&words.has(normalizedEnd)))continue;
        const {start,end,safe}=sourceSpan(projection,normalizedStart,normalizedEnd,graphemes,inverse);
        const editable=run.state==='editable_original'||run.state==='editable_substitution';
        const reason=!safe?'normalization_boundary_unreplaceable':!editable?run.reason||'uneditable':addresses.get(run.run_id)>1?'operator_shared_by_multiple_runs':null;
        const left=Array.from(effective.slice(Math.max(0,start-98),start)).slice(-48).join('');
        const right=Array.from(effective.slice(end,end+98)).slice(0,48).join('');
        results.push({id:JSON.stringify([query,matchCase,wholeWords,Number(pageKey),runOrder,run.run_id,effective,normalizedStart,normalizedEnd]),
          runId:run.run_id,page:Number(pageKey),runOrder,start,end,normalizedStart,normalizedEnd,
          text:effective.slice(start,end),before:(left.length<start?'…':'')+left,
          after:right+(end+right.length<effective.length?'…':''),state:run.state,reason,replaceable:!reason});
      }
    });
  }
  return results;
}

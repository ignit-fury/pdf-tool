import data from '../../../engine/data/search-unicode-15.1.json' with {type:'json'};

export const SEARCH_VERSION=data.version;
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

function boundaries(text,granularity){
  if(typeof Intl.Segmenter!=='function')return null;
  return new Set([0,text.length,...Array.from(new Intl.Segmenter('en',{granularity}).segment(text),part=>part.index)]);
}
function sourceSpan(projection,from,to,graphemes){
  const selected=projection.spans.slice(from,to);
  const start=Math.min(...selected.map(span=>span[0])),end=Math.max(...selected.map(span=>span[1]));
  const closed=projection.spans.every(([a,b],index)=>b<=start||a>=end||(index>=from&&index<to));
  return {start,end,safe:closed&&Boolean(graphemes?.has(start)&&graphemes?.has(end))};
}

export function findMatches(pages,query,{matchCase=false,wholeWords=false,recipe=[]}={}){
  const needle=projectText(query,{matchCase}).text;
  if(!needle)return [];
  if(wholeWords&&typeof Intl.Segmenter!=='function')throw new Error('Unicode whole-word search requires Intl.Segmenter. Turn off Whole words only.');
  const overrides=new Map(recipe.map(op=>[op.run_id,op])),results=[];
  const entries=pages instanceof Map?[...pages.entries()]:Object.entries(pages);
  entries.sort((a,b)=>Number(a[0])-Number(b[0]));
  for(const [pageKey,value] of entries){
    const runs=Array.isArray(value)?value:value?.runs||[];
    runs.forEach((run,runOrder)=>{
      const effective=overrides.get(run.run_id)?.new_text??run.text;
      const cached=effective===run.text&&run.search?.version===SEARCH_VERSION?run.search:null;
      const projection=cached?.[matchCase?'sensitive':'folded']||projectText(effective,{matchCase});
      const graphemes=boundaries(effective,'grapheme'),words=wholeWords?boundaries(projection.text,'word'):null;
      for(let from=0;;){
        const normalizedStart=projection.text.indexOf(needle,from);
        if(normalizedStart<0)break;
        const normalizedEnd=normalizedStart+needle.length;from=normalizedEnd;
        if(wholeWords&&!(words.has(normalizedStart)&&words.has(normalizedEnd)))continue;
        const {start,end,safe}=sourceSpan(projection,normalizedStart,normalizedEnd,graphemes);
        const editable=run.state==='editable_original'||run.state==='editable_substitution';
        const reason=!safe?'normalization_boundary_unreplaceable':editable?null:run.reason||'uneditable';
        const left=Array.from(effective.slice(0,start)),right=Array.from(effective.slice(end));
        results.push({id:JSON.stringify([query,matchCase,wholeWords,run.run_id,effective,normalizedStart,normalizedEnd]),
          runId:run.run_id,page:Number(pageKey),runOrder,start,end,normalizedStart,normalizedEnd,
          text:effective.slice(start,end),before:(left.length>48?'…':'')+left.slice(-48).join(''),
          after:right.slice(0,48).join('')+(right.length>48?'…':''),state:run.state,reason,replaceable:!reason});
      }
    });
  }
  return results;
}

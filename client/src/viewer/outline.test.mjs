import test from 'node:test';
import assert from 'node:assert/strict';
import {normalizeOutline,resolveOutlinePage} from './outline.mjs';

const ref={num:3,gen:0},dest=[ref,{name:'Fit'}];
test('nested outline keeps safe titles and separate internal/external destinations',()=>{
  const result=normalizeOutline([{title:'Start\u0000',dest,items:[{title:'Child',dest:'chapter-2'}]},
    {title:'External',url:'javascript:alert(1)',dest:null},{title:'Attachment',attachment:{},dest:null}]);
  assert.equal(result.items[0].title,'Start');assert.equal(result.items[0].children[0].destination,'chapter-2');
  assert.deepEqual(result.items[0].destination,dest);
  assert.equal(result.items[1].destination,null);assert.match(result.items[1].reason,/External/);
  assert.equal(result.items[2].destination,null);assert.equal(result.limited,false);
  assert.deepEqual(normalizeOutline(null),{items:[],limited:false});
});
test('large, deep and cyclic outlines are bounded and visibly marked incomplete',()=>{
  assert.equal(normalizeOutline(Array.from({length:1001},()=>({title:'x',dest}))).items.length,1000);
  assert.equal(normalizeOutline(Array.from({length:1001},()=>({title:'x',dest}))).limited,true);
  const cycle={title:'Cycle',items:[]};cycle.items.push(cycle);
  assert.equal(normalizeOutline([cycle]).limited,true);
  let node={title:'last',dest};for(let i=0;i<20;i++)node={title:'parent',items:[node]};
  const result=normalizeOutline([node]);let depth=0,n=result.items[0];while(n){depth++;n=n.children[0];}
  assert.equal(depth,16);assert.equal(result.limited,true);
  assert.equal(normalizeOutline([{title:'x'.repeat(1000),dest}]).items[0].title.length,256);
});
test('only bounded explicit/named internal destinations reach local PDF.js resolution',async()=>{
  const calls=[];const pdf={numPages:8,getDestination:async name=>{calls.push(name);return dest;},getPageIndex:async r=>{assert.deepEqual(r,ref);return 5;}};
  assert.equal(await resolveOutlinePage(pdf,dest,()=>true),6);
  assert.equal(await resolveOutlinePage(pdf,'chapter-2',()=>true),6);assert.deepEqual(calls,['chapter-2']);
  assert.equal(await resolveOutlinePage(pdf,[0,{name:'XYZ'},null,null,null],()=>true),1);
  for(const bad of [null,[],[-1,{name:'Fit'}],[8,{name:'Fit'}],[{num:-1,gen:0},{name:'Fit'}],['https://example.invalid',{name:'Fit'}],'x'.repeat(2049)])
    await assert.rejects(()=>resolveOutlinePage(pdf,bad,()=>true),{code:'OUTLINE_DESTINATION_UNAVAILABLE'});
  await assert.rejects(()=>resolveOutlinePage({...pdf,getDestination:async()=>null},'missing',()=>true),{code:'OUTLINE_DESTINATION_UNAVAILABLE'});
});
test('stale named and page-reference responses cannot navigate another document',async()=>{
  for(const stage of ['named','reference']){
    let valid=true,release;
    const pdf={numPages:3,getDestination:()=>stage==='named'?new Promise(r=>release=r):Promise.resolve(dest),getPageIndex:()=>new Promise(r=>release=r)};
    const work=resolveOutlinePage(pdf,stage==='named'?'named':dest,()=>valid);
    while(!release)await new Promise(r=>setImmediate(r));valid=false;release(stage==='named'?dest:1);
    await assert.rejects(work,{name:'AbortError'});
  }
});

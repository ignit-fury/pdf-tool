import test from 'node:test';
import assert from 'node:assert/strict';
import {previewReplacement} from './preview.mjs';

function candidate(refused){
  const changes=[{runId:'new-a',page:1,before:'cat',after:'a',matchIds:['a']},{runId:'new-b',page:2,before:'cat',after:'a',matchIds:['b','c']}].filter(change=>!refused.has(change.runId));
  return {recipe:[{run_id:'prior',new_text:'kept',style:{bold:true}},...changes.map(change=>({run_id:change.runId,new_text:change.after}))],changes,selectedCount:changes.reduce((sum,change)=>sum+change.matchIds.length,0),changedPages:[...new Set(changes.map(change=>change.page))],unchangedCount:0};
}

test('a failed dry run is filtered and exact surviving full recipe is actually previewed',async()=>{
  const seen=[];
  const review=await previewReplacement({buildCandidate:candidate,key:'current',requestPreview:async recipe=>{
    seen.push(structuredClone(recipe));
    return seen.length===1?{ok:false,pdf:null,resolved:[{run_id:'prior',ok:true},{run_id:'new-a',ok:false,reason:'fit_overflow'},{run_id:'new-b',ok:true}]}:{ok:true,pdf:null,resolved:recipe.map(op=>({run_id:op.run_id,ok:true}))};
  }});
  assert.deepEqual(seen.map(recipe=>recipe.map(op=>op.run_id)),[['prior','new-a','new-b'],['prior','new-b']]);
  assert.deepEqual(review.recipe,seen[1]);assert.equal(review.selectedCount,2);
  assert.deepEqual(review.refusals,{'new-a':'fit_overflow'});
  assert.equal(review.result.ok,true);assert.ok(Object.isFrozen(review.recipe));
});

test('late runtime refusals need another successful exact preview',async()=>{
  let calls=0;
  const review=await previewReplacement({buildCandidate:candidate,key:'current',requestPreview:async recipe=>{
    calls++;
    if(calls===1)return {ok:false,resolved:[{run_id:'new-a',ok:false,reason:'fit_overflow'}]};
    if(calls===2)return {ok:false,resolved:[{run_id:'new-b',ok:false,reason:'text_matrix_shifted_after_edit'}]};
    assert.fail('An all-refused batch must not preview only the old recipe');
  }});
  assert.equal(calls,2);assert.equal(review.selectedCount,0);assert.equal(review.result.ok,false);
  assert.deepEqual(review.recipe,[{run_id:'prior',new_text:'kept',style:{bold:true}}]);
});

test('a refusal in a prior operation blocks instead of deleting that edit',async()=>{
  await assert.rejects(previewReplacement({buildCandidate:candidate,key:'x',requestPreview:async()=>({ok:false,resolved:[{run_id:'prior',ok:false,reason:'fit_overflow'}]})}),/previous edit/i);
});

test('batch errors and nonprogressing reports cannot publish ready reviews',async()=>{
  await assert.rejects(previewReplacement({buildCandidate:candidate,key:'x',requestPreview:async()=>({error:'WORKER_FAILED'})}),/WORKER_FAILED/);
  await assert.rejects(previewReplacement({buildCandidate:candidate,key:'x',requestPreview:async()=>({ok:false,resolved:[{run_id:'new-a',ok:true}]})}),/preview/i);
  await assert.rejects(previewReplacement({buildCandidate:candidate,key:'x',requestPreview:async()=>({ok:true,resolved:[{run_id:'new-a',ok:true}]})}),/complete replacement preview/i);
});

test('cancelled generations cannot return a ready review after the worker completes',async()=>{
  let finish,current=true;const waiting=new Promise(resolve=>{finish=resolve;});
  const pending=previewReplacement({buildCandidate:candidate,key:'x',isCurrent:()=>current,requestPreview:()=>waiting});
  current=false;finish({ok:true,resolved:[]});
  await assert.rejects(pending,{name:'AbortError'});
});

import test from 'node:test';
import assert from 'node:assert/strict';
import {applyReviewedReplacement} from './replaceAll.mjs';
import {commitRecipe,previousRecipe} from '../session.mjs';

const recipe=[{run_id:'prior',new_text:'Styled',style:{bold:true,font_family:'Serif'}},{run_id:'batch',new_text:'Changed'}];
const review=()=>({key:'current',recipe:structuredClone(recipe),result:{ok:true,resolved:recipe.map(op=>({run_id:op.run_id,ok:true}))},changes:[{runId:'batch',matchIds:['one','two']}],selectedCount:2,changedPages:[1,2]});
const deferred=()=>{let resolve;const promise=new Promise(done=>{resolve=done;});return {promise,resolve};};
function setup(overrides={}){
  const seen={requests:[],loads:[],commits:[],disposed:0};
  const options={review:review(),currentKey:()=> 'current',isCurrent:()=>true,signed:false,acknowledged:false,
    requestApply:async value=>{seen.requests.push(value);return {ok:true,pdf:'encoded'};},
    loadOutput:async value=>{seen.loads.push(value);return {bytes:new Uint8Array([1]),dispose:()=>{seen.disposed++;}};},
    commit:(output,value)=>seen.commits.push({output,recipe:value}),...overrides};
  return {seen,options};
}

test('only a complete current exact successful review with signature acknowledgement can request apply',async()=>{
  const cases=[{review:null},{review:{...review(),result:{ok:false}}},{review:{...review(),selectedCount:0}},
    {review:{...review(),result:{ok:true,resolved:[]}}},{currentKey:()=> 'changed'},{isCurrent:()=>false},{signed:true,acknowledged:false}];
  for(const value of cases){const {seen,options}=setup(value);const result=await applyReviewedReplacement(options);assert.notEqual(result.status,'applied');assert.equal(seen.requests.length,0);assert.equal(seen.commits.length,0);}
});

test('success sends the accepted full recipe once and commits one whole-recipe undo including prior style',async()=>{
  const prior={recipe:[recipe[0]],history:[]};let state=prior;
  const {seen,options}=setup({signed:true,acknowledged:true,commit:(output,value)=>{state=commitRecipe(state,value);seen.commits.push(output);}});
  const result=await applyReviewedReplacement(options);
  assert.equal(result.status,'applied');assert.equal(result.selectedCount,2);assert.deepEqual(result.changedPages,[1,2]);
  assert.equal(seen.requests.length,1);assert.deepEqual(seen.requests[0],recipe);assert.equal(seen.loads.length,1);assert.equal(seen.commits.length,1);
  assert.equal(state.history.length,1);assert.deepEqual(previousRecipe(state),prior);assert.deepEqual(state.recipe[0].style,prior.recipe[0].style);
});

test('worker refusal, missing PDF and transport/load errors never commit',async()=>{
  for(const response of [{ok:false,pdf:'ignored'},{ok:true,pdf:null}]){
    const {seen,options}=setup({requestApply:async()=>response});const result=await applyReviewedReplacement(options);
    assert.equal(result.status,'refused');assert.equal(seen.loads.length,0);assert.equal(seen.commits.length,0);
  }
  for(const failAt of ['requestApply','loadOutput']){
    const {seen,options}=setup({[failAt]:async()=>{throw new Error('failure');}});
    assert.equal((await applyReviewedReplacement(options)).status,'failed');assert.equal(seen.commits.length,0);
  }
});

test('document/key change while apply is pending never loads or commits its response',async()=>{
  for(const change of ['document','key']){
    const waiting=deferred();let current=true,key='current';
    const {seen,options}=setup({requestApply:()=>waiting.promise,isCurrent:()=>current,currentKey:()=>key});
    const pending=applyReviewedReplacement(options);if(change==='document')current=false;else key='new';
    waiting.resolve({ok:true,pdf:'old'});assert.equal((await pending).status,'stale');assert.equal(seen.loads.length,0);assert.equal(seen.commits.length,0);
  }
});

test('a prepared viewer is discarded after a stale load and the old viewer/history remain owned by the caller',async()=>{
  const waiting=deferred();let current=true;const old={viewer:'old',download:'old',history:[]};let state=old;
  const {seen,options}=setup({loadOutput:()=>waiting.promise,isCurrent:()=>current,commit:()=>{state={viewer:'new'};}});
  const pending=applyReviewedReplacement(options);await Promise.resolve();current=false;
  waiting.resolve({dispose:()=>{seen.disposed++;}});
  assert.equal((await pending).status,'stale');assert.equal(seen.disposed,1);assert.equal(state,old);
});

test('the accepted recipe is captured before awaiting and cannot be changed by later draft mutation',async()=>{
  const accepted=review(),waiting=deferred();let received;
  const {options}=setup({review:accepted,requestApply:value=>{received=value;return waiting.promise;}});
  const pending=applyReviewedReplacement(options);accepted.recipe[1].new_text='tampered';
  assert.equal(received[1].new_text,'Changed');assert.ok(Object.isFrozen(received));assert.ok(Object.isFrozen(received[0].style));
  waiting.resolve({ok:true,pdf:'output'});assert.equal((await pending).status,'applied');
});

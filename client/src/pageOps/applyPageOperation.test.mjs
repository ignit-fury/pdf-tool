import test from 'node:test';
import assert from 'node:assert/strict';
import {applyPageOperation} from './applyPageOperation.mjs';
import {captureSnapshot} from './documentHistory.mjs';
const deferred=()=>{let resolve;const promise=new Promise(r=>resolve=r);return {promise,resolve};};
const snapshot=()=>captureSnapshot({bytes:new Uint8Array([1]),sourceBytes:new Uint8Array([0]),recipe:[{run_id:'old'}],style:{bold:true},analysis:{enabled:true,sourceIdentity:'old',meta:{},index:{}},localMetadata:{signed:false},selectedPage:0});
test('successful page operation prepares before one synchronous full-state publication',async()=>{
  const old=snapshot(),events=[];let committed;
  const result=await applyPageOperation({snapshot:old,transform:async()=>({bytes:new Uint8Array([2]),selectedPage:1,notices:['blank']}),isCurrent:()=>true,admit:info=>{events.push('admit');assert.ok(info.candidateBytes);return {ok:true};},prepare:async bytes=>{events.push('prepare');return {bytes};},commit:(prepared,next,prior)=>{events.push('commit');committed={prepared,next,prior};}});
  assert.equal(result.status,'applied');assert.equal(events.at(-1),'commit');assert.equal(events.filter(x=>x==='commit').length,1);
  assert.equal(committed.prior,old);assert.deepEqual(committed.next.bytes,new Uint8Array([2]));
  assert.equal(committed.next.sourceBytes,committed.next.bytes);assert.deepEqual(committed.next.recipe,[]);
  assert.deepEqual(committed.next.analysis,{enabled:false,sourceIdentity:null,meta:null,index:null});
  assert.equal(committed.next.selection,null);assert.equal(committed.next.selectedPage,1);assert.equal(committed.next.style.bold,true);
});
test('stale transform, stale prepared output, refusal and failed prepare never publish or change old state',async()=>{
  for(const mode of ['transform','prepare','admit','prepare-admit','throw','noop']) {
    const old=snapshot(),gate=deferred();let fresh=true,commits=0,disposed=0,admissions=0;
    const promise=applyPageOperation({snapshot:old,isCurrent:()=>fresh,
      transform:async()=>{if(mode==='transform')await gate.promise;return {bytes:new Uint8Array([2]),noop:mode==='noop'};},
      admit:()=>({ok:!(mode==='admit'||(mode==='prepare-admit'&&++admissions===3)),code:'RETENTION_LIMIT'}),
      prepare:async()=>{if(mode==='throw')throw new Error('prepare failed');if(mode==='prepare')await gate.promise;return {dispose:()=>disposed++};},commit:()=>commits++});
    await new Promise(resolve=>setImmediate(resolve));
    if(['transform','prepare'].includes(mode)){fresh=false;gate.resolve();}
    const result=await promise;
    assert.equal(commits,0,mode);assert.equal(old.bytes[0],1);assert.equal(old.sourceBytes[0],0);
    if(mode==='prepare'||mode==='prepare-admit')assert.equal(disposed,1,mode);
    assert.ok(['stale','refused','failed'].includes(result.status),mode);
  }
});
test('initial stale or unacknowledged signature cannot even transform',async()=>{
  let called=0;
  for(const [fresh,signed] of [[false,false],[true,true]]) {
    const result=await applyPageOperation({snapshot:{...snapshot(),localMetadata:{signed},acknowledged:false},isCurrent:()=>fresh,transform:async()=>called++,commit:()=>called++});
    assert.ok(['stale','refused'].includes(result.status));
  }
  assert.equal(called,0);
});
test('unknown signature metadata refuses before transform; acknowledgement survives successive signed edits and exact Undo',async()=>{
  let transformed=0,committed=0;
  for(const localMetadata of [undefined,null,{}, {signed:null},{signed:'false'}]) {
    const result=await applyPageOperation({snapshot:{...snapshot(),localMetadata},isCurrent:()=>true,transform:async()=>transformed++,commit:()=>committed++});
    assert.equal(result.status,'refused');assert.equal(result.code,'SIGNATURE_UNKNOWN');
  }
  assert.equal(transformed,0);assert.equal(committed,0);
  const original={...snapshot(),localMetadata:{signed:true},acknowledged:true};let current=original;
  const prior=[];
  for(let i=0;i<2;i++) {
    const result=await applyPageOperation({snapshot:current,isCurrent:()=>true,admit:()=>({ok:true}),transform:async()=>({bytes:new Uint8Array([i+3]),localMetadata:{signed:true}}),prepare:async()=>({}),commit:(prepared,next,snapshot)=>{prior.push(snapshot);current=next;}});
    assert.equal(result.status,'applied');assert.equal(current.acknowledged,true);
  }
  current=prior.pop();assert.equal(current.acknowledged,true);current=prior.pop();assert.equal(current,original);
});

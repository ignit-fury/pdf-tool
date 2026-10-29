import test from 'node:test';
import assert from 'node:assert/strict';
import {captureSnapshot,admitHistory,admitTimeline,pushSnapshot,peekSnapshot,popSnapshot,MAX_PDF_BYTES,MAX_RETAINED_BYTES,MAX_TRANSIENT_BYTES,MAX_HISTORY_ENTRIES} from './documentHistory.mjs';

const bytes=n=>new Uint8Array([n]);
test('new history branches use final past entry count while still budgeting Redo bytes',()=>{
  const item={bytes:bytes(1)},past=Array(99).fill(item),future=[item];
  assert.equal(admitTimeline({current:item,past,future,candidateBytes:bytes(2)}).ok,true);
  assert.equal(admitTimeline({current:item,past:Array(100).fill(item),future:[],candidateBytes:bytes(2)}).code,'HISTORY_LIMIT');
  const large=Array.from({length:5},()=>({bytes:new Uint8Array(MAX_PDF_BYTES)}));
  assert.equal(admitTimeline({current:item,past:[],future:large,candidateBytes:bytes(2)}).code,'RETENTION_LIMIT');
});
export const state=n=>({bytes:bytes(n),sourceBytes:bytes(n-1),password:'secret',recipe:[{run_id:'p0-r0',replacement:'new'}],selectedPage:2,style:{bold:true},selection:{id:'p0-r0'},localMetadata:{signed:false,encrypted:true,pageCount:3,pages:[]},analysis:{enabled:true,sourceIdentity:'old-source',meta:{pages:3},index:{runs:[1]}},findState:{query:'new'},acknowledged:true,action:'text'});
test('mixed document history restores byte exact state and distinct replay baseline',()=>{
  const opened=bytes(0),first=state(2),snapshot=captureSnapshot(first);
  first.recipe[0].replacement='changed';first.style.bold=false;first.bytes[0]=9;
  assert.equal(snapshot.bytes[0],2);assert.equal(snapshot.sourceBytes[0],1);
  assert.equal(snapshot.recipe[0].replacement,'new');assert.equal(snapshot.style.bold,true);
  assert.ok(Object.isFrozen(snapshot.analysis.index.runs));
  let history=pushSnapshot([],snapshot);history=pushSnapshot(history,captureSnapshot(state(4)));
  assert.equal(peekSnapshot(history).bytes[0],4);
  history=popSnapshot(history);assert.deepEqual(peekSnapshot(history),snapshot);
  history=popSnapshot(history);assert.equal(peekSnapshot(history),null);
  assert.equal(opened[0],0);assert.equal(snapshot.password,'secret');
  assert.throws(()=>captureSnapshot({...state(2),analysis:{enabled:true,index:new AbortController()}}),{code:'SNAPSHOT_NOT_SERIALIZABLE'});
});
test('admission counts unique full backing stores and refuses boundaries without eviction',()=>{
  const shared=new Uint8Array(MAX_PDF_BYTES),current={bytes:shared.subarray(0,1),sourceBytes:shared.subarray(1,2)};
  const history=Object.freeze(Array.from({length:100},()=>current));
  assert.deepEqual([MAX_PDF_BYTES,MAX_RETAINED_BYTES,MAX_TRANSIENT_BYTES,MAX_HISTORY_ENTRIES],[50,200,300,100].map((n,i)=>i===3?n:n*1024*1024));
  const result=admitHistory({openedBytes:shared,current,history:[],candidateBytes:shared});
  assert.equal(result.ok,true);assert.equal(result.retainedBytes,MAX_PDF_BYTES);
  assert.equal(admitHistory({openedBytes:shared,current,history,candidateBytes:bytes(3)}).code,'HISTORY_LIMIT');
  assert.equal(history.length,100);
  assert.equal(admitHistory({current,history:[],candidateBytes:new Uint8Array(MAX_PDF_BYTES+1)}).code,'LOCAL_PDF_TOO_LARGE');
  assert.equal(admitHistory({current,history:[],candidateBytes:shared,temporaryBytes:MAX_TRANSIENT_BYTES-MAX_PDF_BYTES+1}).code,'TRANSIENT_LIMIT');
  const stores=Array.from({length:4},()=>({bytes:new Uint8Array(MAX_PDF_BYTES)}));
  assert.equal(admitHistory({current:stores[0],history:stores.slice(1),candidateBytes:shared}).code,'RETENTION_LIMIT');
  assert.equal(admitHistory({current,history:[],candidateBytes:shared,temporaryBytes:MAX_TRANSIENT_BYTES-MAX_PDF_BYTES}).ok,true);
});

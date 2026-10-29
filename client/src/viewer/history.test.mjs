import test from 'node:test';
import assert from 'node:assert/strict';
import {historyRows,historyJump} from './history.mjs';

const state=(n,action)=>Object.freeze({bytes:new Uint8Array([n]),sourceBytes:new Uint8Array([0]),recipe:[{text:String(n)}],localMetadata:{pageCount:n+1},selectedPage:n,action});
test('history presents original, committed operations, current and undone future in order',()=>{
  const rows=historyRows([state(0,'blank insertion'),state(1,'page rotation')],[state(4,'image placement'),state(3,'text edit')]);
  assert.deepEqual(rows.map(r=>r.label),['Original document','Insert blank page','Rotate page','Edit text','Insert image']);
  assert.deepEqual(rows.map(r=>r.status),['applied','applied','current','undone','undone']);
  assert.deepEqual(historyRows([],[]),[{position:0,label:'Original document',status:'current'}]);
});
test('atomic jumps preserve exact mixed states and operation labels through undo and redo',()=>{
  const past=Object.freeze([state(0,'blank insertion'),state(1,'text edit'),state(2,'image placement')]),current=state(3,'unused'),future=Object.freeze([]);
  const result=historyJump({past,future,current},0);
  assert.strictEqual(result.target,past[0]);assert.strictEqual(result.target.bytes,past[0].bytes);
  assert.equal(result.past.length,0);assert.deepEqual(result.future.map(s=>s.action),['image placement','text edit','blank insertion']);
  const restored=historyJump({past:result.past,future:result.future,current:result.target},3);
  assert.strictEqual(restored.target.bytes,current.bytes);assert.strictEqual(restored.target.recipe,current.recipe);assert.strictEqual(restored.target.localMetadata,current.localMetadata);
  assert.deepEqual(restored.past.map(s=>s.action),past.map(s=>s.action));assert.deepEqual(restored.future,[]);
  assert.equal(past.length,3);assert.equal(current.action,'unused');
});
test('invalid/current positions return no transition and partial jumps keep both directions',()=>{
  const timeline={past:[state(0,'blank insertion'),state(1,'text edit')],future:[state(3,'image placement')],current:state(2,'unused')};
  for(const position of [-1,4,1.5,NaN,'1',2])assert.equal(historyJump(timeline,position),null);
  const one=historyJump(timeline,1);assert.equal(one.target.bytes[0],1);assert.deepEqual(one.future.map(s=>s.action),['image placement','text edit']);
  const redo=historyJump({...one,current:one.target},2);assert.equal(redo.target.bytes[0],2);assert.equal(redo.future.length,1);
});

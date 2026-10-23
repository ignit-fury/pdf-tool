import test from 'node:test';
import assert from 'node:assert/strict';
import {createIndexingController} from './indexing.mjs';

const tick=()=>new Promise(resolve=>setImmediate(resolve));
function deferred(){let resolve,reject;const promise=new Promise((yes,no)=>{resolve=yes;reject=no;});return {promise,resolve,reject};}

test('indexing counts successful empty pages and retries only missing or failed pages',async()=>{
  const seen=[],progress=[];let fail=true;
  const controller=createIndexingController({fetchPage:async page=>{seen.push(page);if(page===2&&fail)throw Error('busy');return {runs:[]};},onProgress:value=>progress.push(value)});
  await controller.start(3);
  assert.deepEqual(progress.at(-1),{completed:2,completedPages:[1,3],total:3,failedPages:[2],status:'failed'});
  fail=false;await controller.resume();
  assert.deepEqual(seen,[1,2,3,2]);
  assert.deepEqual(progress.at(-1),{completed:3,completedPages:[1,2,3],total:3,failedPages:[],status:'complete'});
});

test('stop ignores a late page and resume retains only completed work',async()=>{
  const waiting=deferred(),seen=[],progress=[];
  const controller=createIndexingController({fetchPage:page=>{seen.push(page);return page===2?waiting.promise:Promise.resolve({runs:[]});},onProgress:value=>progress.push(value)});
  const first=controller.start(3);await tick();controller.stop();
  assert.equal(progress.at(-1).completed,1);
  assert.deepEqual(progress.at(-1).completedPages,[1]);
  assert.equal(progress.at(-1).status,'stopped');
  const count=progress.length;waiting.resolve({runs:[]});await first;
  assert.equal(progress.length,count);
  assert.deepEqual(seen,[1,2]);
  await controller.resume();
  assert.deepEqual(seen,[1,2,2,3]);
  assert.equal(progress.at(-1).status,'complete');
});

test('document closure and disposal cannot publish source-retry completion',async()=>{
  const waiting=deferred(),progress=[];let current=true;
  const controller=createIndexingController({fetchPage:()=>waiting.promise,onProgress:value=>progress.push(value),isCurrent:()=>current});
  const pending=controller.start(2);current=false;controller.dispose();const count=progress.length;
  waiting.resolve({runs:[]});await pending;
  assert.equal(progress.length,count);
  await controller.resume();assert.equal(progress.length,count);
});

test('starting twice does not schedule concurrent producers',async()=>{
  const waiting=deferred(),seen=[];
  const controller=createIndexingController({fetchPage:page=>{seen.push(page);return waiting.promise;},onProgress:()=>{}});
  const first=controller.start(1),second=controller.start(1);
  await tick();assert.deepEqual(seen,[1]);waiting.resolve({runs:[]});await Promise.all([first,second]);
});

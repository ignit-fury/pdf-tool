import test from 'node:test';
import assert from 'node:assert/strict';
import { upsertOperation, commitRecipe, previousRecipe, withSourceRetry, viewportBox, createRequestQueue, retryWorkerBusy } from './session.mjs';

test('font choice is explicit, removable and restored with whole-recipe undo', async () => {
  const {chooseFontFamily,needsFontChoice,explainReason}=await import('./session.mjs');
  const run={state:'editable_substitution',suggested_font_family:null};
  assert.equal(needsFontChoice(run,{}),true);
  const style=chooseFontFamily({bold:true},'Serif');
  assert.equal(needsFontChoice(run,style),false);
  assert.deepEqual(chooseFontFamily(style,''),{bold:true});
  const initial={recipe:[{run_id:'id',new_text:'original',style}],history:[]};
  const changed=commitRecipe(initial,upsertOperation(initial.recipe,{run_id:'id',new_text:'changed',style:chooseFontFamily(style,'Mono')}));
  assert.deepEqual(previousRecipe(changed).recipe,initial.recipe);
  assert.match(explainReason("no mapping table entry for BaseFont 'Unrecognized'"),/Choose a replacement font/);
});

test('password headers preserve UTF-8, whitespace and control characters', async () => {
  const {passwordHeaders} = await import('./session.mjs');
  const password = ' \t密碼\r\n ';
  const headers = new Headers(passwordHeaders(password));
  const bytes = Uint8Array.from(atob(headers.get('X-PDF-Password-B64')), c=>c.charCodeAt(0));
  assert.equal(new TextDecoder().decode(bytes), password);
  assert.deepEqual(passwordHeaders(''), {});
});

test('pdf.js 6 document replacement disposes through the loading task', async () => {
  const {disposeDocument} = await import('./session.mjs');
  let destroyed = false;
  await disposeDocument({loadingTask:{destroy:async()=>{destroyed=true;}}});
  assert.equal(destroyed,true);
  await disposeDocument({loadingTask:{destroy:async()=>{throw new Error('cleanup');}}});
});

test('the undo routing predicate distinguishes browser restore from server replay', async () => {
  const {operationLocation} = await import('./session.mjs');
  assert.equal(operationLocation([]), 'local');
  assert.equal(operationLocation([{run_id:'server-issued',new_text:'changed'}]), 'server');
});

test('a second edit replaces its original address and undo restores text and style together', () => {
  const first = [{run_id: 'server-id', new_text: 'First', style: {bold: true}}];
  const state = commitRecipe({recipe: first, history: [[]]}, upsertOperation(first, {run_id: 'server-id', new_text: 'Second', style: {italic: true}}));
  assert.equal(state.recipe.length, 1);
  assert.deepEqual(previousRecipe(state), {recipe: first, history: [[]]});
  assert.equal(first[0].new_text, 'First');
});

test('cache eviction reuploads authoritative original bytes and retries once', async () => {
  const original = new Uint8Array([37,80,68,70]);
  const session = {original, password: 'secret', jobId: 'old'};
  const seen = [];
  const result = await withSourceRetry(session, async id => {
    seen.push(id);
    if (id === 'old') throw {status: 409, code: 'SOURCE_MISSING'};
    return 'done';
  }, async (bytes, password) => {
    assert.equal(bytes, original);
    assert.equal(password, 'secret');
    return {job_id: 'restored'};
  });
  assert.equal(result, 'done');
  assert.deepEqual(seen, ['old', 'restored']);
});

test('retry does not loop or swallow unrelated conflicts', async () => {
  let restores = 0;
  await assert.rejects(withSourceRetry({jobId:'old'}, async () => {throw {status:409,code:'SOURCE_MISSING'};}, async () => {restores++; return {job_id:'new'};}));
  assert.equal(restores, 1);
  await assert.rejects(withSourceRetry({}, async () => {throw {status:409,code:'OTHER'};}, async () => {assert.fail();}));
});

test('server box transformation handles rotated coordinates', () => {
  assert.deepEqual(viewportBox([10,20,30,40], {convertToViewportPoint: (x,y) => [y,100-x]}), {left:20,top:70,width:20,height:20});
});

test('worker queue bounds concurrency and promotes selected-page analysis', async () => {
  const queue=createRequestQueue({limit:1}),started=[];
  let release;
  const first=queue.run(()=>new Promise(resolve=>{started.push('first');release=resolve;}));
  await new Promise(resolve=>setImmediate(resolve));
  const background=queue.run(async()=>started.push('background'),10);
  const selected=queue.run(async()=>started.push('selected'),10);
  selected.promote(0);
  await new Promise(resolve=>setImmediate(resolve));
  assert.deepEqual(started,['first']);
  release();await Promise.all([first,background,selected]);
  assert.deepEqual(started,['first','selected','background']);
});

test('worker queue aborts queued document requests', async () => {
  const controller=new AbortController(),queue=createRequestQueue({limit:1,signal:controller.signal});
  let release;
  const running=queue.run(()=>new Promise(resolve=>{release=resolve;}));
  await new Promise(resolve=>setImmediate(resolve));
  const queued=queue.run(()=>assert.fail('stale work ran'));
  controller.abort();await assert.rejects(queued,{name:'AbortError'});
  release();await running;
});

test('429 backoff is bounded and other failures are not retried', async () => {
  let attempts=0;
  await assert.rejects(retryWorkerBusy(async()=>{attempts++;throw {status:429};},{delays:[0,0]}));
  assert.equal(attempts,3);
  attempts=0;
  await assert.rejects(retryWorkerBusy(async()=>{attempts++;throw {status:413};},{delays:[0,0]}));
  assert.equal(attempts,1);
});

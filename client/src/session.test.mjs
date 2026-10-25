import test from 'node:test';
import {createLocalSession,restoreSession,snapshotCopyBytes,canAnalyzeText} from './session.mjs';

test('local session and restored snapshots never create a server job or reuse controllers',async()=>{
  const bytes=new Uint8Array([1,2,3]),source=new Uint8Array([4,5]);
  const local=createLocalSession({name:'private.pdf',openedBytes:bytes});
  assert.equal(local.jobId,null);assert.equal(canAnalyzeText(local),false);
  assert.equal(local.openedBytes,bytes);assert.equal(local.bytes,bytes);assert.equal(local.sourceBytes,bytes);
  local.controller.abort();
  const restored=restoreSession(local,{bytes,sourceBytes:source,password:'密碼🔑',analysis:{enabled:true,sourceIdentity:'baseline'},recipe:[]});
  assert.notEqual(restored.controller,local.controller);assert.equal(restored.controller.signal.aborted,false);
  assert.equal(restored.jobId,null);assert.equal(restored.sourceBytes,source);assert.equal(restored.openedBytes,bytes);
  assert.equal(canAnalyzeText(restored),true);
  let uploaded;
  const result=await withSourceRetry(restored,id=>Promise.resolve(id),(body,password)=>{uploaded={body,password};return Promise.resolve({job_id:'fresh'});});
  assert.equal(result,'fresh');assert.equal(uploaded.body,source);assert.equal(uploaded.password,'密碼🔑');
});
test('snapshot copy prediction counts full unique backing stores before allocation',()=>{
  const buffer=new ArrayBuffer(32),a=new Uint8Array(buffer,0,2),b=new Uint8Array(buffer,3,4);
  assert.equal(snapshotCopyBytes({bytes:a,sourceBytes:b,analysis:{index:{raw:a}}}),32);
});
test('closed session cannot upload its baseline or call a retained job',async()=>{
  const local=createLocalSession({openedBytes:new Uint8Array([1])});local.controller.abort();
  let calls=0;
  await assert.rejects(withSourceRetry(local,async()=>{calls++;},async()=>{calls++;return {job_id:'bad'};}),{name:'AbortError'});
  assert.equal(calls,0);
});
test('mixed materialized snapshots restore exact bytes baseline style selection and fresh analysis session',async()=>{
  const {captureSnapshot,pushSnapshot,popSnapshot,peekSnapshot,admitHistory}=await import('./pageOps/documentHistory.mjs');
  const opened=new Uint8Array([1,2,3]),text=new Uint8Array([4,5]),pages=new Uint8Array([8,9,10]);
  const initial={bytes:opened,sourceBytes:opened,password:' secret ',recipe:[],selectedPage:2,style:{bold:true},selection:{run_id:'original'},analysis:{enabled:true,sourceIdentity:'first',meta:{page_count:2},index:{}},findState:{query:'old'},localMetadata:{signed:false},acknowledged:false};
  let history=[],live=createLocalSession({name:'mixed.pdf',openedBytes:opened});
  for(const state of [initial,{...initial,bytes:text,recipe:[{run_id:'original',new_text:'edited',style:{bold:true}}]},{...initial,bytes:pages,sourceBytes:pages,password:'',recipe:[],analysis:{enabled:false},selectedPage:1}]){
    assert.equal(admitHistory({openedBytes:opened,current:state,history,temporaryBytes:snapshotCopyBytes(state)}).ok,true);
    history=pushSnapshot(history,captureSnapshot(state));
  }
  for(const expected of [pages,text,opened]){
    const snapshot=peekSnapshot(history),next=restoreSession(live,snapshot);live.controller.abort();live=next;history=popSnapshot(history);
    assert.deepEqual(live.bytes,expected);assert.equal(live.openedBytes,opened);assert.equal(live.controller.signal.aborted,false);assert.equal(live.jobId,null);
    assert.deepEqual(snapshot.style,{bold:true});assert.equal(snapshot.selection.run_id,'original');assert.equal(snapshot.findState.query,'old');
    if(expected===text){assert.deepEqual(live.sourceBytes,opened);assert.equal(live.password,' secret ');assert.equal(snapshot.recipe[0].style.bold,true);}
  }
  assert.equal(history.length,0);
});
import assert from 'node:assert/strict';
import { upsertOperation, commitRecipe, previousRecipe, withSourceRetry, viewportBox, createRequestQueue, retryWorkerBusy } from './session.mjs';

test('find refusals explain normalized boundaries and retain unknown diagnostic codes', async () => {
  const {explainReason,refusalCode,needsFontChoice}=await import('./session.mjs');
  assert.match(explainReason('normalization_boundary_unreplaceable'),/part of a character/);
  assert.equal(explainReason('future_safe_refusal'),'This text cannot be safely rewritten.');
  assert.equal(refusalCode('future_safe_refusal'),'future_safe_refusal');
  assert.equal(needsFontChoice({state:'editable_original',suggested_font_family:null},{}),true);
  assert.equal(needsFontChoice({state:'editable_original',suggested_font_family:null},{font_family:'Serif'}),false);
});

test('fit refusals use readable copy and never repeat a prose error as a code', async () => {
  const {explainReason,refusalCode,explainFit}=await import('./session.mjs');
  const reason='delta -209.98pt exceeds trailing-kern (+/-3.00pt) and inter-word-kern (+/-0.00pt over 0 gaps) absorption range';
  assert.doesNotMatch(explainReason(reason),/delta|kern/);
  assert.equal(refusalCode(reason),null);
  assert.equal(refusalCode('unknown prose error'),null);
  assert.equal(refusalCode('font_size_change_unsupported'),'font_size_change_unsupported');
  assert.match(explainReason('delta 20.00pt exceeds trailing-kern absorption range'),/too wide/);
  assert.match(explainFit('trailing_kern'),/font size/);
});

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

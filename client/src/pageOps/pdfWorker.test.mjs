import test from 'node:test';
import assert from 'node:assert/strict';
import {runPdfJob} from './pdfWorker.mjs';
function fake() {
  const listeners=new Map();return {terminated:0,listeners,addEventListener:(key,fn)=>listeners.set(key,fn),removeEventListener:(key,fn)=>{if(listeners.get(key)===fn)listeners.delete(key);},postMessage(message,transfer){this.message=structuredClone(message,{transfer});},terminate(){this.terminated++;},emit(key,data){listeners.get(key)?.(key==='message'?{data}:data);}};
}
test('worker uses disposable clones and terminates/removes handlers on successful reply',async()=>{
  const worker=fake(),bytes=new Uint8Array([1,2]),source=bytes.buffer;
  const promise=runPdfJob({workerFactory:()=>worker,command:'inspect',payload:{bytes}});
  assert.equal(bytes.byteLength,2);assert.equal(source.byteLength,2);assert.deepEqual(worker.message.payload.bytes,bytes);
  worker.emit('message',{id:worker.message.id,ok:true,result:{pageCount:2}});
  assert.deepEqual(await promise,{pageCount:2});assert.equal(worker.terminated,1);assert.equal(worker.listeners.size,0);
});
test('abort, timeout, crash, messageerror, malformed and fixed refusal replies terminate exactly once',async()=>{
  for(const mode of ['abort','timeout','error','messageerror','malformed','refusal']) {
    const worker=fake(),controller=new AbortController(),bytes=new Uint8Array([1]);
    const promise=runPdfJob({workerFactory:()=>worker,command:'rotate',payload:{bytes},signal:controller.signal,timeoutMs:mode==='timeout'?5:1000});
    const expected={abort:'PDF_JOB_ABORTED',timeout:'PDF_JOB_TIMEOUT',error:'PDF_WORKER_CRASH',messageerror:'PDF_WORKER_CRASH',malformed:'PDF_WORKER_RESULT_INVALID',refusal:'FINAL_PAGE'}[mode];
    if(mode==='abort')controller.abort();
    if(['error','messageerror'].includes(mode))worker.emit(mode,new Error('secret content'));
    if(mode==='malformed')worker.emit('message',{id:worker.message.id,ok:true});
    if(mode==='refusal')worker.emit('message',{id:worker.message.id,ok:false,error:{code:'FINAL_PAGE',message:'secret'}});
    await assert.rejects(promise,{code:expected});assert.equal(worker.terminated,1);assert.equal(worker.listeners.size,0);assert.equal(bytes.byteLength,1);
    worker.emit('message',{id:worker.message.id,ok:true,result:'late'});assert.equal(worker.terminated,1);
  }
});
test('already aborted and excessive copy budget allocate no worker',async()=>{
  let made=0;const controller=new AbortController();controller.abort();
  await assert.rejects(runPdfJob({workerFactory:()=>made++,command:'inspect',payload:{},signal:controller.signal}),{code:'PDF_JOB_ABORTED'});
  await assert.rejects(runPdfJob({workerFactory:()=>made++,command:'inspect',payload:{bytes:new Uint8Array(50*1024*1024+1)}}),{code:'LOCAL_PDF_TOO_LARGE'});
  assert.equal(made,0);
});
test('caller fixed error codes preserve import refusals while unknown or invalid codes stay generic',async()=>{
  for(const [errorCodes,code,expected] of [[['MERGE_XFA_UNSUPPORTED'],'MERGE_XFA_UNSUPPORTED','MERGE_XFA_UNSUPPORTED'],[[],'MERGE_XFA_UNSUPPORTED','PDF_JOB_FAILED'],[['secret content'],'secret content','PDF_JOB_FAILED']]) {
    const worker=fake(),promise=runPdfJob({workerFactory:()=>worker,command:'merge',payload:{},errorCodes});
    worker.emit('message',{id:worker.message.id,ok:false,error:{code}});
    await assert.rejects(promise,{code:expected});assert.equal(worker.terminated,1);assert.equal(worker.listeners.size,0);
  }
});

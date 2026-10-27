import test from 'node:test';
import assert from 'node:assert/strict';
import {createExportController,validateServerExport} from './controller.mjs';
const response=(overrides={})=>({data:btoa('%PDF-test'),media_type:'application/pdf',filename:'compressed.pdf',before_bytes:3,after_bytes:9,notices:[],changed_images:0,location:'server',...overrides});
function fixture(overrides={}) {
  const bytes=new Uint8Array([1,2,3]),session={password:'π',history:['untouched']},current={session,bytes,version:1,retainedBytes:3},calls=[],revoked=[],states=[];
  const controller=createExportController({getCurrent:()=>current,request:async(path,options)=>{calls.push({path,...options});return response();},createUrl:()=>`blob:${calls.length}:${Math.random()}`,revokeUrl:url=>revoked.push(url),onState:s=>states.push(s),...overrides});
  return {bytes,session,current,calls,revoked,states,controller};
}
test('server posts exact current materialized bytes, password headers and lossless defaults; immutable history',async()=>{
  const f=fixture(),result=await f.controller.prepare({format:'compress'});
  assert.strictEqual(f.calls[0].body,f.bytes);assert.match(f.calls[0].path,/downsample=false/);assert.equal(f.calls[0].headers['Content-Type'],'application/pdf');assert.ok(Object.keys(f.calls[0].headers).some(k=>/password/i.test(k)));
  assert.equal(result.location,'server');assert.equal(result.beforeBytes,3);assert.equal(result.afterBytes,9);assert.equal(result.files[0].bytes.length,9);assert.deepEqual(f.session.history,['untouched']);assert.strictEqual(f.current.bytes,f.bytes);
  f.controller.invalidate();assert.equal(f.revoked.length,1);
});
test('local image/split branch has zero API requests and exposes bounded ZIP for multiple files',async()=>{
  let raster=0,split=0;
  const files=[1,2].map(n=>({bytes:new Uint8Array([n]),filename:`page-000${n}.png`,mediaType:'image/png',notices:[]}));
  const f=fixture({renderImages:async()=>{raster++;return {files,notices:[]};},runSplit:async(bytes,groups,options)=>{split++;assert.deepEqual(groups,[[0],[1]]);assert.ok(options.signal);return {files:files.map((f,i)=>({...f,filename:`split-000${i+1}.pdf`,mediaType:'application/pdf'})),notices:[]};}});
  assert.ok((await f.controller.prepare({format:'png',pages:[1,2],dpi:150},{pdf:{numPages:2}})).archive);
  await f.controller.prepare({format:'split',groups:[[0],[1]]});assert.equal(f.calls.length,0);assert.equal(raster,1);assert.equal(split,1);
});
test('bytes, version and session changes discard stale response; abort releases URLs and never publishes result',async()=>{
  for(const field of ['bytes','version','session']) {
    let release;const f=fixture({request:()=>new Promise(resolve=>release=resolve)}),pending=f.controller.prepare({format:'compress'});
    f.current[field]=field==='version'?2:{};release(response());await assert.rejects(pending,{name:'AbortError'});assert.ok(!f.controller.result);
  }
  let release,signal;const f=fixture({request:(_,options)=>{signal=options.signal;return new Promise(resolve=>release=resolve);}}),pending=f.controller.prepare({format:'compress'});
  f.controller.cancel();assert.ok(signal.aborted);release(response());await assert.rejects(pending,{name:'AbortError'});assert.ok(!f.controller.result);
});
test('strict server schema rejects hostile MIME, base64, size, filename and unknown notices',()=>{
  for(const changes of [{media_type:'text/html'},{data:'!bad'},{data:'JVBERg=='},{after_bytes:48*1024*1024+1},{after_bytes:2},{before_bytes:4},{filename:'../x.pdf'},{notices:['<script>']},{changed_images:-1},{location:'browser'}])assert.throws(()=>validateServerExport(response(changes),'compress',3));
  assert.equal(validateServerExport(response({notices:['NO_SIZE_REDUCTION']}),'compress',3).notices[0],'NO_SIZE_REDUCTION');
});
test('admission blocks work before dispatch and cancellation rejects even ignored aborts',async()=>{
  const f=fixture();f.current.retainedBytes=300*1024*1024;await assert.rejects(f.controller.prepare({format:'compress'}),{code:'EXPORT_LIMIT'});assert.equal(f.calls.length,0);
});

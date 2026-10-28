import test from 'node:test';
import assert from 'node:assert/strict';
import {createExportController,validateServerExport} from './controller.mjs';

const mime='application/vnd.openxmlformats-officedocument.wordprocessingml.document';
async function fixture(overrides={}) {
  const bytes=new Uint8Array([1,2,3]),session={password:'π',history:['untouched']},current={bytes,session,version:1,retainedBytes:3};
  const source=Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',bytes)),n=>n.toString(16).padStart(2,'0')).join('');
  const review={location:'server',source_sha256:source,snapshot_sha256:'a'.repeat(64),policy_version:1,
    review:{schema_version:1,page_count:1,has_text:true,facts:[],supported_ruled_tables:0,images_complete:true}};
  const zip=new Uint8Array([80,75,3,4,255]);
  const artifact={data:btoa(String.fromCharCode(...zip)),media_type:mime,filename:'document.docx',before_bytes:3,after_bytes:5,changed_images:0,notices:[],location:'server'};
  const calls=[],urls=[],states=[];
  const controller=createExportController({getCurrent:()=>current,request:async(path,options)=>{
    calls.push({path,...options});return path.includes('docx-review')?review:artifact;
  },createUrl:()=>{urls.push('url');return 'blob:docx';},revokeUrl:()=>urls.pop(),onState:s=>states.push(s),...overrides});
  return {controller,current,bytes,session,review,artifact,calls,urls,states};
}

test('DOCX requires review, then a separate conversion using identical bytes and digests',async()=>{
  const f=await fixture();
  await assert.rejects(()=>f.controller.convertDocx({format:'docx'}),{code:'DOCX_REVIEW_REQUIRED'});
  assert.equal(f.calls.length,0);
  await f.controller.reviewDocx({format:'docx'});
  assert.equal(f.calls.length,1);assert.equal(f.urls.length,0);
  assert.equal(f.states.at(-1).status,'review-ready');
  const result=await f.controller.convertDocx({format:'docx'});
  assert.equal(f.calls.length,2);assert.strictEqual(f.calls[1].body,f.bytes);
  assert.deepEqual(JSON.parse(f.calls[1].headers['X-DOCX-Review']),{
    source_sha256:f.review.source_sha256,snapshot_sha256:f.review.snapshot_sha256,policy_version:1});
  assert.equal(result.files[0].filename,'document.docx');assert.deepEqual(f.session.history,['untouched']);
  assert.strictEqual(f.current.bytes,f.bytes);
  f.controller.invalidate();assert.equal(f.urls.length,0);
});

test('DOCX stale bytes, revision, session or options require another explicit review',async()=>{
  for(const field of ['bytes','version','session','options']) {
    const f=await fixture();await f.controller.reviewDocx({format:'docx'});
    if(field==='bytes')f.current.bytes=f.bytes.slice();
    if(field==='version')f.current.version++;
    if(field==='session')f.current.session={};
    await assert.rejects(()=>f.controller.convertDocx(field==='options'?{format:'docx',acknowledged:true}:{format:'docx'}),{code:'DOCX_REVIEW_REQUIRED'});
    assert.equal(f.calls.length,1);assert.equal(f.urls.length,0);
  }
});

test('DOCX malformed or wrong-source review cannot authorize generation',async()=>{
  for(const alter of [r=>r.source_sha256='0'.repeat(64),r=>r.review.facts=[{code:'SOURCE TEXT',pages:[0],count:1}],
    r=>r.review.page_count=0,r=>r.review.images_complete=false,r=>r.review.has_text=false,r=>r.extra='source text',
    r=>r.review.facts=[{code:'COLUMN_LAYOUT',pages:[1],count:null}]]) {
    const f=await fixture();alter(f.review);
    await assert.rejects(()=>f.controller.reviewDocx({format:'docx'}),{code:'EXPORT_RESPONSE_INVALID'});
    assert.equal(f.urls.length,0);
  }
});

test('DOCX cancellation suppresses a held review response and all URLs',async()=>{
  let release;
  const f=await fixture({request:()=>new Promise(resolve=>release=resolve)});
  const pending=f.controller.reviewDocx({format:'docx'});
  f.controller.cancel();release(f.review);
  await assert.rejects(pending,{name:'AbortError'});
  assert.equal(f.urls.length,0);assert.notEqual(f.states.at(-1).status,'review-ready');
});

test('DOCX artifact is binary ZIP with a fixed MIME, name and zero changed images',async()=>{
  const f=await fixture();
  assert.equal(validateServerExport(f.artifact,'docx',3).files[0].bytes[4],255);
  for(const value of [{...f.artifact,data:btoa('%PDF-'),after_bytes:5},
    {...f.artifact,filename:'document.docm'},{...f.artifact,changed_images:1}]) {
    assert.throws(()=>validateServerExport(value,'docx',3),{code:'EXPORT_RESPONSE_INVALID'});
  }
});

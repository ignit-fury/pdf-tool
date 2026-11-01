import test from 'node:test';
import assert from 'node:assert/strict';
import {createTextBoxController,validateBoxes} from './controller.mjs';

const style={font_family:'Sans',font_size:12,bold:false,italic:false,color:[0,0,0],character_spacing:0,line_spacing:1.2,paragraph_spacing:0,alignment:'left'};
const payload={operation:'upsert',page_index:0,text:'Two lines\nNative text',rect:{left:30,top:40,width:200,height:70},style,allow_overlap:false};
async function fixture(overrides={}){
  const bytes=new TextEncoder().encode('%PDF-current'),sourceBytes=new TextEncoder().encode('%PDF-old'),session={sourceBytes,password:'密碼',controller:new AbortController()},current={session,bytes,version:1,retainedBytes:30};
  const hash=Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',bytes)),v=>v.toString(16).padStart(2,'0')).join('');
  const box={id:'a'.repeat(32),page_index:0,text:payload.text,rect:payload.rect,style};
  const response={ok:true,source_hash:hash,pdf:btoa('%PDF-exact-candidate'),page_index:0,boxes:[box],layout:{required_height:30,available_height:70,line_count:2},notices:[],location:'server'};
  const calls=[],states=[],disposed=[];
  const controller=createTextBoxController({getCurrent:()=>current,request:async(path,options)=>{calls.push({path,...options});return path==='/upload'?{job_id:'current-job',source_hash:hash}:JSON.parse(options.body).operation==='list'?{ok:true,source_hash:hash,boxes:[box],location:'server'}:response;},prepare:async bytes=>({bytes,document:{name:'candidate'},dispose:()=>disposed.push('candidate')}),onState:s=>states.push(s),...overrides});
  return {controller,current,bytes,sourceBytes,session,hash,box,response,calls,states,disposed};
}
test('explicit preview uploads current materialized bytes and retains an exact separate candidate',async()=>{
  const f=await fixture();assert.equal(f.calls.length,0);
  const result=await f.controller.preview(payload);
  assert.strictEqual(f.calls[0].body,f.bytes);assert.notStrictEqual(f.calls[0].body,f.sourceBytes);
  assert.equal(new TextDecoder().decode(result.prepared.bytes),'%PDF-exact-candidate');
  assert.equal(f.states.at(-1).status,'ready');assert.strictEqual(f.current.bytes,f.bytes);
  assert.deepEqual(JSON.parse(f.calls[1].body),payload);
  assert.equal(f.calls[1].headers['X-PDF-Password-B64'],btoa(String.fromCharCode(...new TextEncoder().encode('密碼'))));
  const taken=f.controller.take(payload);assert.strictEqual(taken.prepared,result.prepared);assert.deepEqual(f.disposed,[]);
  assert.equal(f.controller.take(payload),null);
});
test('source expansion uploads immutable baseline while binding publication to current bytes',async()=>{
  const baseline=new TextEncoder().encode('%PDF-baseline'),hash=Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',baseline)),v=>v.toString(16).padStart(2,'0')).join('');
  const calls=[];let f;
  f=await fixture({request:async(path,options)=>{calls.push({path,...options});return path==='/upload'?{job_id:'baseline',source_hash:hash}:{...f.response,source_hash:hash};}});
  f.session.sourceBytes=baseline;
  const conversion={...payload,operation:'replace-source',source_run_id:'original-run',recipe:[{run_id:'other',new_text:'kept'}]};
  await f.controller.preview(conversion);assert.strictEqual(calls[0].body,baseline);assert.strictEqual(f.current.bytes,f.bytes);
  f.current.version++;assert.equal(f.controller.take(conversion),null);
});
test('preview accepts a verified native box with a separate initial-letter size',async()=>{
  const f=await fixture();
  const mixedStyle={...style,initial_font_size:75};
  f.response.boxes[0].style=mixedStyle;
  const result=await f.controller.preview({...payload,style:mixedStyle});
  assert.equal(result.boxes[0].style.initial_font_size,75);
  assert.equal(f.states.at(-1).status,'ready');
});
test('source expansion admits the larger original upload before any network request',async()=>{
  const f=await fixture();f.session.sourceBytes=new Uint8Array(50*1024*1024);f.current.retainedBytes=200*1024*1024;
  await assert.rejects(()=>f.controller.preview({...payload,operation:'replace-source',source_run_id:'original',recipe:[]}),{code:'EXPORT_LIMIT'});
  assert.equal(f.calls.length,0);
});
test('list performs no candidate generation; source cache recovers from missing source once',async()=>{
  const f=await fixture();let missed=false;
  const g=await fixture({request:async(path,options)=>{f.calls.push({path,...options});if(path==='/upload')return{job_id:'current-job',source_hash:f.hash};if(!missed){missed=true;throw Object.assign(new Error(),{status:409,code:'SOURCE_MISSING'});}return{ok:true,source_hash:f.hash,boxes:[f.box],location:'server'};}});
  const boxes=await g.controller.list();assert.equal(boxes.length,1);
  assert.equal(f.calls.filter(c=>c.path==='/upload').length,2);assert.equal(g.controller.previewResult,null);
});
test('cancel and source/draft changes dispose candidates and cannot publish stale data',async()=>{
  for(const field of ['session','bytes','version','payload']){
    const f=await fixture();await f.controller.preview(payload);
    if(field==='session')f.current.session={controller:new AbortController()};
    if(field==='bytes')f.current.bytes=f.bytes.slice();
    if(field==='version')f.current.version++;
    assert.equal(f.controller.take(field==='payload'?{...payload,text:'different'}:payload),null);
    assert.equal(f.disposed.length,1);
  }
  const f=await fixture();await f.controller.preview(payload);f.controller.cancel();assert.equal(f.disposed.length,1);assert.equal(f.controller.previewResult,null);
});
test('a late prepared viewer is disposed after cancellation without changing current bytes',async()=>{
  let release;const f=await fixture({prepare:()=>new Promise(resolve=>release=resolve)});
  const pending=f.controller.preview(payload);while(!release)await new Promise(resolve=>setImmediate(resolve));
  f.controller.cancel();release({bytes:new TextEncoder().encode('%PDF-late'),document:{},dispose:()=>f.disposed.push('late')});
  await assert.rejects(pending,{name:'AbortError'});assert.deepEqual(f.disposed,['late']);assert.strictEqual(f.current.bytes,f.bytes);
});
test('overflow yields numeric expansion feedback and no viewer or publication',async()=>{
  const f=await fixture();f.response={};let prepared=false;
  const g=await fixture({prepare:async()=>{prepared=true;},request:async(path)=>path==='/upload'?{job_id:'j',source_hash:f.hash}:{ok:false,source_hash:f.hash,code:'TEXT_BOX_OVERFLOW',required_height:120,available_height:70,location:'server'}});
  const result=await g.controller.preview(payload);assert.equal(result.required_height,120);assert.equal(prepared,false);assert.equal(g.states.at(-1).status,'overflow');
});
test('overlapping canceled preparations retain independent memory accounting',async()=>{
  const pending=[];
  const f=await fixture({prepare:bytes=>new Promise(resolve=>pending.push({bytes,resolve}))});
  const first=f.controller.preview(payload);const firstRejected=assert.rejects(first,{name:'AbortError'});
  while(pending.length<1)await new Promise(resolve=>setImmediate(resolve));
  const one=pending[0].bytes.buffer.byteLength*2;
  f.controller.cancel();
  const second=f.controller.preview(payload);
  while(pending.length<2)await new Promise(resolve=>setImmediate(resolve));
  assert.equal(f.controller.retainedBytes,one*2);
  pending[0].resolve({bytes:pending[0].bytes,document:{},dispose:()=>{}});
  await firstRejected;await new Promise(resolve=>setImmediate(resolve));
  assert.equal(f.controller.retainedBytes,one);
  pending[1].resolve({bytes:pending[1].bytes,document:{},dispose:()=>{}});
  await second;assert.equal(f.controller.retainedBytes,one);f.controller.dispose();
});
test('wrong hashes, unknown notices, fake PDF and unbounded metadata refuse before preparation',async()=>{
  for(const alter of [r=>r.source_hash='0'.repeat(64),r=>r.notices=['source text'],r=>r.pdf=btoa('not PDF'),r=>r.boxes[0].text='x'.repeat(10001),r=>r.layout.line_count=0]){
    const f=await fixture();alter(f.response);await assert.rejects(()=>f.controller.preview(payload),{code:'TEXT_BOX_RESPONSE_INVALID'});assert.equal(f.controller.previewResult,null);
  }
  assert.throws(()=>validateBoxes([{id:'bad',page_index:0,text:'a',rect:payload.rect,style}]),{code:'TEXT_BOX_RESPONSE_INVALID'});
  const box={id:'a'.repeat(32),page_index:1,text:'Rotated',rect:payload.rect,style,rotation:90};
  assert.equal(validateBoxes([box])[0].rotation,90);
  assert.throws(()=>validateBoxes([{...box,rotation:45}]),{code:'TEXT_BOX_RESPONSE_INVALID'});
  assert.equal(validateBoxes([{...box,style:{...style,initial_font_size:75}}])[0].style.initial_font_size,75);
  assert.throws(()=>validateBoxes([{...box,style:{...style,initial_font_size:513}}]),{code:'TEXT_BOX_RESPONSE_INVALID'});
});
test('paragraph edits upload the source baseline and expose the server plan',async()=>{
  const baseline=new TextEncoder().encode('%PDF-baseline'),hash=Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',baseline)),v=>v.toString(16).padStart(2,'0')).join('');
  const recipe=[{run_id:'r1',new_text:'New line'}],lines={ok:true,plan:'lines',source_hash:hash,pdf:btoa('%PDF-lines'),recipe,notices:[],location:'server'};
  let reply,f;const calls=[];
  f=await fixture({request:async(path,options)=>{calls.push({path,...options});return path==='/upload'?{job_id:'baseline',source_hash:hash}:reply;}});
  f.session.sourceBytes=baseline;
  const edit={operation:'replace-paragraph',paragraph_id:'p',source_run_ids:['r1'],page_index:0,lines:['New line'],style:{},recipe:[],rect:payload.rect,allow_rebuild:false,run_styles:{}};
  reply=lines;const result=await f.controller.preview(edit);
  assert.strictEqual(calls[0].body,baseline);assert.equal(result.plan,'lines');assert.deepEqual(result.recipe,recipe);
  assert.equal(new TextDecoder().decode(result.prepared.bytes),'%PDF-lines');assert.strictEqual(f.controller.take(edit),result);
  reply={...f.response,source_hash:hash,plan:'rebuild'};const rebuilt=await f.controller.preview({...edit,allow_rebuild:true});
  assert.equal(rebuilt.plan,'rebuild');assert.equal(rebuilt.boxes.length,1);
  reply={...f.response,source_hash:hash,plan:'rebuild',pushed:12.5};assert.equal((await f.controller.preview({...edit,allow_rebuild:true})).pushed,12.5);
  reply={...f.response,source_hash:hash,plan:'rebuild',pushed:-1};await assert.rejects(()=>f.controller.preview(edit),{code:'TEXT_BOX_RESPONSE_INVALID'});
  reply={...lines,pushed:0};assert.equal((await f.controller.preview(edit)).plan,'lines');
  reply={...lines,pushed:3};await assert.rejects(()=>f.controller.preview(edit),{code:'TEXT_BOX_RESPONSE_INVALID'});
  reply={...lines,boxes:[]};await assert.rejects(()=>f.controller.preview(edit),{code:'TEXT_BOX_RESPONSE_INVALID'});
  reply={...lines,plan:'other'};await assert.rejects(()=>f.controller.preview(edit),{code:'TEXT_BOX_RESPONSE_INVALID'});
  reply={...f.response,source_hash:hash,plan:'lines'};await assert.rejects(()=>f.controller.preview(edit),{code:'TEXT_BOX_RESPONSE_INVALID'});
});
test('boxes may carry per-run styles that spell the box text',()=>{
  const runStyle={font_family:'Serif',font_size:11,bold:true,italic:false,color:[0,0,0]};
  const box={id:'b'.repeat(32),page_index:0,text:'Ab',rect:{left:1,top:1,width:10,height:10},style,runs:[{text:'A',style:runStyle},{text:'b',style:runStyle}]};
  assert.deepEqual(validateBoxes([box])[0].runs,box.runs);
  assert.throws(()=>validateBoxes([{...box,runs:[{text:'A',style:runStyle}]}]),{code:'TEXT_BOX_RESPONSE_INVALID'});
  assert.throws(()=>validateBoxes([{...box,runs:[{text:'Ab',style:{...runStyle,font_family:'Comic'}}]}]),{code:'TEXT_BOX_RESPONSE_INVALID'});
});

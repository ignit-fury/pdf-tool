import test from 'node:test';
import assert from 'node:assert/strict';

async function api(){const module=await import('./search.mjs').catch(()=>null);assert.ok(module,'canonical matcher missing');return module;}
const page=(text,state='editable_original')=>({1:{runs:[{run_id:'r1',text,state,suggested_font_family:'Serif'}]}});

test('projection preserves expansion, canonical ordering and UTF16 provenance',async()=>{
  const {projectText}=await api();
  assert.deepEqual(projectText('ﬁß😀é'),{text:'fiss😀e\u0301',spans:[[0,1],[0,1],[1,2],[1,2],[2,4],[2,4],[4,5],[4,5]]});
  assert.deepEqual(projectText('a\u0315\u0300').spans,[[0,1],[2,3],[1,2]]);
});
test('full expansions safe, partial expansions visible locked, graphemes indivisible',async()=>{
  const {findMatches}=await api();
  for(const [text,full,partial] of [['ﬁ','fi','f'],['ß','ss','s'],['é','é','e']]){
    assert.equal(findMatches(page(text),full)[0].replaceable,true);
    const hits=findMatches(page(text),partial);
    assert.ok(hits.length);assert.ok(hits.every(m=>!m.replaceable&&m.reason==='normalization_boundary_unreplaceable'));
  }
  const hit=findMatches(page('😀 cat'),'cat')[0];assert.equal(hit.start,3);assert.equal(hit.end,6);
  assert.equal(findMatches(page('a\u0315\u0300'),'à')[0].replaceable,false);
});
test('literal defaults, match case, Unicode whole words and CJK',async()=>{
  const {findMatches}=await api();
  assert.equal(findMatches(page('Cat cat scatter'),'cat').length,3);
  assert.equal(findMatches(page('Cat cat scatter'),'cat',{matchCase:true}).length,2);
  assert.equal(findMatches(page('Cat cat scatter'),'cat',{wholeWords:true}).length,2);
  assert.equal(findMatches(page('été étéx'),'ÉTÉ',{wholeWords:true}).length,1);
  assert.equal(findMatches(page('你好 世界'),'世界',{wholeWords:true}).length,1);
  assert.equal(findMatches(page('a.b a$b'),'a.b').length,1);
  assert.deepEqual(findMatches(page('hello'),''),[]);
});
test('current recipe and stable incremental IDs retain refused occurrences and context',async()=>{
  const {findMatches,projectSearchText}=await api();const pages=page('cat cat');
  pages[1].runs[0].search=projectSearchText('cat cat');
  const old=findMatches(pages,'cat');
  const added={...pages,2:{runs:[{run_id:'r2',text:'cat',state:'uneditable',reason:'Type3'}]}};
  const hits=findMatches(added,'cat');assert.deepEqual(hits.slice(0,2),old);assert.equal(hits[2].reason,'Type3');assert.equal(hits[2].replaceable,false);
  const edited=findMatches(pages,'dog',{recipe:[{run_id:'r1',new_text:'dog cat'}]});assert.equal(edited.length,1);assert.equal(edited[0].text,'dog');assert.equal(edited[0].after,' cat');
  const context=findMatches(page('x'.repeat(60)+'cat'+'z'.repeat(60)),'cat')[0];assert.equal(context.before,'…'+'x'.repeat(48));assert.equal(context.after,'z'.repeat(48)+'…');
});

test('long literal matches avoid argument-count limits and preserve astral context',async()=>{
  const {findMatches}=await api();const text='a'.repeat(150000);
  assert.equal(findMatches(page(text),text)[0].replaceable,true);
  const context=findMatches(page('😀'.repeat(60)+'cat'+'😀'.repeat(60)),'cat')[0];
  assert.equal(context.before,'…'+'😀'.repeat(48));assert.equal(context.after,'😀'.repeat(48)+'…');
});

test('shared source addresses retain distinct locked fragments and do not block safe replacements',async()=>{
  const {findMatches,sourceRunForMatch}=await api();
  const {buildReplacementRecipe}=await import('./buildRecipe.mjs');
  const first={run_id:'shared',text:'cat',state:'editable_original',box:[0,0,20,10]};
  const second={...first,box:[30,0,50,10]};
  const safe={...first,run_id:'safe',box:[0,20,20,30]};
  const pages={1:{runs:[first,second,safe]}};
  const hits=findMatches(pages,'cat');
  assert.equal(hits.length,3);
  assert.equal(new Set(hits.map(hit=>hit.id)).size,3);
  assert.deepEqual(hits.map(hit=>hit.replaceable),[false,false,true]);
  assert.ok(hits.slice(0,2).every(hit=>hit.reason==='operator_shared_by_multiple_runs'));
  assert.equal(sourceRunForMatch(pages,hits[0]),first);
  assert.equal(sourceRunForMatch(pages,hits[1]),second);
  assert.equal(sourceRunForMatch(pages,{...hits[1],runId:'stale'}),null);
  assert.deepEqual(buildReplacementRecipe({pages,matches:hits,replacement:'a'}).recipe,[{run_id:'safe',new_text:'a'}]);
  assert.equal(findMatches({1:{runs:[first,{...second,text:'dog'}]}},'cat')[0].replaceable,false);
});

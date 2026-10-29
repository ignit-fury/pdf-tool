import test from 'node:test';
import assert from 'node:assert/strict';
import {findMatches} from './search.mjs';
async function api(){const module=await import('./buildRecipe.mjs').catch(()=>null);assert.ok(module,'full recipe builder missing');return module;}
const pages={1:{runs:[{run_id:'r',text:'cat cat',state:'editable_original',suggested_font_family:'Serif'}]}};

test('validated review retains actual output offsets across length changes and exclusions',async()=>{
  const {buildReplacementRecipe:build}=await api(),matches=findMatches(pages,'cat');
  const long=build({pages,matches,replacement:'kitten'});
  assert.deepEqual(long.changes[0].spans,matches.map((m,i)=>({matchId:m.id,start:i*7,end:i*7+6})));
  const short=build({pages,matches,replacement:'x'});assert.deepEqual(short.changes[0].spans.map(s=>[s.start,s.end]),[[0,1],[2,3]]);
  const excluded=build({pages,matches,replacement:'kitten',excludedIds:new Set([matches[0].id])});assert.deepEqual(excluded.changes[0].spans.map(s=>[s.start,s.end]),[[4,10]]);
  const removed=build({pages,matches,replacement:''});assert.deepEqual(removed.changes[0].spans.map(s=>[s.start,s.end]),[[0,0],[1,1]]);
});

test('per-occurrence exclusions build one ordinary operation and preserve prior order/style',async()=>{
  const {buildReplacementRecipe:build}=await api();const matches=findMatches(pages,'cat');
  const recipe=[{run_id:'other',new_text:'old'},{run_id:'r',new_text:'cat cat',style:{bold:true}}];
  const result=build({pages,recipe,matches,excludedIds:new Set([matches[0].id]),replacement:'$\\'});
  assert.deepEqual(result.recipe,[recipe[0],{run_id:'r',new_text:'cat $\\',style:{bold:true}}]);
  assert.equal(result.selectedCount,1);assert.deepEqual(result.changedPages,[1]);assert.equal(result.changes.length,1);
  assert.equal(recipe[1].new_text,'cat cat');
  const removed=build({pages,recipe:[],matches,excludedIds:new Set(),replacement:''});assert.equal(removed.recipe[0].new_text,' ');assert.equal(removed.selectedCount,2);
});
test('no-op and refused proposals retain earlier edits and immutable run IDs',async()=>{
  const {buildReplacementRecipe:build}=await api();const recipe=[{run_id:'r',new_text:'dog dog',style:{italic:true}}];
  const matches=findMatches(pages,'dog',{recipe});
  const unchanged=build({pages,recipe,matches,replacement:'dog'});assert.deepEqual(unchanged.recipe,recipe);assert.equal(unchanged.selectedCount,0);assert.equal(unchanged.unchangedCount,2);
  const refused=build({pages,recipe,matches,replacement:'fox',refusedRunIds:new Set(['r'])});assert.deepEqual(refused.recipe,recipe);assert.equal(refused.changes.length,0);
  const second=build({pages,recipe,matches,replacement:'fox'});assert.deepEqual(second.recipe,[{run_id:'r',new_text:'fox fox',style:{italic:true}}]);
});
test('font recovery is narrow and preserves intentional existing styles',async()=>{
  const {buildReplacementRecipe:build}=await api();
  const p={1:{runs:[
    {run_id:'mapped',text:'cat',state:'editable_original',suggested_font_family:'Serif'},
    {run_id:'unmapped',text:'cat',state:'editable_original',suggested_font_family:null},
    {run_id:'sub',text:'cat',state:'editable_substitution',suggested_font_family:'Sans'},
  ]}};
  const recipe=[{run_id:'unmapped',new_text:'cat',style:{font_family:'Mono',bold:true}}];
  const result=build({pages:p,recipe,matches:findMatches(p,'cat',{recipe}),replacement:'fox',fontFamily:'Sans'});
  assert.equal(result.recipe.find(op=>op.run_id==='mapped').style,undefined);
  assert.deepEqual(result.recipe.find(op=>op.run_id==='unmapped').style,{font_family:'Mono',bold:true});
  assert.equal(result.recipe.find(op=>op.run_id==='sub').style.font_family,'Sans');
  const unknown=build({pages:p,recipe:[],matches:findMatches(p,'cat'),replacement:'fox',fontFamily:'Serif'});
  assert.equal(unknown.recipe.find(op=>op.run_id==='unmapped').style.font_family,'Serif');
});
test('safe Unicode spans and literal replacements retain untouched characters',async()=>{
  const {buildReplacementRecipe:build}=await api();const p={1:{runs:[{run_id:'u',text:'😀 ﬁ é',state:'editable_original'}]}};
  const result=build({pages:p,matches:findMatches(p,'fi'),replacement:'$&\\',recipe:[]});assert.equal(result.recipe[0].new_text,'😀 $&\\ é');
  assert.equal(build({pages:p,matches:findMatches(p,'f'),replacement:'x',recipe:[]}).changes.length,0);
});
test('existing recipe limits refuse atomically and count Unicode scalars',async()=>{
  const {buildReplacementRecipe:build}=await api();const matches=findMatches(pages,'cat');
  assert.throws(()=>build({pages,matches,replacement:'x'.repeat(10001)}),error=>error.code==='RECIPE_TOO_LARGE');
  const p={1:{runs:[{run_id:'one',text:'a',state:'editable_original'}]}};
  assert.equal(build({pages:p,matches:findMatches(p,'a'),replacement:'😀'.repeat(10000)}).changes.length,1);
  assert.throws(()=>build({pages,matches:[],recipe:Array.from({length:50001},(_,i)=>({run_id:String(i),new_text:'x'})),replacement:'x'}),error=>error.code==='RECIPE_TOO_LARGE');
  assert.throws(()=>build({pages,matches:[],recipe:Array.from({length:200},(_,i)=>({run_id:String(i),new_text:'😀'.repeat(2000)})),replacement:'x'}),error=>error.code==='RECIPE_TOO_LARGE');
});

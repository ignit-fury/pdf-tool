import test from 'node:test';
import assert from 'node:assert/strict';
import {effectiveLines,paragraphAt,paragraphPayload,draftChanged,runStyle} from './paragraphs.mjs';

const runs=new Map([['a',{run_id:'a',text:'Hello'}],['b',{run_id:'b',text:'bold'}],['c',{run_id:'c',text:'Next line'}]]);
const paragraph={paragraph_id:'p_1',page_index:0,lines:[['a','b'],['c']],box:[10,10,100,40],state:'editable'};

test('effective lines join runs with gap spaces and apply recipe overrides',()=>{
  assert.deepEqual(effectiveLines(paragraph,runs,[]),['Hello bold','Next line']);
  assert.deepEqual(effectiveLines(paragraph,runs,[{run_id:'b',new_text:'BOLD'}]),['Hello BOLD','Next line']);
});

test('effective lines mirror engine line_segments gap spaces',()=>{
  const r=new Map([['a',{run_id:'a',text:'a'}],['e',{run_id:'e',text:'e'}],['b',{run_id:'b',text:'b'}]]);
  const emptyE=[{run_id:'e',new_text:''}];
  const line=ids=>effectiveLines({paragraph_id:'x',page_index:0,lines:[ids],box:[0,0,1,1]},r,emptyE)[0];
  assert.equal(line(['a','e','b']),'a  b');
  assert.equal(line(['e','b']),' b');
  assert.equal(effectiveLines({paragraph_id:'x',page_index:0,lines:[['a','e','b']],box:[0,0,1,1]},new Map([...r,['a',{run_id:'a',text:'a '}]]),emptyE)[0],'a  b');
  assert.equal(line(['a','e']),'a ');
});

test('paragraphAt hit-tests the box',()=>{
  assert.equal(paragraphAt([paragraph],{x:50,y:20}),paragraph);
  assert.equal(paragraphAt([paragraph],{x:150,y:20}),null);
});

test('payload carries ids, lines and consent flag',()=>{
  const body=paragraphPayload({paragraph,lines:['Hi bold','Next line'],style:{},recipe:[],rect:{left:1,top:2,width:3,height:4},allowRebuild:false,runsById:runs});
  assert.equal(body.operation,'replace-paragraph');
  assert.equal(body.page_index,0);
  assert.deepEqual(body.source_run_ids,['a','b','c']);
  assert.equal(body.allow_rebuild,false);
  assert.deepEqual(body.lines,['Hi bold','Next line']);
  assert.deepEqual(Object.keys(body.run_styles),['a','b','c']);
  assert.equal(body.run_styles.a.font_family,'Sans');
});

test('draftChanged ignores unchanged drafts',()=>{
  assert.equal(draftChanged(paragraph,['Hello bold','Next line'],runs,[]),false);
  assert.equal(draftChanged(paragraph,['Hello bold!','Next line'],runs,[]),true);
});

test('runStyle draws at the visual display size, not the operator size',()=>{
  assert.equal(runStyle({font_display_size:9,font_size:1,bold:true}).font_size,9);
});

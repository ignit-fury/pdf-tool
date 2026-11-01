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

test('rebuild payload leaves family to each run, not the paragraph style',()=>{
  const body=paragraphPayload({paragraph,lines:['Hi bold','Next line'],style:{},recipe:[],rect:{left:1,top:2,width:3,height:4},allowRebuild:true,runsById:runs});
  assert.deepEqual(body.style,{});
});

test('draftChanged ignores unchanged drafts',()=>{
  assert.equal(draftChanged(paragraph,['Hello bold','Next line'],runs,[]),false);
  assert.equal(draftChanged(paragraph,['Hello bold!','Next line'],runs,[]),true);
});

test('runStyle draws at the visual display size, not the operator size',()=>{
  assert.equal(runStyle({font_display_size:9,font_size:1,bold:true}).font_size,9);
});

import {insertText,splitLine,mergeLine} from './paragraphs.mjs';
test('splitLine breaks a line at the caret',()=>{
  assert.deepEqual(splitLine(['abcd','ef'],0,2),{lines:['ab','cd','ef'],caret:{line:1,offset:0}});
  assert.deepEqual(splitLine(['ab'],0,2).lines,['ab','']);
});
test('mergeLine joins into the previous line',()=>{
  assert.deepEqual(mergeLine(['ab','cd','ef'],1),{lines:['abcd','ef'],caret:{line:0,offset:2}});
  assert.deepEqual(mergeLine(['ab'],0).lines,['ab']);
});
test('insertText pastes plain text with newlines',()=>{
  assert.deepEqual(insertText(['abcd'],0,2,'X'),{lines:['abXcd'],caret:{line:0,offset:3}});
  assert.deepEqual(insertText(['abcd','z'],0,2,'1\n2\n3'),{lines:['ab1','2','3cd','z'],caret:{line:2,offset:1}});
});

import {deleteRange,layoutTops} from './paragraphs.mjs';
test('deleteRange joins endpoint lines',()=>{
  assert.deepEqual(deleteRange(['abc','def','ghi'],{line:0,offset:1},{line:2,offset:1}),{lines:['ahi'],caret:{line:0,offset:1}});
  assert.deepEqual(deleteRange(['abc'],{line:0,offset:1},{line:0,offset:2}).lines,['ac']);
});
test('layoutTops restacks lines after the edit point',()=>{
  const src=[0,10,20];
  assert.deepEqual(layoutTops(src,src,10,3,0),src);                    // same count: source layout
  assert.deepEqual(layoutTops(src,src,10,4,0),[0,10,20,30]);           // split mid (line 0)
  assert.deepEqual(layoutTops([0,10,20,30],src,10,3,1),src);           // merge back to source count
  assert.deepEqual(layoutTops([0,10,20,30],src,10,2,0),[0,10]);        // merge mid
  assert.deepEqual(layoutTops(src,src,10,6,0),[0,10,20,30,40,50]);     // paste of 3 extra lines mid
  assert.deepEqual(layoutTops([0,10,20,30],src,10,5,1),[0,10,20,30,40]);// split later keeps earlier tops
});
import {clampRect} from './paragraphs.mjs';
test('clampRect keeps a rebuild rect inside the visible page',()=>{
  const page={visibleWidth:400,visibleHeight:300};
  assert.deepEqual(clampRect({left:-5,top:10,width:500,height:0},page),{left:0,top:10,width:400,height:1});
  assert.deepEqual(clampRect({left:390,top:299.5,width:30,height:20},page),{left:390,top:299,width:10,height:1});
  assert.deepEqual(clampRect({left:30,top:50,width:90,height:26},page),{left:30,top:50,width:90,height:26});
});

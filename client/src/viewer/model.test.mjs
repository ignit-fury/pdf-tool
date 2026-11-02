import test from 'node:test';
import assert from 'node:assert/strict';
import {pageSize,inlineBox,sourceTypography,draftProblem,historyTransition,moveImageRect,viewportFontScale} from './model.mjs';

test('current page follows the largest visible portion after a draft toolbar closes',async()=>{
  const {visibleDocumentPage}=await import('./model.mjs');
  assert.equal(typeof visibleDocumentPage,'function');
  assert.equal(visibleDocumentPage([{number:1,top:-500,bottom:420},{number:2,top:448,bottom:1368}],0,600),1);
  assert.equal(visibleDocumentPage([{number:1,top:-800,bottom:120},{number:2,top:148,bottom:1068}],0,600),2);
});

test('page shells use physical rotated dimensions without allocating a canvas',()=>{
  assert.deepEqual(pageSize({visibleWidth:200,visibleHeight:300},1.5),{width:300,height:450});
  assert.deepEqual(pageSize(null,1),{width:612,height:792});
});
test('inline editor uses authoritative viewport transforms and remains inside the page',()=>{
  const viewport={width:300,height:400,convertToViewportPoint:(x,y)=>[x*2,400-y*2]};
  assert.deepEqual(inlineBox([10,150,80,160],viewport),{left:20,top:80,width:140,height:20});
  assert.equal(inlineBox([0,0,0,0],viewport),null);
  assert.equal(inlineBox([NaN,0,2,3],viewport),null);
});
test('source formatting is displayed without creating recipe overrides',()=>{
  const run={font_size:14,bold:true,italic:true,color:[1,0,0],source_font:'TimesNewRoman'};
  const explicit={};const css=sourceTypography(run,explicit,2);
  assert.equal(css.fontSize,28);assert.equal(css.fontWeight,700);assert.equal(css.fontStyle,'italic');
  assert.equal(css.color,'#ff0000');assert.deepEqual(explicit,{});
  assert.equal(sourceTypography({...run,font_size:12,font_display_size:24},{font_size:6},1).fontSize,12);
  assert.equal(sourceTypography({...run,font_size:12,font_display_size:24},{character_spacing:1},1).letterSpacing,2);
  assert.equal(viewportFontScale({scale:1.15,transform:[2.3,0,0,-2.3,0,0]}),2.3);
});
test('unsupported multiline and excessive drafts explain safe alternatives',()=>{
  assert.equal(draftProblem('Longer inserted text'),null);
  assert.match(draftProblem('a\nb'),/line breaks/i);
  assert.match(draftProblem('a'.repeat(10001)),/10,000/);
});
test('exact mixed history transitions preserve redo order and bound both stacks',()=>{
  const a={bytes:new Uint8Array([1])},b={bytes:new Uint8Array([2])},c={bytes:new Uint8Array([3])};
  const undo=historyTransition({past:[a,b],future:[],current:c},'undo');
  assert.strictEqual(undo.target,b);assert.deepEqual(undo.past,[a]);assert.deepEqual(undo.future,[c]);
  const again=historyTransition({...undo,current:b},'undo');
  const redo=historyTransition({...again,current:a},'redo');
  assert.strictEqual(redo.target,b);assert.deepEqual(redo.future,[c]);
  assert.equal(historyTransition({past:[],future:[],current:a},'undo'),null);
});
test('image pointer geometry clamps movement and keeps aspect ratio while resizing',()=>{
  const rect={left:10,top:20,width:40,height:20},page={visibleWidth:100,visibleHeight:100};
  assert.deepEqual(moveImageRect(rect,100,-100,page,'move',true),{left:60,top:0,width:40,height:20});
  const resized=moveImageRect(rect,20,10,page,'resize',true);
  assert.equal(resized.width/resized.height,2);assert.equal(resized.width,60);
});

test('edge and corner handles resize from the opposite anchor',async()=>{
  const {moveImageRect}=await import('./model.mjs'),page={visibleWidth:500,visibleHeight:400},rect={left:100,top:100,width:200,height:100};
  assert.deepEqual(moveImageRect(rect,20,0,page,'e',false),{...rect,width:220});
  assert.deepEqual(moveImageRect(rect,-20,-10,page,'nw',false),{left:80,top:90,width:220,height:110});
  const locked=moveImageRect(rect,-40,0,page,'w',true);
  assert.equal(locked.left,60);assert.equal(locked.width/locked.height,2);
  const clamped=moveImageRect(rect,999,999,page,'se',true);
  assert.ok(clamped.left+clamped.width<=500&&clamped.top+clamped.height<=400);
});

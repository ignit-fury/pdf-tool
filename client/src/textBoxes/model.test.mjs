import test from 'node:test';
import assert from 'node:assert/strict';
import {newTextBox,textBoxPayload,draftError,expandTextBox,wordRect,fitTextRect,growTextBox,explainInsertError,DEFAULT_STYLE} from './model.mjs';

test('source expansion keeps the draft/recipe, uses physical formatting and normalizes tabs',async()=>{
  const {sourceTextBox}=await import('./model.mjs');
  assert.equal(typeof sourceTextBox,'function','Source expansion bridge is missing');
  const draft=sourceTextBox({run:{run_id:'source',pageNumber:2,text:'Old',source_font:'Times New Roman',font_size:12},text:'First\r\nSecond\tline',style:{bold:true},recipe:[{run_id:'other',new_text:'kept'}],geometry:{visibleWidth:600,visibleHeight:800},box:{left:40,top:100,width:80,height:14},typography:{fontSize:24,letterSpacing:.2}});
  assert.equal(draft.text,'First\nSecond    line');assert.equal(draft.auto_expand,true);assert.equal(draft.style.font_family,'Serif');assert.equal(draft.style.font_size,24);
  assert.equal(draft.rect.width,560,'source expansion should use available width before wrapping');
  const payload=textBoxPayload(draft);assert.equal(payload.operation,'replace-source');assert.equal(payload.source_run_id,'source');assert.equal(payload.recipe[0].new_text,'kept');assert.equal(payload.auto_expand,true);
});
test('split-initial expansion retains both point sizes in the exact PDF payload',async()=>{
  const {sourceTextBox}=await import('./model.mjs');
  const draft=sourceTextBox({run:{run_id:'first',source_run_ids:['first','tail'],source_sizes:[75,60],pageNumber:1,source_font:'Times New Roman',font_size:60},text:'FEDERALS',style:{},recipe:[],geometry:{visibleWidth:612,visibleHeight:792},box:{left:54,top:164.8,width:295.6,height:75},typography:{fontSize:60,letterSpacing:0}});
  assert.equal(draft.style.initial_font_size,75);
  assert.equal(draft.style.font_size,60);
  assert.equal(draftError(draft,{visibleWidth:612,visibleHeight:792}),null);
  assert.equal(textBoxPayload(draft).style.initial_font_size,75);
  assert.match(draftError({...draft,style:{...draft.style,initial_font_size:513}},{visibleWidth:612,visibleHeight:792}),/font size/);
});
test('new text starts word-sized at the click and is clamped inside the visible page',()=>{
  const geometry={visibleWidth:600,visibleHeight:800};
  const draft=newTextBox(1,geometry,{left:100,top:200});
  assert.deepEqual(draft.rect,{left:100,top:200,width:24,height:12*1.2});assert.equal(draft.text,'');assert.deepEqual(draft.style,{...DEFAULT_STYLE,color:[0,0,0]});
  assert.deepEqual(newTextBox(1,geometry,{left:590,top:795}).rect,{left:576,top:800-12*1.2,width:24,height:12*1.2});
  assert.deepEqual(wordRect(geometry,{left:-5,top:-1}),{left:0,top:0,width:24,height:12*1.2});
  assert.match(draftError(draft,geometry),/Enter/);
});
test('typed text grows the box: width to the longest line, wrapping only at the page edge',()=>{
  const geometry={visibleWidth:600,visibleHeight:800},style={...DEFAULT_STYLE},rect={left:100,top:200,width:24,height:12*1.2};
  assert.deepEqual(fitTextRect(rect,[0],style,geometry),rect,'empty text keeps the word-sized box');
  const one=fitTextRect(rect,[100],style,geometry);assert.equal(one.width,105);assert.equal(one.height,12*1.2);
  const two=fitTextRect(rect,[100,200],style,geometry);assert.equal(two.width,208);assert.ok(Math.abs(two.height-28.8)<1e-9,'Enter adds a line');
  const wide=fitTextRect(rect,[900],style,geometry);assert.equal(wide.width,500,'never past the right edge');assert.ok(Math.abs(wide.height-28.8)<1e-9,'soft wrap grows height');
  assert.equal(fitTextRect({...rect,top:790},[100,100,100],style,geometry).height,10,'height stays on the page');
  assert.deepEqual(fitTextRect(rect,[10],style,geometry,{width:80,height:40}),{...rect,width:80,height:40},'an existing box never shrinks');
});
test('the save payload carries the measured text extent',()=>{
  const geometry={visibleWidth:600,visibleHeight:800};
  const draft=growTextBox({...newTextBox(0,geometry,{left:50,top:60}),text:'Hello\nworld'},geometry,[40,50]);
  const payload=textBoxPayload(draft);
  assert.equal(payload.operation,'upsert');assert.equal(payload.auto_expand,true);assert.equal(payload.allow_overlap,false);
  assert.ok(Math.abs(payload.rect.width-53.5)<1e-9);assert.ok(Math.abs(payload.rect.height-28.8)<1e-9);assert.deepEqual([payload.rect.left,payload.rect.top],[50,60]);
  assert.equal(draftError(draft,geometry),null);
  assert.match(explainInsertError({code:'TEXT_BOX_OVERLAP'}),/Click somewhere with free space, or move it/);
});
test('multiline draft accepts explicit breaks, growth and spacing within its own geometry',()=>{
  const draft=newTextBox(1,{visibleWidth:600,visibleHeight:800},{left:40,top:40});
  draft.text='A paragraph\nAnother line';draft.style.font_size=36;draft.style.line_spacing=1.5;draft.style.paragraph_spacing=12;draft.style.alignment='center';
  assert.equal(draftError(draft,{visibleWidth:600,visibleHeight:800}),null);
  assert.equal(textBoxPayload(draft).id,undefined);assert.equal(textBoxPayload(draft).page_index,1);
  assert.equal(textBoxPayload({...draft,id:'a'.repeat(32)}).id,'a'.repeat(32));
});
test('expansion never silently clips text at the page edge',()=>{
  const draft=newTextBox(0,{visibleWidth:600,visibleHeight:800},{left:40,top:40});
  assert.equal(expandTextBox(draft,200.111,{visibleHeight:800}).rect.height,200.12);
  assert.equal(expandTextBox(draft,900,{visibleHeight:800}),null);
});

test('paragraph overlap tells the user to shorten; text-box mode keeps its own advice',async()=>{
  const {explainParagraphError,explainTextBoxError}=await import('./model.mjs');
  assert.equal(explainParagraphError({code:'TEXT_BOX_OVERLAP'}),'The longer text would cover other content on this page (for example a shaded area or a frame). Shorten the text to fit.');
  assert.match(explainTextBoxError({code:'TEXT_BOX_OVERLAP'}),/allow transparent overlap/);
  assert.equal(explainParagraphError({code:'PUSH_DOWN_PAGE_FULL'}),explainTextBoxError({code:'PUSH_DOWN_PAGE_FULL'}));
});

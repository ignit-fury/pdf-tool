import test from 'node:test';
import assert from 'node:assert/strict';
import {newTextBox,textBoxPayload,draftError,expandTextBox} from './model.mjs';
test('page insertion clamps a physical box while retaining a genuine empty draft',()=>{
  const draft=newTextBox(1,{visibleWidth:600,visibleHeight:800},{left:590,top:790});
  assert.deepEqual(draft.rect,{left:360,top:680,width:240,height:120});assert.equal(draft.text,'');
  assert.match(draftError(draft,{visibleWidth:600,visibleHeight:800}),/Enter/);
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

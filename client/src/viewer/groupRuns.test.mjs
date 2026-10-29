import test from 'node:test';
import assert from 'node:assert/strict';
import {groupedEditTargets} from './groupRuns.mjs';

const run=(id,text,box)=>({run_id:id,text,box,state:'editable_original',source_font:'Times New Roman'});

test('a PDF-split initial becomes one selectable word without losing source addresses',()=>{
  const initial=run('first','F',[54,560.2,99.75,635.2]);
  const tail=run('tail','EDERAL',[99.75,563.2,349.6,623.2]);
  const output=groupedEditTargets([initial,tail]);
  assert.equal(output.length,1);
  assert.equal(output[0].text,'FEDERAL');
  assert.deepEqual(output[0].source_run_ids,['first','tail']);
  assert.deepEqual(output[0].box,[54,560.2,349.6,635.2]);
  assert.equal(groupedEditTargets([initial,tail],new Set(['first'])).length,2);
  assert.equal(groupedEditTargets([initial,{...tail,box:[110,563.2,360,623.2]}]).length,2);
  assert.equal(groupedEditTargets([initial,{...tail,text:' EDERAL'}]).length,2);
  assert.equal(groupedEditTargets([{...initial,state:'not_editable'},tail]).length,2);
});

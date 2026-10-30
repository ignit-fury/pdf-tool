import test from 'node:test';
import assert from 'node:assert/strict';
import {groupedEditTargets,splitSourceWord} from './groupRuns.mjs';

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

test('editing a joined word keeps separate source runs and their own formatting',()=>{
  const initial={...run('first','F',[54,560.2,99.75,635.2]),font_size:75};
  const tail={...run('tail','EDERAL',[99.75,563.2,349.6,623.2]),font_size:60};
  const [target]=groupedEditTargets([initial,tail]);
  assert.deepEqual(target.source_sizes,[75,60]);
  assert.deepEqual(splitSourceWord(target,'FEDS'),[{run_id:'first',new_text:'F'},{run_id:'tail',new_text:'EDS'}]);
  assert.deepEqual(splitSourceWord(target,'R'),[{run_id:'first',new_text:'R'},{run_id:'tail',new_text:''}]);
  assert.deepEqual(splitSourceWord(target,'😀word'),[{run_id:'first',new_text:'😀'},{run_id:'tail',new_text:'word'}]);
});

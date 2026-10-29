import test from 'node:test';
import assert from 'node:assert/strict';
import {matchesForScope,beginWalkthrough,stepWalkthrough} from './walkthrough.mjs';
import {buildReplacementRecipe} from './buildRecipe.mjs';

test('Replace One supplies only the active occurrence and preserves earlier style',()=>{
  const matches=[{id:'a',runId:'run',page:1,start:0,end:3,text:'cat',replaceable:true},{id:'b',runId:'run',page:1,start:4,end:7,text:'cat',replaceable:true}];
  const selected=matchesForScope(matches,'b','one');
  const result=buildReplacementRecipe({pages:{1:{runs:[{run_id:'run',text:'cat cat'}]}},recipe:[{run_id:'run',new_text:'cat cat',style:{bold:true}}],matches:selected,replacement:'dog'});
  assert.equal(result.recipe[0].new_text,'cat dog');assert.deepEqual(result.recipe[0].style,{bold:true});
  assert.deepEqual(matchesForScope(matches,'missing','one'),[]);
});
test('walkthrough includes only accepted changed occurrences and survives changed match IDs',()=>{
  const review={changes:[{runId:'run',page:2,matchIds:['accepted']}],refusals:{other:'overflow'}};
  const matches=[{id:'accepted',runId:'run',page:2,runOrder:0},{id:'refused',runId:'other',page:3,runOrder:0}];
  const tour=beginWalkthrough(review,matches,{2:{runs:[{run_id:'run',box:[1,2,3,4]}]}});
  assert.equal(tour.targets.length,1);assert.deepEqual(tour.targets[0].box,[1,2,3,4]);
  assert.equal(tour.status,'playing');assert.equal(stepWalkthrough(tour,'next').status,'complete');
});
test('tour pause/resume/stop has no PDF writer and reduced motion starts paused',()=>{
  const tour={status:'playing',position:0,targets:[{page:1},{page:2}]};
  assert.equal(stepWalkthrough(tour,'pause').status,'paused');
  assert.equal(stepWalkthrough(stepWalkthrough(tour,'pause'),'tick').position,0);
  assert.equal(stepWalkthrough(stepWalkthrough(tour,'pause'),'resume').status,'playing');
  assert.equal(stepWalkthrough(tour,'stop').status,'stopped');
  assert.equal(beginWalkthrough({changes:[]},[],{},true).status,'complete');
  const reduced=beginWalkthrough({changes:[{matchIds:['x']}]},[{id:'x',page:1,runId:'a',runOrder:0}],{1:{runs:[{run_id:'a',box:[0,0,1,1]}]}},true);
  assert.equal(reduced.status,'paused');
});

import test from 'node:test';
import assert from 'node:assert/strict';
async function api(){const module=await import('./highlight.mjs').catch(()=>null);assert.ok(module,'Bounded text highlight mapping is missing');return module;}
test('maps a selected repeated substring using full run and UTF16 offsets',async()=>{
  const {projectedCandidates}=await api();
  assert.deepEqual(projectedCandidates('prefix cat cat suffix','cat cat',4,7).candidates,[{start:11,end:14,runStart:7,runEnd:14}]);
  assert.equal(projectedCandidates('cat cat','cat cat',0,3).candidates[0].start,0);
  assert.equal(projectedCandidates('x 😀cat','😀cat',2,5).candidates[0].start,4);
});
test('canonical mapping covers composed text/ligatures but rejects partial visible glyphs',async()=>{
  const {projectedCandidates}=await api();
  assert.deepEqual(projectedCandidates('cafe\u0301','café',3,4).candidates,[{start:3,end:5,runStart:0,runEnd:5}]);
  assert.deepEqual(projectedCandidates('office','ofﬁce',2,3).candidates,[{start:2,end:4,runStart:0,runEnd:6}]);
  assert.deepEqual(projectedCandidates('ﬁ','f',0,1).candidates,[]);
  assert.deepEqual(projectedCandidates('😀','😀',1,2).candidates,[]);
});
test('missing, invalid and oversized text ranges return explicit fallback reasons',async()=>{
  const {projectedCandidates}=await api();
  assert.equal(projectedCandidates('x','y',0,1).reason,'unmapped');
  assert.equal(projectedCandidates('x'.repeat(100001),'x',0,1).reason,'limit');
  assert.equal(projectedCandidates('x','x'.repeat(20001),0,1).reason,'limit');
  assert.equal(projectedCandidates('x'.repeat(65),'x',0,1).reason,'limit');
  assert.equal(projectedCandidates('ﬁ'.repeat(65),'f',0,1).reason,'limit');
  assert.equal(projectedCandidates('\uFDFA'.repeat(6000),'x',0,1).reason,'limit');
  assert.equal(projectedCandidates('\u0315'.repeat(33)+'\u0300'.repeat(33),'x',0,1).reason,'limit');
  assert.equal(projectedCandidates('x','x',0,0).reason,'empty');
  assert.equal(projectedCandidates('x','x',-1,1).reason,'unmapped');
});
test('geometry selects only a unique source run and refuses overlapping candidates',async()=>{
  const {chooseCandidate}=await api();const candidate=(left,top)=>({runRects:[{left,top,width:60,height:12}],rects:[{left:left+20,top,width:18,height:12}]});
  assert.equal(chooseCandidate([candidate(10,10),candidate(10,40)],{left:10,top:40,width:60,height:12}).rects[0].top,40);
  assert.equal(chooseCandidate([candidate(10,10),candidate(10,10)],{left:10,top:10,width:60,height:12}).reason,'ambiguous');
  assert.equal(chooseCandidate([candidate(200,200)],{left:10,top:10,width:60,height:12}).reason,'unmapped');
  assert.equal(chooseCandidate([{runRects:[{left:NaN,top:1,width:1,height:1}],rects:[]}],{left:10,top:10,width:60,height:12}).reason,'unmapped');
  const disconnected={runRects:[{left:0,top:0,width:10,height:10},{left:100,top:100,width:10,height:10}],rects:[{left:0,top:0,width:10,height:10}]};
  assert.equal(chooseCandidate([disconnected],{left:50,top:50,width:10,height:10}).reason,'unmapped');
  assert.equal(chooseCandidate([disconnected],{left:0,top:0,width:10,height:10}).reason,'unmapped');
});

import test from 'node:test';
import assert from 'node:assert/strict';
import {fitImage,updateAspect,validatePlacement,placementMatrix} from './imageGeometry.mjs';

const geometry=rotation=>({mediaBox:{x:-30,y:10,width:300,height:220},cropBox:{x:20,y:30,width:200,height:160},userUnit:2,rotation,visibleWidth:rotation%180?320:400,visibleHeight:rotation%180?400:320});
const rect={left:20,top:40,width:100,height:60};
const point=(m,x,y)=>[m[0]*x+m[2]*y+m[4],m[1]*x+m[3]*y+m[5]];
for(const rotation of [0,90,180,270])test(`image corners map through ${rotation} degree crop/UserUnit viewport`,()=>{
  const m=placementMatrix(rect,geometry(rotation));
  // Independently project each PDF corner to visible physical points.
  const visible=([x,y])=>rotation===0?[(x-20)*2,(190-y)*2]:rotation===90?[(y-30)*2,(x-20)*2]:rotation===180?[(220-x)*2,(y-30)*2]:[(190-y)*2,(220-x)*2];
  assert.deepEqual(visible(point(m,0,0)),[20,100]);
  assert.deepEqual(visible(point(m,1,0)),[120,100]);
  assert.deepEqual(visible(point(m,0,1)),[20,40]);
  assert.deepEqual(visible(point(m,1,1)),[120,40]);
});
test('effective crop intersects media; disjoint crop falls back to media',()=>{
  const g={mediaBox:{x:-100,y:-50,width:200,height:100},cropBox:{x:-200,y:-200,width:200,height:200},rotation:0,userUnit:1};
  assert.deepEqual(placementMatrix({left:0,top:0,width:100,height:50},g),[100,0,0,50,-100,-50]);
  g.cropBox={x:500,y:500,width:1,height:1};
  assert.deepEqual(placementMatrix({left:0,top:0,width:200,height:100},g),[200,0,0,100,-100,-50]);
});
test('centered fit preserves image ratio in visible dimensions',()=>{
  assert.deepEqual(fitImage({width:800,height:200},geometry(90)),{left:0,top:160,width:320,height:80});
});
test('aspect lock is explicit, accepts original ratio, and never mutates draft',()=>{
  assert.deepEqual(updateAspect(rect,'width',200,{locked:true,ratio:2}),{...rect,width:200,height:100});
  assert.deepEqual(updateAspect(rect,'height',30,{locked:true,ratio:2}),{...rect,width:60,height:30});
  assert.deepEqual(updateAspect(rect,'width',200,{locked:false,ratio:2}),{...rect,width:200});
  assert.deepEqual(updateAspect(rect,'left',5,{locked:true,ratio:2}),{...rect,left:5});
  assert.deepEqual(rect,{left:20,top:40,width:100,height:60});
  assert.throws(()=>updateAspect(rect,'width',20,{locked:true,ratio:0}),{code:'IMAGE_ASPECT_INVALID'});
});
test('placement rejects invalid numbers, nonpositive dimensions, and overflowing bounds',()=>{
  assert.deepEqual(validatePlacement(rect,geometry(0)),{valid:true});
  for(const bad of [{width:0},{height:-1},{left:NaN},{top:Infinity}])assert.deepEqual(validatePlacement({...rect,...bad},geometry(0)),{valid:false,code:'IMAGE_RECT_INVALID'});
  for(const bad of [{left:-1},{left:350},{top:300},{width:Number.MAX_VALUE}])assert.deepEqual(validatePlacement({...rect,...bad},geometry(0)),{valid:false,code:'IMAGE_OUTSIDE_PAGE'});
  assert.throws(()=>placementMatrix({...rect,left:-1},geometry(0)),{code:'IMAGE_OUTSIDE_PAGE'});
  assert.throws(()=>placementMatrix(rect,{...geometry(0),rotation:45}),{code:'PAGE_GEOMETRY_INVALID'});
});

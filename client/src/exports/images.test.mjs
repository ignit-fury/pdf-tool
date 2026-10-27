import test from 'node:test';
import assert from 'node:assert/strict';
import {renderPageImages} from './images.mjs';

function fixture() {
  const calls=[],canvases=[];
  const pdf={numPages:2,getPage:async n=>({getViewport:({scale})=>({width:72*scale,height:144*scale}),render:options=>{calls.push([n,options]);return {promise:Promise.resolve(),cancel(){calls.push('cancel');}};}})};
  const canvasFactory=()=>{const c={width:0,height:0,getContext:()=>({}),toBlob:fn=>fn(new Blob([new Uint8Array([1,2,3])]))};canvases.push(c);return c;};
  return {pdf,calls,canvases,canvasFactory};
}
test('physical DPI, sequential pages, white JPEG and surface cleanup',async()=>{
  for(const dpi of [72,150,300,600]) {
    const f=fixture(),progress=[];
    const result=await renderPageImages({...f,pages:[1,2],format:'jpeg',dpi,onProgress:p=>progress.push(p.completed)});
    assert.equal(result.files.length,2);assert.equal(result.files[0].filename,'page-0001.jpg');
    assert.deepEqual(f.calls.map(([n,o])=>[n,o.viewport.width,o.background]),[[1,dpi,'#ffffff'],[2,dpi,'#ffffff']]);
    assert.deepEqual(progress,[1,2]);assert.ok(f.canvases.every(c=>c.width===0&&c.height===0));
  }
});
test('refuses invalid options, canvas pixels, retained output and transient budget',async()=>{
  for(const options of [{dpi:71},{dpi:601},{pages:[0]},{pages:[1,1]},{format:'gif'},{retainedBytes:300*1024*1024}])await assert.rejects(renderPageImages({...fixture(),pages:[1],format:'png',dpi:150,...options}));
  const f=fixture();f.pdf.getPage=async()=>({getViewport:()=>({width:4001,height:4000})});
  await assert.rejects(renderPageImages({...f,pages:[1],format:'png',dpi:150}),{code:'EXPORT_LIMIT'});assert.equal(f.canvases.length,0);
  await assert.rejects(renderPageImages({...fixture(),pages:[1],format:'png',dpi:150,encode:async()=>({size:49*1024*1024})}),{code:'EXPORT_LIMIT'});
});
test('abort cancels render and cleans the canvas; no partial result',async()=>{
  const f=fixture(),controller=new AbortController();let cancelled=false;
  f.pdf.getPage=async()=>({getViewport:()=>({width:20,height:20}),render:()=>({promise:new Promise(()=>{}),cancel(){cancelled=true;}})});
  const pending=renderPageImages({...f,pages:[1],format:'png',dpi:150,signal:controller.signal});
  await new Promise(resolve=>setTimeout(resolve,0));controller.abort();
  await assert.rejects(pending,{name:'AbortError'});assert.ok(cancelled);assert.equal(f.canvases[0].width,0);
});

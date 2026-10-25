/** G5 CLI: real production helper outputs; no alternate page writer. */
import fs from 'node:fs/promises';
import path from 'node:path';
import {transformPages,loadLocalPdf,describePage} from '../client/src/pageOps/pdfDocument.mjs';
import {mergePdf} from '../client/src/pageOps/mergePdf.mjs';
import {writeImage} from '../client/src/pageOps/images.mjs';

const input=path.resolve(process.argv[2]),dir=path.dirname(input);
const data=JSON.parse(await fs.readFile(input,'utf8'));
const read=async file=>new Uint8Array(await fs.readFile(path.join(dir,file)));
const outputs=[],refusals=[];
const mapped=(file,page=0,extra={})=>({file,page,...extra});
async function emit(file,result,mapping) {
  await fs.writeFile(path.join(dir,file),result.bytes);
  outputs.push({file,mapping,notices:result.notices??[],localMetadata:result.localMetadata});
  return result.bytes;
}
for(const [label,prefix] of [['real','font-real'],['controlled','font-literal']]) {
  const result=await mergePdf(await read(`${prefix}-0.pdf`),await read(`${prefix}-1.pdf`),{position:1});
  await emit(`font-${label}.pdf`,result,[mapped('font-real-0.pdf'),mapped('font-real-1.pdf')]);
}
const simple=await read('resources-0-0.pdf');
let result=await transformPages(simple,{type:'move',from:0,to:1});
await emit('moved.pdf',result,[mapped('resources-0-0.pdf',1),mapped('resources-0-0.pdf',0)]);
result=await transformPages(simple,{type:'delete',index:0});
await emit('deleted.pdf',result,[mapped('resources-0-0.pdf',1)]);
result=await transformPages(simple,{type:'rotate',index:0,quarterTurns:1});
await emit('rotated.pdf',result,[mapped('resources-0-90.pdf',0),mapped('resources-0-0.pdf',1)]);
const blank=await transformPages(simple,{type:'insertBlank',adjacentIndex:0,position:'after'});
// Independent Python fixture supplies the empty physical reference after materialization.
await emit('blank.pdf',blank,[mapped('resources-0-0.pdf',0),mapped('blank-reference.pdf'),mapped('resources-0-0.pdf',1)]);
const graph=await read('graph-source.pdf');
await emit('graph.pdf',await mergePdf(simple,graph,{position:1}),
  [mapped('resources-0-0.pdf',0),mapped('graph-source.pdf'),mapped('resources-0-0.pdf',1)]);
const graphMerged=await mergePdf(graph,graph,{position:1});
await emit('graph-collision.pdf',graphMerged,[mapped('graph-source.pdf'),mapped('graph-source.pdf')]);
await emit('graph-deleted.pdf',await transformPages(graphMerged.bytes,{type:'delete',index:0}),[mapped('graph-source.pdf')]);
try {await mergePdf(simple,await read('unsafe-source.pdf'),{position:1});throw new Error('unsafe source accepted');}
catch(error) {if(!error.code)throw error;refusals.push(error.code);}
const png=await read('white-flattened.png'),rect={left:24,top:26,width:48,height:32};
for(const inherited of [0,1])for(const rotation of [0,90,180,270]) {
  const source=`resources-${inherited}-${rotation}.pdf`,bytes=await read(source);
  await emit(`placed-${inherited}-${rotation}.pdf`,await writeImage(bytes,png,{destination:'current-page',pageIndex:0,rect}),
    [mapped(source,0,{rect,changed:true}),mapped(source,1)]);
}
await fs.writeFile(path.join(dir,'outputs.json'),JSON.stringify({...data,outputs,refusals},null,2));

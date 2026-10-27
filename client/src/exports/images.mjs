import {MAX_EXPORT_BYTES,admitExport,exportError} from './zip.mjs';
const aborted=()=>new DOMException('Export cancelled','AbortError');
const check=signal=>{if(signal?.aborted)throw aborted();};
const defaultEncode=(canvas,type)=>new Promise((resolve,reject)=>canvas.toBlob(blob=>blob?resolve(blob):reject(exportError('EXPORT_UNSUPPORTED')),type,0.92));
function abortable(promise,signal,cancel=()=>{}) {
  return new Promise((resolve,reject)=>{
    const abort=()=>{cancel();reject(aborted());};
    signal?.addEventListener('abort',abort,{once:true});
    if(signal?.aborted)abort();
    Promise.resolve(promise).then(resolve,reject).finally(()=>signal?.removeEventListener('abort',abort));
  });
}
/** Real PDF.js rendering, one physical DPI viewport at a time; no DPR/text extraction.
 * Pages are one-based (PDF.js convention). Canvas/encoder injection is for Node proof.
 * PNG and JPEG use an explicit white page background. No transparency promise. */
export async function renderPageImages({pdf,pages,format,dpi,signal,onProgress=()=>{},retainedBytes=0,canvasFactory=()=>document.createElement('canvas'),encode=defaultEncode}) {
  check(signal);
  if(!Number.isInteger(dpi)||dpi<72||dpi>600||!['png','jpeg'].includes(format)||!Array.isArray(pages)||!pages.length||pages.length>1000||new Set(pages).size!==pages.length||pages.some(n=>!Number.isInteger(n)||n<1||n>pdf?.numPages))throw exportError('EXPORT_OPTIONS_INVALID');
  const files=[];let total=0;
  for(const number of pages) {
    check(signal);const page=await abortable(pdf.getPage(number),signal);check(signal);
    const viewport=page.getViewport({scale:dpi/72}),width=Math.ceil(viewport.width),height=Math.ceil(viewport.height),pixels=width*height;
    if(!Number.isSafeInteger(pixels)||width<=0||height<=0||pixels>16000000)throw exportError('EXPORT_LIMIT');
    // Raster + encoder RGBA copy + max next encoded Blob/array + retained output/ZIP/Blob.
    admitExport(retainedBytes,pixels*8+MAX_EXPORT_BYTES*2+total*3);
    let canvas,task;
    try {
      canvas=canvasFactory();canvas.width=width;canvas.height=height;
      task=page.render({canvasContext:canvas.getContext('2d'),viewport,background:'#ffffff'});
      await abortable(task.promise,signal,()=>task.cancel());check(signal);
      const blob=await abortable(encode(canvas,`image/${format}`),signal);check(signal);
      if(!Number.isSafeInteger(blob?.size)||blob.size<1||total+blob.size>MAX_EXPORT_BYTES)throw exportError('EXPORT_LIMIT');
      admitExport(retainedBytes,pixels*8+total*3+blob.size*4);
      const bytes=new Uint8Array(await abortable(blob.arrayBuffer(),signal));check(signal);total+=bytes.byteLength;
      files.push({bytes,filename:`page-${String(number).padStart(4,'0')}.${format==='jpeg'?'jpg':'png'}`,mediaType:`image/${format}`,notices:[]});
      onProgress({completed:files.length,total:pages.length});
    }finally {if(canvas){canvas.width=0;canvas.height=0;}}
    await abortable(new Promise(resolve=>setTimeout(resolve,0)),signal);
  }
  return {files,notices:[]};
}

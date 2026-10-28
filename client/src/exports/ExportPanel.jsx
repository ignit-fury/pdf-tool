import React,{useEffect,useMemo,useRef,useState} from 'react';
import * as pdfjs from 'pdfjs-dist';
import {createExportController,NOTICE_TEXT,explainExportError} from './controller.mjs';
import {everyNPages,parsePageGroups} from './split.mjs';
import {admitExport,exportError} from './zip.mjs';

const labels={compress:'Compressed PDF',flatten:'Flattened PDF',png:'PNG',jpeg:'JPEG',split:'Split PDF',text:'Plain text',markdown:'Markdown',html:'HTML',pdfa:'PDF/A-2b'};
const size=n=>`${n.toLocaleString()} bytes (${(n/1024).toFixed(1)} KiB)`;

/** Only PDF.js pixels from the exact current and prepared PDF byte streams. */
function CompressionPreview({pdf,bytes,password,page,retainedBytes,onReady}) {
  const before=useRef(null),after=useRef(null),[error,setError]=useState('');
  useEffect(()=>{
    let stopped=false,render,task;onReady(false);setError('');
    const clear=()=>{for(const canvas of [before.current,after.current])if(canvas){canvas.width=0;canvas.height=0;}};
    (async()=>{
      admitExport(retainedBytes,bytes.buffer.byteLength*2+4*1024*1024);
      const assetRoot=`${import.meta.env.BASE_URL}assets/pdfjs/`;
      task=pdfjs.getDocument({data:bytes.slice(),password:password||undefined,isOffscreenCanvasSupported:false,cMapUrl:`${assetRoot}cmaps/`,cMapPacked:true,standardFontDataUrl:`${assetRoot}standard_fonts/`,wasmUrl:`${assetRoot}wasm/`});
      const prepared=await task.promise;if(stopped)return;
      if(prepared.numPages!==pdf.numPages)throw exportError('EXPORT_RESPONSE_INVALID');
      const originalPage=await pdf.getPage(page),base=originalPage.getViewport({scale:1}),scale=Math.min(1,240/base.width);
      for(const [document,canvas] of [[pdf,before.current],[prepared,after.current]]) {
        const selected=await document.getPage(page);if(stopped)return;
        const viewport=selected.getViewport({scale}),width=Math.ceil(viewport.width),height=Math.ceil(viewport.height);
        if(!Number.isSafeInteger(width*height)||width<=0||height<=0||width*height>16000000)throw exportError('EXPORT_LIMIT');
        admitExport(retainedBytes,bytes.buffer.byteLength*2+width*height*12);
        canvas.width=width;canvas.height=height;
        render=selected.render({canvasContext:canvas.getContext('2d'),viewport,background:'#ffffff'});await render.promise;
        if(stopped)return;
      }
      onReady(true);
    })().catch(error=>{if(!stopped){setError(explainExportError(error));clear();}});
    return()=>{stopped=true;render?.cancel();task?.destroy();clear();};
  },[pdf,bytes,password,page,retainedBytes,onReady]);
  return <><div className="export-previews"><figure><figcaption>Before · page {page}</figcaption><canvas ref={before} aria-label={`Before compression page ${page}`}/></figure><figure><figcaption>After · page {page}</figcaption><canvas ref={after} aria-label={`After compression page ${page}`}/></figure></div>{error&&<p role="alert">{error}</p>}</>;
}

export default function ExportPanel({pdf,page,session,version,getCurrent,request,runSplit,busy,beginWork,finishWork,localMetadata,acknowledged}) {
  const [format,setFormat]=useState('compress'),[downsample,setDownsample]=useState(false),[scope,setScope]=useState('current'),[dpiChoice,setDpiChoice]=useState('150'),[customDpi,setCustomDpi]=useState('150'),[splitMode,setSplitMode]=useState('every'),[every,setEvery]=useState('1'),[ranges,setRanges]=useState('1'),[state,setState]=useState({status:'idle'}),[previewPage,setPreviewPage]=useState(page),[previewReady,setPreviewReady]=useState(false);
  const latest=useRef(null),heading=useRef(null),owner=useRef(null),action=useRef(null);
  latest.current={getCurrent,request,runSplit,finishWork};
  const controller=useMemo(()=>createExportController({getCurrent:()=>latest.current.getCurrent(),request:(...args)=>latest.current.request(...args),runSplit:(...args)=>latest.current.runSplit(...args),onState:setState}),[]);
  const local=['png','jpeg','split'].includes(format),raster=['png','jpeg'].includes(format),rewrites=['compress','flatten','split','pdfa'].includes(format);
  const options={format,downsample:format==='compress'&&downsample,acknowledged:!!acknowledged};let validation='';
  try {
    if(raster){options.archive=scope==='all';options.dpi=Number(dpiChoice==='custom'?customDpi:dpiChoice);options.pages=scope==='current'?[page]:Array.from({length:pdf?.numPages||0},(_,i)=>i+1);if(!Number.isInteger(options.dpi)||options.dpi<72||options.dpi>600||!options.pages.length)throw new Error();}
    if(format==='split'){options.archive=true;options.groups=splitMode==='every'?everyNPages(pdf?.numPages||0,Number(every)):parsePageGroups(ranges,pdf?.numPages||0);}
  }catch{validation=raster?'Enter a whole-number DPI from 72 to 600.':'Use ascending, disjoint groups such as 1-3;4;5-8, or a positive number of pages per file (up to 1000 files).';}
  const optionsKey=JSON.stringify(options)+validation;
  useEffect(()=>{controller.invalidate();setPreviewReady(false);},[controller,session,session?.bytes,version,optionsKey]);
  useEffect(()=>()=>{controller.dispose();if(owner.current)latest.current.finishWork(owner.current);},[controller]);
  useEffect(()=>{if(state.status==='ready'||state.status==='error')heading.current?.focus();},[state.status]);
  const prepare=async()=>{
    const work=beginWork('export',local?'Preparing export in this browser…':'Preparing export on the server…');if(!work)return;
    owner.current=work;setPreviewPage(page);setPreviewReady(false);
    try{await controller.prepare(options,{pdf});}catch{}finally{finishWork(work);if(owner.current===work)owner.current=null;}
  };
  const result=state.result,working=state.status==='working',noticeCodes=[...new Set([...(result?.notices||[]),...(result?.files||[]).flatMap(file=>file.notices||[])].map(n=>typeof n==='string'?n:n.code))];
  const retainedBytes=getCurrent().retainedBytes+(result?.files.reduce((n,f)=>n+f.bytes.buffer.byteLength,0)||0)*2+(result?.archive?.bytes.byteLength||0)*2;
  const needsPreview=!!(result&&format==='compress'&&downsample),downloadReady=!needsPreview||previewReady;
  const savings=result?.beforeBytes?((result.beforeBytes-result.afterBytes)/result.beforeBytes*100).toFixed(1):'0';
  return <section className="export-panel" aria-label="Export document">
    <h2>Export <span className={`location ${local?'':'server'}`}>{local?'In this browser':'Server'}</span></h2>
    <p className="export-privacy">{local?'The current PDF is exported in this browser. No export upload is needed.':'This action uploads the current PDF to the server to prepare a download.'} Exports keep your current PDF and Undo history.</p>
    <fieldset disabled={!!busy}>
      <label>Format<select value={format} onChange={event=>setFormat(event.target.value)}>{Object.entries(labels).map(([value,label])=><option key={value} value={value}>{label}</option>)}</select></label>
      {format==='compress'&&<><p>Lossless structural compression is the default. Some PDFs will not get smaller.</p><label className="export-check"><input type="checkbox" checked={downsample} onChange={event=>setDownsample(event.target.checked)}/>Downsample images (changes image quality)</label><p>Unsupported images are retained. Review the actual prepared pages before downloading a downsampled copy.</p></>}
      {format==='flatten'&&<p>Annotation appearances become page content and supported fields stop being interactive. PDFs that cannot be flattened safely are refused.</p>}
      {format==='pdfa'&&<p>Prepare an archival PDF/A-2b copy. Content that cannot be converted safely will be refused.</p>}
      {raster&&<><label>Pages<select value={scope} onChange={event=>setScope(event.target.value)}><option value="current">Current page ({page})</option><option value="all">All pages as ZIP</option></select></label><label>Resolution<select value={dpiChoice} onChange={event=>setDpiChoice(event.target.value)}><option value="150">Screen — 150 DPI</option><option value="300">Print — 300 DPI</option><option value="custom">Custom DPI</option></select></label>{dpiChoice==='custom'&&<label>Custom DPI (72–600)<input type="number" min="72" max="600" step="1" value={customDpi} onChange={event=>setCustomDpi(event.target.value)}/></label>}<p>Physical page dimensions determine pixel size, independent of your screen. Pages have a white background. Limit: 16 million pixels per page and 48 MiB total output.</p></>}
      {format==='split'&&<><label>Split by<select value={splitMode} onChange={event=>setSplitMode(event.target.value)}><option value="every">Every N pages</option><option value="groups">Page groups</option></select></label>{splitMode==='every'?<label>Pages per file<input type="number" min="1" step="1" value={every} onChange={event=>setEvery(event.target.value)}/></label>:<label>Page groups<input type="text" value={ranges} onChange={event=>setRanges(event.target.value)} aria-describedby="export-range-help"/></label>}<p id="export-range-help">Use ascending, nonoverlapping groups, for example 1-3;4;5-8. Links to excluded pages follow the safe deletion policy. Up to 1000 files, 48 MiB total.</p></>}
      {['text','markdown','html'].includes(format)&&<p>Text exports use the shared reading-order index. Complex layouts may lose formatting; scanned pages have no text without OCR. HTML is downloaded as a document.</p>}
      {rewrites&&localMetadata?.signed&&!acknowledged&&<p>Acknowledge the signature warning above to rewrite this signed PDF.</p>}
      {rewrites&&localMetadata?.encrypted&&<p>A rewritten copy may be unlocked. The result reports whether protection was retained.</p>}
      {validation&&<p className="export-error" role="alert">{validation}</p>}
      <button ref={action} className="primary" onClick={prepare} disabled={!pdf||!localMetadata||!!validation||(rewrites&&localMetadata?.signed&&!acknowledged)}>{format==='compress'?'Prepare compressed PDF':`Prepare ${labels[format]}`} <span className="action-location">{local?'Browser':'Server'}</span></button>
    </fieldset>
    {working&&<div aria-live="polite"><p>{state.progress?`Page ${state.progress.completed} of ${state.progress.total}`:'Preparing export…'}</p>{state.progress&&<progress value={state.progress.completed} max={state.progress.total}/>}<button onClick={()=>{controller.cancel();if(owner.current){finishWork(owner.current);owner.current=null;}requestAnimationFrame(()=>action.current?.focus());}}>Cancel export</button></div>}
    {state.status==='error'&&<div className="export-error" role="alert"><h3 tabIndex="-1" ref={heading}>Export could not be prepared</h3><p>{explainExportError(state.error)}</p></div>}
    {result&&<div className="export-result" aria-live="polite"><h3 tabIndex="-1" ref={heading}>Export ready</h3>
      {format==='compress'&&<><p>Before: {size(result.beforeBytes)}<br/>After: {size(result.afterBytes)}</p><p>{result.afterBytes<result.beforeBytes?`${savings}% smaller.`:result.afterBytes===result.beforeBytes?'No size reduction.':`${Math.abs(Number(savings))}% larger. A smaller file is not guaranteed.`}</p></>}
      {!!noticeCodes.length&&<ul>{noticeCodes.map(code=><li key={code}>{NOTICE_TEXT[code]||'A safe page transformation was applied.'}</li>)}</ul>}
      {needsPreview&&<><label>Preview page<select value={previewPage} onChange={event=>{setPreviewReady(false);setPreviewPage(Number(event.target.value));}}>{Array.from({length:pdf.numPages},(_,i)=><option key={i} value={i+1}>Page {i+1}</option>)}</select></label><CompressionPreview pdf={pdf} bytes={result.files[0].bytes} password={session.password} page={previewPage} retainedBytes={retainedBytes} onReady={setPreviewReady}/>{!previewReady&&<p>Preparing exact Before / After page previews…</p>}</>}
      {downloadReady&&<div className="export-downloads">{result.files.map(file=><a key={file.filename} href={file.url} download={file.filename}>{format==='compress'?'Download compressed PDF':format==='pdfa'?'Download PDF/A-2b':`Download ${file.filename}`}</a>)}{result.archive&&<a href={result.archive.url} download={result.archive.filename}>Download all as ZIP</a>}</div>}
    </div>}
  </section>;
}

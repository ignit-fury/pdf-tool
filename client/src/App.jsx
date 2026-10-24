import React,{useState,useRef,useEffect,useCallback,useMemo} from 'react';
import * as pdfjs from 'pdfjs-dist';
import workerUrl from 'pdfjs-dist/build/pdf.worker.min.mjs?url';
import 'pdfjs-dist/web/pdf_viewer.css';
import './style.css';
import {PageCanvas,Thumbnail} from './Viewer.jsx';
import {upsertOperation,commitRecipe,previousRecipe,withSourceRetry,decodePdf,explainReason,createRequestQueue,retryWorkerBusy,disposeDocument,explainBucket,operationLocation,passwordHeaders,chooseFontFamily,needsFontChoice,refusalCode,explainFit} from './session.mjs';
import FindPanel from './find/FindPanel.jsx';
import {findMatches} from './find/search.mjs';
import {buildReplacementRecipe} from './find/buildRecipe.mjs';
import {createIndexingController} from './find/indexing.mjs';
import {previewReplacement} from './find/preview.mjs';
import {applyReviewedReplacement} from './find/replaceAll.mjs';

pdfjs.GlobalWorkerOptions.workerSrc=workerUrl;
const API=import.meta.env.VITE_API_URL||'';
const EMPTY={recipe:[],history:[]};
const EMPTY_PROGRESS={completed:0,completedPages:[],total:0,failedPages:[],status:'idle'};
const ignored=error=>['AbortError','RenderingCancelledException'].includes(error.name);
const current=target=>target&&!target.controller.signal.aborted;
async function request(path,options={}) {
  const response=await fetch(`${API}${path}`,{cache:'no-store',...options}),data=await response.json();
  if(!response.ok){const detail=data.detail||{},error=new Error(typeof detail==='string'?detail:detail.code||`Request failed (${response.status})`);Object.assign(error,{status:response.status,code:detail.code,detail});throw error;}
  return data;
}

export default function App(){
  const sessionRef=useRef(null),inputRef=useRef(null),pdfRef=useRef(null),loadingRef=useRef(null),editVersion=useRef(0);
  const busyOwnerRef=useRef(null),indexingRef=useRef(null),queryRef=useRef(null),rowRefs=useRef(new Map()),inspectorButtonRef=useRef(null);
  const [session,setSession]=useState(null),[pdf,setPdf]=useState(null),[meta,setMeta]=useState(null);
  const [page,setPage]=useState(1),[scale,setScale]=useState(1.15),[mode,setMode]=useState('select');
  const [index,setIndex]=useState({}),[selection,setSelection]=useState(null),[draft,setDraft]=useState(''),[style,setStyle]=useState({});
  const [recipeState,setRecipeState]=useState(EMPTY),[preview,setPreview]=useState(null),[output,setOutput]=useState(null);
  const [busy,setBusy]=useState(''),[message,setMessage]=useState(''),[passwordPrompt,setPasswordPrompt]=useState(null),[passwordInput,setPasswordInput]=useState('');
  const [acknowledged,setAcknowledged]=useState(false),[dragging,setDragging]=useState(false);
  const [panel,setPanel]=useState('inspector'),[query,setQuery]=useState(''),[replacement,setReplacement]=useState(''),[fontFamily,setFontFamily]=useState('');
  const [matchCase,setMatchCase]=useState(false),[wholeWords,setWholeWords]=useState(false),[excludedIds,setExcludedIds]=useState(new Set());
  const [indexProgress,setIndexProgress]=useState(EMPTY_PROGRESS),[batchReview,setBatchReview]=useState(null),[batchError,setBatchError]=useState('');
  const [activeMatch,setActiveMatch]=useState(null),[resultPage,setResultPage]=useState(1),[navigationStatus,setNavigationStatus]=useState('');
  const [sourceMismatch,setSourceMismatch]=useState(false),[indexRevision,setIndexRevision]=useState(0);
  const [historyKinds,setHistoryKinds]=useState([]);
  const beginWork=(kind,label)=>{if(busyOwnerRef.current)return null;const owner={kind};busyOwnerRef.current=owner;setBusy(label);return owner;};
  const finishWork=owner=>{if(busyOwnerRef.current===owner){busyOwnerRef.current=null;setBusy('');}};
  const invalidateBatch=()=>{editVersion.current++;setBatchReview(null);setBatchError('');};
  const clear=useCallback(()=>{
    editVersion.current++;
    indexingRef.current?.dispose();indexingRef.current=null;busyOwnerRef.current=null;
    const old=sessionRef.current;if(old){old.controller.abort();old.passwordResolve?.(null);old.original=null;old.password='';}
    sessionRef.current=null;loadingRef.current?.destroy();loadingRef.current=null;disposeDocument(pdfRef.current);pdfRef.current=null;
    setSession(null);setPdf(null);setMeta(null);setIndex({});setSelection(null);setRecipeState(EMPTY);setPreview(null);setOutput(null);setMessage('');setBusy('');setPage(1);setAcknowledged(false);setPasswordPrompt(null);setPasswordInput('');
    setPanel('inspector');setQuery('');setReplacement('');setFontFamily('');setMatchCase(false);setWholeWords(false);setExcludedIds(new Set());setIndexProgress(EMPTY_PROGRESS);setBatchReview(null);setBatchError('');setActiveMatch(null);setResultPage(1);setNavigationStatus('');rowRefs.current.clear();
    setSourceMismatch(false);setIndexRevision(0);
    setHistoryKinds([]);
  },[]);
  useEffect(()=>{
    if(!passwordPrompt)return;
    const handler=event=>{
      if(event.key==='Escape'){event.preventDefault();clear();}
      if(event.key==='Tab'){
        const elements=[...document.querySelectorAll('.password-dialog input,.password-dialog button')],first=elements[0],last=elements.at(-1);
        if(event.shiftKey&&document.activeElement===first){event.preventDefault();last.focus();}
        else if(!event.shiftKey&&document.activeElement===last){event.preventDefault();first.focus();}
      }
    };
    window.addEventListener('keydown',handler);return()=>window.removeEventListener('keydown',handler);
  },[passwordPrompt,clear]);
  useEffect(()=>()=>{indexingRef.current?.dispose();sessionRef.current?.controller.abort();loadingRef.current?.destroy();disposeDocument(pdfRef.current);},[]);
  const askPassword=useCallback((target,incorrect=false)=>{
    if(!current(target))return Promise.resolve(null);
    if(!target.passwordPromise){target.passwordPromise=new Promise(resolve=>{target.passwordResolve=resolve;});setPasswordInput('');setPasswordPrompt({target,incorrect});}
    return target.passwordPromise;
  },[]);
  const upload=useCallback((target,bytes=target.original,password=target.password)=>request('/upload',{method:'POST',body:bytes,signal:target.controller.signal,headers:{'Content-Type':'application/pdf',...passwordHeaders(password)}}),[]);
  const documentRequest=useCallback((target,suffix,options={},priority=0)=>target.queue.run(()=>retryWorkerBusy(()=>withSourceRetry(target,jobId=>request(`/jobs/${encodeURIComponent(jobId)}${suffix}`,{...options,signal:target.controller.signal,headers:{...passwordHeaders(target.password),...options.headers}}),(bytes,password)=>upload(target,bytes,password)),{signal:target.controller.signal}),priority),[upload]);
  const prepareViewer=useCallback(async(target,bytes,isCurrent=()=>current(target))=>{
    if(!isCurrent())throw new DOMException('Document changed','AbortError');
    const assetRoot=`${import.meta.env.BASE_URL}assets/pdfjs/`;
    const task=pdfjs.getDocument({data:bytes.slice(),password:target.password||undefined,isOffscreenCanvasSupported:false,cMapUrl:`${assetRoot}cmaps/`,cMapPacked:true,standardFontDataUrl:`${assetRoot}standard_fonts/`,wasmUrl:`${assetRoot}wasm/`});
    loadingRef.current?.destroy();loadingRef.current=task;
    task.onPassword=async(update,reason)=>{const password=await askPassword(target,reason===pdfjs.PasswordResponses.INCORRECT_PASSWORD);if(password!==null&&current(target))update(password);else task.destroy();};
    try{
      const document=await task.promise;
      if(!isCurrent()){disposeDocument(document);throw new DOMException('Document changed','AbortError');}
      return {document,bytes,dispose:()=>disposeDocument(document)};
    }catch(error){try{await task.destroy();}catch{}throw error;}
    finally{if(loadingRef.current===task)loadingRef.current=null;}
  },[askPassword]);
  const publishViewer=useCallback((prepared,isCurrent)=>{
    if(!isCurrent())throw new DOMException('Document changed','AbortError');
    const old=pdfRef.current;pdfRef.current=prepared.document;setPdf(prepared.document);if(old&&old!==prepared.document)disposeDocument(old);
  },[]);
  const loadViewer=useCallback(async(target,bytes)=>{
    const valid=()=>current(target)&&sessionRef.current===target,prepared=await prepareViewer(target,bytes,valid);
    if(!valid()){prepared.dispose();return;}
    publishViewer(prepared,valid);
  },[prepareViewer,publishViewer]);
  const openFile=useCallback(async file=>{
    if(!file)return;clear();const owner=beginWork('open','Opening document…');
    const target={name:file.name,password:'',original:null,controller:new AbortController(),jobId:null,pages:new Map()};target.queue=createRequestQueue({limit:2,signal:target.controller.signal});sessionRef.current=target;
    try{
      if(file.size>50*1024*1024)throw new Error('This PDF is larger than the 50 MB limit. Choose a smaller file.');
      const bytes=new Uint8Array(await file.arrayBuffer());if(!current(target))return;
      if(new TextDecoder('ascii').decode(bytes.slice(0,5))!=='%PDF-')throw new Error('This file is not a PDF. Choose a file with a PDF header.');
      target.original=bytes;setSession(target);
      const viewer=loadViewer(target,bytes).catch(error=>{if(current(target)&&!ignored(error))setMessage('The document viewer could not open this PDF.');});
      let result;for(;;){try{result=await upload(target);break;}catch(error){if(!['PASSWORD_REQUIRED','PASSWORD_INCORRECT'].includes(error.code))throw error;if(error.code==='PASSWORD_REQUIRED'&&target.password)continue;const password=await askPassword(target,error.code==='PASSWORD_INCORRECT');if(password===null||!current(target))return;}}
      if(!current(target))return;target.jobId=result.job_id;setMeta(result);await viewer;
    }catch(error){if(current(target)&&!ignored(error))setMessage(error.message);}
    finally{if(current(target))finishWork(owner);}
  },[clear,loadViewer,upload,askPassword]);
  const fetchRuns=useCallback((number,priority=10)=>{
    const target=sessionRef.current;if(!target?.jobId)return Promise.resolve(null);
    if(target.pages.has(number)){target.pages.get(number).promote?.(priority);return target.pages.get(number);}
    const pending=documentRequest(target,`/pages/${number-1}/runs`,{},priority);
    target.pages.set(number,pending);
    pending.then(data=>{if(current(target))setIndex(previous=>({...previous,[number]:data}));}).catch(error=>{target.pages.delete(number);if(current(target)&&!ignored(error))setMessage(`Page ${number}: ${error.status===429?'The server is busy. Select the page again to retry.':error.message}`);});
    return pending;
  },[documentRequest]);
  useEffect(()=>{if(meta)fetchRuns(page,0);},[meta,page,fetchRuns]);
  useEffect(()=>{if(busyOwnerRef.current?.kind==='single-preview')editVersion.current++;setSelection(null);setPreview(null);},[page]);
  useEffect(()=>{setPreview(null);},[draft,style]);
  useEffect(()=>{
    if(!session||!meta)return;
    const target=session,controller=createIndexingController({fetchPage:number=>fetchRuns(number,20),onProgress:setIndexProgress,isCurrent:()=>current(target)&&sessionRef.current===target});
    indexingRef.current=controller;
    return()=>{controller.dispose();if(indexingRef.current===controller)indexingRef.current=null;};
  },[session,meta,fetchRuns,indexRevision]);
  useEffect(()=>{if(panel==='find'&&meta&&indexProgress.status==='idle')indexingRef.current?.start(meta.page_count);},[panel,meta,indexProgress.status]);
  const findPages=useMemo(()=>Object.fromEntries(indexProgress.completedPages.filter(number=>index[number]).map(number=>[number,index[number]])),[index,indexProgress.completedPages]);
  const matches=useMemo(()=>findMatches(findPages,query,{matchCase,wholeWords,recipe:recipeState.recipe}),[findPages,query,matchCase,wholeWords,recipeState.recipe]);
  const runsById=useMemo(()=>new Map(Object.values(findPages).flatMap(data=>data.runs).map(run=>[run.run_id,run])),[findPages]);
  const batchKey=useMemo(()=>JSON.stringify([session?.name,session?.jobId,recipeState.recipe,query,matchCase,wholeWords,replacement,fontFamily,[...excludedIds].sort(),matches.map(match=>match.id),indexProgress.status]),[session,recipeState.recipe,query,matchCase,wholeWords,replacement,fontFamily,excludedIds,matches,indexProgress.status]);
  const batchKeyRef=useRef(batchKey);batchKeyRef.current=batchKey;
  useEffect(()=>{setBatchReview(null);setBatchError('');},[batchKey]);
  const changeFind=(setter,value,reset=false)=>{invalidateBatch();setter(value);if(reset){setExcludedIds(new Set());setResultPage(1);setActiveMatch(null);}};
  const showFind=()=>{setPanel('find');setPreview(null);requestAnimationFrame(()=>queryRef.current?.focus());};
  const showInspector=()=>{setPanel('inspector');requestAnimationFrame(()=>inspectorButtonRef.current?.focus());};
  const choose=run=>{if(['apply','batch-apply','undo'].includes(busyOwnerRef.current?.kind))return;invalidateBatch();const existing=recipeState.recipe.find(op=>op.run_id===run.run_id);setSelection(run);setDraft(existing?.new_text??run.text);setStyle(existing?.style||{});setPreview(null);};
  const navigateMatch=match=>{setActiveMatch(match);setPage(match.page);fetchRuns(match.page,0);setNavigationStatus(`Match ${matches.findIndex(item=>item.id===match.id)+1} of ${matches.length}, page ${match.page}`);};
  const refreshIndex=()=>{invalidateBatch();setSourceMismatch(false);setActiveMatch(null);setExcludedIds(new Set());setResultPage(1);setIndexProgress(EMPTY_PROGRESS);setIndexRevision(previous=>previous+1);};
  const checkReplacements=async()=>{
    if(indexProgress.status!=='complete'||!query)return;
    const owner=beginWork('batch-preview','Checking replacement fit on the server…');if(!owner)return;
    const target=sessionRef.current,version=++editVersion.current,key=batchKey;setPreview(null);setBatchError('');setBatchReview(null);
    const valid=()=>current(target)&&sessionRef.current===target&&editVersion.current===version&&batchKeyRef.current===key;
    try{const review=await previewReplacement({key,isCurrent:valid,buildCandidate:refusedRunIds=>buildReplacementRecipe({pages:findPages,recipe:recipeState.recipe,matches,excludedIds,replacement,fontFamily,refusedRunIds}),requestPreview:recipe=>documentRequest(target,'/edit?dry_run=true',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(recipe)})});if(valid())setBatchReview(review);}
    catch(error){if(valid()&&!ignored(error)){
      if(error.code==='SOURCE_MISMATCH'){indexingRef.current?.dispose();target.pages.clear();setIndex({});setIndexProgress({...EMPTY_PROGRESS,total:meta.page_count,status:'stale'});setSourceMismatch(true);setActiveMatch(null);}
      else setBatchError(error.message||'Could not preview replacements. Your PDF is unchanged. Try again.');
    }}
    finally{finishWork(owner);}
  };
  const cancelBatchPreview=()=>{editVersion.current++;setBatchReview(null);setBatchError('');const owner=busyOwnerRef.current;if(owner?.kind==='batch-preview')finishWork(owner);};
  const candidate=()=>upsertOperation(recipeState.recipe,{run_id:selection.run_id,new_text:draft,...(Object.keys(style).length?{style}:{})});
  const checkFit=async()=>{
    if(!selection)return;const owner=beginWork('single-preview','Checking text fit…');if(!owner)return;
    const target=sessionRef.current,version=++editVersion.current,recipe=candidate();setBatchReview(null);setMessage('');
    try{const result=await documentRequest(target,'/edit?dry_run=true',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(recipe)});if(current(target)&&version===editVersion.current)setPreview({result,recipe,key:JSON.stringify(recipe)});}
    catch(error){if(current(target)&&!ignored(error))setMessage(error.message);}finally{finishWork(owner);}
  };
  const apply=async()=>{
    const target=sessionRef.current,accepted=preview;
    if(!selection||!accepted?.result.ok||accepted.key!==JSON.stringify(candidate())||(meta.signed&&!acknowledged))return;
    const owner=beginWork('apply','Applying edit…');if(!owner)return;
    const version=++editVersion.current,prior=recipeState;
    const valid=()=>current(target)&&sessionRef.current===target&&busyOwnerRef.current===owner&&editVersion.current===version;
    setBatchReview(null);setMessage('');
    let prepared;
    try{
      const result=await documentRequest(target,`/edit?dry_run=false&acknowledge_signature=${acknowledged}`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(accepted.recipe)});
      if(!valid())return;
      if(!result.ok||!result.pdf){setPreview({...accepted,result:{...result,ok:false}});return;}
      const bytes=decodePdf(result.pdf);prepared=await prepareViewer(target,bytes,valid);
      if(!valid()){prepared.dispose();return;}
      publishViewer(prepared,valid);setRecipeState(commitRecipe(prior,accepted.recipe));setHistoryKinds(previous=>[...previous,'single']);setOutput(bytes);
      editVersion.current++;setPreview(null);setBatchReview(null);setActiveMatch(null);setMessage('Edit applied. Download the PDF or undo this change.');
    }catch(error){if(prepared)prepared.dispose();if(valid()&&!ignored(error))setMessage('The edit could not be applied. Your current document is unchanged. Preview again, then retry.');}
    finally{finishWork(owner);}
  };
  const applyBatch=async()=>{
    const accepted=batchReview,target=sessionRef.current;
    if(indexProgress.status!=='complete'||accepted?.key!==batchKey||!accepted?.result.ok||(meta.signed&&!acknowledged))return;
    const owner=beginWork('batch-apply',`Replacing ${accepted.selectedCount} matches on the server…`);if(!owner)return;
    const version=++editVersion.current,prior=recipeState;
    const valid=()=>current(target)&&sessionRef.current===target&&busyOwnerRef.current===owner&&editVersion.current===version;
    setMessage('');setBatchError('');setPreview(null);
    try{
      const result=await applyReviewedReplacement({review:accepted,currentKey:()=>batchKeyRef.current,isCurrent:valid,signed:meta.signed,acknowledged,
        requestApply:recipe=>documentRequest(target,`/edit?dry_run=false&acknowledge_signature=${acknowledged}`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(recipe)}),
        loadOutput:encoded=>prepareViewer(target,decodePdf(encoded),()=>valid()&&batchKeyRef.current===accepted.key),
        commit:(prepared,recipe)=>{
          publishViewer(prepared,()=>valid()&&batchKeyRef.current===accepted.key);
          setRecipeState(commitRecipe(prior,recipe));setHistoryKinds(previous=>[...previous,'batch']);setOutput(prepared.bytes);
          editVersion.current++;setPreview(null);setBatchReview(null);setBatchError('');setActiveMatch(null);setNavigationStatus('');
          setMessage(`Replaced ${accepted.selectedCount} ${accepted.selectedCount===1?'match':'matches'} on ${accepted.changedPages.length} ${accepted.changedPages.length===1?'page':'pages'}. Undo restores the whole batch.`);
        }});
      if(['failed','refused'].includes(result.status)&&valid()){
        setBatchReview(null);
        const reasons=result.result?.resolved?.filter(row=>!row.ok).map(row=>row.reason)||[];
        if(reasons.some(reason=>['source_hash_mismatch','run_id_not_found','source_mismatch'].includes(reason))||result.error?.code==='SOURCE_MISMATCH'){
          indexingRef.current?.dispose();target.pages.clear();setIndex({});setIndexProgress({...EMPTY_PROGRESS,total:meta.page_count,status:'stale'});setSourceMismatch(true);setActiveMatch(null);
        }else setBatchError('Could not apply replacements. Your PDF is unchanged. Preview again, then retry.');
      }
    }finally{finishWork(owner);}
  };
  const undo=useCallback(async()=>{
    if(busyOwnerRef.current||!recipeState.history.length)return;
    const target=sessionRef.current,restored=previousRecipe(recipeState),batch=historyKinds.at(-1)==='batch',owner=beginWork('undo','Undoing edit…');if(!owner)return;
    const version=++editVersion.current;
    const valid=()=>current(target)&&sessionRef.current===target&&busyOwnerRef.current===owner&&editVersion.current===version;
    setBatchReview(null);setPreview(null);setMessage('');let prepared;
    try{
      let bytes=target.original;
      if(operationLocation(restored.recipe)==='server'){
        const result=await documentRequest(target,`/edit?dry_run=false&acknowledge_signature=${acknowledged}`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(restored.recipe)});
        if(!valid())return;
        if(!result.ok||!result.pdf)throw new Error('Previous edit refused');
        bytes=decodePdf(result.pdf);
      }
      if(!valid())return;
      prepared=await prepareViewer(target,bytes,valid);
      if(!valid()){prepared.dispose();return;}
      publishViewer(prepared,valid);setRecipeState(restored);setHistoryKinds(previous=>previous.slice(0,-1));setOutput(restored.recipe.length?bytes:null);
      editVersion.current++;setSelection(null);setPreview(null);setBatchReview(null);setActiveMatch(null);setNavigationStatus('');
      setMessage(batch?'Replacement batch undone.':'Previous edit restored.');
    }catch(error){if(prepared)prepared.dispose();if(valid()&&!ignored(error))setMessage('The previous edit could not be restored. Your current document is unchanged. Try Undo again.');}
    finally{finishWork(owner);}
  },[recipeState,historyKinds,documentRequest,prepareViewer,publishViewer,acknowledged]);
  useEffect(()=>{const handler=event=>{if((event.ctrlKey||event.metaKey)&&event.key.toLowerCase()==='z'&&!event.shiftKey&&!event.target.closest('input,textarea,[contenteditable=true]')){event.preventDefault();undo();}};window.addEventListener('keydown',handler);return()=>window.removeEventListener('keydown',handler);},[undo]);
  const download=()=>{const url=URL.createObjectURL(new Blob([output||session.original],{type:'application/pdf'})),anchor=document.createElement('a');anchor.href=url;anchor.download=output?`edited-${session.name.replace(/\.pdf$/i,'')}.pdf`:session.name;anchor.click();setTimeout(()=>URL.revokeObjectURL(url),1000);};
  const pageData=index[page],runs=pageData?.runs||[],noEditable=pageData&&!runs.some(run=>run.state!=='not_editable');
  const batchPreviewing=busyOwnerRef.current?.kind==='batch-preview',findLocked=!!busy&&!batchPreviewing;
  const currentReview=batchReview?.key===batchKey?batchReview:null;
  const findTarget=useMemo(()=>panel==='find'&&activeMatch&&matches.some(match=>match.id===activeMatch.id)?{...activeMatch,box:runsById.get(activeMatch.runId)?.box}:null,[panel,activeMatch,matches,runsById]);
  return <div className="app" onDragOver={event=>{event.preventDefault();setDragging(true);}} onDragLeave={event=>{if(!event.currentTarget.contains(event.relatedTarget))setDragging(false);}} onDrop={event=>{event.preventDefault();setDragging(false);openFile(event.dataTransfer.files[0]);}}>
    <header className="app-header"><div className="brand"><span className="brand-mark" aria-hidden="true">P<span>↳</span></span><strong>PDF Tool</strong><span className="brand-caption">Document workstation</span></div><button onClick={()=>inputRef.current.click()}>Open PDF</button></header>
    <input ref={inputRef} type="file" accept="application/pdf,.pdf" className="visually-hidden" aria-label="Open PDF file" onChange={event=>{const file=event.target.files[0];event.target.value='';openFile(file);}}/>
    {dragging&&<div className="drop-overlay">Drop your PDF to open it</div>}
    {!session?<main className="welcome"><div className="welcome-copy"><p className="edition">A focused place for precise changes</p><h1>Your document.<br/>A few words better.</h1><p>Open a PDF, select a text run, and make the change. Keep the page around it intact.</p><button className="primary large" onClick={()=>inputRef.current.click()}>Choose a PDF</button><span className="drop-hint">or drop a file anywhere on this page</span></div><div className="welcome-sheet" aria-hidden="true"><div className="sheet-rule"/><span className="sheet-title">A working document</span><div className="ink-line long"/><div className="ink-line"/><div className="ink-line medium"/><div className="sample-edit">Make room for a better word.</div><div className="ink-line long"/><div className="ink-line"/><div className="ink-line medium"/><span className="sheet-page">1</span></div><div className="privacy-intro"><strong>Know where your document goes.</strong><p>Viewing, selecting text, and downloading happen in your browser. Opening uploads the PDF for analysis; text and style edits run on the server. Your browser keeps the original for recovery.</p></div></main>:<>
      <section className="document-bar"><div className="document-title"><strong title={session.name}>{session.name}</strong><span>{meta?`${meta.page_count} ${meta.page_count===1?'page':'pages'}`:'Opening PDF'}{session.original&&` · ${(session.original.length/1024).toFixed(0)} KB`}{recipeState.recipe.length?` · ${recipeState.recipe.length} edited text ${recipeState.recipe.length===1?'run':'runs'}`:''}</span></div><div className="document-actions"><button onClick={undo} disabled={!!busy||!recipeState.history.length} title={`Undo last edit (Ctrl/Cmd+Z): ${operationLocation(previousRecipe(recipeState).recipe)==='server'?'server replay':'browser'}`}>{historyKinds.at(-1)==='batch'?'Undo replacements':'Undo'} <span className="action-location">{operationLocation(previousRecipe(recipeState).recipe)==='server'?'Server':'Browser'}</span></button><button className="primary" disabled={!!busy||!pdf} onClick={download}>{output?'Download edited PDF':'Download original'} <span className="action-location">Browser</span></button><button onClick={clear}>Close</button></div></section>
      {meta?.signed&&<div className="signature-notice"><strong>Digitally signed document.</strong> Any edit invalidates its signature. Downloading the untouched original preserves its bytes.<label><input type="checkbox" checked={acknowledged} onChange={event=>setAcknowledged(event.target.checked)} disabled={!!output}/> I understand that editing invalidates the signature.</label></div>}
      {meta?.encrypted&&<div className="notice">Password-protected PDF. The original download retains its encryption. An edited copy may use different encryption settings.</div>}
      <main className="workspace"><aside className="page-rail" aria-label="Document pages"><h2>Pages <span className="location">Browser</span></h2>{pdf&&Array.from({length:pdf.numPages},(_,i)=><Thumbnail key={`${pdf.fingerprints[0]}-${i}`} pdf={pdf} number={i+1} current={page===i+1} badge={index[i+1]?.bucket} onSelect={number=>{setPage(number);fetchRuns(number,0);}} onVisible={fetchRuns}/>)}</aside>
      <section className="viewer"><div className="viewer-toolbar"><div className="mode-switch" role="group" aria-label="Text mode"><button className={mode==='select'?'active':''} onClick={()=>setMode('select')}>Select text</button><button className={mode==='edit'?'active':''} onClick={()=>setMode('edit')}>Edit text</button></div><div className="page-controls"><button aria-label="Previous page" disabled={page<=1} onClick={()=>setPage(page-1)}>‹</button><span>{page} / {pdf?.numPages||'…'}</span><button aria-label="Next page" disabled={!pdf||page>=pdf.numPages} onClick={()=>setPage(page+1)}>›</button><label className="zoom"><span className="visually-hidden">Zoom</span><select value={scale} onChange={event=>setScale(Number(event.target.value))}><option value="0.65">65%</option><option value="0.85">85%</option><option value="1">100%</option><option value="1.15">115%</option><option value="1.5">150%</option><option value="2">200%</option></select></label></div></div><div className="canvas-stage">{pdf?<PageCanvas pdf={pdf} pageNumber={page} scale={scale} mode={mode} runs={runs} selected={selection?.run_id} onSelect={choose} findTarget={findTarget}/>:<p className="loading-page">Opening the first page…</p>}</div><div className="viewer-caption">{panel==='find'&&activeMatch&&<button className="back-results" onClick={()=>{setResultPage(Math.floor(matches.findIndex(match=>match.id===activeMatch.id)/50)+1);requestAnimationFrame(()=>rowRefs.current.get(activeMatch.id)?.focus());}}>Back to results</button>}<span>{mode==='select'?'Select and copy text, or use your browser’s find on this page.':'Choose an outlined text run to inspect and edit it.'}</span><span className="location">Viewing in browser</span></div>{panel==='find'&&navigationStatus&&<p className="find-navigation-status" aria-live="polite">{navigationStatus}</p>}</section>
      <aside className="inspector"><div className="panel-switch" role="group" aria-label="Inspector panel"><button ref={inspectorButtonRef} aria-pressed={panel==='inspector'} onClick={showInspector}>Text inspector</button><button aria-pressed={panel==='find'} onClick={showFind}>Find and replace</button></div>{panel==='find'?<FindPanel query={query} replacement={replacement} fontFamily={fontFamily} matchCase={matchCase} wholeWords={wholeWords}
        onQuery={value=>changeFind(setQuery,value,true)} onReplacement={value=>changeFind(setReplacement,value)} onFont={value=>changeFind(setFontFamily,value)}
        onMatchCase={value=>changeFind(setMatchCase,value,true)} onWholeWords={value=>changeFind(setWholeWords,value,true)}
        progress={indexProgress} matches={matches} excludedIds={excludedIds} onToggle={id=>{invalidateBatch();setExcludedIds(previous=>{const next=new Set(previous);if(next.has(id))next.delete(id);else next.add(id);return next;});}}
        onStop={()=>indexingRef.current?.stop()} onResume={()=>indexingRef.current?.resume()} review={currentReview} previewing={batchPreviewing} locked={findLocked}
        onPreview={checkReplacements} onCancelPreview={cancelBatchPreview} error={batchError} activeId={activeMatch?.id} onNavigate={navigateMatch}
        resultPage={resultPage} onResultPage={setResultPage} queryRef={queryRef} rowRefs={rowRefs} recipe={recipeState.recipe} runsById={runsById} sourceMismatch={sourceMismatch} onRefresh={refreshIndex} onApply={applyBatch} applyAllowed={!!currentReview?.result.ok&&indexProgress.status==='complete'&&(!meta?.signed||acknowledged)}/>:<><h2>Text inspector <span className="location server">Server edits</span></h2>{!meta?<p>Preparing document analysis…</p>:!pageData?<p>Classifying this page…</p>:<><div className="page-verdict"><strong title={pageData.bucket}>{explainBucket(pageData.bucket)}</strong><span>{runs.length} text {runs.length===1?'run':'runs'}</span></div>{noEditable&&<div className="refusal"><h3>{runs.length?'This page cannot be safely edited':'No editable text was found'}</h3><p>{runs.length?[...new Set(runs.map(run=>explainReason(run.reason)))].join(' '):'This may be a scanned page. Run OCR first, then open the searchable PDF here.'}</p><a href="https://ocrmypdf.readthedocs.io/" target="_blank" rel="noopener noreferrer" >Read the OCRmyPDF guide</a><small>External guide. Your PDF is not sent to this site.</small><button className="ocr-interest" onClick={()=>{const target=sessionRef.current;request('/ocr-notify',{method:'POST'}).then(()=>{if(current(target))setMessage('Interest recorded. This counts demand for built-in OCR; no contact details or PDF were sent.');}).catch(()=>{if(current(target))setMessage('Could not record interest. Try again later.');});}}>Register interest in built-in OCR <span>Server</span></button></div>}
      {selection?<div className="edit-form"><div className="selected-heading"><h3>Selected text</h3><span className={`state-badge ${selection.state==='not_editable'?'blocked':''}`}>{selection.state==='editable_original'?'Original font':selection.state==='editable_substitution'?'Font substitution':'Cannot edit'}</span></div><p className="original-text">{selection.text}</p>{selection.state==='not_editable'?<p className="refusal-reason">{explainReason(selection.reason)}{refusalCode(selection.reason)&&<code>{refusalCode(selection.reason)}</code>}</p>:<><label>Replacement text<textarea value={draft} onChange={event=>{editVersion.current++;setPreview(null);setDraft(event.target.value);}} disabled={!!busy} rows={4}/></label><fieldset disabled={!!busy}><legend>Text style</legend><p className="source-font">Detected font: <strong>{selection.source_font||'Unknown'}</strong></p><label className="font-choice">Replacement font<select value={style.font_family||''} onChange={event=>setStyle(chooseFontFamily(style,event.target.value))}><option value="">Automatic — preserve or match original</option><option value="Serif">Serif — Liberation Serif</option><option value="Sans">Sans-serif — Liberation Sans</option><option value="Mono">Monospace — Liberation Mono</option></select></label>{needsFontChoice(selection,style)&&<p className="font-guidance">No automatic font match. Choose a replacement above to edit this text.</p>}<div className="style-controls"><label><input type="checkbox" checked={style.bold||false} onChange={event=>setStyle({...style,bold:event.target.checked})}/> Bold</label><label><input type="checkbox" checked={style.italic||false} onChange={event=>setStyle({...style,italic:event.target.checked})}/> Italic</label><label className="color-control">Color<input aria-label="Text color" type="color" value={style.color?`#${style.color.map(value=>Math.round(value*255).toString(16).padStart(2,'0')).join('')}`:'#000000'} onChange={event=>setStyle({...style,color:event.target.value.slice(1).match(/../g).map(value=>parseInt(value,16)/255)})}/></label></div><p className="size-refusal">Font-size changes are not supported. Edits must fit the original width.</p></fieldset>{(selection.state==='editable_substitution'||'font_family' in style||'bold' in style||'italic' in style)&&<p className="substitution-note">A bundled substitute font will be used. Preview checks its fit before applying.</p>}<button onClick={checkFit} disabled={!!busy||!meta}>Preview fit <span>Server</span></button>{preview&&<div className={`fit-result ${preview.result.ok?'fits':'does-not-fit'}`} role="status"><strong>{preview.result.ok?'Ready to apply':'Edit refused'}</strong>{preview.result.resolved?.map(item=><p key={item.run_id}>{item.ok?explainFit(item.strategy):explainReason(item.reason)}{!item.ok&&refusalCode(item.reason)&&<code>{refusalCode(item.reason)}</code>}</p>)}</div>}<button className="primary" onClick={apply} disabled={!!busy||!preview?.result.ok||(meta.signed&&!acknowledged)}>Apply edit <span>Server</span></button><p className="edit-disclosure">Preview and apply send the recipe to the server. Edits replay against the original PDF. Undo restores the previous recipe.</p></>}<button className="text-button" onClick={()=>setSelection(null)}>Back to page text</button></div>:!noEditable&&<><p className="inspector-hint">Switch to Edit text and choose a run on the page, or select one below.</p><div className="run-list">{runs.map(run=><button key={run.run_id} onClick={()=>{setMode('edit');choose(run);}}><span>{run.text||'(Empty text)'}</span><small>{run.state==='not_editable'?explainReason(run.reason):run.state==='editable_substitution'?'Substitute font':'Editable'}</small></button>)}</div></>}</>}</>}</aside></main>
    </>}
    {(busy||message)&&<div className="status-bar" role="status" aria-live="polite"><span>{busy||message}</span>{message&&!busy&&<button onClick={()=>setMessage('')} aria-label="Dismiss message">×</button>}</div>}
    <footer className="app-footer"><span>Original stays in this browser’s memory while open.</span><span>Opening, analysis and editing use the server. No account required.</span></footer>
    {passwordPrompt&&<div className="modal-backdrop"><form className="password-dialog" role="dialog" aria-modal="true" aria-labelledby="password-title" onSubmit={event=>{event.preventDefault();const target=passwordPrompt.target;target.password=passwordInput;const resolve=target.passwordResolve;target.passwordPromise=null;target.passwordResolve=null;setPasswordPrompt(null);setPasswordInput('');resolve?.(target.password);}}><h2 id="password-title">Unlock this PDF</h2><p>{passwordPrompt.incorrect?'That password was incorrect. Try again.':'Enter the document password to view and edit it.'}</p><label>PDF password<input autoFocus type="password" value={passwordInput} onChange={event=>setPasswordInput(event.target.value)} autoComplete="off"/></label><p className="small-copy">Kept in memory for this document and sent to the server to unlock it. Cleared when you close the document.</p><div className="dialog-actions"><button type="button" onClick={clear}>Cancel</button><button className="primary" type="submit">Unlock PDF</button></div></form></div>}
  </div>;
}

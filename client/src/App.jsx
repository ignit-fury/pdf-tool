import React,{useState,useRef,useEffect,useCallback,useMemo} from 'react';
import * as pdfjs from 'pdfjs-dist';
import workerUrl from 'pdfjs-dist/build/pdf.worker.min.mjs?url';
import 'pdfjs-dist/web/pdf_viewer.css';
import './style.css';
import {PageCanvas,Thumbnail} from './Viewer.jsx';
import {upsertOperation,withSourceRetry,decodePdf,explainReason,retryWorkerBusy,disposeDocument,explainBucket,passwordHeaders,chooseFontFamily,needsFontChoice,refusalCode,explainFit} from './session.mjs';
import FindPanel from './find/FindPanel.jsx';
import {findMatches,sourceRunForMatch} from './find/search.mjs';
import {buildReplacementRecipe} from './find/buildRecipe.mjs';
import {createIndexingController,normalizeIndexProgress} from './find/indexing.mjs';
import {previewReplacement} from './find/preview.mjs';
import {applyReviewedReplacement} from './find/replaceAll.mjs';
import {createLocalSession,restoreSession,snapshotCopyBytes,canAnalyzeText,prepareImageDraft,imageDraftMatchesPage} from './session.mjs';
import {runPdfJob} from './pageOps/pdfWorker.mjs';
import PageOpsPanel from './pageOps/PageOpsPanel.jsx';
import {captureSnapshot,admitHistory,pushSnapshot,popSnapshot,peekSnapshot,MAX_RETAINED_BYTES,MAX_TRANSIENT_BYTES,MAX_HISTORY_ENTRIES} from './pageOps/documentHistory.mjs';
import {applyPageOperation} from './pageOps/applyPageOperation.mjs';
import {decodeLocalImage,IMAGE_ERROR_CODES,MAX_IMAGE_BYTES,MAX_IMAGE_PNG_BYTES} from './pageOps/images.mjs';
import {fitImage,updateAspect,validatePlacement} from './pageOps/imageGeometry.mjs';

pdfjs.GlobalWorkerOptions.workerSrc=workerUrl;
const API=import.meta.env.VITE_API_URL||'';
const EMPTY={recipe:[],history:[]};
const EMPTY_PROGRESS={completed:0,completedPages:[],total:0,failedPages:[],status:'idle'};
const MERGE_ERRORS=['SOURCE_SIGNATURE_ACK_REQUIRED','MERGE_SOURCE_CHANGED','MERGE_EMPTY_SOURCE','MERGE_GRAPH_UNSAFE','MERGE_NORMALIZE_UNSUPPORTED','MERGE_ACTION_UNSUPPORTED','MERGE_AP_UNSAFE','MERGE_DA_UNSAFE','MERGE_DESTINATION_UNSAFE','MERGE_FIELD_GRAPH_UNSAFE','MERGE_FIELD_TYPE_UNSUPPORTED','MERGE_GRAPH_LIMIT','MERGE_OUTLINE_UNSAFE','MERGE_RESOURCES_UNSAFE','MERGE_XFA_UNSUPPORTED'];
const localFailure=error=>{
  const code=error?.code;
  if(code==='HEIC_UNAVAILABLE')return 'HEIC conversion is unavailable here. Choose PNG, JPEG or WebP, or retry when conversion is available.';
  if(['RETENTION_LIMIT','TRANSIENT_LIMIT','HISTORY_LIMIT'].includes(code))return 'This change would exceed the browser memory or Undo limit. Download your current PDF and open it as a new document to continue. Your document and Undo history are unchanged.';
  if(code==='LOCAL_PDF_TOO_LARGE')return 'This PDF exceeds the 50 MB local page limit. Download your current PDF or choose a smaller file. Your document is unchanged.';
  if(code==='PDF_JOB_TIMEOUT')return 'The page change took too long. Your document is unchanged. Try again or choose a smaller file.';
  if(code==='SIGNATURE_UNKNOWN')return 'Document protection could not be checked. Page changes are unavailable; you can download the untouched original.';
  if(code?.startsWith('IMAGE_'))return 'This image could not be opened. Choose a supported PNG, JPEG, WebP or HEIC image.';
  if(code?.includes('FORM')||code?.includes('FIELD')||code==='MERGE_XFA_UNSUPPORTED'||code==='MERGE_GRAPH_UNSAFE')return "This PDF's form fields cannot be merged safely. Choose another PDF; your current document is unchanged.";
  return 'The page change could not be completed. Your document is unchanged. Try again or choose a smaller file.';
};
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
  const [panel,setPanel]=useState('pages'),[query,setQuery]=useState(''),[replacement,setReplacement]=useState(''),[fontFamily,setFontFamily]=useState('');
  const [localMetadata,setLocalMetadata]=useState(null);
  const imageDestinationRef=useRef(null);imageDestinationRef.current={page,geometry:localMetadata?.pages[page-1]};
  const historyRef=useRef([]),draftRef=useRef(null),restoringPageRef=useRef(false);
  const [documentHistory,setDocumentHistory]=useState([]),[importReview,setImportReview]=useState(null),[imageDraft,setImageDraft]=useState(null),[pageError,setPageError]=useState('');
  const [matchCase,setMatchCase]=useState(false),[wholeWords,setWholeWords]=useState(false),[excludedIds,setExcludedIds]=useState(new Set());
  const [indexProgress,setIndexProgress]=useState(EMPTY_PROGRESS),[batchReview,setBatchReview]=useState(null),[batchError,setBatchError]=useState('');
  const [activeMatch,setActiveMatch]=useState(null),[resultPage,setResultPage]=useState(1),[navigationStatus,setNavigationStatus]=useState('');
  const [sourceMismatch,setSourceMismatch]=useState(false),[indexRevision,setIndexRevision]=useState(0);
  const beginWork=(kind,label)=>{if(busyOwnerRef.current)return null;const owner={kind};busyOwnerRef.current=owner;setBusy(label);return owner;};
  const finishWork=owner=>{if(busyOwnerRef.current===owner){busyOwnerRef.current=null;setBusy('');}};
  const invalidateBatch=()=>{editVersion.current++;setBatchReview(null);setBatchError('');};
  const releaseDraft=()=>{const value=draftRef.current;if(value){value.controller.abort();value.decoded?.dispose();value.preview?.dispose();draftRef.current=null;}setImportReview(null);setImageDraft(null);};
  const clear=useCallback(()=>{
    editVersion.current++;
    const oldDraft=draftRef.current;oldDraft?.controller.abort();oldDraft?.decoded?.dispose();oldDraft?.preview?.dispose();draftRef.current=null;historyRef.current=[];setDocumentHistory([]);setImportReview(null);setImageDraft(null);setPageError('');
    indexingRef.current?.dispose();indexingRef.current=null;busyOwnerRef.current=null;
    const old=sessionRef.current;if(old){old.controller.abort();old.passwordResolve?.(null);old.openedBytes=null;old.sourceBytes=null;old.bytes=null;old.password='';}
    sessionRef.current=null;loadingRef.current?.destroy();loadingRef.current=null;disposeDocument(pdfRef.current);pdfRef.current=null;
    setSession(null);setPdf(null);setMeta(null);setIndex({});setSelection(null);setRecipeState(EMPTY);setPreview(null);setOutput(null);setMessage('');setBusy('');setPage(1);setAcknowledged(false);setPasswordPrompt(null);setPasswordInput('');
    setPanel('pages');setLocalMetadata(null);setQuery('');setReplacement('');setFontFamily('');setMatchCase(false);setWholeWords(false);setExcludedIds(new Set());setIndexProgress(EMPTY_PROGRESS);setBatchReview(null);setBatchError('');setActiveMatch(null);setResultPage(1);setNavigationStatus('');rowRefs.current.clear();
    setSourceMismatch(false);setIndexRevision(0);
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
  useEffect(()=>()=>{indexingRef.current?.dispose();sessionRef.current?.controller.abort();draftRef.current?.controller.abort();draftRef.current?.decoded?.dispose();draftRef.current?.preview?.dispose();loadingRef.current?.destroy();disposeDocument(pdfRef.current);},[]);
  const askPassword=useCallback((target,incorrect=false)=>{
    if(!current(target))return Promise.resolve(null);
    if(!target.passwordPromise){target.passwordPromise=new Promise(resolve=>{target.passwordResolve=resolve;});setPasswordInput('');setPasswordPrompt({target,incorrect});}
    return target.passwordPromise;
  },[]);
  const upload=useCallback((target,bytes=target.sourceBytes,password=target.password)=>request('/upload',{method:'POST',body:bytes,signal:target.controller.signal,headers:{'Content-Type':'application/pdf',...passwordHeaders(password)}}),[]);
  const documentRequest=useCallback((target,suffix,options={},priority=0)=>{
    if(!canAnalyzeText(target))return Promise.reject(new DOMException('Choose Analyze text first','AbortError'));
    target.deferAnalysis=false;
    return target.queue.run(()=>retryWorkerBusy(()=>withSourceRetry(target,jobId=>request(`/jobs/${encodeURIComponent(jobId)}${suffix}`,{...options,signal:target.controller.signal,headers:{...passwordHeaders(target.password),...options.headers}}),(bytes,password)=>upload(target,bytes,password)),{signal:target.controller.signal}),priority);
  },[upload]);
  const pdfJob=(target,command,payload,errorCodes=[])=>runPdfJob({workerFactory:()=>new Worker(new URL('./pageOps/pdfJob.worker.mjs',import.meta.url),{type:'module'}),command,payload,signal:target.controller.signal,errorCodes});
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
    const target=createLocalSession({name:file.name});sessionRef.current=target;
    try{
      if(file.size>50*1024*1024)throw new Error('This PDF is larger than the 50 MB limit. Choose a smaller file.');
      const bytes=new Uint8Array(await file.arrayBuffer());if(!current(target))return;
      if(new TextDecoder('ascii').decode(bytes.slice(0,5))!=='%PDF-')throw new Error('This file is not a PDF. Choose a file with a PDF header.');
      target.openedBytes=bytes;target.sourceBytes=bytes;target.bytes=bytes;setSession(target);
      await loadViewer(target,bytes);
      if(!current(target))return;
      const result=await pdfJob(target,'inspect',{bytes,options:{password:target.password}});
      if(current(target)&&sessionRef.current===target)setLocalMetadata(result);
    }catch(error){if(current(target)&&!ignored(error)){if(error.code)setPageError(localFailure(error));else setMessage(error.message);}}
    finally{if(current(target))finishWork(owner);}
  },[clear,loadViewer]);
  const analyze=async()=>{
    const target=sessionRef.current;if(!target||busyOwnerRef.current)return;
    const owner=beginWork('analysis','Analyzing text on the server…');
    try {
      const result=await upload(target);
      if(!current(target)||sessionRef.current!==target)return;
      target.analysisEnabled=true;target.sourceIdentity=crypto.randomUUID();target.jobId=result.job_id;setMeta(result);
    }catch(error){if(current(target)&&!ignored(error))setMessage(error.message);}
    finally{finishWork(owner);}
  };
  const fetchRuns=useCallback((number,priority=10)=>{
    const target=sessionRef.current;if(!canAnalyzeText(target)||target.deferAnalysis)return Promise.resolve(null);
    if(target.pages.has(number)){target.pages.get(number).promote?.(priority);return target.pages.get(number);}
    const pending=documentRequest(target,`/pages/${number-1}/runs`,{},priority);
    target.pages.set(number,pending);
    pending.then(data=>{if(current(target))setIndex(previous=>({...previous,[number]:data}));}).catch(error=>{target.pages.delete(number);if(current(target)&&!ignored(error))setMessage(`Page ${number}: ${error.status===429?'The server is busy. Select the page again to retry.':error.message}`);});
    return pending;
  },[documentRequest]);
  const makeIndexer=useCallback((target,progress)=>createIndexingController({initialProgress:progress,fetchPage:number=>fetchRuns(number,20),onProgress:setIndexProgress,isCurrent:()=>current(target)&&sessionRef.current===target}),[fetchRuns]);
  useEffect(()=>{if(meta)fetchRuns(page,0);},[meta,page,fetchRuns]);
  useEffect(()=>{if(restoringPageRef.current){restoringPageRef.current=false;return;}if(busyOwnerRef.current?.kind==='single-preview')editVersion.current++;setSelection(null);setPreview(null);},[page]);
  useEffect(()=>{setPreview(null);},[draft,style]);
  useEffect(()=>{
    if(!session||!meta||!canAnalyzeText(sessionRef.current)||sessionRef.current.deferAnalysis)return;
    const target=sessionRef.current,controller=makeIndexer(target,indexProgress);
    indexingRef.current=controller;
    return()=>{controller.dispose();if(indexingRef.current===controller)indexingRef.current=null;};
  },[session,meta,makeIndexer,indexRevision]);
  useEffect(()=>{if(panel==='find'&&meta&&indexProgress.status==='idle')indexingRef.current?.start(meta.page_count);},[panel,meta,indexProgress.status]);
  const findPages=useMemo(()=>Object.fromEntries(indexProgress.completedPages.filter(number=>index[number]).map(number=>[number,index[number]])),[index,indexProgress.completedPages]);
  const matches=useMemo(()=>findMatches(findPages,query,{matchCase,wholeWords,recipe:recipeState.recipe}),[findPages,query,matchCase,wholeWords,recipeState.recipe]);
  const batchKey=useMemo(()=>JSON.stringify([session?.name,session?.jobId,recipeState.recipe,query,matchCase,wholeWords,replacement,fontFamily,[...excludedIds].sort(),matches.map(match=>match.id),indexProgress.status]),[session,recipeState.recipe,query,matchCase,wholeWords,replacement,fontFamily,excludedIds,matches,indexProgress.status]);
  const batchKeyRef=useRef(batchKey);batchKeyRef.current=batchKey;
  useEffect(()=>{setBatchReview(null);setBatchError('');},[batchKey]);
  const changeFind=(setter,value,reset=false)=>{invalidateBatch();setter(value);if(reset){setExcludedIds(new Set());setResultPage(1);setActiveMatch(null);}};
  const resumeAnalysis=()=>{const target=sessionRef.current;if(target?.deferAnalysis){target.deferAnalysis=false;setIndexRevision(value=>value+1);fetchRuns(page,0);}};
  const resumeIndexing=()=>{
    const target=sessionRef.current;if(!canAnalyzeText(target)||busyOwnerRef.current)return;
    target.deferAnalysis=false;
    if(!indexingRef.current)indexingRef.current=makeIndexer(target,{...indexProgress,total:indexProgress.total||meta.page_count});
    indexingRef.current.resume();
  };
  const showFind=()=>{resumeAnalysis();setPanel('find');setPreview(null);requestAnimationFrame(()=>queryRef.current?.focus());};
  const showInspector=()=>{resumeAnalysis();setPanel('inspector');requestAnimationFrame(()=>inspectorButtonRef.current?.focus());};
  const choose=run=>{if(['apply','batch-apply','undo'].includes(busyOwnerRef.current?.kind))return;invalidateBatch();const existing=recipeState.recipe.find(op=>op.run_id===run.run_id);setSelection(run);setDraft(existing?.new_text??run.text);setStyle(existing?.style||{});setPreview(null);};
  const navigateMatch=match=>{setActiveMatch(match);setPage(match.page);fetchRuns(match.page,0);setNavigationStatus(`Match ${matches.findIndex(item=>item.id===match.id)+1} of ${matches.length}, page ${match.page}`);};
  const refreshIndex=()=>{invalidateBatch();setSourceMismatch(false);setActiveMatch(null);setExcludedIds(new Set());setResultPage(1);setIndexProgress(EMPTY_PROGRESS);setIndexRevision(previous=>previous+1);};
  const snapshotState=(action='change')=>{
    const target=sessionRef.current;
    return {bytes:target.bytes,sourceBytes:target.sourceBytes,password:target.password,recipe:recipeState.recipe,selectedPage:page-1,style,selection,
      localMetadata,analysis:{enabled:target.analysisEnabled,sourceIdentity:target.sourceIdentity,meta,index},acknowledged,action,
      findState:{query,replacement,fontFamily,matchCase,wholeWords,excludedIds:[...excludedIds],indexProgress,activeMatch,resultPage,panel,draft,mode}};
  };
  const budget=({current:snapshot,candidateBytes,temporaryBytes=0,retainSnapshot=true,local=false}={})=>{
    const target=sessionRef.current,history=historyRef.current,live={bytes:target?.bytes,sourceBytes:target?.sourceBytes};
    if(local){const admission=admitHistory({openedBytes:target.openedBytes,current:snapshot,history,candidateBytes,temporaryBytes,retainSnapshot});if(!admission.ok)return admission;}
    if(retainSnapshot&&history.length>=MAX_HISTORY_ENTRIES)return {ok:false,code:'HISTORY_LIMIT'};
    const retained=snapshotCopyBytes({openedBytes:target?.openedBytes,live,history,snapshot,candidateBytes,draft:draftRef.current?.bytes,png:draftRef.current?.decoded?.pngBytes});
    if(retained>MAX_RETAINED_BYTES)return {ok:false,code:'RETENTION_LIMIT'};
    const pixels=draftRef.current?.decoded?draftRef.current.decoded.width*draftRef.current.decoded.height*4*3:0;
    const temporary=(typeof temporaryBytes==='number'?temporaryBytes:snapshotCopyBytes(temporaryBytes))+pixels;
    return retained+temporary>MAX_TRANSIENT_BYTES?{ok:false,code:'TRANSIENT_LIMIT'}:{ok:true};
  };
  const requireBudget=options=>{const result=budget(options);if(!result.ok)throw Object.assign(new Error(result.code),{code:result.code});};
  const takeSnapshot=(action,local=false)=>{
    const state=snapshotState(action);requireBudget({current:state,temporaryBytes:snapshotCopyBytes(state),local});
    return captureSnapshot(state);
  };
  const retain=snapshot=>{historyRef.current=pushSnapshot(historyRef.current,snapshot);setDocumentHistory(historyRef.current);};
  const restoreUi=snapshot=>{
    if(page!==snapshot.selectedPage+1)restoringPageRef.current=true;
    setLocalMetadata(snapshot.localMetadata);setMeta(snapshot.analysis?.enabled?snapshot.analysis.meta:null);setIndex(snapshot.analysis?.index||{});setRecipeState({recipe:snapshot.recipe||[],history:[]});setPage(snapshot.selectedPage+1);setStyle(snapshot.style||{});setSelection(snapshot.selection);setAcknowledged(snapshot.acknowledged===true);
    const find=snapshot.findState||{};setQuery(find.query||'');setReplacement(find.replacement||'');setFontFamily(find.fontFamily||'');setMatchCase(!!find.matchCase);setWholeWords(!!find.wholeWords);setExcludedIds(new Set(find.excludedIds||[]));setIndexProgress(normalizeIndexProgress(find.indexProgress));setActiveMatch(find.activeMatch||null);setResultPage(find.resultPage||1);setDraft(find.draft||'');setMode(find.mode||'select');setPanel(find.panel||'pages');
    setPreview(null);setBatchReview(null);setBatchError('');setSourceMismatch(false);setNavigationStatus('');setIndexRevision(value=>value+1);
  };
  const localMutation=async(command,payload,action,success)=>{
    const target=sessionRef.current;if(!target||busyOwnerRef.current)return;
    const owner=beginWork('page','Preparing pages in this browser…'),version=++editVersion.current;
    const valid=()=>current(target)&&sessionRef.current===target&&busyOwnerRef.current===owner&&editVersion.current===version;
    setPageError('');setMessage('');
    try{
      const snapshot=takeSnapshot(action,true);
      const result=await applyPageOperation({snapshot,isCurrent:valid,
        admit:({candidateBytes,temporaryBytes})=>budget({current:snapshot,candidateBytes,temporaryBytes,local:true}),
        transform:async()=>{const result=await pdfJob(target,command,{bytes:target.bytes,...payload,options:{password:target.password,acknowledged,...payload.options}},[...MERGE_ERRORS,...IMAGE_ERROR_CODES]);return {...result,action,acknowledged:result.localMetadata?.signed===true&&(acknowledged||payload.options?.sourceAcknowledged)};},
        prepare:bytes=>prepareViewer(target,bytes,valid),
        commit:(prepared,next,prior)=>{
          const replacement=restoreSession(target,next);indexingRef.current?.dispose();indexingRef.current=null;
          publishViewer(prepared,valid);retain(prior);target.controller.abort();target.password='';target.pages.clear();sessionRef.current=replacement;setSession(replacement);restoreUi(next);setOutput(next.bytes);releaseDraft();editVersion.current++;
        }});
      if(result.status==='applied'){setMessage(`${success} Page changes updated this PDF. Analyze text again to edit its current pages.`);requestAnimationFrame(()=>document.querySelector('.page-ops h2')?.focus());}
      else if(!['stale'].includes(result.status)&&result.code!=='NO_CHANGE')setPageError(localFailure(result));
    }catch(error){if(valid()&&!ignored(error))setPageError(localFailure(error));}
    finally{finishWork(owner);}
  };
  const pageCommand=operation=>{
    const action={insertBlank:'blank insertion',move:'page move',rotate:'page rotation',delete:'page deletion'}[operation.type];
    const success=operation.type==='insertBlank'?`Blank page inserted at position ${operation.adjacentIndex+(operation.position==='after'?2:1)}. Undo restores the previous document.`:operation.type==='move'?`Page moved from ${operation.from+1} to ${operation.to+1}.`:operation.type==='rotate'?`Page ${page} rotated to ${(localMetadata.pages[page-1].rotation+90)%360}°.`:`Page ${page} deleted. Undo restores the previous document.`;
    localMutation('transform',{operation},action,success);
  };
  const cancelDraft=()=>{const owner=draftRef.current?.owner;releaseDraft();setPageError('');if(owner)finishWork(owner);};
  const inspectImport=async(file,existingDraft=null)=>{
    const target=sessionRef.current;if(!file||busyOwnerRef.current)return;
    const owner=beginWork('import','Reviewing PDF in this browser…');setPageError('');
    const draft=existingDraft||{kind:'import',file,controller:new AbortController(),password:''};if(!existingDraft)releaseDraft();draft.owner=owner;draftRef.current=draft;
    const valid=()=>current(target)&&sessionRef.current===target&&draftRef.current===draft&&!draft.controller.signal.aborted;
    try{
      if(file.size>50*1024*1024)throw Object.assign(new Error(),{code:'LOCAL_PDF_TOO_LARGE'});
      requireBudget({temporaryBytes:file.size*3,retainSnapshot:false});
      draft.bytes??=new Uint8Array(await file.arrayBuffer());if(!valid())return;
      const review=await pdfJob(target,'inspectImport',{bytes:draft.bytes,options:{password:draft.password,existingBytes:target.bytes,existingPassword:target.password,filename:file.name}},MERGE_ERRORS);
      if(!valid())return;
      requireBudget({temporaryBytes:draft.bytes.buffer.byteLength,retainSnapshot:false});
      draft.preview=await prepareViewer({password:draft.password,controller:draft.controller},draft.bytes,valid);
      if(!valid()){draft.preview.dispose();return;}
      setImportReview({...review,name:file.name,position:page+1,normalize:false,acknowledged:false,password:draft.password,previewDocument:draft.preview.document});
    }catch(error){if(valid()){
      if(['PASSWORD_REQUIRED','PASSWORD_INVALID'].includes(error.code))setImportReview({name:file.name,needsPassword:true,password:draft.password});
      else{releaseDraft();setPageError(localFailure(error));}
    }}finally{finishWork(owner);}
  };
  const chooseImage=async file=>{
    const target=sessionRef.current;if(!file||busyOwnerRef.current)return;releaseDraft();setPageError('');
    const draft={kind:'image',file,controller:new AbortController()};draftRef.current=draft;
    const valid=()=>current(target)&&sessionRef.current===target&&draftRef.current===draft&&!draft.controller.signal.aborted;
    const owner=beginWork('image-decode','Preparing image in this browser…');draft.owner=owner;
    try{
      if(file.size>MAX_IMAGE_BYTES)throw Object.assign(new Error(),{code:'IMAGE_TOO_LARGE'});
      requireBudget({temporaryBytes:file.size+192*1024*1024,retainSnapshot:false});
      const prepared=await prepareImageDraft({decode:()=>decodeLocalImage(file,{signal:draft.controller.signal}),isCurrent:valid,getDestination:()=>imageDestinationRef.current,name:file.name});
      if(!prepared)return;draft.decoded=prepared;requireBudget({retainSnapshot:false});setImageDraft(prepared);
    }catch(error){if(valid()){if(error.code==='HEIC_CONVERSION_REQUIRED')setImageDraft({heic:true,name:file.name,converting:false});else{releaseDraft();setPageError(localFailure(error));}}}
    finally{finishWork(owner);}
  };
  const convertHeic=async()=>{
    const target=sessionRef.current,draft=draftRef.current;if(!imageDraft?.heic||!draft||busyOwnerRef.current)return;
    const owner=beginWork('heic','Converting HEIC on the server…');draft.owner=owner;setImageDraft(value=>({...value,converting:true}));setPageError('');
    const valid=()=>current(target)&&sessionRef.current===target&&draftRef.current===draft&&!draft.controller.signal.aborted;
    try{
      requireBudget({temporaryBytes:192*1024*1024+draft.file.size,retainSnapshot:false});
      const response=await fetch(`${API}/images/heic-decode`,{method:'POST',headers:{'Content-Type':draft.file.type==='image/heif'?'image/heif':'image/heic'},body:draft.file,signal:draft.controller.signal,cache:'no-store'});
      if(!response.ok){let data;try{data=await response.json();}catch{}throw Object.assign(new Error(),{code:data?.detail?.code||'HEIC_UNAVAILABLE'});}
      if(response.headers.get('content-type')?.split(';')[0]!=='image/png')throw Object.assign(new Error(),{code:'IMAGE_INVALID'});
      const declared=Number(response.headers.get('content-length'));if(declared>MAX_IMAGE_PNG_BYTES)throw Object.assign(new Error(),{code:'IMAGE_PNG_TOO_LARGE'});
      const reader=response.body.getReader(),chunks=[];let total=0;
      try{for(;;){const {done,value}=await reader.read();if(done)break;total+=value.byteLength;if(total>MAX_IMAGE_PNG_BYTES){await reader.cancel();throw Object.assign(new Error(),{code:'IMAGE_PNG_TOO_LARGE'});}chunks.push(value);}}finally{reader.releaseLock();}
      if(!valid())return;
      const prepared=await prepareImageDraft({decode:()=>decodeLocalImage(new Blob(chunks,{type:'image/png'}),{signal:draft.controller.signal,convertedPng:true}),isCurrent:valid,getDestination:()=>imageDestinationRef.current,name:draft.file.name});
      if(!prepared)return;draft.decoded=prepared;requireBudget({retainSnapshot:false});setImageDraft(prepared);
    }catch(error){if(valid()&&!ignored(error)){draft.decoded?.dispose();draft.decoded=undefined;setImageDraft(value=>({...value,converting:false}));setPageError(localFailure(error));}}
    finally{finishWork(owner);}
  };
  const updateDraft=change=>{
    if('importPassword'in change){draftRef.current.password=change.importPassword;setImportReview(value=>({...value,password:change.importPassword}));return;}
    if(change.retryImport){inspectImport(draftRef.current.file,draftRef.current);return;}
    if(importReview){setImportReview(value=>({...value,...('importPosition'in change?{position:change.importPosition}:{}),...('normalize'in change?{normalize:change.normalize}:{}),...('importAcknowledged'in change?{acknowledged:change.importAcknowledged}:{})}));return;}
    setImageDraft(value=>{if(!value||value.heic)return value;const next={...value,...change};if(change.field)next.rect=updateAspect(value.rect,change.field,change.value,{locked:value.locked,ratio:value.width/value.height});if(change.destination)next.rect=fitImage(value,localMetadata.pages[page-1]);return next;});
  };
  useEffect(()=>{setImageDraft(value=>value&&!value.heic&&value.page!==page?{...value,page,rect:fitImage(value,localMetadata.pages[page-1])}:value);},[page,localMetadata]);
  const commitImport=()=>{
    const review=importReview,draft=draftRef.current;if(!review||!draft||review.needsPassword)return;
    const form=!review.formCount?'No form fields in the imported PDF.':`${review.formCount} form fields kept with the “${review.prefix}” prefix. ${review.collisionCount?`${review.collisionCount} duplicate names renamed.`:'No duplicate names found.'}`;
    localMutation('merge',{sourceBytes:draft.bytes,options:{sourcePassword:draft.password,filename:review.name,sourceIdentity:review.sourceIdentity,position:review.position-1,normalizeTo:review.normalize?localMetadata.pages[page-1]:null,sourceAcknowledged:review.acknowledged}},'PDF merge',`Added ${review.pageCount} pages from ${review.name}. Undo restores the previous document. ${review.bookmarkCount?`Bookmarks will be nested under “${review.name}”.`:'No bookmarks to merge.'} ${form}`);
  };
  const commitImage=()=>{
    const draft=imageDraft,destination=imageDestinationRef.current;if(!draft?.pngBytes||!imageDraftMatchesPage(draft,destination.page)||!validatePlacement(draft.rect,destination.geometry).valid)return;
    localMutation('image',{pngBytes:draft.pngBytes,options:{destination:draft.destination,pageIndex:destination.page-1,position:draft.position,rect:draft.rect}},draft.destination==='new-page'?'image page':'image placement',draft.destination==='new-page'?'Image page added. Undo restores the previous document.':'Image placed. Undo restores the previous document.');
  };
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
    if(!selection||!accepted?.result.ok||accepted.key!==JSON.stringify(candidate())||typeof localMetadata?.signed!=='boolean'||(localMetadata.signed&&!acknowledged))return;
    const owner=beginWork('apply','Applying edit…');if(!owner)return;
    const version=++editVersion.current;
    const valid=()=>current(target)&&sessionRef.current===target&&busyOwnerRef.current===owner&&editVersion.current===version;
    setBatchReview(null);setMessage('');
    let prepared;
    try{
      const snapshot=takeSnapshot('text edit');
      requireBudget({current:snapshot,temporaryBytes:80*1024*1024});
      const result=await documentRequest(target,`/edit?dry_run=false&acknowledge_signature=${acknowledged}`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(accepted.recipe)});
      if(!valid())return;
      if(!result.ok||!result.pdf){setPreview({...accepted,result:{...result,ok:false}});return;}
      const bytes=decodePdf(result.pdf);requireBudget({current:snapshot,candidateBytes:bytes,temporaryBytes:bytes.buffer.byteLength});prepared=await prepareViewer(target,bytes,valid);
      if(!valid()){prepared.dispose();return;}
      requireBudget({current:snapshot,candidateBytes:bytes});publishViewer(prepared,valid);retain(snapshot);target.bytes=bytes;setRecipeState({recipe:accepted.recipe,history:[]});setOutput(bytes);
      editVersion.current++;setPreview(null);setBatchReview(null);setActiveMatch(null);setMessage('Edit applied. Download the PDF or undo this change.');
    }catch(error){if(prepared)prepared.dispose();if(valid()&&!ignored(error))setMessage(error.code?localFailure(error):'The edit could not be applied. Your current document is unchanged. Preview again, then retry.');}
    finally{finishWork(owner);}
  };
  const applyBatch=async()=>{
    const accepted=batchReview,target=sessionRef.current;
    if(indexProgress.status!=='complete'||accepted?.key!==batchKey||!accepted?.result.ok||typeof localMetadata?.signed!=='boolean'||(localMetadata.signed&&!acknowledged))return;
    const owner=beginWork('batch-apply',`Replacing ${accepted.selectedCount} matches on the server…`);if(!owner)return;
    const version=++editVersion.current;
    const valid=()=>current(target)&&sessionRef.current===target&&busyOwnerRef.current===owner&&editVersion.current===version;
    setMessage('');setBatchError('');setPreview(null);
    try{
      const snapshot=takeSnapshot('replacements');requireBudget({current:snapshot,temporaryBytes:80*1024*1024});
      const result=await applyReviewedReplacement({review:accepted,currentKey:()=>batchKeyRef.current,isCurrent:valid,signed:meta.signed,acknowledged,
        requestApply:recipe=>documentRequest(target,`/edit?dry_run=false&acknowledge_signature=${acknowledged}`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(recipe)}),
        loadOutput:encoded=>{const bytes=decodePdf(encoded);requireBudget({current:snapshot,candidateBytes:bytes,temporaryBytes:bytes.buffer.byteLength});return prepareViewer(target,bytes,()=>valid()&&batchKeyRef.current===accepted.key);},
        commit:(prepared,recipe)=>{
          requireBudget({current:snapshot,candidateBytes:prepared.bytes});publishViewer(prepared,()=>valid()&&batchKeyRef.current===accepted.key);
          retain(snapshot);target.bytes=prepared.bytes;setRecipeState({recipe,history:[]});setOutput(prepared.bytes);
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
    }catch(error){if(valid()&&!ignored(error))setBatchError(localFailure(error));}finally{finishWork(owner);}
  };
  const undo=async()=>{
    if(busyOwnerRef.current||!historyRef.current.length)return;
    const target=sessionRef.current,snapshot=peekSnapshot(historyRef.current),owner=beginWork('undo','Restoring previous document in this browser…');if(!owner)return;
    const version=++editVersion.current;
    const valid=()=>current(target)&&sessionRef.current===target&&busyOwnerRef.current===owner&&editVersion.current===version;
    setBatchReview(null);setPreview(null);setMessage('');setPageError('');let prepared,replacementSession;
    try{
      requireBudget({current:snapshot,temporaryBytes:snapshot.bytes.buffer.byteLength,retainSnapshot:false});
      replacementSession=restoreSession(target,snapshot);replacementSession.deferAnalysis=true;
      prepared=await prepareViewer(replacementSession,snapshot.bytes,valid);
      if(!valid()){prepared.dispose();return;}
      requireBudget({current:snapshot,retainSnapshot:false});publishViewer(prepared,valid);indexingRef.current?.dispose();indexingRef.current=null;releaseDraft();target.controller.abort();target.password='';target.pages.clear();sessionRef.current=replacementSession;setSession(replacementSession);restoreUi(snapshot);historyRef.current=popSnapshot(historyRef.current);setDocumentHistory(historyRef.current);setOutput(historyRef.current.length?snapshot.bytes:null);editVersion.current++;
      setMessage('Previous document restored.');
    }catch(error){replacementSession?.controller.abort();if(prepared)prepared.dispose();if(valid()&&!ignored(error))setPageError('The previous document could not be restored. Your current document is unchanged. Try Undo again.');}
    finally{finishWork(owner);}
  };
  useEffect(()=>{const handler=event=>{if((event.ctrlKey||event.metaKey)&&event.key.toLowerCase()==='z'&&!event.shiftKey&&!event.target.closest('input,textarea,[contenteditable=true]')){event.preventDefault();undo();}};window.addEventListener('keydown',handler);return()=>window.removeEventListener('keydown',handler);},[undo]);
  const download=(original=false)=>{const url=URL.createObjectURL(new Blob([original?session.openedBytes:session.bytes],{type:'application/pdf'})),anchor=document.createElement('a');anchor.href=url;anchor.download=!original&&output?`edited-${session.name.replace(/\.pdf$/i,'')}.pdf`:session.name;anchor.click();setTimeout(()=>URL.revokeObjectURL(url),1000);};
  const pageData=index[page],runs=pageData?.runs||[],noEditable=pageData&&!runs.some(run=>run.state!=='not_editable');
  const batchPreviewing=busyOwnerRef.current?.kind==='batch-preview',findLocked=!!busy&&!batchPreviewing;
  const currentReview=batchReview?.key===batchKey?batchReview:null;
  const findTarget=useMemo(()=>panel==='find'&&activeMatch&&matches.some(match=>match.id===activeMatch.id)?{...activeMatch,box:sourceRunForMatch(findPages,activeMatch)?.box}:null,[panel,activeMatch,matches,findPages]);
  return <div className="app" onDragOver={event=>{event.preventDefault();setDragging(true);}} onDragLeave={event=>{if(!event.currentTarget.contains(event.relatedTarget))setDragging(false);}} onDrop={event=>{event.preventDefault();setDragging(false);openFile(event.dataTransfer.files[0]);}}>
    <header className="app-header"><div className="brand"><span className="brand-mark" aria-hidden="true">P<span>↳</span></span><strong>PDF Tool</strong><span className="brand-caption">Document workstation</span></div><button onClick={()=>inputRef.current.click()}>Open PDF</button></header>
    <input ref={inputRef} type="file" accept="application/pdf,.pdf" className="visually-hidden" aria-label="Open PDF file" onChange={event=>{const file=event.target.files[0];event.target.value='';openFile(file);}}/>
    {dragging&&<div className="drop-overlay">Drop your PDF to open it</div>}
    {!session?<main className="welcome"><div className="welcome-copy"><p className="edition">A focused place for precise changes</p><h1>Your document.<br/>A few words better.</h1><p>Open a PDF, select a text run, and make the change. Keep the page around it intact.</p><button className="primary large" onClick={()=>inputRef.current.click()}>Choose a PDF</button><span className="drop-hint">or drop a file anywhere on this page</span></div><div className="welcome-sheet" aria-hidden="true"><div className="sheet-rule"/><span className="sheet-title">A working document</span><div className="ink-line long"/><div className="ink-line"/><div className="ink-line medium"/><div className="sample-edit">Make room for a better word.</div><div className="ink-line long"/><div className="ink-line"/><div className="ink-line medium"/><span className="sheet-page">1</span></div><div className="privacy-intro"><strong>Know where your document goes.</strong><p>Open and organize PDFs in your browser. Text analysis and text edits use the server. HEIC conversion uploads only the selected image when you choose Convert.</p></div></main>:<>
      <section className="document-bar"><div className="document-title"><strong title={session.name}>{session.name}</strong><span>{localMetadata?`${localMetadata.pageCount} ${localMetadata.pageCount===1?'page':'pages'}`:'Opening PDF'}{session.openedBytes&&` · ${(session.openedBytes.length/1024).toFixed(0)} KB`}{recipeState.recipe.length?` · ${recipeState.recipe.length} edited text ${recipeState.recipe.length===1?'run':'runs'}`:''}</span></div><div className="document-actions"><button onClick={undo} disabled={!!busy||!documentHistory.length} title="Restore the exact previous document (Ctrl/Cmd+Z)">Undo {documentHistory.at(-1)?.action||''} <span className="action-location">Browser</span></button><button className="primary" disabled={!!busy||!pdf} onClick={()=>download()}>{output?'Download edited PDF':'Download original'} <span className="action-location">Browser</span></button>{output&&<button onClick={()=>download(true)}>Download untouched original <span className="action-location">Browser</span></button>}<button onClick={clear}>Close</button></div></section>
      {localMetadata?.signed&&<div className="signature-notice"><strong>Digitally signed document.</strong> Any edit invalidates its signature. Downloading the untouched original preserves its bytes.<label><input type="checkbox" checked={acknowledged} onChange={event=>setAcknowledged(event.target.checked)} disabled={!!busy}/> I understand that editing invalidates the signature.</label></div>}
      {localMetadata?.encrypted&&<div className="notice">Local edits save an unlocked copy. Your untouched original retains its password protection.</div>}
      <main className="workspace"><aside className="page-rail" aria-label="Document pages"><h2>Pages <span className="location">Browser</span></h2>{pdf&&Array.from({length:pdf.numPages},(_,i)=><Thumbnail key={`${pdf.fingerprints[0]}-${i}`} pdf={pdf} number={i+1} current={page===i+1} badge={index[i+1]?.bucket} onSelect={number=>{setPage(number);fetchRuns(number,0);}} onVisible={fetchRuns}/>)}</aside>
      <section className="viewer"><div className="viewer-toolbar"><div className="mode-switch" role="group" aria-label="Text mode"><button className={mode==='select'?'active':''} onClick={()=>setMode('select')}>Select text</button><button className={mode==='edit'?'active':''} onClick={()=>{setMode('edit');if(!meta)setPanel('inspector');}}>Edit text</button></div><div className="page-controls"><button aria-label="Previous page" disabled={page<=1} onClick={()=>setPage(page-1)}>‹</button><span>{page} / {pdf?.numPages||'…'}</span><button aria-label="Next page" disabled={!pdf||page>=pdf.numPages} onClick={()=>setPage(page+1)}>›</button><label className="zoom"><span className="visually-hidden">Zoom</span><select value={scale} onChange={event=>setScale(Number(event.target.value))}><option value="0.65">65%</option><option value="0.85">85%</option><option value="1">100%</option><option value="1.15">115%</option><option value="1.5">150%</option><option value="2">200%</option></select></label></div></div><div className="canvas-stage">{pdf?<PageCanvas pdf={pdf} pageNumber={page} scale={scale} mode={mode} runs={runs} selected={selection?.run_id} onSelect={choose} findTarget={findTarget} imageDraft={imageDraft?.page===page?imageDraft:null} geometry={localMetadata?.pages[page-1]}/>:<p className="loading-page">Opening the first page…</p>}</div><div className="viewer-caption">{panel==='find'&&activeMatch&&<button className="back-results" onClick={()=>{setResultPage(Math.floor(matches.findIndex(match=>match.id===activeMatch.id)/50)+1);requestAnimationFrame(()=>rowRefs.current.get(activeMatch.id)?.focus());}}>Back to results</button>}<span>{mode==='select'?'Select and copy text, or use your browser’s find on this page.':'Choose an outlined text run to inspect and edit it.'}</span><span className="location">Viewing in browser</span></div>{panel==='find'&&navigationStatus&&<p className="find-navigation-status" aria-live="polite">{navigationStatus}</p>}</section>
      <aside className="inspector"><div className="panel-switch" role="group" aria-label="Inspector panel"><button aria-pressed={panel==='pages'} onClick={()=>setPanel('pages')}>Pages</button><button ref={inspectorButtonRef} aria-pressed={panel==='inspector'} onClick={showInspector}>Text inspector</button><button aria-pressed={panel==='find'} onClick={showFind}>Find and replace</button></div>{panel==='pages'?<PageOpsPanel page={page} pageCount={pdf?.numPages||0} geometry={localMetadata?.pages[page-1]} busy={busy} localMetadata={localMetadata} acknowledged={acknowledged} importReview={importReview} imageDraft={imageDraft} error={pageError} onCommand={pageCommand} onChoosePdf={inspectImport} onChooseImage={chooseImage} onCancelDraft={cancelDraft} onConvertHeic={convertHeic} onUpdateDraft={updateDraft} onCommitImport={commitImport} onCommitImage={commitImage}/>:!meta?<div className="analysis-gate"><h2>Analyze text to edit it</h2><p>This uploads the current PDF for classification and text edits. Page tools work without uploading.</p><button className="primary" disabled={!!busy} onClick={analyze}>Analyze text <span className="location server">Server</span></button></div>:panel==='find'?<FindPanel query={query} replacement={replacement} fontFamily={fontFamily} matchCase={matchCase} wholeWords={wholeWords}
        onQuery={value=>changeFind(setQuery,value,true)} onReplacement={value=>changeFind(setReplacement,value)} onFont={value=>changeFind(setFontFamily,value)}
        onMatchCase={value=>changeFind(setMatchCase,value,true)} onWholeWords={value=>changeFind(setWholeWords,value,true)}
        progress={indexProgress} matches={matches} excludedIds={excludedIds} onToggle={id=>{invalidateBatch();setExcludedIds(previous=>{const next=new Set(previous);if(next.has(id))next.delete(id);else next.add(id);return next;});}}
        onStop={()=>indexingRef.current?.stop()} onResume={resumeIndexing} review={currentReview} previewing={batchPreviewing} locked={findLocked}
        onPreview={checkReplacements} onCancelPreview={cancelBatchPreview} error={batchError} activeId={activeMatch?.id} onNavigate={navigateMatch}
        resultPage={resultPage} onResultPage={setResultPage} queryRef={queryRef} rowRefs={rowRefs} recipe={recipeState.recipe} pages={findPages} sourceMismatch={sourceMismatch} onRefresh={refreshIndex} onApply={applyBatch} applyAllowed={!!currentReview?.result.ok&&indexProgress.status==='complete'&&(!meta?.signed||acknowledged)}/>:<><h2>Text inspector <span className="location server">Server edits</span></h2>{!meta?<p>Preparing document analysis…</p>:!pageData?<p>Classifying this page…</p>:<><div className="page-verdict"><strong title={pageData.bucket}>{explainBucket(pageData.bucket)}</strong><span>{runs.length} text {runs.length===1?'run':'runs'}</span></div>{noEditable&&<div className="refusal"><h3>{runs.length?'This page cannot be safely edited':'No editable text was found'}</h3><p>{runs.length?[...new Set(runs.map(run=>explainReason(run.reason)))].join(' '):'This may be a scanned page. Run OCR first, then open the searchable PDF here.'}</p><a href="https://ocrmypdf.readthedocs.io/" target="_blank" rel="noopener noreferrer" >Read the OCRmyPDF guide</a><small>External guide. Your PDF is not sent to this site.</small><button className="ocr-interest" onClick={()=>{const target=sessionRef.current;request('/ocr-notify',{method:'POST'}).then(()=>{if(current(target))setMessage('Interest recorded. This counts demand for built-in OCR; no contact details or PDF were sent.');}).catch(()=>{if(current(target))setMessage('Could not record interest. Try again later.');});}}>Register interest in built-in OCR <span>Server</span></button></div>}
      {selection?<div className="edit-form"><div className="selected-heading"><h3>Selected text</h3><span className={`state-badge ${selection.state==='not_editable'?'blocked':''}`}>{selection.state==='editable_original'?'Original font':selection.state==='editable_substitution'?'Font substitution':'Cannot edit'}</span></div><p className="original-text">{selection.text}</p>{selection.state==='not_editable'?<p className="refusal-reason">{explainReason(selection.reason)}{refusalCode(selection.reason)&&<code>{refusalCode(selection.reason)}</code>}</p>:<><label>Replacement text<textarea value={draft} onChange={event=>{editVersion.current++;setPreview(null);setDraft(event.target.value);}} disabled={!!busy} rows={4}/></label><fieldset disabled={!!busy}><legend>Text style</legend><p className="source-font">Detected font: <strong>{selection.source_font||'Unknown'}</strong></p><label className="font-choice">Replacement font<select value={style.font_family||''} onChange={event=>setStyle(chooseFontFamily(style,event.target.value))}><option value="">Automatic — preserve or match original</option><option value="Serif">Serif — Liberation Serif</option><option value="Sans">Sans-serif — Liberation Sans</option><option value="Mono">Monospace — Liberation Mono</option></select></label>{needsFontChoice(selection,style)&&<p className="font-guidance">No automatic font match. Choose a replacement above to edit this text.</p>}<div className="style-controls"><label><input type="checkbox" checked={style.bold||false} onChange={event=>setStyle({...style,bold:event.target.checked})}/> Bold</label><label><input type="checkbox" checked={style.italic||false} onChange={event=>setStyle({...style,italic:event.target.checked})}/> Italic</label><label className="color-control">Color<input aria-label="Text color" type="color" value={style.color?`#${style.color.map(value=>Math.round(value*255).toString(16).padStart(2,'0')).join('')}`:'#000000'} onChange={event=>setStyle({...style,color:event.target.value.slice(1).match(/../g).map(value=>parseInt(value,16)/255)})}/></label></div><p className="size-refusal">Font-size changes are not supported. Edits must fit the original width.</p></fieldset>{(selection.state==='editable_substitution'||'font_family' in style||'bold' in style||'italic' in style)&&<p className="substitution-note">A bundled substitute font will be used. Preview checks its fit before applying.</p>}<button onClick={checkFit} disabled={!!busy||!meta}>Preview fit <span>Server</span></button>{preview&&<div className={`fit-result ${preview.result.ok?'fits':'does-not-fit'}`} role="status"><strong>{preview.result.ok?'Ready to apply':'Edit refused'}</strong>{preview.result.resolved?.map(item=><p key={item.run_id}>{item.ok?explainFit(item.strategy):explainReason(item.reason)}{!item.ok&&refusalCode(item.reason)&&<code>{refusalCode(item.reason)}</code>}</p>)}</div>}<button className="primary" onClick={apply} disabled={!!busy||!preview?.result.ok||(meta.signed&&!acknowledged)}>Apply edit <span>Server</span></button><p className="edit-disclosure">Preview and apply send the recipe to the server. Edits replay against the current analyzed PDF. Undo restores the exact previous document in this browser.</p></>}<button className="text-button" onClick={()=>setSelection(null)}>Back to page text</button></div>:!noEditable&&<><p className="inspector-hint">Switch to Edit text and choose a run on the page, or select one below.</p><div className="run-list">{runs.map(run=><button key={run.run_id} onClick={()=>{setMode('edit');choose(run);}}><span>{run.text||'(Empty text)'}</span><small>{run.state==='not_editable'?explainReason(run.reason):run.state==='editable_substitution'?'Substitute font':'Editable'}</small></button>)}</div></>}</>}</>}</aside></main>
    </>}
    {(busy||message)&&<div className="status-bar" role="status" aria-live="polite"><span>{busy||message}</span>{message&&!busy&&<button onClick={()=>setMessage('')} aria-label="Dismiss message">×</button>}</div>}
    <footer className="app-footer"><span>Original stays in this browser’s memory while open.</span><span>Page changes and PDF download stay in this browser. Text analysis uses the server; HEIC conversion is a separate server action.</span></footer>
    {passwordPrompt&&<div className="modal-backdrop"><form className="password-dialog" role="dialog" aria-modal="true" aria-labelledby="password-title" onSubmit={event=>{event.preventDefault();const target=passwordPrompt.target;target.password=passwordInput;const resolve=target.passwordResolve;target.passwordPromise=null;target.passwordResolve=null;setPasswordPrompt(null);setPasswordInput('');resolve?.(target.password);}}><h2 id="password-title">Unlock this PDF</h2><p>{passwordPrompt.incorrect?'That password was incorrect. Try again.':'Enter the document password to view and organize it in this browser.'}</p><label>PDF password<input autoFocus type="password" value={passwordInput} onChange={event=>setPasswordInput(event.target.value)} autoComplete="off"/></label><p className="small-copy">Kept in memory while this document is open. Sent to the server only if you choose text analysis.</p><div className="dialog-actions"><button type="button" onClick={clear}>Cancel</button><button className="primary" type="submit">Unlock PDF</button></div></form></div>}
  </div>;
}

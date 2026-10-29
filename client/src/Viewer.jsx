import React, {useEffect,useRef,useState} from 'react';
import * as pdfjs from 'pdfjs-dist';
import {viewportBox,explainReason,explainBucket} from './session.mjs';
import FindHighlight from './find/FindHighlight.jsx';

export function PageCanvas({pdf,pageNumber,scale,mode,runs=[],selected,onSelect,findTarget,onFindRendered,imageDraft,geometry,renderOverlay,disabled=false}) {
  const canvas=useRef(null),text=useRef(null),paper=useRef(null);
  const [viewport,setViewport]=useState(null),[error,setError]=useState(''),[rendered,setRendered]=useState(null);
  useEffect(()=>{
    let stopped=false,render,layer;
    setViewport(null);setError('');setRendered(null);
    (async()=>{
      const page=await pdf.getPage(pageNumber);
      if(stopped)return;
      const view=page.getViewport({scale}),ratio=Math.min(window.devicePixelRatio||1,Math.sqrt(16000000/(view.width*view.height))),element=canvas.current;
      setViewport(view);
      element.width=Math.ceil(view.width*ratio);element.height=Math.ceil(view.height*ratio);
      element.style.width=`${view.width}px`;element.style.height=`${view.height}px`;
      render=page.render({canvasContext:element.getContext('2d'),viewport:view,transform:ratio===1?null:[ratio,0,0,ratio,0,0]});
      text.current.replaceChildren();
      layer=new pdfjs.TextLayer({textContentSource:page.streamTextContent(),container:text.current,viewport:view});
      await Promise.all([render.promise,layer.render()]);
      if(!stopped)setRendered({pdf,pageNumber,scale});
    })().catch(error=>{if(!stopped&&error.name!=='RenderingCancelledException')setError('This page could not be rendered. Try reopening the PDF.');});
    return ()=>{stopped=true;render?.cancel();layer?.cancel();};
  },[pdf,pageNumber,scale]);
  return <div ref={paper} className="paper" onDoubleClick={event=>{if(mode!=='select'||disabled||!viewport)return;const rect=event.currentTarget.getBoundingClientRect(),x=event.clientX-rect.left,y=event.clientY-rect.top;const run=runs.find(run=>{const b=viewportBox(run.box,viewport);return x>=b.left&&x<=b.left+b.width&&y>=b.top&&y<=b.top+b.height;});if(run)onSelect(run);}} style={viewport?{width:viewport.width,height:viewport.height,'--scale-factor':scale,'--total-scale-factor':viewport.scale*(viewport.userUnit||1)}:undefined}>
    <canvas ref={canvas} aria-label={`PDF page ${pageNumber}`}/>
    <div ref={text} className={`textLayer ${mode==='edit'?'inactive':''}`}/>
    {viewport&&geometry&&imageDraft?.preview&&imageDraft.rect&&<canvas className="placement-preview" aria-label="Temporary image placement preview" ref={element=>{if(element&&imageDraft.preview){element.width=imageDraft.width;element.height=imageDraft.height;element.getContext('2d').drawImage(imageDraft.preview,0,0);}}} style={{left:imageDraft.rect.left/geometry.visibleWidth*viewport.width,top:imageDraft.rect.top/geometry.visibleHeight*viewport.height,width:imageDraft.rect.width/geometry.visibleWidth*viewport.width,height:imageDraft.rect.height/geometry.visibleHeight*viewport.height}}/>}
    {viewport&&mode==='edit'&&<div className="edit-layer" aria-label="Text edit targets">{runs.map(run=><button key={run.run_id} type="button" disabled={disabled} className={`run-box ${selected===run.run_id?'selected':''} ${run.state==='not_editable'?'refused':''}`} style={viewportBox(run.box,viewport)} title={`${run.text}: ${run.state==='not_editable'?explainReason(run.reason):'Edit text'}`} aria-label={`Edit text: ${run.text}`} onClick={()=>onSelect(run)}/>)}</div>}
    {viewport&&findTarget?.page===pageNumber&&<FindHighlight pdf={pdf} pageNumber={pageNumber} scale={scale} viewport={viewport} rendered={rendered} textRef={text} paperRef={paper} target={findTarget} onRendered={onFindRendered}/>}
    {error&&<p className="render-error" role="alert">{error}</p>}
    {viewport&&renderOverlay?.(viewport)}
  </div>;
}

export function Thumbnail({pdf,number,current,badge,onSelect,onVisible}) {
  const root=useRef(null),canvas=useRef(null),[visible,setVisible]=useState(false);
  useEffect(()=>{
    const observer=new IntersectionObserver(entries=>setVisible(entries.some(entry=>entry.isIntersecting)),{rootMargin:'200px'});
    observer.observe(root.current);return()=>observer.disconnect();
  },[]);
  useEffect(()=>{
    if(!visible){if(canvas.current){canvas.current.width=0;canvas.current.height=0;}return;}
    let stopped=false,render;
    onVisible(number);
    pdf.getPage(number).then(page=>{
      if(stopped)return;
      const viewport=page.getViewport({scale:90/page.getViewport({scale:1}).width});
      canvas.current.width=Math.ceil(viewport.width);canvas.current.height=Math.ceil(viewport.height);
      render=page.render({canvasContext:canvas.current.getContext('2d'),viewport});return render.promise;
    }).catch(()=>{});
    return()=>{stopped=true;render?.cancel();};
  },[pdf,number,visible,onVisible]);
  return <button ref={root} className={`thumbnail ${current?'current':''}`} onClick={()=>onSelect(number)} aria-current={current?'page':undefined} aria-label={`Page ${number}${badge?`, ${badge}`:''}`}><div className="thumbnail-paper"><canvas ref={canvas}/></div><span>Page {number}</span><small title={badge}>{badge?explainBucket(badge):'Page tools available'}</small></button>;
}

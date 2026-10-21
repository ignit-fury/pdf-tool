import React, {useEffect,useRef,useState} from 'react';
import * as pdfjs from 'pdfjs-dist';
import {viewportBox,explainReason,explainBucket} from './session.mjs';

export function PageCanvas({pdf,pageNumber,scale,mode,runs,selected,onSelect}) {
  const canvas=useRef(null),text=useRef(null);
  const [viewport,setViewport]=useState(null),[error,setError]=useState('');
  useEffect(()=>{
    let stopped=false,render,layer;
    setViewport(null);setError('');
    (async()=>{
      const page=await pdf.getPage(pageNumber);
      if(stopped)return;
      const view=page.getViewport({scale}),ratio=window.devicePixelRatio||1,element=canvas.current;
      setViewport(view);
      element.width=Math.ceil(view.width*ratio);element.height=Math.ceil(view.height*ratio);
      element.style.width=`${view.width}px`;element.style.height=`${view.height}px`;
      render=page.render({canvasContext:element.getContext('2d'),viewport:view,transform:ratio===1?null:[ratio,0,0,ratio,0,0]});
      text.current.replaceChildren();
      layer=new pdfjs.TextLayer({textContentSource:page.streamTextContent(),container:text.current,viewport:view});
      await Promise.all([render.promise,layer.render()]);
    })().catch(error=>{if(!stopped&&error.name!=='RenderingCancelledException')setError('This page could not be rendered. Try reopening the PDF.');});
    return ()=>{stopped=true;render?.cancel();layer?.cancel();};
  },[pdf,pageNumber,scale]);
  return <div className="paper" style={viewport?{width:viewport.width,height:viewport.height,'--scale-factor':scale,'--total-scale-factor':viewport.scale}:undefined}>
    <canvas ref={canvas} aria-label={`PDF page ${pageNumber}`}/>
    <div ref={text} className={`textLayer ${mode==='edit'?'inactive':''}`}/>
    {viewport&&mode==='edit'&&<div className="edit-layer" aria-label="Text edit targets">{runs.map(run=><button key={run.run_id} type="button" className={`run-box ${selected===run.run_id?'selected':''} ${run.state==='not_editable'?'refused':''}`} style={viewportBox(run.box,viewport)} title={`${run.text}: ${run.state==='not_editable'?explainReason(run.reason):'Edit text'}`} aria-label={`Edit text: ${run.text}`} onClick={()=>onSelect(run)}/>)}</div>}
    {error&&<p className="render-error" role="alert">{error}</p>}
  </div>;
}

export function Thumbnail({pdf,number,current,badge,onSelect,onVisible}) {
  const root=useRef(null),canvas=useRef(null),[visible,setVisible]=useState(false);
  useEffect(()=>{
    const observer=new IntersectionObserver(entries=>{if(entries.some(entry=>entry.isIntersecting)){setVisible(true);observer.disconnect();}},{rootMargin:'100px'});
    observer.observe(root.current);return()=>observer.disconnect();
  },[]);
  useEffect(()=>{
    if(!visible)return;
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
  return <button ref={root} className={`thumbnail ${current?'current':''}`} onClick={()=>onSelect(number)} aria-current={current?'page':undefined} aria-label={`Page ${number}${badge?`, ${badge}`:''}`}><div className="thumbnail-paper"><canvas ref={canvas}/></div><span>Page {number}</span><small title={badge}>{badge?explainBucket(badge):'Not classified yet'}</small></button>;
}

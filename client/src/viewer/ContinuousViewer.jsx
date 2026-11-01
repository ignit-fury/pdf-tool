import React,{useEffect,useRef,useState} from 'react';
import {PageCanvas} from '../Viewer.jsx';
import {pageSize,visibleDocumentPage} from './model.mjs';
import {scrollWithinDocument} from './scroll.mjs';
import {groupedEditTargets} from './groupRuns.mjs';

function PageShell({number,pdf,scale,geometry,root,register,pinned,...props}) {
  const element=useRef(null),[near,setNear]=useState(number===1);
  useEffect(()=>{
    const node=element.current;register(number,node);
    const observer=new IntersectionObserver(entries=>setNear(entries.some(e=>e.isIntersecting)),{root:root.current,rootMargin:'700px'});
    observer.observe(node);return()=>{observer.disconnect();register(number,null);};
  },[number,root,register]);
  const size=pageSize(geometry,scale);
  return <section ref={element} className="document-page" data-page-number={number} aria-label={`Document page ${number}`} style={{width:size.width,minHeight:size.height}}>
    <span className="page-number-label" aria-hidden="true">{number}</span>
    {near||pinned?<PageCanvas {...props} pdf={pdf} pageNumber={number} scale={scale} geometry={geometry}/>:<div className="page-placeholder" style={size} aria-label={`Page ${number} loads when nearby`}/>}
  </section>;
}

export default function ContinuousViewer({pdf,scale,metadata,index,navigation,onPageChange,onVisible,selection,renderOverlay,editedRunIds,...props}) {
  const root=useRef(null),shells=useRef(new Map()),latest=useRef(null),register=useRef((number,node)=>{if(node)shells.current.set(number,node);else shells.current.delete(number);}).current;
  latest.current={onPageChange,onVisible};
  useEffect(()=>{
    const visible=new Map();
    const observer=new IntersectionObserver(entries=>{
      for(const entry of entries){const number=Number(entry.target.dataset.pageNumber);if(entry.isIntersecting)visible.set(number,entry);else visible.delete(number);}
      if(!root.current)return;
      const bounds=root.current.getBoundingClientRect();
      const positions=[...visible.keys()].flatMap(number=>{const node=shells.current.get(number);if(!node)return [];const rect=node.getBoundingClientRect();return [{number,top:rect.top,bottom:rect.bottom}];});
      const current=visibleDocumentPage(positions,bounds.top,bounds.bottom);
      if(current)latest.current.onPageChange(current);
      for(const [number] of visible)latest.current.onVisible(number,0);
    },{root:root.current,threshold:[0,.15,.4,.7,1]});
    for(const node of shells.current.values())observer.observe(node);
    return()=>observer.disconnect();
  },[pdf]);
  // Not keyed on pdf: a publish after an edit swaps pdf and must keep the reader's viewport.
  useEffect(()=>{scrollWithinDocument(root.current,shells.current.get(navigation?.page),{align:'start',behavior:navigation?.behavior||'instant'});},[navigation?.serial,scale]);
  return <div ref={root} className="canvas-stage continuous-stage" tabIndex="0" aria-label="Continuous PDF document">
    {Array.from({length:pdf.numPages},(_,i)=>{const number=i+1;return <PageShell key={number} number={number} root={root} register={register} pinned={selection?.pageNumber===number} pdf={pdf} scale={scale} geometry={metadata?.pages[number-1]} {...props}
      runs={groupedEditTargets(index[number]?.runs||[],editedRunIds)} selected={selection?.pageNumber===number?selection.run_id:null}
      onSelect={run=>props.onSelect({...run,pageNumber:number})} imageDraft={props.imageDraft?.page===number?props.imageDraft:null}
      renderOverlay={viewport=>renderOverlay?.(number,viewport)}/>;})}
  </div>;
}

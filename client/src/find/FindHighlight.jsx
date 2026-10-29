import React,{useEffect,useRef,useState} from 'react';
import {viewportBox} from '../session.mjs';
import {highlightKey,highlightMessage} from './highlight.mjs';
import {measureHighlight} from './highlightDom.mjs';
import {scrollWithinDocument} from '../viewer/scroll.mjs';

export default function FindHighlight({pdf,pageNumber,scale,viewport,rendered,textRef,paperRef,target,onRendered}){
  const [state,setState]=useState(null),anchor=useRef(null),latest=useRef(null),callback=useRef(onRendered);
  const key=target?highlightKey(target):null,ready=rendered?.pdf===pdf&&rendered?.pageNumber===pageNumber&&rendered?.scale===scale;
  latest.current={pdf,key,scale,ready};callback.current=onRendered;
  useEffect(()=>{
    if(!target||!ready||!viewport||target.page!==pageNumber||!Array.isArray(target.box)){setState(null);return;}
    const captured={pdf,key,scale},valid=()=>latest.current.ready&&latest.current.pdf===pdf&&latest.current.key===key&&latest.current.scale===scale;
    const frame=requestAnimationFrame(()=>{
      if(!valid())return;
      const results=(target.highlights||[target]).flatMap(item=>{
        if(!Array.isArray(item.box))return [];
        const expected=viewportBox(item.box,viewport);
        if(!Object.values(expected).every(Number.isFinite)||expected.width<=0||expected.height<=0)return [];
        return [measureHighlight(textRef.current,paperRef.current,expected,item)];
      });
      if(valid())setState({...captured,results});
    });return()=>cancelAnimationFrame(frame);
  },[pdf,pageNumber,scale,key,ready,viewport,textRef,paperRef]);
  const visible=ready&&state?.pdf===pdf&&state?.key===key&&state?.scale===scale?state.results:null;
  useEffect(()=>{
    if(!visible?.length||!anchor.current)return;
    const frame=requestAnimationFrame(()=>{
      if(latest.current.pdf!==pdf||latest.current.key!==key||latest.current.scale!==scale||!latest.current.ready)return;
      scrollWithinDocument(anchor.current?.closest('.continuous-stage'),anchor.current,{behavior:target.behavior||'instant'});
      callback.current?.({pdf,scale,key,id:target.id,quality:visible[0].quality,reason:visible[0].reason});
    });return()=>cancelAnimationFrame(frame);
  },[pdf,scale,key,visible,target?.behavior]);
  if(!visible?.length)return null;
  return <div className="find-highlight-layer" role="group" aria-label={visible.length===1?highlightMessage(visible[0]):`${visible.length} applied replacement areas highlighted on this page.`} data-highlight-quality={visible[0].quality}>
    {visible.flatMap((result,index)=>result.rects.map((rect,i)=><div key={`${index}-${i}`} ref={index===0&&i===0?anchor:null} className={`find-highlight ${result.quality}`} style={rect} aria-label={result.quality==='precise'?'Applied replacement text':result.quality==='removed'?'Removed text original area':'Approximate search result text area'}/>))}
  </div>;
}

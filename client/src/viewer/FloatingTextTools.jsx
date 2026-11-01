import React,{useLayoutEffect,useRef,useState} from 'react';
import {createPortal} from 'react-dom';
import {placeInlineTools} from './inlineTools.mjs';

export default function FloatingTextTools({box,children}){
  const anchor=useRef(null),tools=useRef(null),[position,setPosition]=useState(null);
  useLayoutEffect(()=>{
    let frame;
    const update=()=>{
      const target=anchor.current,toolbar=tools.current;
      if(!target||!toolbar)return;
      const rect=target.getBoundingClientRect();
      const scroller=target.closest('.continuous-stage');
      const bounds=scroller?.getBoundingClientRect();
      const visible=rect.bottom>Math.max(0,bounds?.top??0)&&rect.top<Math.min(window.innerHeight,bounds?.bottom??window.innerHeight);
      setPosition({...placeInlineTools(rect,toolbar.offsetWidth,toolbar.offsetHeight,window.innerWidth,window.innerHeight),visibility:visible?'visible':'hidden'});
    };
    const schedule=()=>{cancelAnimationFrame(frame);frame=requestAnimationFrame(update);};
    const observer=new ResizeObserver(schedule);observer.observe(tools.current);observer.observe(anchor.current);
    window.addEventListener('scroll',schedule,true);window.addEventListener('resize',schedule);
    update();
    return()=>{cancelAnimationFrame(frame);observer.disconnect();window.removeEventListener('scroll',schedule,true);window.removeEventListener('resize',schedule);};
  },[box.left,box.top,box.width,box.height]);
  return <><span ref={anchor} aria-hidden="true" style={{position:'absolute',pointerEvents:'none',...box}}/>{createPortal(
    <div ref={tools} className="floating-text-tools" style={position||{visibility:'hidden'}}>{children}</div>,document.body)}</>;
}

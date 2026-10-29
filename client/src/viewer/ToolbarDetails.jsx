import React,{useEffect,useRef} from 'react';

/** Low-frequency controls float over the page instead of taking document height. */
export default function ToolbarDetails({label,children,closeKey}){
  const root=useRef(null);
  const close=focus=>{const node=root.current;if(!node)return;node.open=false;if(focus)node.querySelector('summary')?.focus();};
  useEffect(()=>{close(false);},[closeKey]);
  useEffect(()=>{
    const outside=event=>{const node=root.current;if(node?.open&&!node.contains(event.target)&&(!event.target.closest('.context-toolbar')||event.target.closest('.context-actions')))close(false);};
    document.addEventListener('pointerdown',outside);return()=>document.removeEventListener('pointerdown',outside);
  },[]);
  return <details ref={root} className="toolbar-details" onKeyDown={event=>{if(event.key==='Escape'){event.preventDefault();event.stopPropagation();close(true);}}}>
    <summary>{label}</summary><div className="toolbar-popover">{children}<button type="button" className="toolbar-done" onClick={()=>close(true)}>Done</button></div>
  </details>;
}

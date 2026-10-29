import React,{useEffect,useRef,useState} from 'react';
import {normalizeOutline,resolveOutlinePage} from './outline.mjs';

function Branch({items,collapsed,onCollapse,onChoose,disabled}){
  return <ul className="outline-list">{items.map(item=><li key={item.id}>
    <div className="outline-row">{item.children.length>0&&<button className="outline-toggle" aria-label={`${collapsed.has(item.id)?'Expand':'Collapse'} ${item.title}`} aria-expanded={!collapsed.has(item.id)} onClick={()=>onCollapse(item.id)}>{collapsed.has(item.id)?'▸':'▾'}</button>}
      <button className="outline-destination" disabled={disabled||!item.destination} onClick={()=>onChoose(item)} style={{fontWeight:item.bold?700:400,fontStyle:item.italic?'italic':'normal'}}>{item.title}</button>
    </div>{item.reason&&<small>{item.reason}</small>}
    {!!item.children.length&&!collapsed.has(item.id)&&<Branch items={item.children} collapsed={collapsed} onCollapse={onCollapse} onChoose={onChoose} disabled={disabled}/>}
  </li>)}</ul>;
}
export default function OutlinePanel({pdf,busy,navigationKey,onNavigate}){
  const heading=useRef(null),source=useRef(pdf),view=useRef(navigationKey),serial=useRef(0);
  const [revision,setRevision]=useState(0),[state,setState]=useState(null),[collapsed,setCollapsed]=useState(new Set()),[message,setMessage]=useState(''),[resolving,setResolving]=useState(false);
  source.current=pdf;view.current=navigationKey;
  useEffect(()=>{heading.current?.focus();},[]);
  useEffect(()=>{serial.current++;setResolving(false);setMessage('');},[navigationKey]);
  useEffect(()=>{
    let active=true;serial.current++;setState(null);setMessage('');setResolving(false);setCollapsed(new Set());
    Promise.resolve().then(()=>pdf.getOutline()).then(tree=>{if(active&&source.current===pdf)setState({pdf,...normalizeOutline(tree)});},()=>{if(active&&source.current===pdf)setState({pdf,error:true});});
    return()=>{active=false;serial.current++;};
  },[pdf,revision]);
  const choose=async item=>{
    const token=++serial.current,captured=pdf,capturedView=navigationKey;setResolving(true);setMessage('Resolving bookmark…');
    const valid=()=>source.current===captured&&serial.current===token&&view.current===capturedView;
    try{const page=await resolveOutlinePage(captured,item.destination,valid);if(valid()){setMessage(`Page ${page}`);onNavigate(page);}}
    catch(error){if(valid()&&error.name!=='AbortError')setMessage('This bookmark cannot be resolved to a page in the current document.');}
    finally{if(valid())setResolving(false);}
  };
  const current=state?.pdf===pdf?state:null;
  return <section className="navigation-panel" aria-label="Document outline" aria-busy={!current||resolving}>
    <h2 ref={heading} tabIndex={-1}>Outline <span className="location">Browser</span></h2>
    <p className="navigation-guidance">Bookmarks from this PDF. Navigation stays in this browser and keeps your zoom. Text analysis pauses here; choose Edit text or Find to resume.</p>
    {!current?<p role="status">Reading document outline…</p>:current.error?<><p role="alert">The outline could not be read. Your PDF is unchanged.</p><button onClick={()=>setRevision(n=>n+1)}>Retry outline</button></>:!current.items.length?<p>No bookmarks in this document.</p>:<Branch items={current.items} collapsed={collapsed} onCollapse={id=>setCollapsed(previous=>{const next=new Set(previous);if(next.has(id))next.delete(id);else next.add(id);return next;})} onChoose={choose} disabled={!!busy}/>}
    {current?.limited&&<p className="context-warning">The outline is too large, deeply nested or cyclic. Showing a bounded portion.</p>}
    {message&&<p role="status">{message}</p>}
  </section>;
}

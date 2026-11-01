import React,{useEffect,useLayoutEffect,useRef} from 'react';
import {colorHex} from '../viewer/model.mjs';
import {FONT_STACKS} from './model.mjs';
import {useClickAway} from '../viewer/ParagraphEditor.jsx';
import {scrollWithinDocument} from '../viewer/scroll.mjs';

// Edit text mode: empty page area places new text; inserted boxes open inline. The place layer sits
// under the run targets (z-index 3) and paragraph outlines (4), so those still win the click.
export function TextBoxOverlay({number,viewport,geometry,draft,boxes,disabled,onPlace,onSelect,onDraft,onCommit,onCancel}){
  const sx=viewport.width/geometry.visibleWidth,sy=viewport.height/geometry.visibleHeight;
  const rect=value=>({left:value.left*sx,top:value.top*sy,width:value.width*sx,height:value.height*sy});
  return <>
    <button type="button" className="text-place-layer" aria-label={`Add text on page ${number}`} disabled={disabled} onClick={event=>{const b=event.currentTarget.getBoundingClientRect();onPlace(number-1,event.detail?{left:(event.clientX-b.left)/sx,top:(event.clientY-b.top)/sy}:{left:40,top:40});}}/>
    <div className="text-box-layer">
      {boxes.filter(box=>box.page_index===number-1&&box.id!==draft?.id).map((box,i)=><button key={box.id} type="button" className="saved-text-box" style={rect(box.rect)} aria-label={`Edit inserted text ${i+1} on page ${number}`} disabled={disabled} onClick={()=>onSelect(box)}/>)}
      {draft?.page_index===number-1&&<TextDraftEditor key={draft.serial} draft={draft} geometry={geometry} sx={sx} sy={sy} box={rect(draft.rect)} disabled={disabled} onDraft={onDraft} onCommit={onCommit} onCancel={onCancel}/>}
    </div>
  </>;
}

function TextDraftEditor({draft,geometry,sx,sy,box,disabled,onDraft,onCommit,onCancel}){
  const root=useRef(null),input=useRef(null),drag=useRef(null),latest=useRef();
  latest.current={draft,busy:disabled,onCommit,onDraft};
  const pointer=useClickAway(root,latest,()=>input.current?.focus({preventScroll:true}));
  useEffect(()=>{
    const node=input.current,stage=node.closest('.continuous-stage');node.focus({preventScroll:true});node.setSelectionRange(node.value.length,node.value.length);
    // Scroll only when off-screen (e.g. opened from the inspector), so a click never moves the page under the pointer.
    const view=stage?.getBoundingClientRect(),own=node.getBoundingClientRect();
    if(view&&(own.top<view.top||own.bottom>view.bottom||own.left<view.left||own.right>view.right))scrollWithinDocument(stage,node);
  },[]);
  // Canvas measurement sizes the box; scrollHeight only covers a browser wrap the estimate missed.
  useLayoutEffect(()=>{const node=input.current;node.style.height=`${box.height}px`;node.style.height=`${Math.max(box.height,node.scrollHeight)}px`;},[draft.text,draft.style,box.height,box.width]);
  const move=event=>{
    const start=drag.current,{draft:current,busy}=latest.current;if(!start||busy)return;
    const left=Math.max(0,Math.min(geometry.visibleWidth-current.rect.width,start.left+(event.clientX-start.x)/sx));
    const top=Math.max(0,Math.min(geometry.visibleHeight-current.rect.height,start.top+(event.clientY-start.y)/sy));
    latest.current.onDraft({...current,rect:{...current.rect,left,top}});
  };
  const s=draft.style;
  return <div ref={root} className="text-draft" data-status={draft.status==='saving'?'saving':draft.status?.refused?'refused':'editing'} style={{position:'absolute',left:box.left,top:box.top,width:box.width,height:box.height}}>
    <textarea ref={input} className="text-box-input" aria-label="Text on page" placeholder="Type…" spellCheck={false} wrap="soft" disabled={disabled} value={draft.text}
      style={{left:0,top:0,width:'100%',fontFamily:FONT_STACKS[s.font_family],fontSize:s.font_size*sy,lineHeight:s.line_spacing,fontWeight:s.bold?700:400,fontStyle:s.italic?'italic':'normal',color:colorHex(s.color),letterSpacing:s.character_spacing*sx,textAlign:s.alignment}}
      onChange={event=>onDraft({...draft,text:event.target.value})}
      onKeyDown={event=>{if(event.key==='Escape'){event.preventDefault();onCancel();}else if(event.key==='Tab'){event.preventDefault();onCommit();}}}
      onBlur={event=>{if(pointer.current)return;if(event.relatedTarget?.closest?.('.floating-text-tools')||root.current?.contains(event.relatedTarget))return;onCommit();}}/>
    <span className="text-draft-handle" title="Drag to move" aria-hidden="true" onMouseDown={event=>event.preventDefault()}
      onPointerDown={event=>{if(disabled)return;event.preventDefault();event.currentTarget.setPointerCapture(event.pointerId);drag.current={x:event.clientX,y:event.clientY,left:draft.rect.left,top:draft.rect.top};}}
      onPointerMove={move} onPointerUp={()=>{drag.current=null;input.current?.focus({preventScroll:true});}} onPointerCancel={()=>{drag.current=null;}}/>
  </div>;
}

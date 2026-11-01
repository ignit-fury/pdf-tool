import React,{useEffect,useRef} from 'react';
import {inlineBox,sourceTypography,colorHex,viewportFontScale} from './model.mjs';
import ToolbarDetails from './ToolbarDetails.jsx';

export function InlineInput({run,style,draft,viewport,busy,onDraft,onCancel,onPreview}) {
  const input=useRef(null),box=inlineBox(run.box,viewport);
  useEffect(()=>{input.current?.focus({preventScroll:true});input.current?.setSelectionRange(input.current.value.length,input.current.value.length);},[run.run_id]);
  useEffect(()=>{const node=input.current;if(!node||!box)return;node.style.width=`${box.width}px`;node.style.width=`${Math.min(Math.max(box.width,node.scrollWidth+2),Math.max(30,viewport.width-box.left))}px`;},[draft,style,viewport,box?.width]);
  if(!box)return null;
  return <textarea ref={input} className="inline-text-input" aria-label="Edit text on page" aria-describedby="inline-edit-guidance" wrap="off" spellCheck={false} value={draft} disabled={busy}
    style={{...box,...sourceTypography(run,style,viewportFontScale(viewport)),height:Math.max(box.height,sourceTypography(run,style,viewportFontScale(viewport)).fontSize*1.3),minWidth:30,maxWidth:Math.max(30,viewport.width-box.left)}}
    onChange={event=>onDraft(event.target.value,{start:event.target.selectionStart,end:event.target.selectionEnd})} onKeyDown={event=>{if(event.key==='Escape'){event.preventDefault();onCancel();}if((event.ctrlKey||event.metaKey)&&event.key==='Enter'){event.preventDefault();onPreview();}}}/>;
}

export default function TextToolbar({run,style,busy,status,onStyle,onDelete,onRevert}) {
  if(!run)return null;
  const size=style.font_size??run.font_size??12;
  return <section className="context-toolbar compact" aria-label="Text formatting">
    <fieldset disabled={!!busy}>
      <select aria-label="Font" value={style.font_family||''} onChange={event=>{const next={...style};if(event.target.value)next.font_family=event.target.value;else delete next.font_family;onStyle(next);}}><option value="">{run.source_font||'Source font'}</option><option value="Sans">Liberation Sans</option><option value="Serif">Liberation Serif</option><option value="Mono">Liberation Mono</option></select>
      <button aria-label="Decrease font size" onClick={()=>onStyle({...style,font_size:Math.max(1,Number(size)-1)})}>−</button>
      <input aria-label="Font size" type="number" min="1" max="512" step="0.5" value={size} onChange={event=>onStyle({...style,font_size:Number(event.target.value)})}/>
      <button aria-label="Increase font size" onClick={()=>onStyle({...style,font_size:Math.min(512,Number(size)+1)})}>+</button>
      <button aria-pressed={style.bold??!!run.bold} aria-label="Bold" onClick={()=>onStyle({...style,bold:!(style.bold??run.bold)})}><strong>B</strong></button>
      <button aria-pressed={style.italic??!!run.italic} aria-label="Italic" onClick={()=>onStyle({...style,italic:!(style.italic??run.italic)})}><em>I</em></button>
      <input type="color" aria-label="Text color" value={colorHex(style.color??run.color)} onChange={event=>onStyle({...style,color:event.target.value.slice(1).match(/../g).map(v=>parseInt(v,16)/255)})}/>
      <button aria-label="Delete paragraph" onClick={onDelete}>Delete</button>
      <ToolbarDetails label="⋯" closeKey={run.run_id}><label>Character spacing<input type="number" aria-label="Character spacing" min="0" max="10" step="0.1" value={style.character_spacing??run.character_spacing??0} onChange={event=>onStyle({...style,character_spacing:Number(event.target.value)})}/></label></ToolbarDetails>
      <span className="action-location">Server</span>
    </fieldset>
    {status==='saving'&&<p role="status">Saving…</p>}
    {status?.refused&&<p className="context-warning" role="alert">{status.refused} <button onClick={onRevert}>Revert</button></p>}
  </section>;
}

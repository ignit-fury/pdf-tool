import React,{useEffect,useRef} from 'react';
import {inlineBox,sourceTypography,draftProblem,colorHex,viewportFontScale} from './model.mjs';
import {explainReason,needsFontChoice} from '../session.mjs';

export function InlineInput({run,style,draft,viewport,busy,onDraft,onCancel,onPreview}) {
  const input=useRef(null),box=inlineBox(run.box,viewport);
  useEffect(()=>{input.current?.focus({preventScroll:true});input.current?.select();},[run.run_id]);
  if(!box)return null;
  return <textarea ref={input} className="inline-text-input" aria-label="Edit text on page" aria-describedby="inline-edit-guidance" wrap="off" spellCheck={false} value={draft} disabled={busy}
    style={{...box,...sourceTypography(run,style,viewportFontScale(viewport)),height:Math.max(box.height,sourceTypography(run,style,viewportFontScale(viewport)).fontSize*1.3),minWidth:30,maxWidth:Math.max(30,viewport.width-box.left)}}
    onChange={event=>onDraft(event.target.value,{start:event.target.selectionStart,end:event.target.selectionEnd})} onKeyDown={event=>{if(event.key==='Escape'){event.preventDefault();onCancel();}if((event.ctrlKey||event.metaKey)&&event.key==='Enter'){event.preventDefault();onPreview();}}}/>;
}

export default function TextToolbar({run,style,draft,preview,busy,allowed,onStyle,onPreview,onApply,onCancel,onExpand}) {
  if(!run)return null;
  const problem=draftProblem(draft),uneditable=run.state==='not_editable',size=style.font_size??run.font_size??12;
  const refused=preview?.result.resolved?.filter(row=>!row.ok)||[];
  return <section className="context-toolbar" aria-label="Text formatting">
    <div className="context-heading"><strong>Text on page {run.pageNumber}</strong><span>Detected: {run.source_font||'Unknown font'}{run.font_size?` · ${run.font_size} pt`:''}</span><button onClick={onCancel} disabled={!!busy} aria-label="Cancel text editing">Close</button></div>
    {uneditable?<p role="status">{explainReason(run.reason)} Select another text run. Page tools and exports remain available.</p>:<>
      <fieldset disabled={!!busy}><label>Font<select aria-label="Replacement font" value={style.font_family||''} onChange={event=>{const next={...style};if(event.target.value)next.font_family=event.target.value;else delete next.font_family;onStyle(next);}}><option value="">Automatic / source font</option><option value="Sans">Liberation Sans</option><option value="Serif">Liberation Serif</option><option value="Mono">Liberation Mono</option></select></label>
        <div className="size-buttons"><button title="Decrease font size" aria-label="Decrease font size" onClick={()=>onStyle({...style,font_size:Math.max(1,Number(size)-1)})}>−</button><label>Size<input aria-label="Font size" type="number" min="1" max="512" step="0.5" value={size} onChange={event=>onStyle({...style,font_size:Number(event.target.value)})}/></label><button title="Increase font size (growth may be refused)" aria-label="Increase font size" onClick={()=>onStyle({...style,font_size:Math.min(512,Number(size)+1)})}>+</button></div>
        <button aria-pressed={style.bold??!!run.bold} onClick={()=>onStyle({...style,bold:!(style.bold??run.bold)})}><strong>Bold</strong></button><button aria-pressed={style.italic??!!run.italic} onClick={()=>onStyle({...style,italic:!(style.italic??run.italic)})}><em>Italic</em></button>
        <label>Color<input type="color" aria-label="Text color" value={colorHex(style.color??run.color)} onChange={event=>onStyle({...style,color:event.target.value.slice(1).match(/../g).map(v=>parseInt(v,16)/255)})}/></label>
        <label>Hex<input aria-label="Text color hex" key={colorHex(style.color??run.color)} defaultValue={colorHex(style.color??run.color)} maxLength={7} pattern="#[0-9a-fA-F]{6}" onBlur={event=>{if(/^#[0-9a-fA-F]{6}$/.test(event.target.value))onStyle({...style,color:event.target.value.slice(1).match(/../g).map(v=>parseInt(v,16)/255)});else event.target.value=colorHex(style.color??run.color);}}/></label>
        <label>Character spacing<input type="number" aria-label="Character spacing" min="0" max="10" step="0.1" value={style.character_spacing??run.character_spacing??0} onChange={event=>onStyle({...style,character_spacing:Number(event.target.value)})}/></label>
        <label>Layout<select value="preserve" aria-label="Text layout mode" onChange={event=>{if(event.target.value==='flexible')onExpand();}}><option value="preserve">Preserve layout</option><option value="flexible">Flexible text box — wrap and grow</option></select></label>
      </fieldset>
      <p id="inline-edit-guidance" className="context-guidance">Temporary input preview. Preview and Apply use the server; only validated content-stream edits enter your PDF. Preserve layout keeps the original line. Choose Flexible text box for wrapping, size growth, alignment and spacing. Line breaks switch to it automatically; nearby PDF content stays fixed.</p>
      {needsFontChoice(run,style)&&<p className="context-warning">No automatic font match. Choose a replacement font before previewing.</p>}
      {problem&&<p className="context-warning" role="status">{problem}</p>}
      {preview&&<div className={`inline-fit ${preview.result.ok?'':'context-warning'}`} role="status">{preview.result.ok?'Validated — ready to apply.':`Edit refused. ${refused.map(row=>explainReason(row.reason)).join(' ')}`}</div>}
      <div className="context-actions"><button onClick={()=>onExpand()} disabled={!!busy}>Expand text box</button><button onClick={onPreview} disabled={!!busy||!!problem||needsFontChoice(run,style)}>Preview fit <span className="action-location">Server</span></button><button className="primary" onClick={onApply} disabled={!!busy||!!problem||!preview?.result.ok||!allowed}>Apply edit <span className="action-location">Server</span></button><button onClick={onCancel} disabled={!!busy}>Cancel</button><span>Esc cancels · Ctrl/⌘ Enter previews</span></div>
    </>}
  </section>;
}

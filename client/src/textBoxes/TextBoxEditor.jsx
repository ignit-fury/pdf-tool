import React,{useEffect,useLayoutEffect,useRef,useState} from 'react';
import {colorHex} from '../viewer/model.mjs';
import {draftError,expandTextBox,explainTextBoxError} from './model.mjs';
import {scrollWithinDocument} from '../viewer/scroll.mjs';
import ToolbarDetails from '../viewer/ToolbarDetails.jsx';

export function TextBoxOverlay({number,viewport,geometry,draft,boxes,state,disabled,onPlace,onSelect,onDraft}){
  const input=useRef(null),outline=useRef(null),sx=viewport.width/geometry.visibleWidth,sy=viewport.height/geometry.visibleHeight;
  useEffect(()=>{if(draft){if(state.status!=='ready'){input.current?.focus({preventScroll:true});if(draft.caret)input.current?.setSelectionRange(draft.caret.start,draft.caret.end);}const area=input.current||outline.current;scrollWithinDocument(area?.closest('.continuous-stage'),area);}},[!!draft,draft?.id,draft?.page_index,state.status==='ready']);
  useLayoutEffect(()=>{
    const element=input.current;if(!element||!draft||state.status==='ready')return;
    const minimum=draft.rect.height*sy;element.style.height=`${minimum}px`;
    if(draft.auto_expand!==false)element.style.height=`${Math.min((geometry.visibleHeight-draft.rect.top)*sy,Math.max(minimum,element.scrollHeight))}px`;
  },[draft,sy,geometry.visibleHeight,state.status]);
  const rect=value=>({left:value.left*sx,top:value.top*sy,width:value.width*sx,height:value.height*sy});
  const active=draft?.page_index===number-1;
  return <div className="text-box-layer">
    {!draft&&<button className="text-box-place" aria-label={`Insert text on page ${number}`} disabled={disabled} onClick={event=>{const b=event.currentTarget.getBoundingClientRect();onPlace(number-1,event.detail?{left:(event.clientX-b.left)/sx,top:(event.clientY-b.top)/sy}:{left:40,top:40});}}/>}
    {state.status!=='ready'&&boxes.filter(box=>box.page_index===number-1&&box.id!==draft?.id).map((box,i)=><button key={box.id} className="saved-text-box" style={rect(box.rect)} aria-label={`Edit inserted text box ${i+1} on page ${number}`} disabled={disabled} onClick={()=>onSelect(box)}/>)}
    {active&&(state.status==='ready'||draft.rotation?<div ref={outline} className="text-box-preview-outline" style={rect(draft.rect)} aria-label="Prepared text box area"/>:<textarea ref={input} className="text-box-input" aria-label="Text box content on page" aria-describedby="text-box-disclosure" placeholder="Type text here…" spellCheck={false} wrap="soft" disabled={disabled} value={draft.text} style={{...rect(draft.rect),fontFamily:{Sans:'Arial,sans-serif',Serif:'"Times New Roman",serif',Mono:'"Courier New",monospace'}[draft.style.font_family],fontSize:draft.style.font_size*sy,lineHeight:draft.style.line_spacing,fontWeight:draft.style.bold?700:400,fontStyle:draft.style.italic?'italic':'normal',color:colorHex(draft.style.color),letterSpacing:draft.style.character_spacing*sx,textAlign:draft.style.alignment}} onChange={event=>onDraft({...draft,text:event.target.value,caret:{start:event.target.selectionStart,end:event.target.selectionEnd}})}/>)}
  </div>;
}

export default function TextBoxToolbar({draft,state,geometry,pageCount,busy,allowed,onDraft,onPreview,onApply,onCancel,onEdit,onRemove}){
  const [confirm,setConfirm]=useState(false);
  if(!draft)return null;
  const ready=state.status==='ready',overflow=state.status==='overflow',problem=draftError(draft,geometry);
  const change=(field,value)=>onDraft({...draft,style:{...draft.style,[field]:value}});
  const expanded=overflow?expandTextBox(draft,state.required_height,geometry):null;
  return <section className="context-toolbar text-box-toolbar" aria-label="Text box formatting">
    <div className="context-heading"><strong>{draft.source_run_id?'Expand original text':draft.id?'Edit inserted text':'Insert text'} · Page {draft.page_index+1}</strong><span>{ready?'Exact PDF preview — not applied':'Native, searchable text container'}</span><button onClick={onCancel} disabled={!!busy} aria-label="Cancel text box">Close</button></div>
    <fieldset disabled={!!busy||ready||!!draft.rotation}>
      <label>Font<select aria-label="Text box font" value={draft.style.font_family} onChange={event=>change('font_family',event.target.value)}><option value="Sans">Liberation Sans</option><option value="Serif">Liberation Serif</option><option value="Mono">Liberation Mono</option></select></label>
      <label>Size<input type="number" aria-label="Text box font size" min="1" max="512" value={draft.style.font_size} onChange={event=>change('font_size',Number(event.target.value))}/></label>
      <button aria-pressed={draft.style.bold} onClick={()=>change('bold',!draft.style.bold)}><strong>Bold</strong></button><button aria-pressed={draft.style.italic} onClick={()=>change('italic',!draft.style.italic)}><em>Italic</em></button>
      <label>Color<input type="color" aria-label="Text box color" value={colorHex(draft.style.color)} onChange={event=>change('color',event.target.value.slice(1).match(/../g).map(v=>parseInt(v,16)/255))}/></label>
      <ToolbarDetails label="Layout & spacing" closeKey={`${draft.id||draft.source_run_id||''}:${ready}`}><fieldset disabled={!!busy||ready||!!draft.rotation}>
      <label>Page<input type="number" aria-label="Text box page" min="1" max={pageCount} value={draft.page_index+1} onChange={event=>onDraft({...draft,page_index:Number(event.target.value)-1})}/></label>
      {['left','top','width','height'].map(field=><label key={field}>{field[0].toUpperCase()+field.slice(1)} (pt)<input aria-label={`Text box ${field}`} type="number" min={['width','height'].includes(field)?1:0} step="1" value={draft.rect[field]} onChange={event=>onDraft({...draft,rect:{...draft.rect,[field]:Number(event.target.value)}})}/></label>)}
      <label>Hex<input key={colorHex(draft.style.color)} aria-label="Text box color hex" defaultValue={colorHex(draft.style.color)} maxLength={7} pattern="#[0-9a-fA-F]{6}" onBlur={event=>{if(/^#[0-9a-fA-F]{6}$/.test(event.target.value))change('color',event.target.value.slice(1).match(/../g).map(v=>parseInt(v,16)/255));else event.target.value=colorHex(draft.style.color);}}/></label>
      <label>Alignment<select aria-label="Text box alignment" value={draft.style.alignment} onChange={event=>change('alignment',event.target.value)}><option value="left">Left</option><option value="center">Center</option><option value="right">Right</option></select></label>
      {[['character_spacing','Character spacing',0,10,.1],['line_spacing','Line spacing',1,3,.1],['paragraph_spacing','Paragraph spacing',0,144,1]].map(([key,label,min,max,step])=><label key={key}>{label}<input type="number" aria-label={`Text box ${label.toLowerCase()}`} min={min} max={max} step={step} value={draft.style[key]} onChange={event=>change(key,Number(event.target.value))}/></label>)}
      <label className="text-box-overlap"><input type="checkbox" checked={!!draft.allow_overlap} onChange={event=>onDraft({...draft,allow_overlap:event.target.checked})}/> Allow transparent overlap with existing content</label>
      <label className="text-box-overlap"><input type="checkbox" aria-label="Grow height to fit text" checked={draft.auto_expand!==false} onChange={event=>onDraft({...draft,auto_expand:event.target.checked})}/> Grow height to fit text</label>
      </fieldset></ToolbarDetails>
    </fieldset>
    <ToolbarDetails label="Edit details" closeKey={ready}>
    <p id="text-box-disclosure" className="context-guidance">{draft.source_run_id?'Preview sends the source PDF, committed edit recipe and replacement text to the server. Apply uses the exact prepared PDF locally. Nearby content stays fixed.':'Preview uploads the current PDF and this text to the server. Apply uses the exact prepared PDF in this browser. This creates or edits an inserted text container; it does not reflow surrounding source text.'} The draft font/wrapping is approximate until PDF preview.</p>
    {draft.source_run_id&&<p className="context-guidance">This replaces the selected original text through the validated content-stream writer. Other content stays fixed; growth requires free space. The original font ({draft.source_font||'unknown'}) is replaced by the selected Liberation font. Tabs use four spaces. Preview includes all prior edits.</p>}
    </ToolbarDetails>
    {!!draft.rotation&&<p className="context-warning">This text box rotated with its page. Rotate the page back to edit its layout. You can still preview removal of this inserted text.</p>}
    {problem&&!ready&&<p className="context-warning">{problem}</p>}
    {state.status==='error'&&<p className="context-warning" role="alert">{explainTextBoxError(state.error)}</p>}
    {overflow&&<div className="context-warning" role="status"><p>Text needs {state.required_height.toFixed(2)} pt height; this box has {state.available_height.toFixed(2)} pt. No text was applied or clipped.</p>{expanded?<button onClick={()=>onDraft(expanded)}>Expand text box to fit</button>:<p>There is not enough room below this box. Reduce the font size, move it, or choose another page.</p>}</div>}
    {ready&&<p role="status">Exact candidate PDF is visible. The working PDF and Undo history are unchanged until Apply.{state.preview.layout?` ${state.preview.layout.line_count} lines.`:''}{state.preview.notices.includes('UNLOCKED_COPY')?' The prepared copy is unlocked.':''}{state.preview.notices.includes('SIGNATURES_INVALIDATED')?' Applying invalidates signatures.':''}</p>}
    <div className="context-actions">{ready?<><button onClick={onEdit} disabled={!!busy}>Edit text box draft</button><button className="primary" onClick={onApply} disabled={!!busy||!allowed}>Apply text box <span className="action-location">Browser</span></button></>:<button className="primary" onClick={onPreview} disabled={!!busy||!!problem||!allowed||!!draft.rotation}>Preview text box <span className="action-location">Server</span></button>}{draft.id&&!ready&&<button onClick={()=>setConfirm(true)} disabled={!!busy}>Remove text box</button>}<button onClick={onCancel}>Cancel text box changes</button></div>
    {confirm&&!ready&&<div role="group" aria-label="Confirm text box removal"><p>Preview removal of this inserted text only? Apply will commit it; Undo can restore it.</p><button onClick={()=>{setConfirm(false);onRemove();}} disabled={!!busy||!allowed}>Preview text box removal <span className="action-location">Server</span></button><button onClick={()=>setConfirm(false)}>Keep text box</button></div>}
  </section>;
}

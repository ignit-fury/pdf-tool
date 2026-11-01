import React,{useEffect,useLayoutEffect,useRef} from 'react';
import {insertText,splitLine,mergeLine,deleteRange,layoutTops} from './paragraphs.mjs';
import {viewportBox,explainReason} from '../session.mjs';
import {sourceTypography,viewportFontScale} from './model.mjs';

// zIndex 4 sits above the per-run .edit-layer (z-index 3), so paragraph targets win the click;
// refused paragraphs let clicks through to their runs (e.g. inserted text boxes open in text-box mode).
export function ParagraphOutlines({paragraphs,runs=[],viewport,activeId,onChoose}){
  const text=new Map(runs.map(r=>[r.run_id,r.text]));
  return paragraphs.filter(p=>p.paragraph_id!==activeId).map(p=>{
    const box=viewportBox(p.box,viewport);
    const words=p.lines.flat().map(id=>text.get(id)||'').join(' ').replace(/\s+/g,' ').trim(),label=words?`Edit paragraph: ${words.length>40?words.slice(0,40)+'…':words}`:'Edit paragraph';
    // Inserted text boxes pass clicks through to their own editor; other refusals stay reachable so the reason can be read.
    const passThrough=p.state==='not_editable'&&String(p.reason).startsWith('managed_text_box');
    return <button key={p.paragraph_id} type="button" className="paragraph-outline" data-state={p.state}
      style={{position:'absolute',zIndex:4,...box,...(passThrough?{pointerEvents:'none'}:{})}} title={p.state==='not_editable'?explainReason(p.reason):'Edit paragraph'}
      aria-label={p.state==='not_editable'?`Not editable: ${explainReason(p.reason)}`:label}
      aria-disabled={p.state==='not_editable'||undefined} disabled={passThrough} onClick={event=>onChoose(p,event)}/>;
  });
}

export default function ParagraphEditor({paragraph,resetKey,lines,runsById,style,viewport,caret,busy,status,onLines,onCommit,onCancel}){
  const root=useRef(null),latest=useRef(),pointer=useRef(null),saved=useRef(null),tops=useRef([]),src=useRef([]),step=useRef(14);
  latest.current={lines,runsById,viewport,caret,paragraph,onLines,onCommit,busy};
  const first=runsById.get(paragraph.lines[0][0]);
  const typography=sourceTypography(first||{},style,viewportFontScale(viewport));
  const origin=viewportBox(paragraph.box,viewport);
  // The line DOM is uncontrolled: React never re-renders it, so typing and Enter cannot fight the browser.
  const paint=(next,at,editIndex)=>{
    const node=root.current,{viewport:vp,paragraph:para,runsById:runs}=latest.current,o=viewportBox(para.box,vp);
    tops.current=layoutTops(tops.current,src.current,step.current,next.length,editIndex);
    node.replaceChildren(...next.map((text,k)=>{
      const div=document.createElement('div');div.dataset.line=k;div.textContent=text;
      Object.assign(div.style,{position:'absolute',left:`${leftOf(k)}px`,top:`${tops.current[k]}px`,whiteSpace:'pre',minHeight:'1em'});
      return div;
    }));
    fit();
    if(at)place(node,at);
    function leftOf(k){const b=viewportBox(lineBox(para,Math.min(k,para.lines.length-1),runs),vp);return b.left-o.left;}
  };
  // Lines are absolute, so the box cannot size itself: grow it to cover typed text and hide the page beneath.
  const fit=()=>{
    const node=root.current,o=viewportBox(latest.current.paragraph.box,latest.current.viewport);let w=o.width,h=o.height;
    for(const line of node.children){w=Math.max(w,line.offsetLeft+line.offsetWidth+2);h=Math.max(h,line.offsetTop+line.offsetHeight);}
    node.style.width=`${w}px`;node.style.height=`${h}px`;
  };
  const read=()=>[...root.current.children].map(div=>div.textContent.replace(/\u00a0/g,' '));
  const endOfDoc=()=>{const n=root.current.children.length-1;return {line:n,offset:root.current.children[n]?.textContent.length??0};};
  const position=(node,offset)=>{
    const kids=[...root.current.children];
    if(node===root.current)return offset>=kids.length?endOfDoc():{line:offset,offset:0};
    const div=(node.nodeType===1?node:node.parentNode).closest?.('[data-line]');if(!div)return endOfDoc();
    const pre=document.createRange();pre.selectNodeContents(div);pre.setEnd(node,offset);
    return {line:kids.indexOf(div),offset:pre.toString().length};
  };
  // Selection as {start,end,collapsed}; falls back to the end of the last line when the range sits on the root.
  const where=()=>{
    const sel=getSelection();if(!sel.rangeCount||!root.current.contains(sel.anchorNode))return null;
    const r=sel.getRangeAt(0),start=position(r.startContainer,r.startOffset),end=position(r.endContainer,r.endOffset);
    return {start,end,line:start.line,offset:start.offset,collapsed:sel.isCollapsed};
  };
  // Run a pure edit on the lines, after removing any selected text.
  const apply=(edit)=>{
    const w=where();if(!w)return;
    let cur=read(),from=w.start;
    if(!w.collapsed){const d=deleteRange(cur,w.start,w.end);cur=d.lines;from=d.caret;}
    const r=edit(cur,from);if(!r)return;
    paint(r.lines,r.caret,Math.min(from.line,r.caret.line));latest.current.onLines(r.lines);
  };
  useLayoutEffect(()=>{
    const {lines:init,caret:c,viewport:vp,paragraph:para,runsById:runs}=latest.current,o=viewportBox(para.box,vp);
    src.current=para.lines.map((_,k)=>viewportBox(lineBox(para,k,runs),vp).top-o.top);
    step.current=src.current.length>1?src.current[1]-src.current[0]:0;
    tops.current=[...src.current];
    paint(init,null,src.current.length-1);
    if(!step.current)step.current=root.current.children[0]?.offsetHeight||14;
    paint(init,null,src.current.length-1);
    root.current.focus({preventScroll:true});
    place(root.current,{line:c?.line??0,offset:c?.offset??Infinity});
  },[paragraph.paragraph_id,resetKey]); // resetKey repaints from the current draft lines (toolbar Delete)
  useEffect(()=>{
    const inside=target=>target.closest?.('.floating-text-tools')?'toolbar':root.current?.contains(target)?'editor':'outside';
    const control=target=>!!target.closest?.('input,select,textarea');
    const down=event=>{
      pointer.current=inside(event.target);
      if(pointer.current==='outside'&&!latest.current.busy)latest.current.onCommit();
    };
    const end=event=>{
      if(pointer.current==='toolbar'&&!control(event.target))setTimeout(()=>{
        if(!root.current)return;root.current.focus({preventScroll:true});
        const r=saved.current,sel=getSelection();if(r){sel.removeAllRanges();sel.addRange(r);}
      },0);
      setTimeout(()=>{pointer.current=null;},0);
    };
    // A toolbar form control keeps focus; when it blurs to somewhere outside, commit.
    const out=event=>{
      if(!control(event.target)||!event.target.closest('.floating-text-tools'))return;
      const to=event.relatedTarget;
      if(pointer.current==='outside'||pointer.current==='editor'||to?.closest?.('.floating-text-tools')||root.current?.contains(to))return;
      if(pointer.current==='toolbar'&&!to)return;
      if(!latest.current.busy)latest.current.onCommit();
    };
    const before=event=>{
      const t=event.inputType;
      if(t==='insertFromDrop'||t==='deleteByDrag'||t==='historyUndo'||t==='historyRedo'){event.preventDefault();return;}
      const w=where();if(!w)return;
      const multi=!w.collapsed&&w.start.line!==w.end.line;
      if(t==='deleteContentForward'&&w.collapsed&&w.offset===read()[w.line]?.length&&w.line<root.current.children.length-1){event.preventDefault();apply(cur=>mergeLine(cur,w.line+1));}
      else if(multi&&/^delete/.test(t)){event.preventDefault();apply(cur=>({lines:cur,caret:w.start}));}
      else if(multi&&t==='insertText'&&event.data){event.preventDefault();apply((cur,at)=>insertText(cur,at.line,at.offset,event.data));}
    };
    document.addEventListener('pointerdown',down,true);document.addEventListener('pointerup',end,true);document.addEventListener('pointercancel',end,true);
    document.addEventListener('focusout',out,true);root.current.addEventListener('beforeinput',before);
    const node=root.current;
    return()=>{document.removeEventListener('pointerdown',down,true);document.removeEventListener('pointerup',end,true);document.removeEventListener('pointercancel',end,true);
      document.removeEventListener('focusout',out,true);node.removeEventListener('beforeinput',before);};
  },[]);
  return <div ref={root} className="paragraph-editor" data-status={status==='saving'?'saving':status?.refused?'refused':'editing'}
    contentEditable={!busy} suppressContentEditableWarning role="textbox" aria-multiline="true" aria-label="Edit paragraph on page" spellCheck={false}
    style={{position:'absolute',zIndex:4,...origin,...typography}}
    onInput={()=>{fit();latest.current.onLines(read());}}
    onDragStart={event=>event.preventDefault()} // a drag-move would delete text the blocked drop never re-inserts
    onPaste={event=>{event.preventDefault();const text=event.clipboardData.getData('text/plain');apply((cur,at)=>insertText(cur,at.line,at.offset,text));}}
    onKeyDown={event=>{
      if(event.key==='Escape'){event.preventDefault();onCancel();}
      else if(event.key==='Tab'){event.preventDefault();onCommit();}
      else if(event.key==='Enter'&&!event.nativeEvent.isComposing){event.preventDefault();
        apply((cur,at)=>splitLine(cur,at.line,at.offset));}
      else if(event.key==='Backspace'){const w=where();if(w?.collapsed&&w.offset===0&&w.line>0){event.preventDefault();apply(cur=>mergeLine(cur,w.line));}}
    }}
    onBlur={event=>{
      const sel=getSelection();if(sel.rangeCount&&root.current.contains(sel.anchorNode))saved.current=sel.getRangeAt(0).cloneRange();
      if(pointer.current==='toolbar'||pointer.current==='editor'||pointer.current==='outside')return;
      if(event.relatedTarget?.closest?.('.floating-text-tools')||event.currentTarget.contains(event.relatedTarget))return;
      onCommit();
    }}/>;
}

function place(node,{line,offset}){
  const div=node.children[Math.min(line,node.children.length-1)];if(!div)return;
  const text=div.firstChild,range=document.createRange();
  if(text)range.setStart(text,Math.min(offset,text.length));else range.setStart(div,0);
  range.collapse(true);const sel=getSelection();sel.removeAllRanges();sel.addRange(range);
}

function lineBox(paragraph,index,runsById){
  const ids=paragraph.lines[index]||paragraph.lines.at(-1),boxes=ids.map(id=>runsById.get(id)?.box||paragraph.box);
  return [Math.min(...boxes.map(b=>b[0])),Math.min(...boxes.map(b=>b[1])),Math.max(...boxes.map(b=>b[2])),Math.max(...boxes.map(b=>b[3]))];
}

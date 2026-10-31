import React,{useEffect,useLayoutEffect,useRef} from 'react';
import {insertText,splitLine,mergeLine} from './paragraphs.mjs';
import {viewportBox,explainReason} from '../session.mjs';
import {sourceTypography,viewportFontScale} from './model.mjs';

export function ParagraphOutlines({paragraphs,viewport,activeId,onChoose}){
  return paragraphs.filter(p=>p.paragraph_id!==activeId).map(p=>{
    const box=viewportBox(p.box,viewport);
    return <button key={p.paragraph_id} type="button" className="paragraph-outline" data-state={p.state}
      style={{position:'absolute',...box}} title={p.state==='not_editable'?explainReason(p.reason):'Edit paragraph'}
      aria-label={p.state==='not_editable'?`Not editable: ${explainReason(p.reason)}`:'Edit paragraph'}
      disabled={p.state==='not_editable'} onClick={event=>onChoose(p,event)}/>;
  });
}

export default function ParagraphEditor({paragraph,lines,runsById,style,viewport,caret,busy,status,onLines,onCommit,onCancel}){
  const root=useRef(null),latest=useRef(),pointer=useRef(null),saved=useRef(null),tops=useRef([]);
  latest.current={lines,runsById,viewport,caret,paragraph,onLines,onCommit};
  const first=runsById.get(paragraph.lines[0][0]);
  const typography=sourceTypography(first||{},style,viewportFontScale(viewport));
  const origin=viewportBox(paragraph.box,viewport);
  // The line DOM is uncontrolled: React never re-renders it, so typing and Enter cannot fight the browser.
  const paint=(next,at)=>{
    const node=root.current,{viewport:vp,paragraph:para,runsById:runs}=latest.current,o=viewportBox(para.box,vp);
    const step=tops.current.length>1&&tops.current[1]!=null&&tops.current[0]!=null?tops.current[1]-tops.current[0]:0;
    for(let k=0;k<next.length;k++)if(tops.current[k]==null)tops.current[k]=k?tops.current[k-1]+(step||node.children[k-1]?.offsetHeight||14):0;
    tops.current.length=next.length;
    node.replaceChildren(...next.map((text,k)=>{
      const div=document.createElement('div');div.dataset.line=k;div.textContent=text;
      Object.assign(div.style,{position:'absolute',left:`${leftOf(k)}px`,top:`${tops.current[k]}px`,whiteSpace:'pre',minHeight:'1em'});
      return div;
    }));
    if(at)place(node,at);
    function leftOf(k){const b=viewportBox(lineBox(para,Math.min(k,para.lines.length-1),runs),vp);return b.left-o.left;}
  };
  const read=()=>[...root.current.children].map(div=>div.textContent.replace(/\u00a0/g,' '));
  const where=()=>{
    const sel=getSelection();if(!sel.rangeCount||!root.current.contains(sel.anchorNode))return null;
    const div=(sel.anchorNode.nodeType===1?sel.anchorNode:sel.anchorNode.parentNode).closest('[data-line]');if(!div)return null;
    const pre=sel.getRangeAt(0).cloneRange();pre.selectNodeContents(div);pre.setEnd(sel.anchorNode,sel.anchorOffset);
    return {line:[...root.current.children].indexOf(div),offset:pre.toString().length,collapsed:sel.isCollapsed};
  };
  const apply=(edit)=>{const r=edit(read(),where());if(!r)return;
    const at=r.caret.line,idx=r.lines.length-read().length;
    // Keep tops aligned with the structural change; new rows get a position in paint().
    if(idx>0)tops.current.splice(at-idx+1,0,...Array(idx).fill(null));else if(idx<0)tops.current.splice(at+1,-idx);
    paint(r.lines,r.caret);latest.current.onLines(r.lines);};
  useLayoutEffect(()=>{
    const {lines:init,caret:c}=latest.current,{viewport:vp,paragraph:para,runsById:runs}=latest.current,o=viewportBox(para.box,vp);
    tops.current=init.map((_,k)=>k<para.lines.length?viewportBox(lineBox(para,k,runs),vp).top-o.top:null);
    paint(init,null);
    root.current.focus({preventScroll:true});
    place(root.current,{line:c?.line??0,offset:c?.offset??Infinity});
  },[paragraph.paragraph_id]);
  useEffect(()=>{
    const inside=target=>target.closest?.('.floating-text-tools')?'toolbar':root.current?.contains(target)?'editor':'outside';
    const down=event=>{
      pointer.current=inside(event.target);
      if(pointer.current==='outside'&&document.activeElement===root.current)latest.current.onCommit();
    };
    const up=event=>{
      if(pointer.current==='toolbar'&&event.target.closest?.('button'))setTimeout(()=>{
        if(!root.current)return;root.current.focus({preventScroll:true});
        const r=saved.current,sel=getSelection();if(r){sel.removeAllRanges();sel.addRange(r);}
      },0);
      setTimeout(()=>{pointer.current=null;},0);
    };
    document.addEventListener('pointerdown',down,true);document.addEventListener('pointerup',up,true);
    return()=>{document.removeEventListener('pointerdown',down,true);document.removeEventListener('pointerup',up,true);};
  },[]);
  return <div ref={root} className="paragraph-editor" data-status={status==='saving'?'saving':status?.refused?'refused':'editing'}
    contentEditable={!busy} suppressContentEditableWarning role="textbox" aria-multiline="true" aria-label="Edit paragraph on page" spellCheck={false}
    style={{position:'absolute',...origin,...typography}}
    onInput={()=>latest.current.onLines(read())}
    onPaste={event=>{event.preventDefault();const text=event.clipboardData.getData('text/plain');apply((cur,w)=>{if(!w)return null;return insertText(cur,w.line,w.offset,text);});}}
    onKeyDown={event=>{
      if(event.key==='Escape'){event.preventDefault();onCancel();}
      else if(event.key==='Tab'){event.preventDefault();onCommit();}
      else if(event.key==='Enter'&&!event.nativeEvent.isComposing){event.preventDefault();
        if(!getSelection().isCollapsed)getSelection().deleteFromDocument();
        apply((cur,w)=>w&&splitLine(cur,w.line,w.offset));}
      else if(event.key==='Backspace'){const w=where();if(w?.collapsed&&w.offset===0&&w.line>0){event.preventDefault();apply((cur,w2)=>mergeLine(cur,w2.line));}}
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

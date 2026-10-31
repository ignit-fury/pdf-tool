import React,{useLayoutEffect,useRef} from 'react';
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
  const root=useRef(null);
  const first=runsById.get(paragraph.lines[0][0]);
  const typography=sourceTypography(first,style,viewportFontScale(viewport));
  useLayoutEffect(()=>{
    const node=root.current;if(!node)return;
    node.focus({preventScroll:true});
    const target=node.children[caret?.line??0]?.firstChild;
    if(target){const range=document.createRange();range.setStart(target,Math.min(caret?.offset??target.length,target.length));range.collapse(true);const sel=getSelection();sel.removeAllRanges();sel.addRange(range);}
  },[paragraph.paragraph_id]);
  const read=()=>[...root.current.children].map(div=>div.textContent.replace(/ /g,' '));
  const origin=viewportBox(paragraph.box,viewport);
  const boxes=lines.map((_,i)=>i<paragraph.lines.length?viewportBox(lineBox(paragraph,i,runsById),viewport):null);
  const lastIndex=Math.min(lines.length,paragraph.lines.length)-1,last=boxes[lastIndex];
  return <div ref={root} className="paragraph-editor" data-status={status==='saving'?'saving':status?.refused?'refused':'editing'}
    contentEditable={!busy} suppressContentEditableWarning role="textbox" aria-multiline="true" aria-label="Edit paragraph on page" spellCheck={false}
    style={{position:'absolute',...origin,...typography}}
    onInput={()=>onLines(read())}
    onKeyDown={event=>{if(event.key==='Escape'){event.preventDefault();onCancel();}if(event.key==='Tab'){event.preventDefault();onCommit();}}}
    onBlur={event=>{if(!event.currentTarget.contains(event.relatedTarget)&&!event.relatedTarget?.closest?.('.floating-text-tools'))onCommit();}}>
    {lines.map((line,i)=>{
      // Lines added by Enter have no source box: stack them below the last source line.
      const box=boxes[i]||{left:last.left,top:last.top+last.height*(i-lastIndex)};
      return <div key={i} data-line={i} style={{position:'absolute',left:box.left-origin.left,top:box.top-origin.top,whiteSpace:'pre'}}>{line}</div>;
    })}
  </div>;
}

function lineBox(paragraph,index,runsById){
  const ids=paragraph.lines[index]||paragraph.lines.at(-1),boxes=ids.map(id=>runsById.get(id).box);
  return [Math.min(...boxes.map(b=>b[0])),Math.min(...boxes.map(b=>b[1])),Math.max(...boxes.map(b=>b[2])),Math.max(...boxes.map(b=>b[3]))];
}

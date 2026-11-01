/** Paragraph drafts: one string per original PDF line, matching engine.paragraph_edit. */
export function effectiveLines(paragraph,runsById,recipe){
  const overrides=new Map(recipe.map(op=>[op.run_id,op.new_text]));
  // Gap spaces follow the previous run's text, as engine.paragraph_edit.line_segments does.
  return paragraph.lines.map(ids=>{
    let line='',prev=null;
    for(const id of ids){
      const text=overrides.get(id)??runsById.get(id)?.text??'';
      if(prev!==null&&!prev.endsWith(' ')&&!text.startsWith(' ')) line+=' ';
      line+=text;
      prev=text;
    }
    return line;
  });
}
export function paragraphAt(paragraphs,{x,y}){
  return paragraphs.find(p=>x>=p.box[0]&&x<=p.box[2]&&y>=p.box[1]&&y<=p.box[3])||null;
}
export function draftChanged(paragraph,lines,runsById,recipe){
  const before=effectiveLines(paragraph,runsById,recipe);
  return before.length!==lines.length||before.some((line,i)=>line!==lines[i]);
}
export function paragraphPayload({paragraph,lines,style,recipe,rect,runsById}){
  return {operation:'replace-paragraph',paragraph_id:paragraph.paragraph_id,source_run_ids:paragraph.lines.flat(),
    page_index:paragraph.page_index,lines:[...lines],style:{...style},
    recipe:structuredClone(recipe),rect:{...rect},allow_rebuild:true,
    run_styles:Object.fromEntries(paragraph.lines.flat().map(id=>[id,runStyle(runsById.get(id))]))};
}
// Each source run's own look, so a rebuild keeps per-word styles (engine.paragraph_edit.styled_runs).
// Size is the visual size in page points (font_display_size), since the rebuilt box is drawn in points.
export function runStyle(run){
  const family=run?.suggested_font_family||(/Times|Serif|Roman/i.test(run?.source_font||'')?'Serif':/Courier|Mono/i.test(run?.source_font||'')?'Mono':'Sans');
  return {font_family:family,bold:!!run?.bold,italic:!!run?.italic,font_size:run?.font_display_size??run?.font_size??12,...(run?.color?{color:[...run.color]}:{})};
}

// Pure line edits for the contenteditable paragraph editor. Each returns {lines, caret:{line,offset}}.
export function insertText(lines,line,offset,text){
  const parts=String(text).split(/\r\n|\r|\n/),cur=lines[line]??'',head=cur.slice(0,offset)+parts[0],last=parts.at(-1);
  const tail=parts.length>1?last:head;
  const mid=parts.length>1?[head,...parts.slice(1,-1),last+cur.slice(offset)]:[head+cur.slice(offset)];
  return {lines:[...lines.slice(0,line),...mid,...lines.slice(line+1)],caret:{line:line+parts.length-1,offset:tail.length}};
}
export const splitLine=(lines,line,offset)=>insertText(lines,line,offset,'\n');
export function mergeLine(lines,line){
  if(line<=0||line>=lines.length)return {lines,caret:{line,offset:0}};
  const offset=lines[line-1].length;
  return {lines:[...lines.slice(0,line-1),lines[line-1]+lines[line],...lines.slice(line+1)],caret:{line:line-1,offset}};
}

// Remove the text between two {line,offset} positions (start before end), joining the end lines.
export function deleteRange(lines,start,end){
  const head=lines[start.line].slice(0,start.offset),tail=lines[end.line].slice(end.offset);
  return {lines:[...lines.slice(0,start.line),head+tail,...lines.slice(end.line+1)],caret:{...start}};
}
// Line tops after an edit: source layout when the count matches the source, else lines after editIndex restack by step.
export function layoutTops(current,source,step,count,editIndex){
  if(count===source.length)return [...source];
  const out=[];
  for(let i=0;i<count;i++)out.push(i===0?(current[0]??source[0]??0):i<=editIndex&&current[i]!=null?current[i]:out[i-1]+step);
  return out;
}
// Keep a rebuild rect inside the visible page (as sourceTextBox did); geometry is localMetadata.pages[i].
export function clampRect(rect,{visibleWidth:w,visibleHeight:h}){
  const left=Math.min(Math.max(0,rect.left),w-1),top=Math.min(Math.max(0,rect.top),h-1);
  return {left,top,width:Math.min(Math.max(1,rect.width),w-left),height:Math.min(Math.max(1,rect.height),h-top)};
}

/** Paragraph drafts: one string per original PDF line, matching engine.paragraph_edit. */
export function effectiveLines(paragraph,runsById,recipe){
  const overrides=new Map(recipe.map(op=>[op.run_id,op.new_text]));
  return paragraph.lines.map(ids=>ids.reduce((line,id)=>{
    const text=overrides.get(id)??runsById.get(id)?.text??'';
    return line&&!line.endsWith(' ')&&!text.startsWith(' ')?`${line} ${text}`:line+text;
  },''));
}
export function paragraphAt(paragraphs,{x,y}){
  return paragraphs.find(p=>x>=p.box[0]&&x<=p.box[2]&&y>=p.box[1]&&y<=p.box[3])||null;
}
export function draftChanged(paragraph,lines,runsById,recipe){
  const before=effectiveLines(paragraph,runsById,recipe);
  return before.length!==lines.length||before.some((line,i)=>line!==lines[i]);
}
export function paragraphPayload({paragraph,lines,style,recipe,rect,allowRebuild,runsById}){
  const first=runsById.get(paragraph.lines[0][0]);
  const family=style.font_family||first?.suggested_font_family;
  return {operation:'replace-paragraph',paragraph_id:paragraph.paragraph_id,source_run_ids:paragraph.lines.flat(),
    page_index:paragraph.page_index,lines:[...lines],style:{...style,...(allowRebuild&&family?{font_family:family}:{})},
    recipe:structuredClone(recipe),rect:{...rect},allow_rebuild:!!allowRebuild,
    run_styles:Object.fromEntries(paragraph.lines.flat().map(id=>[id,runStyle(runsById.get(id))]))};
}
// Each source run's own look, so a rebuild keeps per-word styles (engine.paragraph_edit.styled_runs).
// Size is the visual size in page points (font_display_size), since the rebuilt box is drawn in points.
export function runStyle(run){
  const family=run?.suggested_font_family||(/Times|Serif|Roman/i.test(run?.source_font||'')?'Serif':/Courier|Mono/i.test(run?.source_font||'')?'Mono':'Sans');
  return {font_family:family,bold:!!run?.bold,italic:!!run?.italic,font_size:run?.font_display_size??run?.font_size??12,...(run?.color?{color:[...run.color]}:{})};
}

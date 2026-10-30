export const DEFAULT_STYLE=Object.freeze({font_family:'Sans',font_size:12,bold:false,italic:false,color:Object.freeze([0,0,0]),character_spacing:0,line_spacing:1.2,paragraph_spacing:0,alignment:'left'});
export function newTextBox(page_index,geometry,point={left:40,top:40}){
  const width=Math.min(240,geometry.visibleWidth),height=Math.min(120,geometry.visibleHeight);
  return {page_index,text:'',rect:{left:Math.max(0,Math.min(geometry.visibleWidth-width,point.left)),top:Math.max(0,Math.min(geometry.visibleHeight-height,point.top)),width,height},style:structuredClone(DEFAULT_STYLE),allow_overlap:false,auto_expand:true};
}
export function textBoxPayload(draft){return {operation:draft.source_run_id||draft.source_run_ids?'replace-source':'upsert',...(draft.source_run_ids?{source_run_ids:[...draft.source_run_ids],recipe:structuredClone(draft.recipe)}:draft.source_run_id?{source_run_id:draft.source_run_id,recipe:structuredClone(draft.recipe)}:{}),auto_expand:draft.auto_expand!==false,page_index:draft.page_index,...(draft.id?{id:draft.id}:{}),text:draft.text,rect:{left:draft.rect.left,top:draft.rect.top,width:draft.rect.width,height:draft.rect.height},style:{...DEFAULT_STYLE,...draft.style},allow_overlap:!!draft.allow_overlap};}
export function draftError(draft,geometry){
  if(!draft?.text?.length)return 'Enter the text to insert.';
  if(Array.from(draft.text).length>10000)return 'A text box supports at most 10,000 characters.';
  const r=draft.rect,s=draft.style;
  if(!geometry||!Object.values(r).every(Number.isFinite)||r.left<0||r.top<0||r.width<=0||r.height<=0||r.left+r.width>geometry.visibleWidth||r.top+r.height>geometry.visibleHeight)return 'Keep this text box entirely inside the visible page.';
  if(!Number.isFinite(s.font_size)||s.font_size<1||s.font_size>512||!Number.isFinite(s.character_spacing)||s.character_spacing<0||s.character_spacing>10||!Number.isFinite(s.line_spacing)||s.line_spacing<1||s.line_spacing>3||!Number.isFinite(s.paragraph_spacing)||s.paragraph_spacing<0||s.paragraph_spacing>144)return 'Check font size and spacing limits.';
  return null;
}
export function expandTextBox(draft,required,geometry){
  const height=Math.ceil(required*100)/100;
  return Number.isFinite(height)&&height>0&&draft.rect.top+height<=geometry.visibleHeight?{...draft,rect:{...draft.rect,height}}:null;
}
export function explainTextBoxError(error){
  const messages={TEXT_BOX_RESPONSE_INVALID:'The text box response could not be verified. No change was applied.',TEXT_BOX_OVERLAP:'This area contains visible content or an annotation. Move or resize the box, or explicitly allow transparent overlap.',TEXT_BOX_UNSUPPORTED_TEXT:'This text needs glyphs or shaping the bundled font cannot safely represent. Try another font or simpler text.',TEXT_BOX_SOURCE_UNSAFE:'The original text cannot be removed safely through the content-stream writer. Your PDF is unchanged; keep this run in Preserve layout or choose another text run.',TEXT_BOX_UNSAFE:'This PDF or saved text box cannot be changed safely. Try another page or create a new box.',TEXT_BOX_NOT_FOUND:'That saved text box no longer matches this PDF. Load the text boxes again.',TEXT_BOX_LIMIT:'This operation exceeds a document or text-box limit. Use a smaller box or document.',TEXT_BOX_OUTPUT_LIMIT:'The prepared PDF exceeds the output limit. Your current document is unchanged.',INVALID_TEXT_BOX:'Check text, size, position, font and spacing before previewing.',SIGNATURE_ACKNOWLEDGEMENT_REQUIRED:'Acknowledge the signature warning before changing this document.',EXPORT_LIMIT:'This preview exceeds the browser memory limit. Use a smaller PDF or reopen the current PDF to release Undo memory.',WORKER_TIMEOUT:'The preview took too long. Try a smaller document or text box.'};
  return messages[error?.code]||'The text box could not be prepared. Your current PDF is unchanged.';
}

export function sourceTextBox({run,text,style,recipe,geometry,box,typography,caret}){
  const family=style.font_family||run.suggested_font_family||(/Times|Serif|Roman/i.test(run.source_font||'')?'Serif':/Courier|Mono/i.test(run.source_font||'')?'Mono':'Sans');
  const left=Math.max(0,box.left),top=Math.max(0,box.top),width=geometry.visibleWidth-left,height=Math.min(Math.max(box.height,typography.fontSize*1.3),geometry.visibleHeight-top);
  const normalize=value=>value.replace(/\r\n?/g,'\n').replace(/[\v\f\u0085\u2028\u2029]/g,'\n').replace(/\t/g,'    ');
  return {...(caret?{caret:{start:normalize(text.slice(0,caret.start)).length,end:normalize(text.slice(0,caret.end)).length}}:{}),...(run.source_run_ids?{source_run_ids:[...run.source_run_ids],source_sizes:run.source_sizes? [...run.source_sizes]:undefined}:{source_run_id:run.run_id}),source_font:run.source_font,recipe:structuredClone(recipe),page_index:run.pageNumber-1,text:text.replace(/\r\n?/g,'\n').replace(/[\v\f\u0085\u2028\u2029]/g,'\n').replace(/\t/g,'    '),rect:{left,top,width,height},auto_expand:true,allow_overlap:false,
    style:{...structuredClone(DEFAULT_STYLE),font_family:family,font_size:typography.fontSize,bold:style.bold??!!run.bold,italic:style.italic??!!run.italic,color:style.color??run.color??[0,0,0],character_spacing:typography.letterSpacing||0}};
}

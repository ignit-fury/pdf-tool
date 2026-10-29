export const DEFAULT_STYLE=Object.freeze({font_family:'Sans',font_size:12,bold:false,italic:false,color:Object.freeze([0,0,0]),character_spacing:0,line_spacing:1.2,paragraph_spacing:0,alignment:'left'});
export function newTextBox(page_index,geometry,point={left:40,top:40}){
  const width=Math.min(240,geometry.visibleWidth),height=Math.min(120,geometry.visibleHeight);
  return {page_index,text:'',rect:{left:Math.max(0,Math.min(geometry.visibleWidth-width,point.left)),top:Math.max(0,Math.min(geometry.visibleHeight-height,point.top)),width,height},style:structuredClone(DEFAULT_STYLE),allow_overlap:false};
}
export function textBoxPayload(draft){return {operation:'upsert',page_index:draft.page_index,...(draft.id?{id:draft.id}:{}),text:draft.text,rect:{left:draft.rect.left,top:draft.rect.top,width:draft.rect.width,height:draft.rect.height},style:{...DEFAULT_STYLE,...draft.style},allow_overlap:!!draft.allow_overlap};}
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
  const messages={TEXT_BOX_RESPONSE_INVALID:'The text box response could not be verified. No change was applied.',TEXT_BOX_OVERLAP:'This area contains visible content or an annotation. Move or resize the box, or explicitly allow transparent overlap.',TEXT_BOX_UNSUPPORTED_TEXT:'This text needs glyphs or shaping the bundled font cannot safely represent. Try another font or simpler text.',TEXT_BOX_UNSAFE:'This PDF or saved text box cannot be changed safely. Try another page or create a new box.',TEXT_BOX_NOT_FOUND:'That saved text box no longer matches this PDF. Load the text boxes again.',TEXT_BOX_LIMIT:'This operation exceeds a document or text-box limit. Use a smaller box or document.',TEXT_BOX_OUTPUT_LIMIT:'The prepared PDF exceeds the output limit. Your current document is unchanged.',INVALID_TEXT_BOX:'Check text, size, position, font and spacing before previewing.',SIGNATURE_ACKNOWLEDGEMENT_REQUIRED:'Acknowledge the signature warning before changing this document.',EXPORT_LIMIT:'This preview exceeds the browser memory limit. Use a smaller PDF or reopen the current PDF to release Undo memory.',WORKER_TIMEOUT:'The preview took too long. Try a smaller document or text box.'};
  return messages[error?.code]||'The text box could not be prepared. Your current PDF is unchanged.';
}

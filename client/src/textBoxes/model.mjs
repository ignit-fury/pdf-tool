export const DEFAULT_STYLE=Object.freeze({font_family:'Sans',font_size:12,bold:false,italic:false,color:Object.freeze([0,0,0]),character_spacing:0,line_spacing:1.2,paragraph_spacing:0,alignment:'left'});
// The overlay's browser fonts, metric-compatible with the bundled Liberation families.
export const FONT_STACKS=Object.freeze({Sans:'Arial,sans-serif',Serif:'"Times New Roman",serif',Mono:'"Courier New",monospace'});
const clamp=(value,lo,hi)=>Math.max(lo,Math.min(hi,value));
// New text starts the size of a short word, top-left at the click, kept inside the visible page.
export function wordRect(geometry,point,style=DEFAULT_STYLE){
  const width=Math.min(2*style.font_size,geometry.visibleWidth),height=Math.min(style.font_size*style.line_spacing,geometry.visibleHeight);
  return {left:clamp(point.left,0,geometry.visibleWidth-width),top:clamp(point.top,0,geometry.visibleHeight-height),width,height};
}
export function newTextBox(page_index,geometry,point={left:40,top:40}){
  const style=structuredClone(DEFAULT_STYLE);
  return {page_index,text:'',rect:wordRect(geometry,point,style),style,allow_overlap:false,auto_expand:true};
}
const slack=width=>width*1.03+2;
/** Grow a box to its text: width follows the longest measured line (pt) until the visible page's right
 * edge, then lines soft-wrap and height grows by lines. An existing box passes fixed: its saved width is
 * kept (its wrapping must not reflow on open) and only its height grows, never below the saved height. */
export function fitTextRect(rect,widths,style,geometry,fixed=null){
  const maxWidth=Math.max(1,geometry.visibleWidth-rect.left),line=style.font_size*style.line_spacing;
  const width=Math.min(maxWidth,fixed?fixed.width:Math.max(2*style.font_size,...widths.map(slack)));
  const rows=widths.reduce((sum,w)=>sum+Math.max(1,Math.ceil(slack(w)/width-1e-9)),0);
  // paragraph_spacing is not drawn by the typing textarea; it is counted here and server auto_expand covers any shortfall.
  const height=Math.min(geometry.visibleHeight-rect.top,Math.max(fixed?.height||0,rows*line+style.paragraph_spacing*(widths.length-1)));
  return {left:rect.left,top:rect.top,width,height};
}
let canvas;
// Browser only: unwrapped width in points of each typed line (a px font size at scale 1 is points).
export function measureLineWidths(text,style){
  canvas??=document.createElement('canvas');const context=canvas.getContext('2d');
  context.fontKerning='none'; // the server lays text out with unkerned advances
  context.font=`${style.italic?'italic ':''}${style.bold?'700 ':''}${style.font_size}px ${FONT_STACKS[style.font_family]||FONT_STACKS.Sans}`;
  return text.split('\n').map(line=>context.measureText(line).width+(style.character_spacing||0)*Array.from(line).length);
}
/** On open, decide per box. If every hard line of the saved text fits the saved width (with slack),
 * the box sat at its natural width: return null so it keeps growing in width like a new draft.
 * Otherwise its text soft-wraps inside that width (e.g. a paragraph rebuild): hold the width, grow height. */
export function fixedOnOpen(rect,widths){
  return widths.every(w=>slack(w)<=rect.width+0.5)?null:{width:rect.width,height:rect.height}; // 0.5pt: font rounding
}
export function growTextBox(draft,geometry,widths=measureLineWidths(draft.text,draft.style)){
  return {...draft,rect:fitTextRect(draft.rect,widths,draft.style,geometry,draft.fixed)};
}
// What a click-away save compares against: moving a box (rect) is a change, like its text or style.
export const draftSignature=draft=>JSON.stringify([draft.text,draft.style,draft.rect]);
/** A click on free space while a refused draft with text is open on that page moves the draft there
 * (keeping the typed text, so the next click-away retries) instead of starting new text. */
export function relocateRefused(draft,page_index,point,geometry){
  if(!draft?.status?.refused||!draft.text.trim()||draft.page_index!==page_index||draft.readOnly)return null;
  return {...draft,rect:{...draft.rect,left:clamp(point.left,0,geometry.visibleWidth-draft.rect.width),top:clamp(point.top,0,geometry.visibleHeight-draft.rect.height)}};
}
export function textBoxPayload(draft){return {operation:draft.source_run_id||draft.source_run_ids?'replace-source':'upsert',...(draft.source_run_ids?{source_run_ids:[...draft.source_run_ids],recipe:structuredClone(draft.recipe)}:draft.source_run_id?{source_run_id:draft.source_run_id,recipe:structuredClone(draft.recipe)}:{}),auto_expand:draft.auto_expand!==false,page_index:draft.page_index,...(draft.id?{id:draft.id}:{}),text:draft.text,rect:{left:draft.rect.left,top:draft.rect.top,width:draft.rect.width,height:draft.rect.height},style:{...DEFAULT_STYLE,...draft.style},allow_overlap:!!draft.allow_overlap};}
export function draftError(draft,geometry){
  if(!draft?.text?.length)return 'Enter the text to insert.';
  if(Array.from(draft.text).length>10000)return 'A text box supports at most 10,000 characters.';
  const r=draft.rect,s=draft.style;
  if(!geometry||!Object.values(r).every(Number.isFinite)||r.left<0||r.top<0||r.width<=0||r.height<=0||r.left+r.width>geometry.visibleWidth||r.top+r.height>geometry.visibleHeight)return 'Keep this text box entirely inside the visible page.';
  if(!Number.isFinite(s.font_size)||s.font_size<1||s.font_size>512||('initial_font_size' in s&&(!Number.isFinite(s.initial_font_size)||s.initial_font_size<1||s.initial_font_size>512))||!Number.isFinite(s.character_spacing)||s.character_spacing<0||s.character_spacing>10||!Number.isFinite(s.line_spacing)||s.line_spacing<1||s.line_spacing>3||!Number.isFinite(s.paragraph_spacing)||s.paragraph_spacing<0||s.paragraph_spacing>144)return 'Check font size and spacing limits.';
  return null;
}
export function expandTextBox(draft,required,geometry){
  const height=Math.ceil(required*100)/100;
  return Number.isFinite(height)&&height>0&&draft.rect.top+height<=geometry.visibleHeight?{...draft,rect:{...draft.rect,height}}:null;
}
export function explainTextBoxError(error){
  const messages={TEXT_BOX_RESPONSE_INVALID:'The text box response could not be verified. No change was applied.',TEXT_BOX_OVERLAP:'This area contains visible content or an annotation. Move or resize the box, or explicitly allow transparent overlap.',TEXT_BOX_UNSUPPORTED_TEXT:'This text needs glyphs or shaping the bundled font cannot safely represent. Try another font or simpler text.',TEXT_BOX_SOURCE_UNSAFE:'The original text cannot be removed safely through the content-stream writer. Your PDF is unchanged; keep this run in Preserve layout or choose another text run.',TEXT_BOX_UNSAFE:'This PDF or saved text box cannot be changed safely. Try another page or create a new box.',TEXT_BOX_NOT_FOUND:'That saved text box no longer matches this PDF. Load the text boxes again.',TEXT_BOX_LIMIT:'This operation exceeds a document or text-box limit. Use a smaller box or document.',TEXT_BOX_OUTPUT_LIMIT:'The prepared PDF exceeds the output limit. Your current document is unchanged.',INVALID_TEXT_BOX:'Check text, size, position, font and spacing before previewing.',SIGNATURE_ACKNOWLEDGEMENT_REQUIRED:'Acknowledge the signature warning before changing this document.',EXPORT_LIMIT:'This preview exceeds the browser memory limit. Use a smaller PDF or reopen the current PDF to release Undo memory.',PUSH_DOWN_PAGE_FULL:'Not enough room on this page for the longer text. Shorten it, or move content to another page.',PUSH_DOWN_STRADDLE:"Content beside this paragraph can't be moved down. Shorten the text to fit.",PUSH_DOWN_MANAGED_IMAGE:'An inserted image below would have to move. Move the image first, or shorten the text.',PUSH_DOWN_UNSUPPORTED:"This page's layout can't be moved safely (for example, it has columns). Shorten the text to fit.",WORKER_TIMEOUT:'The preview took too long. Try a smaller document or text box.'};
  return messages[error?.code]||'The text box could not be prepared. Your current PDF is unchanged.';
}
// Inline new text can be moved, so overlap advice says where to put it rather than to shorten.
export function explainInsertError(error){
  if(error?.code==='TEXT_BOX_OVERLAP')return 'This text would cover other content on the page. Click somewhere with free space, or move it.';
  if(error?.code==='TEXT_BOX_OVERFLOW')return 'This text runs past the bottom of the page. Shorten it, or move it higher.';
  return explainTextBoxError(error);
}
// A paragraph's rebuilt box has no move, resize or overlap controls: only shortening helps.
export function explainParagraphError(error){
  return error?.code==='TEXT_BOX_OVERLAP'?'The longer text would cover other content on this page (for example a shaded area or a frame). Shorten the text to fit.':explainTextBoxError(error);
}

export function sourceTextBox({run,text,style,recipe,geometry,box,typography,caret}){
  const family=style.font_family||run.suggested_font_family||(/Times|Serif|Roman/i.test(run.source_font||'')?'Serif':/Courier|Mono/i.test(run.source_font||'')?'Mono':'Sans');
  const left=Math.max(0,box.left),top=Math.max(0,box.top),width=geometry.visibleWidth-left,height=Math.min(Math.max(box.height,typography.fontSize*1.3),geometry.visibleHeight-top);
  const normalize=value=>value.replace(/\r\n?/g,'\n').replace(/[\v\f\u0085\u2028\u2029]/g,'\n').replace(/\t/g,'    ');
  return {...(caret?{caret:{start:normalize(text.slice(0,caret.start)).length,end:normalize(text.slice(0,caret.end)).length}}:{}),...(run.source_run_ids?{source_run_ids:[...run.source_run_ids],source_sizes:run.source_sizes? [...run.source_sizes]:undefined}:{source_run_id:run.run_id}),source_font:run.source_font,recipe:structuredClone(recipe),page_index:run.pageNumber-1,text:text.replace(/\r\n?/g,'\n').replace(/[\v\f\u0085\u2028\u2029]/g,'\n').replace(/\t/g,'    '),rect:{left,top,width,height},auto_expand:true,allow_overlap:false,
    style:{...structuredClone(DEFAULT_STYLE),font_family:family,font_size:typography.fontSize,...(run.source_run_ids&&run.source_sizes?.every(Number.isFinite)?{initial_font_size:run.source_sizes[0]}:{}),bold:style.bold??!!run.bold,italic:style.italic??!!run.italic,color:style.color??run.color??[0,0,0],character_spacing:typography.letterSpacing||0}};
}

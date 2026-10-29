import {viewportBox} from '../session.mjs';

export function pageSize(geometry,scale=1) {
  return {width:(geometry?.visibleWidth||612)*scale,height:(geometry?.visibleHeight||792)*scale};
}
export function inlineBox(box,viewport) {
  if(!Array.isArray(box)||box.length!==4||!box.every(Number.isFinite))return null;
  const result=viewportBox(box,viewport);
  if(result.width<=0||result.height<=0||!Object.values(result).every(Number.isFinite))return null;
  return result;
}
export const colorHex=color=>Array.isArray(color)&&color.length===3&&color.every(v=>Number.isFinite(v)&&v>=0&&v<=1)?`#${color.map(v=>Math.round(v*255).toString(16).padStart(2,'0')).join('')}`:'#000000';
export const viewportFontScale=viewport=>viewport.transform?Math.hypot(viewport.transform[2],viewport.transform[3]):viewport.scale;
export function sourceTypography(run,style={},scale=1) {
  const family=style.font_family||run.suggested_font_family||(/Times|Serif|Roman/i.test(run.source_font||'')?'Serif':/Courier|Mono/i.test(run.source_font||'')?'Mono':'Sans');
  return {fontFamily:{Serif:'"Times New Roman",serif',Mono:'"Courier New",monospace',Sans:'Arial,sans-serif'}[family],
    fontSize:(style.font_size||run.font_size||12)*((run.font_display_size||run.font_size||12)/(run.font_size||12))*scale,fontWeight:(style.bold??run.bold)?700:400,
    fontStyle:(style.italic??run.italic)?'italic':'normal',color:colorHex(style.color??run.color),
    letterSpacing:(style.character_spacing??run.character_spacing??0)*((run.font_display_size||run.font_size||12)/(run.font_size||12))*scale};
}
export function draftProblem(text) {
  if(Array.from(text).length>10000)return 'A text run supports at most 10,000 characters. Use a shorter edit.';
  if(/[\r\n\t\v\f\u0085\u2028\u2029]/.test(text))return 'This source text run cannot safely wrap or contain line breaks or tabs. Keep this edit on one line, choose a smaller font, or edit a structured source document for reflow.';
  return null;
}
export function historyTransition({past,future,current},direction) {
  if(direction==='undo')return past.length?{target:past.at(-1),past:past.slice(0,-1),future:[...future,current]}:null;
  if(direction==='redo')return future.length?{target:future.at(-1),past:[...past,current],future:future.slice(0,-1)}:null;
  return null;
}
export function moveImageRect(rect,dx,dy,page,kind='move',locked=true) {
  const w=page.visibleWidth,h=page.visibleHeight;
  if(kind==='move')return {...rect,left:Math.max(0,Math.min(w-rect.width,rect.left+dx)),top:Math.max(0,Math.min(h-rect.height,rect.top+dy))};
  let width=Math.max(1,Math.min(w-rect.left,rect.width+dx)),height=Math.max(1,Math.min(h-rect.top,rect.height+dy));
  if(locked){height=width/(rect.width/rect.height);if(height>h-rect.top){height=h-rect.top;width=height*(rect.width/rect.height);}}
  return {...rect,width,height};
}

import {viewportBox} from '../session.mjs';

export function pageSize(geometry,scale=1) {
  return {width:(geometry?.visibleWidth||612)*scale,height:(geometry?.visibleHeight||792)*scale};
}
export function visibleDocumentPage(pages,top,bottom){
  return pages.map(page=>({...page,visible:Math.max(0,Math.min(bottom,page.bottom)-Math.max(top,page.top))}))
    .filter(page=>page.visible>0).sort((a,b)=>b.visible-a.visible||Math.abs(a.top-top)-Math.abs(b.top-top))[0]?.number;
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
  if(/[\r\n\t\v\f\u0085\u2028\u2029]/.test(text))return 'Line breaks and tabs need Flexible text box. Choose Expand text box to wrap and grow within free page space.';
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
  // Resize from a handle: kind is a compass direction (n, se, w, …); 'resize' is the legacy corner.
  const k=kind==='resize'?'se':kind,l=rect.left,t=rect.top,r=rect.left+rect.width,b=rect.top+rect.height;
  let left=l,top=t,right=r,bottom=b;
  if(k.includes('e'))right=Math.min(w,Math.max(l+1,r+dx));
  if(k.includes('w'))left=Math.max(0,Math.min(r-1,l+dx));
  if(k.includes('s'))bottom=Math.min(h,Math.max(t+1,b+dy));
  if(k.includes('n'))top=Math.max(0,Math.min(b-1,t+dy));
  let width=right-left,height=bottom-top;
  if(locked) {
    const ratio=rect.width/rect.height,vertical=!/[ew]/.test(k);
    if(vertical)width=height*ratio;else height=width/ratio;
    const anchorRight=k.includes('w'),anchorBottom=k.includes('n');
    const scale=Math.min(1,(anchorRight?r:w-l)/width,(anchorBottom?b:h-t)/height);
    width*=scale;height*=scale;
    left=anchorRight?r-width:l;top=anchorBottom?b-height:t;
  }
  return {...rect,left,top,width,height};
}

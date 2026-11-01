/** Position contextual controls in CSS pixels, independent of PDF zoom. */
export function placeInlineTools(anchor,width,height,windowWidth,windowHeight){
  const left=Math.max(8,Math.min(anchor.left,windowWidth-width-8));
  const preferred=anchor.top-height-10>=8?anchor.top-height-10:anchor.bottom+10;
  return {left,top:Math.max(8,Math.min(preferred,windowHeight-height-8))};
}

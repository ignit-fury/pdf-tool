const fail=code=>{throw Object.assign(new Error(code),{code});};
/** Match pdf.js/describePage: effective crop ∩ media, with MediaBox fallback. */
function basis(page) {
  const {mediaBox:m,cropBox:c=m,userUnit:u=1}=page??{};
  const rotation=(((page?.rotation??0)%360)+360)%360;
  if(!m||![m,c].every(b=>[b.x,b.y,b.width,b.height].every(Number.isFinite)&&b.width>0&&b.height>0)||!Number.isFinite(u)||u<=0||u>75000||rotation%90)fail('PAGE_GEOMETRY_INVALID');
  let x=Math.max(m.x,c.x),y=Math.max(m.y,c.y),right=Math.min(m.x+m.width,c.x+c.width),top=Math.min(m.y+m.height,c.y+c.height);
  if(right<=x||top<=y){x=m.x;y=m.y;right=x+m.width;top=y+m.height;}
  const w=(right-x)*u,h=(top-y)*u;
  if(![x,y,right,top,w,h].every(Number.isFinite)||w<=0||h<=0)fail('PAGE_GEOMETRY_INVALID');
  return {x,y,right,top,u,rotation,width:rotation%180?h:w,height:rotation%180?w:h};
}
function size(page) {
  if(page?.mediaBox)return basis(page);
  const width=page?.visibleWidth??page?.width,height=page?.visibleHeight??page?.height;
  if(![width,height].every(n=>Number.isFinite(n)&&n>0))fail('PAGE_GEOMETRY_INVALID');
  return {width,height};
}
/** Physical points from the top-left of the visible, rotated page. */
export function fitImage(imageSize,visiblePage) {
  const {width:iw,height:ih}=imageSize??{},page=size(visiblePage);
  if(![iw,ih].every(n=>Number.isFinite(n)&&n>0))fail('IMAGE_SIZE_INVALID');
  const scale=Math.min(page.width/iw,page.height/ih),width=iw*scale,height=ih*scale;
  return {left:(page.width-width)/2,top:(page.height-height)/2,width,height};
}
/** UI owns the explicit checked state; ratio belongs to the decoded image. */
export function updateAspect(rect,field,value,{locked=false,ratio}={}) {
  if(!['left','top','width','height'].includes(field)||!Number.isFinite(value))fail('IMAGE_RECT_INVALID');
  const next={...rect,[field]:value};
  if(locked&&(field==='width'||field==='height')) {
    if(!Number.isFinite(ratio)||ratio<=0)fail('IMAGE_ASPECT_INVALID');
    if(field==='width')next.height=value/ratio;else next.width=value*ratio;
  }
  return next;
}
export function validatePlacement(rect,page) {
  const {width,height}=size(page),{left:l,top:t,width:w,height:h}=rect??{};
  if(![l,t,w,h].every(Number.isFinite)||w<=0||h<=0)return {valid:false,code:'IMAGE_RECT_INVALID'};
  // Arithmetic is bounded as differences so overflow cannot accidentally pass.
  if(l<0||t<0||l>width||t>height||w>width-l||h>height-t)return {valid:false,code:'IMAGE_OUTSIDE_PAGE'};
  return {valid:true};
}
/** Unit image square (bottom-left origin) → PDF user coordinates. This same
 * transform is consumed by the content writer and the draft preview. */
export function placementMatrix(rect,pageGeometry) {
  const b=basis(pageGeometry),validation=validatePlacement(rect,pageGeometry);
  if(!validation.valid)fail(validation.code);
  const inverse=(left,top)=>{
    const l=left/b.u,t=top/b.u;
    switch(b.rotation) {
      case 0:return [b.x+l,b.top-t];
      case 90:return [b.x+t,b.y+l];
      case 180:return [b.right-l,b.y+t];
      case 270:return [b.right-t,b.top-l];
    }
  };
  const {left,top,width,height}=rect,bl=inverse(left,top+height),br=inverse(left+width,top+height),tl=inverse(left,top);
  return [br[0]-bl[0],br[1]-bl[1],tl[0]-bl[0],tl[1]-bl[1],...bl].map(n=>Object.is(n,-0)?0:n);
}

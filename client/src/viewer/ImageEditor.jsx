import React,{useRef,useState} from 'react';
import {moveImageRect} from './model.mjs';

export function ImageHandles({images,selected,geometry,viewport,disabled,onSelect,onChange}) {
  const drag=useRef(null),sx=viewport.width/geometry.visibleWidth,sy=viewport.height/geometry.visibleHeight;
  const pointerDown=(event,kind)=>{
    if(disabled||!selected)return;event.preventDefault();event.stopPropagation();
    event.currentTarget.setPointerCapture(event.pointerId);
    drag.current={x:event.clientX,y:event.clientY,rect:{...selected.rect},kind};
  };
  const pointerMove=event=>{if(!drag.current||disabled)return;onChange({...selected,rect:moveImageRect(drag.current.rect,(event.clientX-drag.current.x)/sx,(event.clientY-drag.current.y)/sy,geometry,drag.current.kind,selected.locked!==false)});};
  const box=item=>({left:item.rect.left*sx,top:item.rect.top*sy,width:item.rect.width*sx,height:item.rect.height*sy,transform:`rotate(${item.rotation||0}deg)`});
  return <div className="image-edit-layer" aria-label="Image edit targets">
    {images.filter(item=>item.id!==selected?.id).map((image,i)=><button key={image.id} className="image-hit-target" disabled={disabled} style={box(image)} aria-label={`Select image ${i+1} on page`} onClick={()=>onSelect(image)}/>)}
    {selected&&<div className="image-selection" style={box(selected)}><button className="image-drag-handle" aria-label="Move selected image" disabled={disabled} onPointerDown={event=>pointerDown(event,'move')} onPointerMove={pointerMove} onPointerUp={()=>drag.current=null} onPointerCancel={()=>drag.current=null} onKeyDown={event=>{if(['ArrowLeft','ArrowRight','ArrowUp','ArrowDown'].includes(event.key)){event.preventDefault();const dx=event.key==='ArrowLeft'?-1:event.key==='ArrowRight'?1:0,dy=event.key==='ArrowUp'?-1:event.key==='ArrowDown'?1:0;onChange({...selected,rect:moveImageRect(selected.rect,dx*(event.shiftKey?10:1),dy*(event.shiftKey?10:1),geometry)});}}}/><button className="image-resize-handle" aria-label="Resize selected image" disabled={disabled} onPointerDown={event=>pointerDown(event,'resize')} onPointerMove={pointerMove} onPointerUp={()=>drag.current=null} onPointerCancel={()=>drag.current=null}/></div>}
  </div>;
}

export default function ImageToolbar({image,newImage,busy,valid,error,onChange,onApply,onCancel,onReplace,onDelete}) {
  const picker=useRef(null),[confirm,setConfirm]=useState(false);
  const ratio=image.pixelWidth&&image.pixelHeight?image.pixelWidth/image.pixelHeight:image.width&&image.height?image.width/image.height:image.rect.width/image.rect.height;
  const update=(field,value)=>{
    const rect={...image.rect,[field]:value};
    if(image.locked!==false){if(field==='width')rect.height=value/ratio;else if(field==='height')rect.width=value*ratio;}
    onChange({...image,rect});
  };
  return <section className="context-toolbar image-toolbar" aria-label="Image formatting"><div className="context-heading"><strong>{newImage?'Insert image':'Selected image'} · Page {image.pageNumber||image.page}</strong><span>In this browser</span></div>
    <fieldset disabled={!!busy}>{['left','top','width','height'].map(field=><label key={field}>{field[0].toUpperCase()+field.slice(1)} (pt)<input type="number" aria-label={`Image ${field}`} min={['width','height'].includes(field)?1:0} step="1" value={Number(image.rect[field].toFixed(2))} onChange={event=>update(field,Number(event.target.value))}/></label>)}
      <label>Rotation<select aria-label="Image rotation" value={image.rotation||0} onChange={event=>onChange({...image,rotation:Number(event.target.value)})}>{[0,90,180,270].map(value=><option key={value} value={value}>{value}°</option>)}</select></label>
      <label className="aspect-lock"><input type="checkbox" checked={image.locked!==false} onChange={event=>onChange({...image,locked:event.target.checked})}/> Lock aspect ratio</label>
    </fieldset>
    <p className="context-guidance">Drag the outline to move; drag its corner to resize. Position and bounds are previewed before Apply. Existing PDF content stays unchanged until then. Original, unowned PDF images cannot be altered safely here.</p>
    {error&&<p className="context-warning" role="status">{error}</p>}
    {!valid&&<p className="context-warning">Keep the entire image within this page. Rotation may require a smaller size.</p>}
    <div className="context-actions"><button className="primary" onClick={onApply} disabled={!!busy||!valid}>Apply image <span className="action-location">Browser</span></button><button onClick={()=>picker.current.click()} disabled={!!busy}>Replace image file</button>{!newImage&&<button onClick={()=>setConfirm(true)} disabled={!!busy}>Remove image</button>}<button onClick={onCancel} disabled={!!busy}>Cancel image changes</button></div>
    {confirm&&<div role="group" aria-label="Confirm image removal"><p>Remove this selected image? Undo can restore it.</p><button onClick={()=>{setConfirm(false);onDelete();}} disabled={!!busy}>Confirm remove image</button><button onClick={()=>setConfirm(false)}>Keep image</button></div>}
    <input ref={picker} type="file" accept="image/png,image/jpeg,image/webp" className="visually-hidden" aria-label="Replace selected image file" onChange={event=>{const file=event.target.files[0];event.target.value='';if(file)onReplace(file);}}/>
  </section>;
}

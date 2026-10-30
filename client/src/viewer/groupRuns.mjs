/** Merge only a separately drawn initial and its touching letter-only tail. */
export function groupedEditTargets(runs, editedIds=new Set()) {
  const result=[];
  for(let i=0;i<runs.length;i++){
    const first=runs[i],next=runs[i+1];
    if(next&&!editedIds.has(first.run_id)&&!editedIds.has(next.run_id)&&
        first.state!=='not_editable'&&next.state!=='not_editable'&&
        !first.text_box_id&&!next.text_box_id&&
        /^\p{L}$/u.test(first.text||'')&&/^\p{L}{2,}$/u.test(next.text||'')&&
        Array.isArray(first.box)&&Array.isArray(next.box)){
      const a=first.box,b=next.box,small=Math.min(a[3]-a[1],b[3]-b[1]);
      const overlap=Math.min(a[3],b[3])-Math.max(a[1],b[1]);
      if(small>0&&overlap>=small*.75&&Math.abs(b[0]-a[2])<=Math.max(.5,small*.03)){
        result.push({...next,run_id:first.run_id,text:first.text+next.text,
          source_run_ids:[first.run_id,next.run_id],
          source_sizes:[first.font_size,next.font_size],
          source_font_reusable:first.source_font_reusable===true&&next.source_font_reusable===true,
          box:[Math.min(a[0],b[0]),Math.min(a[1],b[1]),Math.max(a[2],b[2]),Math.max(a[3],b[3])]});
        i++;continue;
      }
    }
    result.push(first);
  }
  return result;
}

/** Keep each source run's font and size when editing a visually joined word. */
export function splitSourceWord(run,text){
  if(!run?.source_run_ids||run.source_run_ids.length!==2)return [{run_id:run.run_id,new_text:text}];
  const initial=Array.from(text)[0]||'';
  return [{run_id:run.source_run_ids[0],new_text:initial},
    {run_id:run.source_run_ids[1],new_text:text.slice(initial.length)}];
}

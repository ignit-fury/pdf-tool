import {historyTransition} from './model.mjs';

const labels={'blank insertion':'Insert blank page','page rotation':'Rotate page','page move':'Move page',
  'page deletion':'Delete page','text edit':'Edit text','replacements':'Replace text',
  'image placement':'Insert image','image change':'Change image','image removal':'Remove image',
  'image replacement':'Replace image','image page':'Insert image page','PDF merge':'Merge PDF',
  'text insertion':'Insert text box','text box edit':'Edit text box','text box removal':'Remove text box'};
export const historyLabel=action=>labels[action]||'Document change';
export function historyRows(past,future){
  const labelsInOrder=['Original document',...past.map(s=>historyLabel(s.action)),...future.slice().reverse().map(s=>historyLabel(s.action))];
  return labelsInOrder.map((label,position)=>({position,label,status:position===past.length?'current':position<past.length?'applied':'undone'}));
}
/** Reuse one-step action semantics without copying buffers or publishing intermediate states. */
export function historyJump({past,future,current},position){
  if(!Number.isSafeInteger(position)||position<0||position>past.length+future.length||position===past.length)return null;
  const direction=position<past.length?'undo':'redo';let state={past,future,current},target;
  while(state.past.length!==position){
    const source=direction==='undo'?state.past:state.future;
    const previous=Object.freeze({...state.current,action:source.at(-1).action});
    const next=historyTransition({...state,current:previous},direction);
    target=next.target;state={past:next.past,future:next.future,current:target};
  }
  return {target,past:state.past,future:state.future};
}

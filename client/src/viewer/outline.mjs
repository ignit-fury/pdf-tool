const MAX_NODES=1000,MAX_DEPTH=16;
const unavailable=()=>Object.assign(new Error('Bookmark destination is unavailable'),{code:'OUTLINE_DESTINATION_UNAVAILABLE'});
const abort=()=>new DOMException('Document or bookmark selection changed','AbortError');
const title=value=>(typeof value==='string'?value:'').replace(/[\u0000-\u001f\u007f\u202a-\u202e\u2066-\u2069]/g,'').slice(0,256).trim()||'Untitled bookmark';
const reference=value=>value&&typeof value==='object'&&Number.isInteger(value.num)&&value.num>0&&value.num<=2147483647&&Number.isInteger(value.gen)&&value.gen>=0&&value.gen<=65535;
function destination(value){
  if(typeof value==='string')return value.length>0&&value.length<=2048?value:null;
  if(!Array.isArray(value)||value.length<2||!['XYZ','Fit','FitH','FitV','FitR','FitB','FitBH','FitBV'].includes(value[1]?.name))return null;
  const target=value[0];
  if(!reference(target)&&!(Number.isSafeInteger(target)&&target>=0))return null;
  return [reference(target)?{num:target.num,gen:target.gen}:target,{name:value[1].name}];
}
/** Copy only bounded display/internal destination data. No URLs/actions are retained. */
export function normalizeOutline(tree){
  const items=[],seen=new Set();let limited=false,count=0;
  const pending=[];
  const enqueue=(nodes,output,depth)=>{
    if(!Array.isArray(nodes))return;
    const available=Math.max(0,MAX_NODES-count-pending.length);
    if(nodes.length>available)limited=true;
    for(let i=Math.min(nodes.length,available)-1;i>=0;i--)pending.push({node:nodes[i],output,depth});
  };
  enqueue(tree,items,1);
  while(pending.length&&count<MAX_NODES){
    const {node,output,depth}=pending.pop();
    if(!node||typeof node!=='object')continue;
    if(seen.has(node)){limited=true;continue;}seen.add(node);count++;
    const external=!!(node.url||node.unsafeUrl||node.action||node.attachment||node.setOCGState);
    const target=external?null:destination(node.dest);
    const item={id:String(count),title:title(node.title),destination:target,
      reason:target?null:external?'External links and document actions are not opened.':'No supported page destination.',
      bold:node.bold===true,italic:node.italic===true,children:[]};
    output.push(item);
    if(depth<MAX_DEPTH)enqueue(node.items,item.children,depth+1);
    else if(node.items?.length)limited=true;
  }
  return {items,limited};
}
/** Resolve page only; destination zoom/coordinates and all external actions are ignored. */
export async function resolveOutlinePage(pdf,value,isCurrent){
  const check=()=>{if(!isCurrent())throw abort();};
  try{
    check();let target=destination(value);if(target===null)throw unavailable();
    if(typeof target==='string'){target=destination(await pdf.getDestination(target));check();}
    if(!Array.isArray(target))throw unavailable();
    const index=Number.isSafeInteger(target[0])?target[0]:await pdf.getPageIndex(target[0]);check();
    if(!Number.isSafeInteger(index)||index<0||index>=pdf.numPages)throw unavailable();
    return index+1;
  }catch(error){check();if(error.name==='AbortError')throw error;throw unavailable();}
}

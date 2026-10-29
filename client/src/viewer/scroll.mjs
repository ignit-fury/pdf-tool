/** Scroll only the PDF viewport, never outer chrome or other scroll containers. */
export function scrollWithinDocument(root,node,{align='center',behavior='instant'}={}){
  if(!root||!node||!root.contains(node))return;
  const box=root.getBoundingClientRect(),target=node.getBoundingClientRect();
  root.scrollTo({top:root.scrollTop+target.top-box.top-root.clientTop-(align==='start'?24:(root.clientHeight-target.height)/2),
    left:align==='start'?0:root.scrollLeft+target.left-box.left-root.clientLeft-(root.clientWidth-target.width)/2,behavior});
}

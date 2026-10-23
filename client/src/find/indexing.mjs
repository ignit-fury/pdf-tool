// This producer owns progress, not the document's page cache or request lifetime.
// A stopped request may still serve the viewer; only this generation stops consuming it.
export function createIndexingController({fetchPage,onProgress,isCurrent=()=>true}) {
  const completed=new Set(),failed=new Set();
  let total=0,generation=0,disposed=false,status='idle',pending;
  const alive=token=>!disposed&&token===generation&&isCurrent();
  const publish=()=>{if(!disposed&&isCurrent())onProgress({completed:completed.size,completedPages:[...completed].sort((a,b)=>a-b),total,failedPages:[...failed].sort((a,b)=>a-b),status});};
  const run=()=>{
    if(disposed||!isCurrent())return Promise.resolve();
    if(status==='indexing')return pending;
    const token=++generation;status='indexing';publish();
    pending=(async()=>{
      for(let page=1;page<=total;page++){
        if(!alive(token))return;
        if(completed.has(page))continue;
        try{
          await fetchPage(page);
          if(!alive(token))return;
          completed.add(page);failed.delete(page);
        }catch(error){
          if(!alive(token))return;
          failed.add(page);
        }
        publish();
      }
      if(alive(token)){status=completed.size===total?'complete':'failed';publish();}
    })();
    return pending;
  };
  return {
    start(pageCount){
      if(!Number.isInteger(pageCount)||pageCount<1)throw new RangeError('Invalid page count');
      total=pageCount;return run();
    },
    resume:run,
    stop(){if(disposed||status!=='indexing')return;generation++;status='stopped';publish();},
    dispose(){disposed=true;generation++;},
  };
}

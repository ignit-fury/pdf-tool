import React,{useEffect,useRef} from 'react';
import {historyRows} from './history.mjs';

export default function HistoryPanel({past,future,busy,error,onRestore}){
  const heading=useRef(null),active=useRef(null),rows=historyRows(past,future);
  useEffect(()=>{heading.current?.focus();},[]);
  useEffect(()=>{heading.current?.focus({preventScroll:true});active.current?.scrollIntoView({block:'nearest',behavior:'instant'});},[past.length,future.length]);
  return <section className="navigation-panel" aria-label="Document history" aria-busy={!!busy}>
    <h2 ref={heading} tabIndex={-1}>History <span className="location">Browser</span></h2>
    <p className="navigation-guidance">{past.length} applied {past.length===1?'change':'changes'} · {future.length} available to redo. Choose a state to restore its exact PDF.</p>
    <p className="navigation-guidance">Only committed edits appear here. Kept in memory while open; a new edit clears undone future changes.</p>
    {error&&<p className="context-warning" role="alert">{error}</p>}
    <ol className="history-list">{rows.map(row=><li key={row.position} ref={row.status==='current'?active:null}>
      <button aria-current={row.status==='current'?'step':undefined} disabled={!!busy||row.status==='current'} onClick={()=>onRestore(row.position)} aria-label={`Restore state ${row.position}: ${row.label}`}>
        <span className="history-position">{row.position}</span><span>{row.label}<small>{row.status==='current'?'Current state':row.status==='undone'?'Undone · available to redo':'Applied'}</small></span>
      </button>
    </li>)}</ol>
  </section>;
}

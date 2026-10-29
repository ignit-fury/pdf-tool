import React,{useEffect,useRef,useState} from 'react';
import {explainReason,refusalCode,needsFontChoice} from '../session.mjs';
import {sourceRunForMatch} from './search.mjs';

const plural=(count,word)=>`${count} ${word}${count===1?'':word.endsWith('match')?'es':'s'}`;
export default function FindPanel({query,replacement,fontFamily,matchCase,wholeWords,onQuery,onReplacement,onFont,onMatchCase,onWholeWords,
  progress,matches,excludedIds,onToggle,onStop,onResume,review,previewing,locked,onPreview,onCancelPreview,error,
  activeId,onNavigate,resultPage,onResultPage,queryRef,rowRefs,recipe=[],pages:sourcePages,sourceMismatch=false,onRefresh,applyAllowed=false,onApply}){
  const complete=progress.status==='complete',segmenter=typeof Intl.Segmenter==='function';
  const refused=match=>match.reason||review?.refusals[match.runId];
  const blocked=matches.filter(refused).length,excluded=matches.filter(match=>!refused(match)&&excludedIds.has(match.id)).length;
  const changing=matches.filter(match=>!refused(match)&&!excludedIds.has(match.id)&&match.text!==replacement).length;
  const summary=complete?`${plural(matches.length,'match')} across ${plural(progress.total,'page')}`:`Indexed ${progress.completed} of ${progress.total} pages · ${plural(matches.length,'match')} so far`;
  const [announcement,setAnnouncement]=useState('');
  useEffect(()=>{const timer=setTimeout(()=>setAnnouncement(summary),500);return()=>clearTimeout(timer);},[summary]);
  const pageSummary=useRef(null),previousPage=useRef(resultPage);
  useEffect(()=>{if(previousPage.current!==resultPage){pageSummary.current?.focus();previousPage.current=resultPage;}},[resultPage]);
  const pages=Math.max(1,Math.ceil(matches.length/50)),safePage=Math.min(resultPage,pages),start=(safePage-1)*50,visible=matches.slice(start,start+50);
  const active=matches.find(match=>match.id===activeId),activeChange=review?.changes.find(change=>change.runId===active?.runId)||(!active?review?.changes[0]:null);
  const ready=review?.result.ok===true;
  let help=!complete?'Finish indexing every page before previewing replacements.':!matches.some(match=>!refused(match)&&!excludedIds.has(match.id))?'Select at least one replaceable match to preview.':!changing?'The replacement does not change any selected text.':'';
  return <section className="find-panel" aria-labelledby="find-heading">
    <h2 id="find-heading">Find and replace <span className="location">Local search</span></h2>
    <label>Find text<input ref={queryRef} value={query} placeholder="Word or phrase" onChange={event=>onQuery(event.target.value)} disabled={locked}/></label>
    <div className="find-options"><label><input type="checkbox" checked={matchCase} onChange={event=>onMatchCase(event.target.checked)} disabled={locked}/> Match case</label><label><input type="checkbox" checked={wholeWords} onChange={event=>onWholeWords(event.target.checked)} disabled={locked||!segmenter} aria-describedby={!segmenter?'whole-word-help':undefined}/> Whole words only</label></div>
    {!segmenter&&<p id="whole-word-help" className="find-support">This browser does not support Unicode whole-word search. Use substring search or update your browser.</p>}
    <div className="find-index" aria-busy={progress.status==='indexing'}><p>{summary}</p>{!complete&&<progress value={progress.completed} max={Math.max(1,progress.total)} aria-label="Pages indexed"/>}<span className="location server">Server index</span>
      {progress.status==='indexing'&&<button onClick={onStop}>Stop indexing</button>}
      {progress.status==='stopped'&&<><p>Indexing stopped at {progress.completed} of {progress.total} pages. Results are incomplete.</p><button onClick={onResume}>Resume indexing</button></>}
      {progress.failedPages.length>0&&<><p>Could not index {progress.failedPages.map(page=>`page ${page}`).join(', ')}. Results are incomplete. Retry indexing to search every page.</p>{progress.status!=='indexing'&&<button onClick={onResume}>Retry indexing</button>}</>}
    </div>
    {query&&<p className="find-support">{plural(changing,'changing match')} selected · {excluded} excluded · {blocked} cannot be replaced</p>}
    <div className="visually-hidden" aria-live="polite" aria-atomic="true">{announcement}</div>
    <label>Replace with<textarea value={replacement} placeholder="Replacement text" rows={2} onChange={event=>onReplacement(event.target.value)} disabled={locked}/></label>
    {replacement===''&&query&&<p className="find-removal">Replacement is empty. Included matches will be removed.</p>}
    <label>Replacement font<select value={fontFamily} onChange={event=>onFont(event.target.value)} disabled={locked}><option value="">Automatic — preserve or match original</option><option value="Serif">Serif — Liberation Serif</option><option value="Sans">Sans-serif — Liberation Sans</option><option value="Mono">Monospace — Liberation Mono</option></select></label>
    <p className="find-support">Used where the original font cannot supply the replacement. Existing per-run font choices are preserved.</p>
    <nav className="find-preview-actions" aria-label="Navigate matches"><button onClick={()=>onNavigate(matches[(Math.max(0,matches.findIndex(m=>m.id===activeId))-1+matches.length)%matches.length])} disabled={locked||!matches.length}>Previous match</button><button onClick={()=>onNavigate(matches[(matches.findIndex(m=>m.id===activeId)+1)%matches.length])} disabled={locked||!matches.length}>Next match</button></nav>
    <div className="find-preview-actions"><button onClick={()=>onPreview('one')} disabled={locked||previewing||!complete||!active||!!refused(active)||excludedIds.has(active.id)||active.text===replacement}>Preview Replace One <span className="location server">Server</span></button><button className={ready?'':'primary'} onClick={()=>onPreview('all')} disabled={locked||previewing||!query||!complete||!changing}>Preview Replace All <span className="location server">Server</span></button>{previewing&&<button onClick={onCancelPreview}>Cancel preview</button>}</div>
    {previewing&&<p>Checking replacement fit on the server…</p>}{help&&<p className="find-support">{help}</p>}
    {error&&<p className="find-error" role="alert">{error}</p>}
    {sourceMismatch&&<div role="alert"><p>This preview no longer matches the document. Refresh the index and preview again.</p><button onClick={onRefresh} disabled={locked}>Refresh index</button></div>}
    {review&&<section className={`find-review ${ready?'':'find-review-refused'}`} aria-busy={previewing} aria-labelledby="review-heading"><h3 id="review-heading">Review replacements</h3><p>{plural(review.selectedCount,'match')} on {plural(review.changedPages.length,'page')} will change. {excluded} excluded. {blocked} cannot be replaced.</p>
      {!replacement&&<p className="find-removal">Replacement is empty. Included matches will be removed.</p>}
      {activeChange&&<div className="find-before-after"><strong>Page {activeChange.page}</strong><h4>Before</h4><p>{activeChange.before}</p><h4>After</h4><p>{activeChange.after||<em>Empty text</em>}</p></div>}
      <p>{ready?`Ready to replace ${plural(review.selectedCount,'match')}. One undo restores this batch.`:'No selected matches can be replaced. Review the reasons below, adjust the text or font, then preview again.'}</p>
      {onApply&&<button className="primary" onClick={onApply} disabled={!ready||!applyAllowed||locked||previewing}>{review.scope==='one'?'Replace One':`Replace All (${review.selectedCount})`} <span className="location server">Server</span></button>}
    </section>}
    <section className="find-results" aria-label="Search results"><h3 ref={pageSummary} tabIndex={-1}>{matches.length?`Matches ${start+1}–${Math.min(start+50,matches.length)} of ${matches.length}`:query?(complete?'No matches found':`No matches yet. Results cover ${progress.completed} of ${progress.total} pages.`):'Find text across this PDF'}</h3>
      {!matches.length&&<p>{!query?'Enter a word or phrase. Matches appear as pages are indexed.':complete?'Try another spelling or turn off Match case or Whole words only.':''}</p>}
      <ol start={start+1}>{visible.map((match,index)=>{
        const ordinal=start+index+1,reason=refused(match),isExcluded=excludedIds.has(match.id),unchanged=match.text===replacement;
        const run=sourceRunForMatch(sourcePages,match),prior=recipe.find(op=>op.run_id===match.runId),fontNeeded=!fontFamily&&needsFontChoice(run,prior?.style||{});
        const reasonId=`match-reason-${ordinal}`,code=refusalCode(reason);
        return <li key={match.id} className={activeId===match.id?'find-active':''}>
          <div className="find-row-controls"><label className="find-checkbox"><input type="checkbox" checked={!reason&&!isExcluded&&!unchanged} disabled={!!reason||locked||unchanged} onChange={()=>onToggle(match.id)} aria-label={`Include match ${ordinal} on page ${match.page}`} aria-describedby={reason?reasonId:undefined}/><span className="visually-hidden">Include match {ordinal}</span></label>
            <button ref={element=>{if(element)rowRefs.current.set(match.id,element);else rowRefs.current.delete(match.id);}} onClick={()=>onNavigate(match)} aria-label={`Show match ${ordinal} on page ${match.page}: ${match.before}${match.text}${match.after}`} aria-current={activeId===match.id?'true':undefined}>Page {match.page}</button>
            <span className="find-row-state">{reason?'Cannot replace':isExcluded?'Excluded':unchanged?'Unchanged':review?.changes.some(change=>change.matchIds.includes(match.id))?'Ready':'Fit not checked'}</span></div>
          <p className="find-context">{match.before}<mark>{match.text}</mark>{match.after}</p>
          {reason&&<p id={reasonId} className="find-reason">{explainReason(reason)}{code&&<code>{code}</code>}</p>}
          {!reason&&fontNeeded&&<p className="find-support">No automatic font match. Choose a replacement font, then preview again.</p>}
        </li>;
      })}</ol>
      {pages>1&&<nav className="find-pagination" aria-label="Result pages"><button onClick={()=>onResultPage(safePage-1)} disabled={safePage<=1}>Previous results</button><span>{safePage} / {pages}</span><button onClick={()=>onResultPage(safePage+1)} disabled={safePage>=pages}>Next results</button></nav>}
    </section>
    <p className="find-support">Search runs in your browser over text indexed by the server. Indexing, preview, and replacement use the server.</p>
  </section>;
}

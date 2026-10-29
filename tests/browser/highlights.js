// Synthetic PDF from tools/build_highlight_fixtures.py; existing Playwright connector.
async(page)=>{
  const root=page.__highlightFixtureRoot||'/private/tmp/pdf-tool-highlights-20261029';
  const check=(value,message)=>{if(!value)throw Error(message);};
  await page.emulateMedia({reducedMotion:'reduce'});
  await page.goto(page.__highlightBaseUrl||'http://127.0.0.1:8768/');
  const requests=[],listener=request=>{const url=new URL(request.url());if(url.pathname==='/upload'||url.pathname.startsWith('/jobs/'))requests.push({path:url.pathname,query:url.search});};page.on('request',listener);
  const save=async name=>{const download=page.waitForEvent('download');await page.locator('.document-actions button.primary').click();await(await download).saveAs(`${root}/${name}.pdf`);};
  const query=async(text,summary)=>{await page.getByRole('textbox',{name:'Find text',exact:true}).fill(text);if(summary)await page.getByText(summary,{exact:true}).first().waitFor();};
  const select=async number=>{await page.locator('.find-row-controls button').nth(number-1).click();};
  const precise=async(number,source,start,end,highlightIndex=null)=>{
    const area=page.locator(`[data-page-number="${number}"]`);await area.locator('[data-highlight-quality="precise"]').waitFor();
    const facts=await area.evaluate((paperPage,{source,start,end,highlightIndex})=>{
      const span=Array.from(paperPage.querySelectorAll('.textLayer span')).find(s=>s.textContent===source&&!s.querySelector('span'));
      if(!span)throw Error('Expected actual PDF text span missing');
      const nodes=[],walker=document.createTreeWalker(span,4);let n,total=0;while(n=walker.nextNode()){nodes.push({node:n,start:total,end:total+n.length});total+=n.length;}
      const a=nodes.find(n=>n.end>start),b=nodes.find(n=>n.end>=end),range=document.createRange();range.setStart(a.node,start-a.start);range.setEnd(b.node,end-b.start);
      const expected=range.getBoundingClientRect(),all=Array.from(paperPage.querySelectorAll('.find-highlight'),r=>r.getBoundingClientRect()),rects=highlightIndex===null?all:[all[highlightIndex]],left=Math.min(...rects.map(r=>r.left)),top=Math.min(...rects.map(r=>r.top)),actual={left,top,width:Math.max(...rects.map(r=>r.right))-left,height:Math.max(...rects.map(r=>r.bottom))-top},run=span.getBoundingClientRect();
      return {delta:Math.max(...['left','top','width','height'].map(k=>Math.abs(expected[k]-actual[k]))),actual:{left:actual.left,top:actual.top,width:actual.width,height:actual.height},run:{width:run.width,height:run.height},pointer:getComputedStyle(paperPage.querySelector('.find-highlight-layer')).pointerEvents};
    },{source,start,end,highlightIndex});
    check(facts.delta<.25,'Highlight differs from actual DOM Range: '+JSON.stringify(facts));check(facts.pointer==='none','Highlight intercepts text selection');return facts;
  };
  await page.locator('input[aria-label="Open PDF file"]').setInputFiles(`${root}/highlights.pdf`);
  await page.locator('.document-actions').getByRole('button',{name:'Find and replace',exact:true}).click();await page.getByRole('button',{name:'Analyze text Server',exact:true}).click();await query('cat','4 matches across 3 pages');
  await select(1);const first=await precise(1,'alpha cat cat omega',6,9);await select(2);const second=await precise(1,'alpha cat cat omega',10,13);check(second.actual.left>first.actual.left+first.actual.width,'Repeated occurrences share a full-run highlight');check(first.actual.width<first.run.width*.3,'Highlight covers whole run');check(await page.evaluate(()=>document.querySelector('.app-header').getBoundingClientRect().top>=-.5&&document.querySelector('.app').scrollTop===0),'Search scrolling moved the fixed viewer chrome');await page.screenshot({path:`${root}/precise-match.png`});
  await page.locator('.zoom select').selectOption('2');await precise(1,'alpha cat cat omega',10,13);
  await page.evaluate(()=>{const span=Array.from(document.querySelectorAll('[data-page-number="1"] .textLayer span')).find(s=>s.textContent==='alpha cat cat omega');span.firstChild.splitText(8);});await select(1);await precise(1,'alpha cat cat omega',6,9);
  await page.locator('.zoom select').selectOption('1.15');await select(3);const rotated=await precise(2,'alpha cat cat omega',6,9);check(rotated.actual.height>rotated.actual.width,'Rotated match was not measured vertically');
  await query('cafe\u0301','6 matches across 3 pages');await select(2);await precise(1,'café CAFÉ',5,9);
  await query('ca','12 matches across 3 pages');await select(9);await page.locator('[data-page-number="3"] [data-highlight-quality="approximate"]').waitFor();await page.getByText(/Approximate text area — exact text-layer mapping is unavailable/).waitFor();await page.screenshot({path:`${root}/approximate-match.png`});
  await query('not-present','No matches found');check(!await page.locator('.find-highlight').count(),'Old rectangles survived query change');await save('after-highlighting');
  await query('cat','4 matches across 3 pages');await page.getByRole('textbox',{name:'Replace with',exact:true}).fill('otter');await page.getByRole('combobox',{name:'Replacement font',exact:true}).selectOption('Serif');
  await page.getByRole('button',{name:'Preview Replace All Server',exact:true}).click();await page.getByRole('button',{name:'Replace All (4) Server',exact:true}).click();
  await page.getByRole('region',{name:'Applied replacement walkthrough',exact:true}).waitFor();await precise(1,'alpha otter otter omega',6,11,0);await precise(1,'alpha otter otter omega',12,17,1);await save('replaced');
  await page.getByRole('button',{name:'Next page',exact:true}).click();await precise(2,'alpha otter otter omega',6,11,0);
  await page.getByRole('button',{name:'Stop walkthrough',exact:true}).click();await query('otter','4 matches across 3 pages');await page.getByRole('textbox',{name:'Replace with',exact:true}).fill('');await page.getByRole('button',{name:'Preview Replace All Server',exact:true}).click();await page.getByRole('button',{name:'Replace All (4) Server',exact:true}).click();
  await page.locator('.find-highlight.removed').first().waitFor();await save('removed');
  const writes=requests.filter(r=>r.query.includes('dry_run=false')).length;check(writes===2,'Highlight/tour introduced additional PDF writes');
  await page.locator('.document-actions').getByRole('button',{name:'Undo replacements Browser',exact:true}).click();await page.locator('.document-actions').getByRole('button',{name:'Redo Browser',exact:true}).waitFor();await save('undo-removal');
  page.off('request',listener);await page.screenshot({path:`${root}/highlight-restored.png`});
  return {passed:true,repeatedOccurrences:true,splitNodes:true,unicode:true,rotatedCropUserUnit:true,zoom:true,explicitFallback:true,queryClears:true,actualReplacementOffsets:true,deletionMarker:true,atomicWrites:writes,undo:true};
}

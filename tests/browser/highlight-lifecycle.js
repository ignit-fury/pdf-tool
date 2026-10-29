// Hold actual PDF.js text-content RPCs to prove timing and stale-layer cancellation.
async(page)=>{
  const root=page.__highlightFixtureRoot||'/private/tmp/pdf-tool-highlights-20261029';
  const check=(value,message)=>{if(!value)throw Error(message);};
  await page.addInitScript(()=>{
    let Original=window.Worker;while(!Function.prototype.toString.call(Original).includes('[native code]'))Original=Object.getPrototypeOf(Original);
    window.__highlightOriginalWorker=Original;window.__highlightHoldPage=null;window.__highlightHeld=null;
    window.Worker=class extends Original{postMessage(message,...args){
      if(message?.action==='GetTextContent'&&window.__highlightHoldPage!==null&&message.data?.pageIndex===window.__highlightHoldPage){window.__highlightHoldPage=null;window.__highlightHeld={worker:this,message,args};return;}
      return super.postMessage(message,...args);
    }};
  });
  await page.emulateMedia({reducedMotion:'no-preference'});await page.goto(page.__highlightBaseUrl||'http://127.0.0.1:8768/');
  const open=async()=>{await page.locator('input[aria-label="Open PDF file"]').setInputFiles(`${root}/highlights.pdf`);await page.waitForFunction(()=>!!document.querySelector('.document-actions button.primary')&&!document.querySelector('.document-actions button.primary').disabled);};
  const release=()=>page.evaluate(()=>{const held=window.__highlightHeld;try{window.__highlightOriginalWorker.prototype.postMessage.call(held.worker,held.message,...held.args);}catch{}window.__highlightHeld=null;});
  await open();await page.locator('.document-actions').getByRole('button',{name:'Find and replace',exact:true}).click();await page.getByRole('button',{name:'Analyze text Server',exact:true}).click();await page.getByRole('textbox',{name:'Find text',exact:true}).fill('cat');await page.getByText('4 matches across 3 pages',{exact:true}).first().waitFor();await page.getByRole('textbox',{name:'Replace with',exact:true}).fill('dog');await page.getByRole('combobox',{name:'Replacement font',exact:true}).selectOption('Serif');await page.getByRole('button',{name:'Preview Replace All Server',exact:true}).click();
  await page.evaluate(()=>window.__highlightHoldPage=0);await page.getByRole('button',{name:'Replace All (4) Server',exact:true}).click();await page.waitForFunction(()=>!!window.__highlightHeld);await page.getByText(/Applied replacements 1–2 of 4/).waitFor();
  await page.waitForTimeout(800);check((await page.getByRole('region',{name:'Applied replacement walkthrough',exact:true}).innerText()).includes('Applied replacements 1–2 of 4'),'Tour advanced before the current page rendered');check(!await page.locator('.find-highlight-layer').count(),'Stale highlight shown while new layer is pending');
  await release();await page.locator('[data-highlight-quality="precise"]').waitFor();await page.locator('.replacement-tour').waitFor({state:'detached'});
  await page.evaluate(()=>window.__highlightHoldPage=0);await page.locator('.zoom select').selectOption('2');await page.waitForFunction(()=>!!window.__highlightHeld);await page.getByRole('textbox',{name:'Find text',exact:true}).fill('not-present');await release();
  check(!await page.getByRole('region',{name:'Applied replacement walkthrough',exact:true}).count(),'Changing query retained an unrelated applied-results tour');
  await page.locator('[data-page-number="1"] .textLayer').getByText('alpha dog dog omega',{exact:true}).waitFor();await page.evaluate(()=>new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve))));check(!await page.locator('.find-highlight-layer').count(),'Old range appeared after query changed');
  await page.getByRole('textbox',{name:'Find text',exact:true}).fill('dog');await page.getByText('4 matches across 3 pages',{exact:true}).first().waitFor();await page.getByRole('button',{name:'Next match',exact:true}).click();await page.locator('[data-highlight-quality="precise"]').waitFor();
  await page.evaluate(()=>window.__highlightHoldPage=0);await page.locator('.zoom select').selectOption('1.15');await page.waitForFunction(()=>!!window.__highlightHeld);await open();await release();
  check(!await page.locator('.find-highlight-layer').count(),'Old highlight leaked into a new document');
  const download=page.waitForEvent('download');await page.locator('.document-actions button.primary').click();await(await download).saveAs(`${root}/after-stale-source.pdf`);
  await page.evaluate(()=>{window.Worker=window.__highlightOriginalWorker;window.__highlightHoldPage=null;});
  return {passed:true,tourWaitsForActualRender:true,automaticAdvanceAfterRender:true,staleQueryRejected:true,staleSourceRejected:true};
}

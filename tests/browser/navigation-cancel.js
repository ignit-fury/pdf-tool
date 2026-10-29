// Continue after navigation.js registered the local test-only worker instrumentation.
async(page)=>{
  const root=page.__navigationFixtureRoot||'/private/tmp/pdf-tool-navigation-20261029';
  await page.goto(page.__navigationBaseUrl||'http://127.0.0.1:8768/');
  const open=async()=>{await page.locator('input[aria-label="Open PDF file"]').setInputFiles(`${root}/source.pdf`);await page.waitForFunction(()=>!!document.querySelector('.document-actions button.primary')&&!document.querySelector('.document-actions button.primary').disabled);};
  const top=name=>page.locator('.document-actions').getByRole('button',{name,exact:true});
  await open();await top('Page tools').click();await page.getByRole('button',{name:'Insert before',exact:true}).click();await top('Undo blank insertion Browser').waitFor();
  await page.getByRole('button',{name:'Rotate clockwise 90°',exact:true}).click();await top('Undo page rotation Browser').waitFor();
  await top('History').click();await page.evaluate(()=>window.__navigationHold='GetDocRequest');await page.getByRole('button',{name:'Restore state 0: Original document',exact:true}).click();await page.waitForFunction(()=>!!window.__navigationHeld);
  await open();await top('History').click();
  await page.evaluate(()=>{const held=window.__navigationHeld;try{window.__navigationOriginalWorker.prototype.postMessage.call(held.worker,held.message,...held.args);}catch{}window.__navigationHeld=null;window.__navigationHold=null;});
  const panel=page.getByRole('region',{name:'Document history',exact:true});
  if(await panel.getByRole('button').count()!==1||!await top('Undo Browser').isDisabled())throw Error('Late history preparation published into the new document');
  const download=page.waitForEvent('download');await page.locator('.document-actions button.primary').click();await(await download).saveAs(`${root}/after-canceled-jump.pdf`);
  return {passed:true,staleRestoreRejected:true,newSourceHistoryEmpty:true};
}

// Independent Unicode-password fixture and simulated cache-loss transport check.
async(page)=>{
  const root=page.__viewerFixtureRoot||'/private/tmp/pdf-tool-viewer-20261029';
  await page.goto(page.__viewerBaseUrl||'http://127.0.0.1:8767/');
  page.__viewerNetwork=[];
  await page.locator('input[aria-label="Open PDF file"]').setInputFiles(`${root}/unicode-password.pdf`);
  await page.getByRole('textbox',{name:'PDF password',exact:true}).fill('密碼');
  await page.getByRole('button',{name:'Unlock PDF',exact:true}).click();
  await page.locator('.continuous-stage').waitFor();
  await page.waitForFunction(()=>!document.querySelector('.document-actions .primary').disabled);
  if(page.__viewerNetwork.length)throw new Error('Unlocking unexpectedly uploaded the PDF');
  await page.getByRole('button',{name:'Edit text',exact:true}).click();
  await page.getByRole('button',{name:'Analyze text Server',exact:true}).click();
  await page.locator('[data-page-number="1"]').getByRole('button',{name:'Edit text: Hello world',exact:true}).first().click();
  await page.getByRole('textbox',{name:'Edit text on page',exact:true}).fill('Hi');
  let missing=false;
  const pattern='**/jobs/*/edit?dry_run=true';
  await page.route(pattern,async route=>{if(!missing){missing=true;await route.fulfill({status:409,contentType:'application/json',body:JSON.stringify({detail:{code:'SOURCE_MISSING'}})});}else await route.continue();});
  await page.getByRole('button',{name:'Preview fit Server',exact:true}).click();
  await page.getByText('Validated — ready to apply.',{exact:true}).waitFor();
  await page.unroute(pattern);
  if(!missing||page.__viewerNetwork.filter(r=>r.path==='/upload').length!==2)throw new Error('Cache-loss recovery did not reupload the encrypted original once');
  await page.getByRole('button',{name:'Apply edit Server',exact:true}).click();
  await page.getByRole('button',{name:'Download untouched original Browser',exact:true}).waitFor();
  const original=page.waitForEvent('download');await page.getByRole('button',{name:'Download untouched original Browser',exact:true}).click();await (await original).saveAs(`${root}/unicode-original.pdf`);
  const edited=page.waitForEvent('download');await page.getByRole('button',{name:'Download edited PDF Browser',exact:true}).click();await (await edited).saveAs(`${root}/unicode-edited.pdf`);
  return {passed:true,unicodePassword:true,noEagerUpload:true,simulatedCacheLoss:true,uploads:2};
}

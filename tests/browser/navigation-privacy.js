// Explicit analysis first, then cache-miss simulation: outline must initiate no server work.
async(page)=>{
  const root=page.__navigationFixtureRoot||'/private/tmp/pdf-tool-navigation-20261029';
  await page.goto(page.__navigationBaseUrl||'http://127.0.0.1:8768/');
  await page.locator('input[aria-label="Open PDF file"]').setInputFiles(`${root}/bookmarks.pdf`);
  await page.getByRole('button',{name:'Edit text',exact:true}).click();await page.getByRole('button',{name:'Analyze text Server',exact:true}).click();
  await page.locator('[data-page-number="1"]').getByRole('button',{name:'Edit text: Document page 1',exact:true}).waitFor();await page.waitForLoadState('networkidle');
  const paths=[],listener=request=>{const path=new URL(request.url()).pathname;if(path==='/upload'||path.startsWith('/jobs/'))paths.push(path);};page.on('request',listener);
  const pattern='**/jobs/*/pages/*/runs',missing=route=>route.fulfill({status:409,contentType:'application/json',body:JSON.stringify({detail:{code:'SOURCE_MISSING'}})});
  await page.route(pattern,missing);
  try{
    await page.locator('.document-actions').getByRole('button',{name:'Outline',exact:true}).click();
    await page.getByRole('region',{name:'Document outline',exact:true}).getByRole('button',{name:'Last chapter',exact:true}).click();
    await page.waitForFunction(()=>document.querySelector('.page-controls>span')?.textContent.trim().startsWith('12 /'));
    await page.waitForLoadState('networkidle');
    if(paths.length)throw Error('Outline initiated server work after analysis: '+paths.join(','));
    await page.unroute(pattern,missing);
    await page.getByRole('button',{name:'Edit text',exact:true}).click();
    await page.locator('[data-page-number="12"]').getByRole('button',{name:'Edit text: Document page 12',exact:true}).waitFor();
    if(!paths.length)throw Error('Explicit Edit did not resume analysis');
    return {passed:true,analyzedSource:true,cacheMissRoute:true,outlineServerRequests:0,explicitResume:true};
  }finally{page.off('request',listener);await page.unroute(pattern,missing);}
}

// With an analyzed document open, switching to Find must release an inline draft.
async(page)=>{
  await page.getByRole('button',{name:'Edit text',exact:true}).click();
  if(await page.getByRole('button',{name:'Analyze text Server',exact:true}).count())await page.getByRole('button',{name:'Analyze text Server',exact:true}).click();
  await page.locator('[data-page-number="1"] .run-box').first().click();
  await page.getByRole('textbox',{name:'Edit text on page',exact:true}).waitFor();
  await page.locator('.document-actions').getByRole('button',{name:'Find and replace',exact:true}).click();
  if(await page.getByRole('textbox',{name:'Edit text on page',exact:true}).count())throw new Error('Stale inline input remains when switching to batch replacement');
  return {passed:true};
}

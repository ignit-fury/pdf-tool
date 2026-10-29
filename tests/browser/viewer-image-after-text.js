// The real UI path that previously lost ownership when native text saving compressed streams.
async(page)=>{
  const root=page.__viewerFixtureRoot||'/private/tmp/pdf-tool-viewer-20261029';
  await page.goto(page.__viewerBaseUrl||'http://127.0.0.1:8767/');
  await page.locator('input[aria-label="Open PDF file"]').setInputFiles(`${root}/image-replaced.pdf`);
  await page.locator('.continuous-stage').waitFor();
  await page.waitForFunction(()=>!document.querySelector('.document-actions .primary').disabled);
  await page.getByRole('button',{name:'Edit text',exact:true}).click();
  await page.getByRole('button',{name:'Analyze text Server',exact:true}).click();
  await page.locator('[data-page-number="1"]').getByRole('button',{name:'Edit text: Neighbor must stay unchanged',exact:true}).click();
  await page.getByRole('textbox',{name:'Edit text on page',exact:true}).fill('Neighbor stays unchanged');
  await page.getByRole('button',{name:'Preview fit Server',exact:true}).click();
  await page.getByText('Validated — ready to apply.',{exact:true}).waitFor();
  await page.getByRole('button',{name:'Apply edit Server',exact:true}).click();
  await page.waitForFunction(()=>!document.querySelector('.inline-text-input'));
  await page.getByRole('button',{name:'Images',exact:true}).click();
  await page.locator('[data-page-number="1"]').getByRole('button',{name:'Select image 1 on page',exact:true}).click();
  await page.getByRole('spinbutton',{name:'Image left',exact:true}).fill('70');
  await page.getByRole('button',{name:'Apply image Browser',exact:true}).click();
  await page.getByRole('button',{name:'Undo image change Browser',exact:true}).waitFor();
  return {passed:true,reopenedManagedImage:true,nativeTextSave:true,subsequentImageUpdate:true};
}

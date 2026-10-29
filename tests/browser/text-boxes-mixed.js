// Continue after text-boxes.js/safety. Tests the real mixed-history/page/source path.
async(page)=>{
  const root=page.__textBoxFixtureRoot||'/private/tmp/pdf-tool-text-boxes-20261029';
  const check=(value,message)=>{if(!value)throw new Error(message);};
  await page.locator('.document-actions').getByRole('button',{name:'Page tools',exact:true}).click();
  await page.getByRole('button',{name:'Insert before',exact:true}).click();await page.getByRole('button',{name:'Undo blank insertion Browser',exact:true}).waitFor();
  await page.getByRole('button',{name:'Text boxes',exact:true}).click();await page.getByRole('button',{name:'Load inserted text boxes Server',exact:true}).click();
  await page.getByRole('button',{name:'Edit inserted text box 1 on page 2',exact:true}).click();
  await page.locator('.document-actions').getByRole('button',{name:'Page tools',exact:true}).click();
  await page.getByRole('button',{name:'Rotate clockwise 90°',exact:true}).click();await page.getByRole('button',{name:'Undo page rotation Browser',exact:true}).waitFor();
  await page.getByRole('button',{name:'Text boxes',exact:true}).click();await page.getByRole('button',{name:'Load inserted text boxes Server',exact:true}).click();
  await page.getByRole('button',{name:'Edit inserted text box 1 on page 2',exact:true}).click();
  await page.getByText(/This text box rotated with its page/).waitFor();
  check(await page.getByRole('button',{name:'Preview text box Server',exact:true}).isDisabled(),'Rotated source container must not silently change orientation');
  await page.getByRole('button',{name:'Cancel text box changes',exact:true}).click();
  await page.getByRole('button',{name:'Undo page rotation Browser',exact:true}).click();await page.getByRole('button',{name:'Undo blank insertion Browser',exact:true}).waitFor();
  await page.getByRole('button',{name:'Edit text',exact:true}).click();
  await page.getByRole('button',{name:'Analyze text Server',exact:true}).click();
  await page.locator('[data-page-number="2"]').getByRole('button',{name:'Edit text: Document page 1',exact:true}).click();
  await page.getByRole('textbox',{name:'Edit text on page',exact:true}).fill('Changed title');await page.getByRole('button',{name:'Preview fit Server',exact:true}).click();await page.getByText('Validated — ready to apply.',{exact:true}).waitFor();
  await page.getByRole('button',{name:'Apply edit Server',exact:true}).click();await page.getByRole('button',{name:'Undo text edit Browser',exact:true}).waitFor();
  await page.locator('[data-page-number="2"] .run-box.refused').first().click();
  await page.getByRole('textbox',{name:'Text box content on page',exact:true}).waitFor();
  check((await page.getByRole('textbox',{name:'Text box content on page',exact:true}).inputValue()).includes('Updated paragraph'),'A managed source target must route to its complete text-box layout');
  await page.getByRole('button',{name:'Cancel text box changes',exact:true}).click();
  await page.locator('input[aria-label="Insert image file"]').setInputFiles(`${root}/image.png`);
  await page.getByRole('spinbutton',{name:'Image width',exact:true}).fill('80');await page.getByRole('spinbutton',{name:'Image left',exact:true}).fill('450');await page.getByRole('spinbutton',{name:'Image top',exact:true}).fill('500');
  await page.getByRole('button',{name:'Apply image Browser',exact:true}).click();await page.getByRole('button',{name:'Undo image placement Browser',exact:true}).waitFor();
  await page.getByRole('button',{name:'Text boxes',exact:true}).click();await page.getByRole('button',{name:'Load inserted text boxes Server',exact:true}).click();await page.getByRole('button',{name:'Edit inserted text box 1 on page 2',exact:true}).click();
  await page.getByRole('textbox',{name:'Text box content on page',exact:true}).fill('Mixed workflow keeps the changed title and managed image.\nNative text remains editable.');await page.getByRole('spinbutton',{name:'Text box font size',exact:true}).fill('14');
  await page.getByRole('button',{name:'Preview text box Server',exact:true}).click();await page.getByText('Exact candidate PDF is visible.',{exact:false}).waitFor();await page.getByRole('button',{name:'Apply text box Browser',exact:true}).click();await page.getByRole('button',{name:'Undo text box edit Browser',exact:true}).waitFor();
  const text=await page.locator('[data-page-number="2"] .textLayer').innerText();check(text.includes('Changed title')&&text.includes('Mixed workflow'),'Text-box publication lost an earlier source edit');
  const dl=page.waitForEvent('download');await page.getByRole('button',{name:'Download edited PDF Browser',exact:true}).click();await(await dl).saveAs(`${root}/mixed.pdf`);
  await page.getByRole('button',{name:'Images',exact:true}).click();await page.locator('[data-page-number="2"]').getByRole('button',{name:'Select image 1 on page',exact:true}).click();await page.getByRole('spinbutton',{name:'Image left',exact:true}).fill('440');
  await page.getByRole('button',{name:'Apply image Browser',exact:true}).click();await page.getByRole('button',{name:'Undo image change Browser',exact:true}).waitFor();
  return {passed:true,pageInsertion:true,rotationPreserved:true,sourceRunRedirect:true,sourceEditRetained:true,imageBoxRoundTrip:true};
}

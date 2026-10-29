// Continue after text-boxes.js (one updated inserted box remains after Undo removal).
async(page)=>{
  const check=(value,message)=>{if(!value)throw new Error(message);};
  await page.getByRole('button',{name:'Insert text',exact:true}).click();
  await page.getByRole('button',{name:'Insert text on page 1',exact:true}).click({position:{x:100,y:135}});
  await page.getByRole('textbox',{name:'Text box content on page',exact:true}).fill('Overlap check');
  await page.getByRole('button',{name:'Preview text box Server',exact:true}).click();
  await page.getByText(/This area contains visible content or an annotation/).waitFor();
  check(!await page.locator('.text-box-preview-banner').count(),'Overlap failure must not publish a candidate');
  await page.getByRole('checkbox',{name:'Allow transparent overlap with existing content',exact:true}).check();
  await page.getByRole('button',{name:'Preview text box Server',exact:true}).click();await page.getByText('Exact candidate PDF is visible.',{exact:false}).waitFor();
  await page.getByRole('button',{name:'Cancel text box changes',exact:true}).click();
  await page.getByRole('button',{name:'Insert text on page 1',exact:true}).click({position:{x:100,y:600}});
  await page.getByRole('textbox',{name:'Text box content on page',exact:true}).fill('Line one wraps into several words that are measured correctly.\nLine two also wraps.');
  await page.getByRole('spinbutton',{name:'Text box width',exact:true}).fill('80');await page.getByRole('spinbutton',{name:'Text box height',exact:true}).fill('10');
  await page.getByRole('checkbox',{name:'Grow height to fit text',exact:true}).uncheck();
  await page.getByRole('button',{name:'Preview text box Server',exact:true}).click();await page.getByText(/No text was applied or clipped/).waitFor();
  const before=Number(await page.getByRole('spinbutton',{name:'Text box height',exact:true}).inputValue());
  await page.getByRole('button',{name:'Expand text box to fit',exact:true}).click();
  check(Number(await page.getByRole('spinbutton',{name:'Text box height',exact:true}).inputValue())>before,'Expansion feedback must increase geometry');
  await page.getByRole('button',{name:'Preview text box Server',exact:true}).click();await page.getByText('Exact candidate PDF is visible.',{exact:false}).waitFor();
  await page.getByRole('button',{name:'Cancel text box changes',exact:true}).click();
  await page.getByRole('button',{name:'Insert text on page 1',exact:true}).click({position:{x:100,y:600}});
  await page.getByRole('textbox',{name:'Text box content on page',exact:true}).fill('Canceled late response');
  const pattern='**/jobs/*/text-box?acknowledge_signature=false';let release,ready;
  const held=new Promise(resolve=>ready=resolve),gate=new Promise(resolve=>release=resolve);
  await page.route(pattern,async route=>{const response=await route.fetch();ready();await gate;await route.fulfill({response}).catch(()=>{});});
  await page.getByRole('button',{name:'Preview text box Server',exact:true}).click();await held;
  await page.getByRole('button',{name:'Cancel text box operation',exact:true}).click();release();await page.unroute(pattern);
  check(!await page.locator('.text-box-preview-banner').count(),'Late canceled candidate became visible');
  check(!await page.getByRole('textbox',{name:'Text box content on page',exact:true}).count(),'Cancel left a stale draft');
  return {passed:true,overlapRefused:true,explicitTransparentOverlap:true,overflowRefused:true,expandToFit:true,lateCancel:true};
}

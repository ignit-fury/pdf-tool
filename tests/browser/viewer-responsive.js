// Run after viewer-inline.js; checks real preview refusal and compact document chrome.
async(page)=>{
  const root=page.__viewerFixtureRoot||'/private/tmp/pdf-tool-viewer-20261029';
  const check=(condition,message)=>{if(!condition)throw new Error(message);};
  await page.locator('[data-page-number="1"] .run-box').first().click();
  const result=[];
  for(const width of [1280,760,320]){
    await page.setViewportSize({width,height:900});
    await page.screenshot({path:`${root}/viewer-${width}.png`});
    const geometry=await page.evaluate(()=>({width:innerWidth,scroll:document.documentElement.scrollWidth,stage:document.querySelector('.continuous-stage').clientHeight,focus:document.activeElement?.getAttribute('aria-label')}));
    check(geometry.scroll===width,`Unexpected body overflow at ${width}`);
    check(geometry.stage>=150,`Document reading area too small at ${width}`);
    check(geometry.focus==='Edit text on page','Inline focus was lost');
    result.push(geometry);
  }
  await page.setViewportSize({width:1280,height:900});
  await page.getByRole('spinbutton',{name:'Font size',exact:true}).fill('21');
  await page.getByRole('button',{name:'Preview fit Server',exact:true}).click();
  await page.getByText(/Increasing source text height could overlap nearby content/).waitFor();
  check(await page.getByRole('button',{name:'Apply edit Server',exact:true}).isDisabled(),'Unsafe font growth must refuse');
  await page.getByRole('spinbutton',{name:'Font size',exact:true}).fill('20');
  await page.getByRole('textbox',{name:'Edit text on page',exact:true}).fill('X'.repeat(100));
  await page.getByRole('button',{name:'Preview fit Server',exact:true}).click();
  await page.getByText(/Edit refused/).waitFor();
  check(await page.getByRole('button',{name:'Apply edit Server',exact:true}).isDisabled(),'Overflow must not authorize Apply');
  await page.getByRole('button',{name:'Cancel text editing',exact:true}).click();
  return {passed:true,viewports:result,growthRefused:true,overflowRefused:true};
}

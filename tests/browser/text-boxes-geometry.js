// Independent rotated/cropped/UserUnit fixture and responsive exact preview.
async(page)=>{
  const root=page.__textBoxFixtureRoot||'/private/tmp/pdf-tool-text-boxes-20261029';
  await page.getByRole('button',{name:'Close',exact:true}).click();
  await page.locator('input[aria-label="Open PDF file"]').setInputFiles(`${root}/rotated-source.pdf`);
  await page.locator('.continuous-stage').waitFor();
  await page.getByRole('button',{name:'Insert text',exact:true}).click();
  await page.getByRole('button',{name:'Insert text on page 1',exact:true}).click({position:{x:400,y:300}});
  await page.getByRole('textbox',{name:'Text box content on page',exact:true}).fill('Rotated page supports upright new text.\nSearchable second line.');
  await page.getByRole('spinbutton',{name:'Text box left',exact:true}).fill('400');
  await page.getByRole('spinbutton',{name:'Text box top',exact:true}).fill('300');
  await page.getByRole('spinbutton',{name:'Text box width',exact:true}).fill('300');
  await page.getByRole('spinbutton',{name:'Text box height',exact:true}).fill('120');
  const widths=[];
  for(const width of [760,320,1280]){
    await page.setViewportSize({width,height:1000});
    const facts=await page.evaluate(()=>({body:document.body.scrollWidth,view:innerWidth,stage:document.querySelector('.continuous-stage').getBoundingClientRect().height}));
    if(facts.body>width||facts.stage<150)throw Error('Unusable text-box responsive layout: '+JSON.stringify(facts));
    widths.push({width,...facts});
  }
  const response=page.waitForResponse(r=>r.url().includes('/text-box?')&&r.request().method()==='POST');
  await page.getByRole('button',{name:'Preview text box Server',exact:true}).click();
  const result=await(await response).json();
  await page.getByText('Exact candidate PDF is visible.',{exact:false}).waitFor();
  const hash=await page.evaluate(async encoded=>{
    const bytes=Uint8Array.from(atob(encoded),c=>c.charCodeAt(0));
    return Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',bytes)),v=>v.toString(16).padStart(2,'0')).join('');
  },result.pdf);
  await page.screenshot({path:`${root}/rotated-exact-preview.png`});
  await page.getByRole('button',{name:'Apply text box Browser',exact:true}).click();
  await page.getByRole('button',{name:'Undo text insertion Browser',exact:true}).waitFor();
  const download=page.waitForEvent('download');
  await page.getByRole('button',{name:'Download edited PDF Browser',exact:true}).click();
  await(await download).saveAs(`${root}/rotated-inserted.pdf`);
  await page.getByRole('button',{name:'Edit inserted text box 1 on page 1',exact:true}).click();
  await page.getByRole('textbox',{name:'Text box content on page',exact:true}).waitFor();
  return {passed:true,widths,candidateSha256:hash,rotatedNewBoxEditable:true};
}

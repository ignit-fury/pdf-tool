// Original source editing now bridges to a genuinely replacing, growing native container.
async(page)=>{
  const root='/private/tmp/pdf-tool-source-expansion-20261029';
  const check=(value,message)=>{if(!value)throw Error(message);};
  await page.goto('http://127.0.0.1:8768/');
  const network=[],listener=request=>{const url=new URL(request.url());if(url.pathname==='/upload'||url.pathname.startsWith('/jobs/'))network.push({path:url.pathname,query:url.search,operation:request.postData()?.startsWith('{')?JSON.parse(request.postData()).operation:null});};page.on('request',listener);
  const save=async name=>{const download=page.waitForEvent('download');await page.locator('.document-actions button.primary').click();await(await download).saveAs(`${root}/${name}.pdf`);};
  const editMode=()=>page.getByRole('button',{name:'Edit text',exact:true}).click();
  const choose=label=>page.locator('[data-page-number="1"]').getByRole('button',{name:`Edit text: ${label}`,exact:true}).first().click();
  const original='Document page 1',replacement='First title line\nSecond title line';
  await page.locator('input[aria-label="Open PDF file"]').setInputFiles(`${root}/source.pdf`);await editMode();await page.getByRole('button',{name:'Analyze text Server',exact:true}).click();
  await choose('Neighbor must stay unchanged');await page.getByRole('textbox',{name:'Edit text on page',exact:true}).fill('Neighbor intact');await page.getByRole('button',{name:'Preview fit Server',exact:true}).click();await page.getByText('Validated — ready to apply.',{exact:true}).waitFor();await page.getByRole('button',{name:'Apply edit Server',exact:true}).click();await page.getByRole('button',{name:'Undo text edit Browser',exact:true}).waitFor();await save('before-expansion');
  const enterMultiline=async()=>{await editMode();await choose(original);await page.getByRole('textbox',{name:'Edit text on page',exact:true}).fill(replacement);await page.getByRole('textbox',{name:'Text box content on page',exact:true}).waitFor();};
  await enterMultiline();
  const input=page.getByRole('textbox',{name:'Text box content on page',exact:true});check(await input.inputValue()===replacement,'Transition lost typed text');
  check(await input.evaluate(e=>e.clientHeight>=e.scrollHeight-1),'Multiline draft did not visually expand');
  check(await page.getByRole('checkbox',{name:'Grow height to fit text',exact:true}).isChecked(),'Automatic growth is not enabled');
  const minimum=Number(await page.getByRole('spinbutton',{name:'Text box height',exact:true}).inputValue());
  await page.getByRole('button',{name:'Preview text box Server',exact:true}).click();await page.getByText('Exact candidate PDF is visible.',{exact:false}).waitFor();
  check(Number(await page.getByRole('spinbutton',{name:'Text box height',exact:true}).inputValue())>minimum,'Candidate bounds did not grow');
  const text=await page.locator('[data-page-number="1"] .textLayer').innerText();check(!text.includes(original)&&text.includes('First title line')&&text.includes('Neighbor intact'),'Combined preview lost source removal or prior edits');
  await page.getByRole('button',{name:'Cancel text box changes',exact:true}).click();await save('after-cancel');
  await enterMultiline();await page.getByRole('button',{name:'Preview text box Server',exact:true}).click();await page.getByText('Exact candidate PDF is visible.',{exact:false}).waitFor();const requests=network.length;
  await page.getByRole('button',{name:'Apply text box Browser',exact:true}).click();await page.getByRole('button',{name:'Undo source text expansion Browser',exact:true}).waitFor();check(network.length===requests,'Apply performed a second destructive rewrite');await save('expanded');
  await page.getByRole('button',{name:'Undo source text expansion Browser',exact:true}).click();await page.getByRole('button',{name:'Undo text edit Browser',exact:true}).waitFor();await save('undone');
  await page.getByRole('button',{name:'Redo Browser',exact:true}).click();await page.getByRole('button',{name:'Undo source text expansion Browser',exact:true}).waitFor();await save('redone');
  await page.getByRole('button',{name:'Text boxes',exact:true}).click();await page.getByRole('button',{name:'Load inserted text boxes Server',exact:true}).click();await page.getByRole('button',{name:'Edit inserted text box 1 on page 1',exact:true}).click();
  await page.getByRole('textbox',{name:'Text box content on page',exact:true}).fill('First title line\nSecond title line\nThird line needs room');await page.getByRole('button',{name:'Preview text box Server',exact:true}).click();await page.getByText(/This area contains visible content or an annotation/).waitFor();check(!await page.locator('.text-box-preview-banner').count(),'Collision published a candidate');
  await page.getByRole('spinbutton',{name:'Text box top',exact:true}).fill('300');await page.getByRole('button',{name:'Preview text box Server',exact:true}).click();await page.getByText('Exact candidate PDF is visible.',{exact:false}).waitFor();await page.getByRole('button',{name:'Apply text box Browser',exact:true}).click();await page.getByRole('button',{name:'Undo text box edit Browser',exact:true}).waitFor();await save('grown-again');
  page.off('request',listener);await page.screenshot({path:`${root}/grown-source.png`});
  return {passed:true,automaticSourceTransition:true,visualGrowth:true,nativeGrowth:true,originalRemoved:true,priorRecipeRetained:true,cancel:true,oneApply:true,undoRedo:true,collisionRefused:true,subsequentManagedGrowth:true};
}

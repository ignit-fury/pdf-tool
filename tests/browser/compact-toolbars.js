// Local representative fixture: tools/build_text_box_fixtures.py.
async(page)=>{
  const check=(v,m)=>{if(!v)throw Error(m);};
  const metrics=()=>page.evaluate(()=>({stage:Math.round(document.querySelector('.continuous-stage').getBoundingClientRect().height),formatting:Math.round(document.querySelector('.context-toolbar')?.getBoundingClientRect().height||0),overflow:document.documentElement.scrollWidth>innerWidth}));
  const within=locator=>locator.evaluate(e=>{const b=e.getBoundingClientRect();return b.left>=0&&b.right<=innerWidth+1&&b.top>=0&&b.bottom<=innerHeight;});
  await page.setViewportSize({width:1280,height:1000});await page.goto('http://127.0.0.1:8768/');
  await page.locator('input[aria-label="Open PDF file"]').setInputFiles('/private/tmp/pdf-tool-source-expansion-20261029/source.pdf');await page.locator('[data-page-number="1"] .textLayer').waitFor();
  const reading=await metrics();check(reading.stage>800,'Reading area too short');
  await page.getByRole('button',{name:'Edit text',exact:true}).click();await page.getByRole('button',{name:'Analyze text Server',exact:true}).click();
  await page.locator('[data-page-number="1"]').getByRole('button',{name:'Edit text: Document page 1',exact:true}).click();
  await page.getByText('More formatting',{exact:true}).click();await page.getByRole('spinbutton',{name:'Character spacing',exact:true}).fill('0.1');await page.keyboard.press('Escape');
  check(await page.locator('summary:focus').innerText()==='More formatting','Escape focus lost');
  await page.getByRole('textbox',{name:'Edit text on page',exact:true}).fill('First line\nSecond line');await page.getByRole('textbox',{name:'Text box content on page',exact:true}).waitFor();
  const desktop=await metrics();check(desktop.stage>700&&desktop.formatting<120,'Editing area too short');
  const popup=page.locator('.toolbar-details[open] .toolbar-popover');
  await page.getByText('Layout & spacing',{exact:true}).click();check(await within(popup),'Desktop popup outside viewport');check((await metrics()).stage===desktop.stage,'Popup shrinks document');
  await page.getByRole('spinbutton',{name:'Text box character spacing',exact:true}).fill('0.2');await popup.getByRole('button',{name:'Done',exact:true}).click();check(await page.locator('summary:focus').innerText()==='Layout & spacing','Done focus lost');
  await page.getByText('Edit details',{exact:true}).click();await page.getByText(/Preview sends the source PDF, committed edit recipe/).waitFor();await page.keyboard.press('Escape');
  const responsive=[];for(const width of [760,390,320]){
    await page.setViewportSize({width,height:900});const item={width,...await metrics()};responsive.push(item);check(!item.overflow&&item.stage>500,`Cramped viewport ${width}`);
    check(await within(page.locator('.document-actions>button.primary')),'Download outside viewport');await page.getByText('Layout & spacing',{exact:true}).click();check(await within(popup),'Mobile popup outside viewport');check((await metrics()).stage===item.stage,'Mobile popup shrinks document');
    await page.getByRole('spinbutton',{name:'Text box width',exact:true}).fill('240');await page.keyboard.press('Escape');await page.screenshot({path:`/private/tmp/pdf-tool-toolbar-final-${width}.png`});
  }
  await page.setViewportSize({width:1280,height:1000});await page.waitForLoadState('networkidle');const responses=[];const capture=async r=>{if(r.url().includes('/jobs/')||r.url().endsWith('/upload')){const body=await r.json().catch(()=>({}));responses.push({status:r.status(),code:body.code,detail:body.detail,ok:body.ok});}};page.on('response',capture);for(let attempt=0;attempt<4;attempt++){await page.getByRole('button',{name:'Preview text box Server',exact:true}).click();await Promise.race([page.getByText('Exact candidate PDF is visible.',{exact:false}).waitFor(),page.locator('.context-warning[role=alert]').waitFor()]);if(!await page.locator('.context-warning[role=alert]').count())break;check(responses.at(-1)?.detail?.code==='WORKER_BUSY',JSON.stringify(responses));/* Match server admission Retry-After while canceled analysis workers drain. */await new Promise(resolve=>setTimeout(resolve,1000));}page.off('response',capture);check(!await page.locator('.context-warning[role=alert]').count(),JSON.stringify(responses));check(!await page.locator('.toolbar-details[open]').count(),'Popup remains over preview');
  const text=await page.locator('[data-page-number="1"] .textLayer').innerText();check(text.includes('First line')&&!text.includes('Document page 1'),'Native PDF preview incorrect');
  await page.getByRole('button',{name:'Apply text box Browser',exact:true}).click();await page.getByRole('button',{name:'Undo source text expansion Browser',exact:true}).click();await page.locator('[data-page-number="1"] .textLayer').getByText('Document page 1',{exact:true}).waitFor();await page.getByRole('button',{name:'Redo Browser',exact:true}).click();await page.getByRole('button',{name:'Undo source text expansion Browser',exact:true}).waitFor();
  await page.screenshot({path:'/private/tmp/pdf-tool-toolbar-final-desktop.png'});await page.setViewportSize({width:320,height:900});await page.getByRole('combobox',{name:'Editing tool',exact:true}).selectOption('select');await page.getByRole('button',{name:'Next page',exact:true}).click();await page.getByRole('button',{name:'Previous page',exact:true}).waitFor({state:'visible'});
  await page.getByRole('button',{name:'Close',exact:true}).click();return {passed:true,reading,desktop,responsive,focus:true,previewApplyUndoRedo:true,mobileToolPicker:true};
}

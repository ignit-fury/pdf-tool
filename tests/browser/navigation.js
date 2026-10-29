// Existing Playwright connector; synthetic fixtures from build_navigation_fixtures.py.
async(page)=>{
  const root=page.__navigationFixtureRoot||'/private/tmp/pdf-tool-navigation-20261029';
  const check=(value,message)=>{if(!value)throw Error(message);};
  await page.addInitScript(()=>{
    let Original=window.Worker;while(!Function.prototype.toString.call(Original).includes('[native code]'))Original=Object.getPrototypeOf(Original);
    window.__navigationOriginalWorker=Original;window.__navigationPreparations=0;window.__navigationFault=null;window.__navigationHold=null;window.__navigationHeld=null;
    window.Worker=class extends Original{
      postMessage(message,...args){
        if(message?.action==='GetDocRequest')window.__navigationPreparations++;
        if(window.__navigationFault&&window.__navigationFault===message?.action){window.__navigationFault=null;throw Error('Synthetic PDF preparation failure');}
        if(window.__navigationHold&&window.__navigationHold===message?.action){window.__navigationHold=null;window.__navigationHeld={worker:this,message,args};return;}
        return super.postMessage(message,...args);
      }
    };
  });
  await page.goto(page.__navigationBaseUrl||'http://127.0.0.1:8768/');
  const requests=[];const listener=request=>{const path=new URL(request.url()).pathname;if(path==='/upload'||path.startsWith('/jobs/'))requests.push(path);};page.on('request',listener);
  const open=async file=>{await page.locator('input[aria-label="Open PDF file"]').setInputFiles(`${root}/${file}`);await page.waitForFunction(()=>!!document.querySelector('.document-actions button.primary')&&!document.querySelector('.document-actions button.primary').disabled);};
  const top=name=>page.locator('.document-actions').getByRole('button',{name,exact:true});
  const outline=()=>page.getByRole('region',{name:'Document outline',exact:true});
  const history=()=>page.getByRole('region',{name:'Document history',exact:true});
  const atPage=async number=>page.waitForFunction(n=>document.querySelector('.page-controls>span')?.textContent.trim().startsWith(`${n} /`),number);
  const save=async name=>{const download=page.waitForEvent('download');await page.locator('.document-actions button.primary').click();await(await download).saveAs(`${root}/${name}.pdf`);};
  await open('bookmarks.pdf');await top('Outline').click();await outline().getByRole('button',{name:'Introduction',exact:true}).waitFor();
  check(await page.evaluate(()=>document.activeElement?.textContent.includes('Outline')),'Outline heading must receive focus');
  await outline().getByRole('button',{name:'Collapse Introduction',exact:true}).click();check(!await outline().getByRole('button',{name:'Named chapter',exact:true}).count(),'Collapsed child remains visible');
  await outline().getByRole('button',{name:'Expand Introduction',exact:true}).click();await outline().getByRole('button',{name:'Named chapter',exact:true}).click();await atPage(4);
  check(await page.locator('.zoom select').inputValue()==='1.15','Bookmark changed zoom');
  await outline().getByRole('button',{name:'Last chapter',exact:true}).click();await atPage(12);
  check(await outline().getByRole('button',{name:'External website',exact:true}).isDisabled(),'External action must not be opened');
  check(await outline().getByRole('button',{name:'Document script',exact:true}).isDisabled(),'Document script must not execute');
  await outline().getByRole('button',{name:'Named chapter',exact:true}).click();await atPage(4);check(!requests.length,'Outline uploaded a document');
  await outline().getByRole('button',{name:'Introduction',exact:true}).click();await atPage(1);
  await page.evaluate(()=>window.__navigationHold='GetDestination');await outline().getByRole('button',{name:'Named chapter',exact:true}).click();await page.waitForFunction(()=>!!window.__navigationHeld);
  await page.getByRole('button',{name:'Next page',exact:true}).click();await atPage(2);
  await page.evaluate(async()=>{const held=window.__navigationHeld;await new Promise(resolve=>{const listener=event=>{if(event.data.callbackId===held.message.callbackId){held.worker.removeEventListener('message',listener);resolve();}};held.worker.addEventListener('message',listener);window.__navigationOriginalWorker.prototype.postMessage.call(held.worker,held.message,...held.args);});window.__navigationHeld=null;});
  check((await page.locator('.page-controls>span').innerText()).startsWith('2 /'),'Delayed bookmark overrode newer page navigation');
  await outline().getByRole('button',{name:'Named chapter',exact:true}).click();await atPage(4);
  await top('Page tools').click();await page.getByRole('button',{name:'Insert before',exact:true}).click();await top('Undo blank insertion Browser').waitFor();
  await top('Outline').click();await outline().getByRole('button',{name:'Named chapter',exact:true}).click();await atPage(5);
  await top('Page tools').click();await page.getByRole('button',{name:'Rotate clockwise 90°',exact:true}).click();await top('Undo page rotation Browser').waitFor();
  await top('Outline').click();await outline().getByRole('button',{name:'Introduction',exact:true}).click();await atPage(1);
  await top('Insert text').click();await page.getByRole('button',{name:'Insert text on page 1',exact:true}).click({position:{x:100,y:350}});
  await page.getByRole('textbox',{name:'Text box content on page',exact:true}).fill('History preserves searchable inserted text.');await page.getByRole('button',{name:'Preview text box Server',exact:true}).click();await page.getByText('Exact candidate PDF is visible.',{exact:false}).waitFor();await page.getByRole('button',{name:'Apply text box Browser',exact:true}).click();await top('Undo text insertion Browser').waitFor();
  await page.locator('input[aria-label="Insert image file"]').setInputFiles(`${root}/image.png`);await page.getByRole('spinbutton',{name:'Image width',exact:true}).fill('80');await page.getByRole('spinbutton',{name:'Image left',exact:true}).fill('450');await page.getByRole('spinbutton',{name:'Image top',exact:true}).fill('500');await page.getByRole('button',{name:'Apply image Browser',exact:true}).click();await top('Undo image placement Browser').waitFor();await save('latest');
  await top('History').click();await history().getByRole('heading',{name:'History Browser',exact:true}).waitFor();check(await history().getByRole('button').count()===5,'History must contain original plus four committed operations');
  const count=requests.length,preparations=await page.evaluate(()=>window.__navigationPreparations);
  await history().getByRole('button',{name:'Restore state 0: Original document',exact:true}).click();await top('Undo Browser').waitFor();check(await top('Undo Browser').isDisabled(),'Original state still has Undo');
  check(await history().getByRole('button',{name:'Restore state 0: Original document',exact:true}).getAttribute('aria-current')==='step','History did not retain its current marker');
  check(await page.evaluate(()=>document.activeElement?.tagName==='H2'&&document.activeElement.textContent.includes('History')),'History restoration lost keyboard focus');await save('restored-original');
  check(await page.evaluate(()=>window.__navigationPreparations)===preparations+1,'Multi-step jump prepared intermediate PDFs');check(requests.length===count,'History jump uploaded');
  await history().getByRole('button',{name:'Restore state 4: Insert image',exact:true}).click();await top('Undo image placement Browser').waitFor();await save('restored-latest');
  await page.evaluate(()=>window.__navigationFault='GetDocRequest');await history().getByRole('button',{name:'Restore state 0: Original document',exact:true}).click();
  await history().getByRole('alert').waitFor();check(await history().getByRole('button',{name:'Restore state 4: Insert image',exact:true}).getAttribute('aria-current')==='step','Failed preparation changed history');await save('after-failed-restore');
  await history().getByRole('button',{name:'Restore state 2: Rotate page',exact:true}).click();await top('Undo page rotation Browser').waitFor();await save('restored-middle');
  await top('Redo Browser').click();await top('Undo text insertion Browser').waitFor();await top('Redo Browser').click();await top('Undo image placement Browser').waitFor();await save('redone-latest');
  await history().getByRole('button',{name:'Restore state 1: Insert blank page',exact:true}).click();await top('Undo blank insertion Browser').waitFor();
  await top('Page tools').click();await page.getByRole('button',{name:'Rotate clockwise 90°',exact:true}).click();await top('Undo page rotation Browser').waitFor();await top('History').click();check(await history().getByRole('button').count()===3,'New branch retained abandoned future');check(await top('Redo Browser').isDisabled(),'New branch retained Redo');
  const widths=[];for(const width of [760,320,1280]){await page.setViewportSize({width,height:1000});const size=await page.evaluate(()=>({body:document.body.scrollWidth,stage:document.querySelector('.continuous-stage').getBoundingClientRect().height}));check(size.body<=width&&size.stage>=150,'Unusable responsive history');widths.push({width,...size});}
  await page.screenshot({path:`root/history.png`.replace('root',root)});
  await top('Outline').click();await outline().getByRole('button',{name:'Introduction',exact:true}).waitFor();await page.evaluate(()=>window.__navigationHold='GetDestination');await outline().getByRole('button',{name:'Named chapter',exact:true}).click();await page.waitForFunction(()=>!!window.__navigationHeld);
  await open('source.pdf');await top('Outline').click();await outline().getByText('No bookmarks in this document.',{exact:true}).waitFor();await atPage(1);
  await page.evaluate(()=>{const held=window.__navigationHeld;try{window.__navigationOriginalWorker.prototype.postMessage.call(held.worker,held.message,...held.args);}catch{}window.__navigationHeld=null;window.__navigationHold=null;window.Worker=window.__navigationOriginalWorker;});
  check(!await outline().getByRole('button',{name:'Named chapter',exact:true}).count(),'Old outline leaked into new source');
  page.off('request',listener);
  return {passed:true,localOutline:true,namedDestination:true,afterPageInsertion:true,mixedHistory:true,singlePreparation:true,exactDownloads:true,failureAtomic:true,newBranch:true,staleOutline:true,widths};
}

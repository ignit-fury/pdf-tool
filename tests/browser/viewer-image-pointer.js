// Any open synthetic fixture; this draft is canceled after checking real pointer geometry.
async(page)=>{
  const root=page.__viewerFixtureRoot||'/private/tmp/pdf-tool-viewer-20261029';
  await page.locator('input[aria-label="Insert image file"]').setInputFiles(`${root}/image.png`);
  const left=page.getByRole('spinbutton',{name:'Image left',exact:true});
  const initial=Number(await left.inputValue());
  const handle=page.getByRole('button',{name:'Move selected image',exact:true});
  await handle.scrollIntoViewIfNeeded();const a=await handle.boundingBox();
  await page.mouse.move(a.x+a.width/2,a.y+a.height/2);await page.mouse.down();await page.mouse.move(a.x+a.width/2+23,a.y+a.height/2+11.5,{steps:3});await page.mouse.up();
  if(Math.abs(Number(await left.inputValue())-initial-20)>.05)throw new Error('Pointer move did not use physical page coordinates');
  const resize=page.getByRole('button',{name:'Resize selected image se',exact:true});
  await resize.scrollIntoViewIfNeeded();const b=await resize.boundingBox();
  const oldWidth=Number(await page.getByRole('spinbutton',{name:'Image width',exact:true}).inputValue());
  await page.mouse.move(b.x+b.width/2,b.y+b.height/2);await page.mouse.down();await page.mouse.move(b.x+b.width/2+23,b.y+b.height/2+10,{steps:3});await page.mouse.up();
  const width=Number(await page.getByRole('spinbutton',{name:'Image width',exact:true}).inputValue()),height=Number(await page.getByRole('spinbutton',{name:'Image height',exact:true}).inputValue());
  if(Math.abs(width-oldWidth-20)>.05||Math.abs(width/height-1.6)>.01)throw new Error('Resize lost physical geometry/aspect lock');
  await page.screenshot({path:`${root}/image-handles.png`});
  await page.getByRole('button',{name:'Cancel image changes',exact:true}).click();
  return {passed:true,movedPoints:20,resizedPoints:20,aspectRatio:width/height};
}

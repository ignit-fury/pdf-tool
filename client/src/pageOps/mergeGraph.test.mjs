import test from 'node:test';
import assert from 'node:assert/strict';
import {PDFDocument,PDFObjectCopier,PDFPage,PDFName,PDFString,PDFHexString,PDFDict,PDFArray} from '@cantoo/pdf-lib';

const n=PDFName.of;
const get=(pdf,obj,key)=>pdf.context.lookup(obj.get(n(key)));
const save=pdf=>pdf.save({updateFieldAppearances:false});
async function importGraph(source,destination,filename='invoice.pdf') {
  const {preflightMergeGraph,importMergeGraph}=await import('./mergeGraph.mjs');
  const preflight=preflightMergeGraph(source,{destination,filename});
  const copier=PDFObjectCopier.for(source.context,destination.context),pageMap=new Map();
  for(const page of source.getPages())pageMap.set(page.ref,copier.copy(page.ref));
  for(const ref of pageMap.values())destination.addPage(PDFPage.of(destination.context.lookup(ref),ref,destination));
  importMergeGraph({source,destination,copier,pageMap,prefix:preflight.prefix,preflight,filename});
  return {pdf:await PDFDocument.load(await save(destination)),preflight};
}
async function forms(fieldName='customer.name') {
  const pdf=await PDFDocument.create(),page=pdf.addPage([300,400]);
  const form=pdf.getForm(),text=form.createTextField(fieldName);
  text.setText('kept value');text.addToPage(page,{x:20,y:40,width:120,height:20});
  text.addToPage(page,{x:20,y:80,width:120,height:20});
  const radio=form.createRadioGroup('choice');
  radio.addOptionToPage('A',page,{x:20,y:120,width:15,height:15});
  radio.addOptionToPage('B',page,{x:50,y:120,width:15,height:15});radio.select('B');
  const choice=form.createDropdown('country');choice.addOptions(['one','two']);choice.select('two');
  choice.addToPage(page,{x:20,y:160,width:100,height:20});
  const acro=get(pdf,pdf.catalog,'AcroForm');
  const fields=get(pdf,acro,'Fields');acro.set(n('CO'),pdf.context.obj([fields.get(0)]));
  acro.set(n('NeedAppearances'),pdf.context.obj(true));
  // DA uses an escaped PDF name. Resource aliases and field names are different namespaces.
  const font=pdf.context.register(pdf.context.obj({Type:'Font',Subtype:'Type1',BaseFont:'Courier'}));
  const helvetica=await pdf.embedFont('Helvetica');
  acro.set(n('DR'),pdf.context.obj({Font:{Helv:font,Helvetica:helvetica.ref}}));
  acro.set(n('DA'),PDFString.of('/H#65lv 11 Tf 0 g'));
  text.acroField.dict.delete(n('DA'));
  return PDFDocument.load(await save(pdf));
}

test('one copier preserves real hierarchical, multi-widget, radio and choice fields on inserted pages',async()=>{
  const source=await forms(),destination=await forms();
  destination.catalog.set(n('Lang'),PDFString.of('en-US'));
  const originalFont=get(destination,get(destination,destination.catalog,'AcroForm'),'DR').lookup(n('Font')).get(n('Helv'));
  const {pdf,preflight}=await importGraph(source,destination);
  assert.equal(preflight.formCount,3);assert.equal(preflight.collisionCount,3);
  const form=pdf.getForm();
  assert.equal(form.getTextField(`${preflight.prefix}.customer.name`).getText(),'kept value');
  assert.equal(form.getRadioGroup(`${preflight.prefix}.choice`).getSelected(),'B');
  assert.deepEqual(form.getDropdown(`${preflight.prefix}.country`).getSelected(),['two']);
  const imported=form.getTextField(`${preflight.prefix}.customer.name`).acroField;
  assert.equal(imported.getWidgets().length,2);
  for(const widget of imported.getWidgets()) {
    assert.equal(widget.dict.get(n('P')).toString(),pdf.getPage(1).ref.toString());
    assert.ok(get(pdf,widget.dict,'AP') instanceof PDFDict);
    assert.ok(get(pdf,pdf.getPage(1).node,'Annots').asArray().some(ref=>pdf.context.lookup(ref)===widget.dict));
  }
  const acro=get(pdf,pdf.catalog,'AcroForm'),dr=get(pdf,acro,'DR'),fonts=get(pdf,dr,'Font');
  assert.equal(fonts.get(n('Helv')).toString(),originalFont.toString());
  assert.notEqual(fonts.get(n(`${preflight.prefix}_Helv`)).toString(),fonts.get(n('Helv')).toString());
  const parent=get(pdf,imported.dict,'Parent');
  assert.match(get(pdf,parent,'DA')?.decodeText()??get(pdf,get(pdf,parent,'Parent'),'DA').decodeText(),new RegExp(`/${preflight.prefix}(?:_f\\d+)?_Helv 11 Tf`));
  assert.equal(get(pdf,acro,'NeedAppearances').asBoolean(),true);
  assert.equal(get(pdf,acro,'CO').size(),2);
  assert.equal(get(pdf,pdf.catalog,'Lang').decodeText(),'en-US');
});

test('field namespace does not depend on DR collisions and uses an unused deterministic prefix',async()=>{
  const source=await forms('unique'),destination=await forms('import_1.name');
  const {pdf,preflight}=await importGraph(source,destination);
  assert.equal(preflight.prefix,'import_2');
  assert.equal(preflight.collisionCount,2); // radio and dropdown still collide
  assert.equal(pdf.getForm().getTextField('import_2.unique').getText(),'kept value');
  assert.match(preflight.notices.join(' '),/duplicate names/);
});

test('nested styled outlines, named destinations and links target actual inserted page references',async()=>{
  const source=await PDFDocument.create();source.addPage();source.addPage();
  const destination=await PDFDocument.create();destination.addPage();
  const ctx=source.context,outline=ctx.register(ctx.obj({Type:'Outlines'}));
  const first=ctx.register(ctx.obj({Title:PDFHexString.fromText('Section α'),Parent:outline,C:[1,0,0],F:2,Dest:PDFString.of('chapter')}));
  const child=ctx.register(ctx.obj({Title:PDFString.of('child'),Parent:first,Dest:[source.getPage(1).ref,'XYZ',10,20,null]}));
  ctx.lookup(first).set(n('First'),child);ctx.lookup(first).set(n('Last'),child);ctx.lookup(first).set(n('Count'),ctx.obj(1));
  ctx.lookup(outline).set(n('First'),first);ctx.lookup(outline).set(n('Last'),first);ctx.lookup(outline).set(n('Count'),ctx.obj(2));
  source.catalog.set(n('Outlines'),outline);
  source.catalog.set(n('Names'),ctx.obj({Dests:{Names:[PDFString.of('chapter'),[source.getPage(0).ref,'Fit']]}}));
  const link=ctx.register(ctx.obj({Type:'Annot',Subtype:'Link',Rect:[0,0,30,30],A:{S:'GoTo',D:PDFString.of('chapter')}}));
  source.getPage(1).node.set(n('Annots'),ctx.obj([link]));
  const old=destination.context.register(destination.context.obj({Type:'Outlines'}));
  const oldItem=destination.context.register(destination.context.obj({Title:PDFString.of('existing'),Parent:old,Dest:[destination.getPage(0).ref,'Fit']}));
  destination.context.lookup(old).set(n('First'),oldItem);destination.context.lookup(old).set(n('Last'),oldItem);destination.context.lookup(old).set(n('Count'),destination.context.obj(1));
  destination.catalog.set(n('Outlines'),old);
  destination.catalog.set(n('Names'),destination.context.obj({Dests:{Names:[PDFString.of('chapter'),[destination.getPage(0).ref,'Fit']]},EmbeddedFiles:{Names:[]}}));
  const {pdf,preflight}=await importGraph(source,destination);
  assert.equal(preflight.bookmarkCount,2);
  const root=get(pdf,pdf.catalog,'Outlines'),existing=get(pdf,root,'First'),file=get(pdf,existing,'Next'),section=get(pdf,file,'First'),nested=get(pdf,section,'First');
  assert.equal(get(pdf,existing,'Title').decodeText(),'existing');
  assert.equal(get(pdf,file,'Title').decodeText(),'invoice.pdf');
  assert.equal(get(pdf,section,'Title').decodeText(),'Section α');
  assert.equal(get(pdf,section,'F').asNumber(),2);assert.deepEqual(get(pdf,section,'C').asArray().map(v=>v.asNumber()),[1,0,0]);
  assert.equal(get(pdf,section,'Dest').get(0).toString(),pdf.getPage(1).ref.toString());
  assert.equal(get(pdf,nested,'Dest').get(0).toString(),pdf.getPage(2).ref.toString());
  const annotation=pdf.context.lookup(get(pdf,pdf.getPage(2).node,'Annots').get(0));
  assert.equal(get(pdf,get(pdf,annotation,'A'),'D').get(0).toString(),pdf.getPage(1).ref.toString());
  assert.ok(get(pdf,pdf.catalog,'Names').has(n('EmbeddedFiles')));
  assert.equal(get(pdf,get(pdf,get(pdf,pdf.catalog,'Names'),'Dests'),'Names').size(),4);
});

test('preflight refuses XFA, JavaScript, field cycles and unsafe DA without mutating real inputs',async()=>{
  const {preflightMergeGraph}=await import('./mergeGraph.mjs');
  for(const [kind,code] of [['XFA','MERGE_XFA_UNSUPPORTED'],['JS','MERGE_ACTION_UNSUPPORTED'],['cycle','MERGE_FIELD_GRAPH_UNSAFE'],['DA','MERGE_DA_UNSAFE']]) {
    const source=await forms(),destination=await forms('other'),acro=get(source,source.catalog,'AcroForm');
    if(kind==='XFA')acro.set(n('XFA'),PDFString.of('xml'));
    if(kind==='JS')source.getPage(0).node.set(n('AA'),source.context.obj({O:{S:'JavaScript',JS:PDFString.of('app.alert(1)')}}));
    if(kind==='cycle') {const field=get(source,acro,'Fields').get(0);source.context.lookup(field).set(n('Kids'),source.context.obj([field]));}
    if(kind==='DA')acro.set(n('DA'),PDFString.of('/Helv 12 Tf (unsafe /Helv) Tj'));
    const before=await save(source),target=await save(destination);
    assert.throws(()=>preflightMergeGraph(source,{destination}),error=>error.code===code);
    assert.deepEqual(await save(source),before);assert.deepEqual(await save(destination),target);
  }
});

test('preflight bounds graph depth and announces absent forms and bookmarks',async()=>{
  const {preflightMergeGraph}=await import('./mergeGraph.mjs');
  const source=await PDFDocument.create();source.addPage();
  const review=preflightMergeGraph(source);
  assert.equal(review.formCount,0);assert.equal(review.bookmarkCount,0);
  assert.ok(review.notices.includes('No form fields in the imported PDF.'));
  assert.ok(review.notices.includes('No bookmarks to merge.'));
  let deep=source.context.obj({});source.catalog.set(n('Probe'),deep);
  for(let i=0;i<66;i++) {const child=source.context.obj({});deep.set(n('Child'),child);deep=child;}
  assert.throws(()=>preflightMergeGraph(source),error=>error.code==='MERGE_GRAPH_LIMIT');
});

test('ordinary generated text forms recover unambiguous AP fonts and announce no field collisions',async()=>{
  const source=await PDFDocument.create(),page=source.addPage();
  const field=source.getForm().createTextField('plain');field.setText('visible');field.addToPage(page);
  const loaded=await PDFDocument.load(await save(source)),destination=await PDFDocument.create();destination.addPage();
  const {pdf,preflight}=await importGraph(loaded,destination);
  assert.equal(pdf.getForm().getTextField(`${preflight.prefix}.plain`).getText(),'visible');
  assert.equal(preflight.collisionCount,0);assert.match(preflight.notices.join(' '),/No duplicate names found/);
});

test('an existing DR alias cannot collide with the independent imported resource namespace',async()=>{
  const source=await forms('unique'),destination=await forms('other');
  const fonts=get(destination,get(destination,get(destination,destination.catalog,'AcroForm'),'DR'),'Font');
  fonts.set(n('import_1_Helv'),fonts.get(n('Helv')));
  const {pdf,preflight}=await importGraph(source,destination);
  assert.equal(preflight.prefix,'import_2');
  assert.equal(pdf.getForm().getTextField('import_2.unique').getText(),'kept value');
});

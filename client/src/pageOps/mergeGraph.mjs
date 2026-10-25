import {PDFName,PDFDict,PDFArray,PDFStream,PDFString,PDFHexString,PDFRef,PDFNumber,PDFNull} from '@cantoo/pdf-lib';
import {pdfError,GRAPH_MAX_DEPTH,GRAPH_MAX_NODES} from './pdfDocument.mjs';

const n=PDFName.of;
const fail=code=>{throw pdfError(code);};
const resolve=(pdf,value)=>value===undefined?undefined:pdf.context.lookup(value);
const get=(pdf,dict,key)=>resolve(pdf,dict?.get(n(key)));
const text=value=>value instanceof PDFString||value instanceof PDFHexString?value.decodeText():value instanceof PDFName?value.decodeText():undefined;
function dict(pdf,value,code='MERGE_GRAPH_UNSAFE') {const result=resolve(pdf,value);if(!(result instanceof PDFDict))fail(code);return result;}
function array(pdf,value,code='MERGE_GRAPH_UNSAFE') {const result=resolve(pdf,value);if(!(result instanceof PDFArray))fail(code);return result.asArray();}
const safeResources=(pdf,value)=>{
  if(value===undefined)return undefined;
  const resources=dict(pdf,value,'MERGE_RESOURCES_UNSAFE');
  for(const [key,raw] of resources.entries()) {
    if(key===n('ProcSet')) {array(pdf,raw,'MERGE_RESOURCES_UNSAFE');continue;}
    if(!['Font','XObject','ExtGState','ColorSpace','Pattern','Shading','Properties'].some(item=>key===n(item)))fail('MERGE_RESOURCES_UNSAFE');
    dict(pdf,raw,'MERGE_RESOURCES_UNSAFE');
  }
  return resources;
};

/** DA is a small PDF program, not a string to search/replace. Only text-state/color operators are accepted. */
function rewriteDA(pdf,value,resources,prefix,button=false) {
  if(value===undefined)return undefined;
  const input=text(resolve(pdf,value));if(input===undefined)fail('MERGE_DA_UNSAFE');
  const tokens=[],pattern=/\s+|%[^\r\n]*|\/[^\s()[\]<>\/%]+|[-+]?(?:\d+\.?\d*|\.\d+)|[A-Za-z]+/gy;
  let offset=0;
  while(offset<input.length) {
    pattern.lastIndex=offset;const match=pattern.exec(input);if(!match)fail('MERGE_DA_UNSAFE');
    offset=pattern.lastIndex;if(!/^\s|^%/.test(match[0]))tokens.push(match[0]);
  }
  const arities={g:1,rg:3,k:4,Tc:1,Tw:1,Tz:1,TL:1,Tr:1,Ts:1};
  let operands=[],out=[];
  for(const token of tokens) {
    if(token.startsWith('/')||/^[-+.\d]/.test(token)) {operands.push(token);continue;}
    if(token==='Tf') {
      if(operands.length!==2||!operands[0].startsWith('/')||!Number.isFinite(Number(operands[1])))fail('MERGE_DA_UNSAFE');
      const font=operands[0].slice(1).replace(/#([\da-f]{2})/gi,(_,hex)=>String.fromCharCode(parseInt(hex,16)));
      // cantoo emits this intentionally unused marker for button-only appearances.
      if(button&&font==='dummy__noop'&&Number(operands[1])===0) {operands=[];continue;}
      if(font.includes('#')||!get(pdf,resources,'Font')?.has(n(font)))fail('MERGE_DA_UNSAFE');
      out.push(n(`${prefix}_${font}`).toString(),operands[1],token);
    }else {
      if(!(token in arities)||operands.length!==arities[token]||operands.some(v=>!Number.isFinite(Number(v))))fail('MERGE_DA_UNSAFE');
      out.push(...operands,token);
    }
    operands=[];
  }
  if(operands.length)fail('MERGE_DA_UNSAFE');
  return PDFString.of(out.join(' '));
}

/** Bound every reachable object before copying; semantic tree walks below reject ambiguous cycles. */
function scanGraph(pdf) {
  const seen=new Set();let nodes=0;
  const visit=(raw,depth)=>{
    if(depth>GRAPH_MAX_DEPTH||++nodes>GRAPH_MAX_NODES)fail('MERGE_GRAPH_LIMIT');
    const object=resolve(pdf,raw);if(object===undefined)fail('MERGE_GRAPH_UNSAFE');
    if(seen.has(object))return;seen.add(object);
    if(object instanceof PDFArray)for(const entry of object.asArray())visit(entry,depth+1);
    const d=object instanceof PDFStream?object.dict:object instanceof PDFDict?object:undefined;
    if(d) {
      if(d.has(n('XFA')))fail('MERGE_XFA_UNSUPPORTED');
      if(d.has(n('AA'))||d.has(n('JS'))||d.has(n('JavaScript')))fail('MERGE_ACTION_UNSUPPORTED');
      if(d.has(n('A'))) {
        const action=get(pdf,d,'A');
        if(action instanceof PDFDict&&action.has(n('S'))&&(!['GoTo','URI'].some(key=>get(pdf,action,'S')===n(key))||action.has(n('Next'))))fail('MERGE_ACTION_UNSUPPORTED');
      }
      const action=get(pdf,d,'S');
      if(action instanceof PDFName&&!['GoTo','URI','Transparency','Luminosity','Alpha'].some(key=>action===n(key))) {
        // /S also identifies benign structure elements; only actual action dictionaries are constrained here.
        if(d.has(n('Type'))&&get(pdf,d,'Type')===n('Action')||['JavaScript','Launch','GoToR','GoToE','SubmitForm','ResetForm','ImportData','Rendition','Sound','Movie','Hide','Named','SetOCGState','Trans'].some(key=>action===n(key)))fail('MERGE_ACTION_UNSUPPORTED');
      }
      for(const [key,value] of d.entries()) {
        // These are validated by field/outline/page membership walks instead of following backlinks.
        if(['Parent','P','Prev'].some(item=>key===n(item)))continue;
        visit(value,depth+1);
      }
    }
  };
  visit(pdf.catalog,0);
}

function appearanceResources(pdf,field,kids,inherited) {
  // Some producers (including cantoo) keep font resources only in AP. Recover
  // missing default fonts only when all appearances agree on the same object.
  const found=new Map(),baseFonts=get(pdf,inherited,'Font');
  const stream=(raw,depth=0)=>{
    const value=resolve(pdf,raw);
    if(value instanceof PDFStream) {
      const resources=safeResources(pdf,value.dict.get(n('Resources'))),fonts=get(pdf,resources,'Font');
      if(fonts)for(const [key,font] of fonts.entries()) {
        if(baseFonts?.has(key))continue;
        if(found.has(key)&&resolve(pdf,found.get(key))!==resolve(pdf,font))fail('MERGE_RESOURCES_UNSAFE');found.set(key,font);
      }
    }else if(value instanceof PDFDict&&depth===0)for(const [,child] of value.entries())stream(child,depth+1);
    else fail('MERGE_AP_UNSAFE');
  };
  for(const candidate of [field,...kids.map(raw=>dict(pdf,raw))]) {
    const ap=get(pdf,candidate,'AP');if(ap)for(const [,value] of dict(pdf,ap).entries())stream(value);
  }
  if(!found.size)return inherited;
  const resources=inherited?inherited.clone(pdf.context):pdf.context.obj({}),fonts=baseFonts?baseFonts.clone(pdf.context):pdf.context.obj({});
  for(const [key,font] of found)fonts.set(key,font);resources.set(n('Font'),fonts);return resources;
}

function collectFields(pdf) {
  // An annotation belongs to one Annots slot on one page. The shared copier
  // preserves object identity, so accepting aliases here would let a later
  // per-page normalization transform the same mutable dictionary twice.
  const owners=new Set(),members=new Map();
  for(const page of pdf.getPages()) {
    const annotations=page.node.has(n('Annots'))?array(pdf,page.node.get(n('Annots'))):[];
    for(const raw of annotations) {
      const annotation=dict(pdf,raw),widget=get(pdf,annotation,'Subtype')===n('Widget');
      const code=widget?'MERGE_FIELD_GRAPH_UNSAFE':'MERGE_GRAPH_UNSAFE',owner=annotation.get(n('P'));
      if(owners.has(annotation)||owner&&(!(owner instanceof PDFRef)||owner.toString()!==page.ref.toString()))fail(code);
      owners.add(annotation);if(widget)members.set(annotation,page.ref);
    }
  }
  const acroRaw=pdf.catalog.get(n('AcroForm'));
  if(!acroRaw) {
    if(members.size)fail('MERGE_FIELD_GRAPH_UNSAFE');
    return {acro:undefined,fields:[],roots:[],names:[]};
  }
  const acro=dict(pdf,acroRaw,'MERGE_FIELD_GRAPH_UNSAFE'),fields=[],names=[],seen=new Set();
  const walk=(raw,parent,path,ft,dr,da,depth)=>{
    if(depth>GRAPH_MAX_DEPTH||fields.length>=GRAPH_MAX_NODES)fail('MERGE_GRAPH_LIMIT');
    const field=dict(pdf,raw,'MERGE_FIELD_GRAPH_UNSAFE');if(seen.has(field))fail('MERGE_FIELD_GRAPH_UNSAFE');seen.add(field);
    const ownName=get(pdf,field,'T');if(ownName&&text(ownName)===undefined)fail('MERGE_FIELD_GRAPH_UNSAFE');
    const part=text(ownName);if(part?.includes('.'))fail('MERGE_FIELD_GRAPH_UNSAFE');
    const full=part?[...path,part]:path;
    ft=get(pdf,field,'FT')??ft;dr=safeResources(pdf,field.get(n('DR')))??dr;da=field.get(n('DA'))??da;
    if(ft&&!['Tx','Btn','Ch','Sig'].some(type=>ft===n(type)))fail('MERGE_FIELD_TYPE_UNSUPPORTED');
    if(parent&&resolve(pdf,field.get(n('Parent')))!==parent||!parent&&field.has(n('Parent')))fail('MERGE_FIELD_GRAPH_UNSAFE');
    const kids=field.has(n('Kids'))?array(pdf,field.get(n('Kids')),'MERGE_FIELD_GRAPH_UNSAFE'):[];
    dr=appearanceResources(pdf,field,kids,dr);
    const widget=get(pdf,field,'Subtype')===n('Widget');
    if(widget) {
      if(!members.has(field)||field.has(n('P'))&&field.get(n('P')).toString()!==members.get(field).toString())fail('MERGE_FIELD_GRAPH_UNSAFE');
      const ap=get(pdf,field,'AP');
      if(ap) {
        if(!(ap instanceof PDFDict))fail('MERGE_AP_UNSAFE');
        const check=value=>{
          const item=resolve(pdf,value);
          if(item instanceof PDFStream) {safeResources(pdf,item.dict.get(n('Resources')));return;}
          if(!(item instanceof PDFDict))fail('MERGE_AP_UNSAFE');
          for(const [,stream] of item.entries())if(!(resolve(pdf,stream) instanceof PDFStream))fail('MERGE_AP_UNSAFE');
        };
        for(const [,value] of ap.entries())check(value);
      }
    }
    const terminal=!!ft&&(!kids.some(child=>dict(pdf,child).has(n('T'))))&&(!!part||!!get(pdf,field,'FT'));
    if(terminal) {if(!full.length||names.includes(full.join('.')))fail('MERGE_FIELD_GRAPH_UNSAFE');names.push(full.join('.'));}
    if(da)rewriteDA(pdf,da,dr,'validate',ft===n('Btn'));
    fields.push({raw,field,parent,ft,dr,da,widget,pageRef:members.get(field),terminal});
    for(const child of kids)walk(child,field,full,ft,dr,da,depth+1);
  };
  const roots=acro.has(n('Fields'))?array(pdf,acro.get(n('Fields')),'MERGE_FIELD_GRAPH_UNSAFE'):[];
  const dr=safeResources(pdf,acro.get(n('DR'))),da=acro.get(n('DA'));
  if(da&&dr)rewriteDA(pdf,da,dr,'validate');
  for(const raw of roots)walk(raw,undefined,[],undefined,dr,da,0);
  for(const member of members.keys())if(!seen.has(member))fail('MERGE_FIELD_GRAPH_UNSAFE');
  if(acro.has(n('CO')))for(const ref of array(pdf,acro.get(n('CO'))))if(!seen.has(resolve(pdf,ref)))fail('MERGE_FIELD_GRAPH_UNSAFE');
  return {acro,fields,roots,names,dr,da};
}

function collectDestinations(pdf) {
  const named=new Map(),seen=new Set();
  const put=(key,value)=>{if(key===undefined||named.has(key))fail('MERGE_DESTINATION_UNSAFE');named.set(key,value);};
  const legacy=get(pdf,pdf.catalog,'Dests');if(legacy)for(const [key,value] of dict(pdf,legacy).entries())put(key.decodeText(),value);
  const names=get(pdf,pdf.catalog,'Names'),root=names?get(pdf,dict(pdf,names),'Dests'):undefined;
  const walk=(raw,depth)=>{
    if(depth>GRAPH_MAX_DEPTH)fail('MERGE_GRAPH_LIMIT');
    const node=dict(pdf,raw,'MERGE_DESTINATION_UNSAFE');if(seen.has(node))fail('MERGE_DESTINATION_UNSAFE');seen.add(node);
    if(node.has(n('Names'))) {
      const values=array(pdf,node.get(n('Names')),'MERGE_DESTINATION_UNSAFE');if(values.length%2)fail('MERGE_DESTINATION_UNSAFE');
      for(let i=0;i<values.length;i+=2)put(text(resolve(pdf,values[i])),values[i+1]);
    }
    if(node.has(n('Kids')))for(const child of array(pdf,node.get(n('Kids'))))walk(child,depth+1);
  };
  if(root)walk(root,0);
  const pageRefs=new Set(pdf.getPages().map(page=>page.ref.toString()));
  const destination=(raw,trail=new Set())=>{
    const value=resolve(pdf,raw);
    if(trail.size>GRAPH_MAX_DEPTH)fail('MERGE_GRAPH_LIMIT');
    if(value instanceof PDFDict) {if(trail.has(value))fail('MERGE_DESTINATION_UNSAFE');trail.add(value);return destination(value.get(n('D')),trail);}
    const key=text(value);
    if(key!==undefined) {
      if(trail.has(key)||!named.has(key))fail('MERGE_DESTINATION_UNSAFE');trail.add(key);return destination(named.get(key),trail);
    }
    if(!(value instanceof PDFArray)||value.size()<2||!(value.get(0) instanceof PDFRef)||!pageRefs.has(value.get(0).toString()))fail('MERGE_DESTINATION_UNSAFE');
    const mode=resolve(pdf,value.get(1));
    const lengths={XYZ:5,Fit:2,FitH:3,FitV:3,FitR:6,FitB:2,FitBH:3,FitBV:3};
    if(!(mode instanceof PDFName)||lengths[mode.decodeText()]!==value.size())fail('MERGE_DESTINATION_UNSAFE');
    for(let i=2;i<value.size();i++) {
      const coordinate=resolve(pdf,value.get(i));
      if(coordinate===PDFNull&&mode!==n('FitR'))continue;
      if(!(coordinate instanceof PDFNumber)||!Number.isFinite(coordinate.asNumber()))fail('MERGE_DESTINATION_UNSAFE');
      if(mode===n('XYZ')&&i===4&&coordinate.asNumber()<0)fail('MERGE_DESTINATION_UNSAFE');
    }
    return value;
  };
  for(const value of named.values())destination(value);
  const targets=[];
  for(const page of pdf.getPages())for(const ref of page.node.Annots()?.asArray()??[]) {
    const annotation=dict(pdf,ref);
    if(annotation.has(n('Dest')))targets.push({dict:annotation,key:'Dest',target:destination(annotation.get(n('Dest')))});
    if(annotation.has(n('A'))) {
      const action=dict(pdf,annotation.get(n('A')),'MERGE_ACTION_UNSUPPORTED'),kind=get(pdf,action,'S');
      if(kind===n('GoTo'))targets.push({dict:action,key:'D',target:destination(action.get(n('D')))});
      else if(kind!==n('URI')||action.has(n('Next')))fail('MERGE_ACTION_UNSUPPORTED');
    }
  }
  return {named,destination,targets};
}

function collectOutlines(pdf,destinations) {
  const root=get(pdf,pdf.catalog,'Outlines');if(!root)return [];
  const seen=new Set();let count=0;
  const walk=(first,parent,depth)=>{
    if(depth>GRAPH_MAX_DEPTH)fail('MERGE_GRAPH_LIMIT');const items=[];let raw=first;
    while(raw) {
      const item=dict(pdf,raw,'MERGE_OUTLINE_UNSAFE');if(seen.has(item)||++count>GRAPH_MAX_NODES)fail('MERGE_OUTLINE_UNSAFE');seen.add(item);
      if(text(get(pdf,item,'Title'))===undefined||resolve(pdf,item.get(n('Parent')))!==parent)fail('MERGE_OUTLINE_UNSAFE');
      let target;
      if(item.has(n('Dest')))target=destinations.destination(item.get(n('Dest')));
      if(item.has(n('A'))) {
        const action=dict(pdf,item.get(n('A')));if(get(pdf,action,'S')!==n('GoTo')||action.has(n('Next'))||target)fail('MERGE_ACTION_UNSUPPORTED');
        target=destinations.destination(action.get(n('D')));
      }
      const children=item.has(n('First'))?walk(item.get(n('First')),item,depth+1):[];
      items.push({item,target,children});raw=item.get(n('Next'));
    }
    return items;
  };
  return walk(dict(pdf,root).get(n('First')),root,0);
}
const outlineCount=items=>items.reduce((count,item)=>count+1+outlineCount(item.children),0);

/** Pure preflight. The returned graph is internal; public review serializes only counts/notices. */
export function preflightMergeGraph(source,{destination,filename='import.pdf'}={}) {
  scanGraph(source);
  const forms=collectFields(source),existing=destination?collectFields(destination):{names:[]};
  const destinations=collectDestinations(source),outlines=collectOutlines(source,destinations);
  if(destination) {const dests=collectDestinations(destination);collectOutlines(destination,dests);}
  const existingResources=[existing.dr,...(existing.fields??[]).map(field=>field.dr)].filter(Boolean).flatMap(resources=>resources.entries().filter(([category])=>category!==n('ProcSet')).flatMap(([,value])=>dict(destination,value).keys().map(key=>key.decodeText())));
  let index=1;while(existing.names.some(name=>name===`import_${index}`||name.startsWith(`import_${index}.`))||existingResources.some(name=>name.startsWith(`import_${index}_`)))index++;
  const prefix=`import_${index}`,formCount=forms.names.length,collisionCount=forms.names.filter(name=>existing.names.includes(name)).length;
  const bookmarkCount=outlineCount(outlines),notices=[formCount?`${formCount} form fields will be kept with the “${prefix}” name prefix. ${collisionCount?`${collisionCount} duplicate names will be renamed.`:'No duplicate names found.'}`:'No form fields in the imported PDF.',bookmarkCount?`${bookmarkCount} bookmarks will be nested under “${filename}”.`:'No bookmarks to merge.'];
  return {prefix,formCount,collisionCount,bookmarkCount,notices,forms,destinations,outlines};
}

function aliasResources(pdf,resources,prefix) {
  const result=pdf.context.obj({});if(!resources)return result;
  for(const [category,value] of resources.entries()) {
    if(category===n('ProcSet')) {result.set(category,value);continue;}
    const categoryDict=dict(pdf,value),renamed=pdf.context.obj({});
    for(const [key,item] of categoryDict.entries())renamed.set(n(`${prefix}_${key.decodeText()}`),item);
    result.set(category,renamed);
  }
  return result;
}
function mergeResources(pdf,target,incoming) {
  for(const [key,value] of incoming.entries()) {
    if(key===n('ProcSet')) {if(!target.has(key))target.set(key,value);continue;}
    const next=dict(pdf,value),old=target.has(key)?dict(pdf,target.get(key)).clone(pdf.context):pdf.context.obj({});
    for(const [name,item] of next.entries()) {if(old.has(name))fail('MERGE_RESOURCES_UNSAFE');old.set(name,item);}
    target.set(key,old);
  }
}
/** All references, including pages, must pass through this identical memoized copier. */
export function importMergeGraph({source,destination,copier,pageMap,prefix,preflight,filename='import.pdf'}) {
  const graph=preflight??preflightMergeGraph(source,{destination,filename});prefix??=graph.prefix;
  const ctx=destination.context,copy=value=>copier.copy(value);
  const mappedTarget=value=>{
    const result=copy(value),page=pageMap.get(value.get(0));if(!page)fail('MERGE_DESTINATION_UNSAFE');result.set(0,page);return result;
  };
  for(const target of graph.destinations.targets)copy(target.dict).set(n(target.key),mappedTarget(target.target));
  const form=graph.forms;
  if(form.roots.length) {
    let acro=get(destination,destination.catalog,'AcroForm');
    if(!acro) {acro=ctx.obj({Fields:[]});destination.catalog.set(n('AcroForm'),ctx.register(acro));}
    const roots=get(destination,acro,'Fields')??ctx.obj([]);acro.set(n('Fields'),roots);
    const group=ctx.obj({T:PDFHexString.fromText(prefix),Kids:form.roots.map(copy)}),groupRef=ctx.register(group);
    if(form.da&&form.dr)group.set(n('DA'),rewriteDA(source,form.da,form.dr,prefix));
    if(form.dr)group.set(n('DR'),aliasResources(destination,copy(form.dr),prefix));
    for(const raw of form.roots)copy(raw) instanceof PDFRef?ctx.lookup(copy(raw)).set(n('Parent'),groupRef):copy(raw).set(n('Parent'),groupRef);
    roots.push(groupRef);
    const dr=(get(destination,acro,'DR')??ctx.obj({})).clone(ctx);acro.set(n('DR'),dr);
    if(form.dr)mergeResources(destination,dr,aliasResources(destination,copy(form.dr),prefix));
    for(const [index,entry] of form.fields.entries()) {
      const field=copy(entry.field);
      const resourcePrefix=`${prefix}_f${index}`;
      if(entry.da)field.set(n('DA'),rewriteDA(source,entry.da,entry.dr,resourcePrefix,entry.ft===n('Btn')));
      if(entry.dr) {
        const resources=aliasResources(destination,copy(entry.dr),resourcePrefix);field.set(n('DR'),resources);mergeResources(destination,dr,resources);
      }
      if(entry.widget) {
        field.set(n('P'),pageMap.get(entry.pageRef));
        const ap=get(destination,field,'AP');
        if(ap) {
          const materialize=raw=>{
            const value=resolve(destination,raw);
            if(value instanceof PDFStream) {if(!value.dict.has(n('Resources'))&&entry.dr)value.dict.set(n('Resources'),copy(entry.dr));}
            else for(const [,stream] of value.entries())materialize(stream);
          };
          for(const [,value] of ap.entries())materialize(value);
        }
      }
    }
    if(form.acro.has(n('NeedAppearances'))&&get(source,form.acro,'NeedAppearances')?.asBoolean())acro.set(n('NeedAppearances'),ctx.obj(true));
    if(form.acro.has(n('SigFlags'))) {
      const flags=(get(destination,acro,'SigFlags')?.asNumber()??0)|(get(source,form.acro,'SigFlags')?.asNumber()??0);acro.set(n('SigFlags'),ctx.obj(flags));
    }
    if(form.acro.has(n('CO'))) {
      const order=get(destination,acro,'CO')??ctx.obj([]);for(const raw of array(source,form.acro.get(n('CO'))))order.push(copy(raw));acro.set(n('CO'),order);
    }
  }
  if(graph.destinations.named.size) {
    let names=get(destination,destination.catalog,'Names');if(!names) {names=ctx.obj({});destination.catalog.set(n('Names'),names);}
    // Flatten only the destination-name tree; preserve every other Names category.
    const existing=collectDestinations(destination).named;
    const values=new Map([...existing].map(([key,value])=>[key,value]));
    for(const [key,value] of graph.destinations.named) {
      let alias=`${prefix}.${key}`,suffix=1;while(values.has(alias))alias=`${prefix}.${key}.${suffix++}`;
      values.set(alias,mappedTarget(graph.destinations.destination(value)));
    }
    const pairs=[...values].sort(([a],[b])=>a<b?-1:a>b?1:0).flatMap(([key,value])=>[PDFHexString.fromText(key),value]);
    names.set(n('Dests'),ctx.obj({Names:pairs}));
    destination.catalog.delete(n('Dests'));
  }
  if(graph.outlines.length) {
    let root=get(destination,destination.catalog,'Outlines'),rootRef=destination.catalog.get(n('Outlines'));
    if(!root) {root=ctx.obj({Type:'Outlines'});rootRef=ctx.register(root);destination.catalog.set(n('Outlines'),rootRef);}
    else if(!(rootRef instanceof PDFRef)) {rootRef=ctx.register(root);destination.catalog.set(n('Outlines'),rootRef);}
    const file=ctx.obj({Title:PDFHexString.fromText(filename),Parent:rootRef}),fileRef=ctx.register(file);
    const build=(items,parent)=>{
      const entries=items.map(item=>{
        const node=ctx.obj({Title:copy(item.item.get(n('Title'))),Parent:parent}),ref=ctx.register(node);
        for(const key of ['C','F'])if(item.item.has(n(key)))node.set(n(key),copy(item.item.get(n(key))));
        if(item.target)node.set(n('Dest'),mappedTarget(item.target));
        if(item.children.length) {
          const children=build(item.children,ref);node.set(n('First'),children[0].ref);node.set(n('Last'),children.at(-1).ref);
          const old=get(source,item.item,'Count')?.asNumber()??1;node.set(n('Count'),ctx.obj((old<0?-1:1)*outlineCount(item.children)));
        }
        return {node,ref};
      });
      entries.forEach((entry,i)=>{if(i)entry.node.set(n('Prev'),entries[i-1].ref);if(i+1<entries.length)entry.node.set(n('Next'),entries[i+1].ref);});return entries;
    };
    const children=build(graph.outlines,fileRef);file.set(n('First'),children[0].ref);file.set(n('Last'),children.at(-1).ref);file.set(n('Count'),ctx.obj(graph.bookmarkCount));
    const last=root.get(n('Last'));
    if(last) {dict(destination,last).set(n('Next'),fileRef);file.set(n('Prev'),last);}else root.set(n('First'),fileRef);
    root.set(n('Last'),fileRef);root.set(n('Count'),ctx.obj((get(destination,root,'Count')?.asNumber()??0)+graph.bookmarkCount+1));
  }
  return {prefix,notices:graph.notices};
}

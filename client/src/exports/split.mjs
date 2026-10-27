import {subsetPages,validateSubsetGroups,pdfError} from '../pageOps/pdfDocument.mjs';
export const SPLIT_ERROR_CODES=['EXPORT_OPTIONS_INVALID','EXPORT_LIMIT'];
export const splitPdf=subsetPages;
export function everyNPages(pageCount,n=1) {
  if(!Number.isInteger(pageCount)||pageCount<1||!Number.isInteger(n)||n<1||Math.ceil(pageCount/n)>1000)throw pdfError('EXPORT_OPTIONS_INVALID');
  return Array.from({length:Math.ceil(pageCount/n)},(_,i)=>Array.from({length:Math.min(n,pageCount-i*n)},(_,j)=>i*n+j));
}
export function parsePageGroups(text,pageCount) {
  if(typeof text!=='string'||text.length>20000||!Number.isInteger(pageCount)||pageCount<1)throw pdfError('EXPORT_OPTIONS_INVALID');
  const groups=text.split(';').map(part=>{
    const match=/^\s*(\d+)(?:\s*-\s*(\d+))?\s*$/.exec(part);
    if(!match)throw pdfError('EXPORT_OPTIONS_INVALID');
    const start=Number(match[1]),end=Number(match[2]??match[1]);
    if(start<1||end<start||end>pageCount)throw pdfError('EXPORT_OPTIONS_INVALID');
    return Array.from({length:end-start+1},(_,i)=>start-1+i);
  });
  validateSubsetGroups(groups,pageCount);return groups;
}

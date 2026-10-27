import {inspectLocalPdf,transformPages,subsetPages} from './pdfDocument.mjs';
import {inspectPdfImport,mergePdf} from './mergePdf.mjs';
import {writeImage} from './images.mjs';

self.onmessage=async({data})=>{
  const {id,command,payload}=data||{};
  try {
    let result;
    switch(command){
      case 'inspect':result=await inspectLocalPdf(payload.bytes,payload.options);break;
      case 'transform':result=await transformPages(payload.bytes,payload.operation,payload.options);break;
      case 'split':result=await subsetPages(payload.bytes,payload.groups,payload.options);break;
      case 'inspectImport':result=await inspectPdfImport(payload.bytes,payload.options);break;
      case 'merge':result=await mergePdf(payload.bytes,payload.sourceBytes,payload.options);break;
      case 'image':result=await writeImage(payload.bytes,payload.pngBytes,payload.options);break;
      default:throw Object.assign(new Error('PDF_JOB_FAILED'),{code:'PDF_JOB_FAILED'});
    }
    self.postMessage({id,ok:true,result});
  }catch(error){self.postMessage({id,ok:false,error:{code:error?.code||'PDF_JOB_FAILED'}});}
};

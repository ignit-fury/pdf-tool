import {MAX_PDF_BYTES,MAX_TRANSIENT_BYTES} from './documentHistory.mjs';
const error=code=>Object.assign(new Error(code),{code});
let sequence=0;
const allowedCodes=new Set(['PASSWORD_REQUIRED','PASSWORD_INVALID','PDF_INVALID','PDF_INPUT_INVALID','LOCAL_PDF_TOO_LARGE','SIGNATURE_UNKNOWN','SIGNATURE_ACK_REQUIRED','CATALOG_UNSAFE','FINAL_PAGE','PAGE_INDEX_INVALID','PAGE_COMMAND_INVALID','PAGE_GEOMETRY_INVALID','RESOURCES_UNSAFE','TRANSIENT_LIMIT']);
function buffersIn(value,buffers=new Set(),seen=new Set()) {
  if(!value||typeof value!=='object'||seen.has(value))return buffers;
  seen.add(value);
  if(value instanceof ArrayBuffer)buffers.add(value);
  else if(ArrayBuffer.isView(value))buffers.add(value.buffer);
  else for(const child of Object.values(value))buffersIn(child,buffers,seen);
  return buffers;
}
/** Protocol: post {id,command,payload}; reply {id,ok:true,result} or
 * {id,ok:false,error:{code}}. Every terminal path terminates and removes handlers.
 * Payload buffers are cloned into disposable backing stores before transfer. Caller
 * must separately admit retention plus all import/output/prepared buffers; this
 * facade additionally caps known source/copy stores before allocating them.
 * timeoutMs defaults to one 30s deadline covering the entire worker operation.
 * errorCodes accepts only caller-constant uppercase codes for imported operation modules;
 * unknown/untrusted worker error content is never passed to the UI. */
export function runPdfJob({workerFactory,command,payload,signal,timeoutMs=30000,errorCodes=[]}) {
  return new Promise((resolve,reject)=>{
    if(signal?.aborted){reject(error('PDF_JOB_ABORTED'));return;}
    const buffers=buffersIn(payload),size=[...buffers].reduce((n,buffer)=>n+buffer.byteLength,0);
    if(payload?.bytes?.byteLength>MAX_PDF_BYTES){reject(error('LOCAL_PDF_TOO_LARGE'));return;}
    if(size*2>MAX_TRANSIENT_BYTES){reject(error('TRANSIENT_LIMIT'));return;}
    if(!Number.isFinite(timeoutMs)||timeoutMs<=0||timeoutMs>30000){reject(error('PDF_JOB_TIMEOUT'));return;}
    let worker,timer,settled=false;
    const codes=new Set(allowedCodes);
    if(Array.isArray(errorCodes))for(const code of errorCodes)if(typeof code==='string'&&/^[A-Z][A-Z0-9_]{0,63}$/.test(code))codes.add(code);
    const id=++sequence;
    const finish=(err,result)=>{
      if(settled)return;settled=true;clearTimeout(timer);
      signal?.removeEventListener('abort',abort);
      if(worker) {
        for(const [kind,handler] of [['message',message],['error',crash],['messageerror',crash]])try{worker.removeEventListener(kind,handler);}catch{}
        try{worker.terminate();}catch{}
      }
      if(err)reject(err);else resolve(result);
    };
    const abort=()=>finish(error('PDF_JOB_ABORTED'));
    const crash=()=>finish(error('PDF_WORKER_CRASH'));
    const message=event=>{
      const data=event.data;
      if(!data||data.id!==id||typeof data.ok!=='boolean')return finish(error('PDF_WORKER_RESULT_INVALID'));
      if(!data.ok)return finish(error(codes.has(data.error?.code)?data.error.code:'PDF_JOB_FAILED'));
      if(data.result===undefined||data.result===null||typeof data.result!=='object')return finish(error('PDF_WORKER_RESULT_INVALID'));
      finish(null,data.result);
    };
    try {
      timer=setTimeout(()=>finish(error('PDF_JOB_TIMEOUT')),timeoutMs);
      const disposable=structuredClone(payload);
      worker=workerFactory();
      for(const [kind,handler] of [['message',message],['error',crash],['messageerror',crash]])worker.addEventListener(kind,handler);
      signal?.addEventListener('abort',abort,{once:true});
      if(signal?.aborted){abort();return;}
      worker.postMessage({id,command,payload:disposable},[...buffersIn(disposable)]);
    }catch{finish(error('PDF_WORKER_CRASH'));}
  });
}

export const MAX_PDF_BYTES=50*1024*1024;
export const MAX_RETAINED_BYTES=200*1024*1024;
export const MAX_TRANSIENT_BYTES=300*1024*1024;
export const MAX_HISTORY_ENTRIES=100;
const failure=code=>({ok:false,code});
const snapshotError=()=>Object.assign(new Error('SNAPSHOT_NOT_SERIALIZABLE'),{code:'SNAPSHOT_NOT_SERIALIZABLE'});
const fields=['bytes','sourceBytes','password','recipe','selectedPage','style','selection','localMetadata','analysis','findState','acknowledged','action'];
function cloneData(value,buffers,active=new Set()) {
  if(value===null||value===undefined||['string','boolean','number'].includes(typeof value))return value;
  if(typeof value!=='object'||active.has(value))throw snapshotError();
  if(value instanceof ArrayBuffer||ArrayBuffer.isView(value)) {
    const buffer=value instanceof ArrayBuffer?value:value.buffer;
    if(!(buffer instanceof ArrayBuffer))throw snapshotError();
    if(!buffers.has(buffer))buffers.set(buffer,buffer.slice(0));
    if(value instanceof ArrayBuffer)return buffers.get(buffer);
    if(value instanceof DataView)return new DataView(buffers.get(buffer),value.byteOffset,value.byteLength);
    return new value.constructor(buffers.get(buffer),value.byteOffset,value.length);
  }
  if(!Array.isArray(value)&&Object.getPrototypeOf(value)!==Object.prototype&&Object.getPrototypeOf(value)!==null)throw snapshotError();
  active.add(value);
  const result=Array.isArray(value)?value.map(child=>cloneData(child,buffers,active)):Object.fromEntries(Object.entries(value).map(([key,child])=>[key,cloneData(child,buffers,active)]));
  active.delete(value);return Object.freeze(result);
}
/** Copy backing stores and freeze plain snapshot data. Typed arrays are read-only by ownership:
 * never mutate snapshot buffers or transfer them to workers/renderers. Opened bytes live separately.
 * Only whitelisted state is retained; no controllers, proxies, queues or pending work. */
export function captureSnapshot(state) {
  const picked=Object.fromEntries(fields.filter(key=>key in state).map(key=>[key,state[key]]));
  if(picked.analysis)picked.analysis=Object.fromEntries(['enabled','sourceIdentity','meta','index'].filter(key=>key in picked.analysis).map(key=>[key,picked.analysis[key]]));
  return cloneData(picked,new Map());
}
function collect(value,stores,seen=new Set()) {
  if(!value||typeof value!=='object'||seen.has(value))return;
  seen.add(value);
  if(value instanceof ArrayBuffer)stores.add(value);
  else if(ArrayBuffer.isView(value))stores.add(value.buffer);
  else for(const child of Object.values(value))collect(child,stores,seen);
}
/** Conservative application-owned backing-store admission. Numeric temporaryBytes represents
 * known copies not allocated yet; buffers/arrays count real stores once. No eviction occurs.
 * Call before snapshot/output/viewer copies and again after serialization/preparation.
 * retainSnapshot=false supports Undo, whose admission precedes pop/publication. */
export function admitHistory({openedBytes,current,history=[],candidateBytes,temporaryBytes=0,retainSnapshot=true}={}) {
  if(retainSnapshot&&history.length>=MAX_HISTORY_ENTRIES)return failure('HISTORY_LIMIT');
  for(const pdf of [openedBytes,current?.bytes,current?.sourceBytes,candidateBytes])if(pdf?.byteLength>MAX_PDF_BYTES)return failure('LOCAL_PDF_TOO_LARGE');
  const retained=new Set();collect([openedBytes,current,history,candidateBytes],retained);
  const retainedBytes=[...retained].reduce((sum,buffer)=>sum+buffer.byteLength,0);
  if(retainedBytes>MAX_RETAINED_BYTES)return failure('RETENTION_LIMIT');
  const transient=new Set(retained);let predicted=0;
  if(typeof temporaryBytes==='number')predicted=temporaryBytes;
  else collect(temporaryBytes,transient);
  if(!Number.isSafeInteger(predicted)||predicted<0)return failure('MEMORY_INPUT_INVALID');
  const transientBytes=[...transient].reduce((sum,buffer)=>sum+buffer.byteLength,0)+predicted;
  if(transientBytes>MAX_TRANSIENT_BYTES)return failure('TRANSIENT_LIMIT');
  return {ok:true,retainedBytes,transientBytes};
}
export function pushSnapshot(history,snapshot) {
  if(history.length>=MAX_HISTORY_ENTRIES)throw Object.assign(new Error('HISTORY_LIMIT'),{code:'HISTORY_LIMIT'});
  return Object.freeze([...history,snapshot]);
}
export function peekSnapshot(history) {return history.at(-1)??null;}
export function popSnapshot(history) {return Object.freeze(history.slice(0,-1));}

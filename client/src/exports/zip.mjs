export const MAX_EXPORT_BYTES=48*1024*1024;
export const MAX_EXPORT_TRANSIENT=300*1024*1024;
export const exportError=code=>Object.assign(new Error(code),{code});
export function admitExport(retainedBytes,temporaryBytes) {
  if(!Number.isSafeInteger(retainedBytes)||retainedBytes<0||!Number.isSafeInteger(temporaryBytes)||temporaryBytes<0||retainedBytes+temporaryBytes>MAX_EXPORT_TRANSIENT)throw exportError('EXPORT_LIMIT');
}
const table=Uint32Array.from({length:256},(_,n)=>{for(let i=0;i<8;i++)n=n&1?0xedb88320^(n>>>1):n>>>1;return n>>>0;});
export function crc32(bytes) {let crc=0xffffffff;for(const byte of bytes)crc=table[(crc^byte)&255]^(crc>>>8);return (crc^0xffffffff)>>>0;}
/** Stored ZIP32 only. Already-compressed bytes, flat safe ASCII names and fixed dates.
 * Account for retained inputs, archive allocation and the future download Blob copy. */
export function createStoredZip(entries,{retainedBytes=0}={}) {
  if(!Array.isArray(entries)||!entries.length||entries.length>1000)throw exportError('EXPORT_OPTIONS_INVALID');
  const names=new Set();let size=22,inputSize=0;
  for(const {filename,bytes} of entries) {
    if(typeof filename!=='string'||filename.length>100||!/^\w[\w.-]*\.(?:pdf|png|jpg)$/.test(filename)||filename.includes('..')||names.has(filename)||!(bytes instanceof Uint8Array))throw exportError('EXPORT_OPTIONS_INVALID');
    names.add(filename);size+=76+filename.length*2+bytes.byteLength;inputSize+=bytes.buffer.byteLength;
    if(size>MAX_EXPORT_BYTES||size>0xffffffff)throw exportError('EXPORT_LIMIT');
  }
  admitExport(retainedBytes,inputSize+size*2);
  const output=new Uint8Array(size),view=new DataView(output.buffer),central=[];let offset=0;
  const u16=(at,n)=>view.setUint16(at,n,true),u32=(at,n)=>view.setUint32(at,n,true);
  for(const {filename,bytes} of entries) {
    const start=offset,name=new TextEncoder().encode(filename),crc=crc32(bytes);
    u32(offset,0x04034b50);u16(offset+4,20);u16(offset+6,0x800);u16(offset+12,0x21);
    u32(offset+14,crc);u32(offset+18,bytes.length);u32(offset+22,bytes.length);u16(offset+26,name.length);
    output.set(name,offset+30);output.set(bytes,offset+30+name.length);offset+=30+name.length+bytes.length;
    central.push({start,name,crc,length:bytes.length});
  }
  const centralStart=offset;
  for(const {start,name,crc,length} of central) {
    u32(offset,0x02014b50);u16(offset+4,20);u16(offset+6,20);u16(offset+8,0x800);u16(offset+14,0x21);
    u32(offset+16,crc);u32(offset+20,length);u32(offset+24,length);u16(offset+28,name.length);u32(offset+42,start);
    output.set(name,offset+46);offset+=46+name.length;
  }
  u32(offset,0x06054b50);u16(offset+8,entries.length);u16(offset+10,entries.length);u32(offset+12,offset-centralStart);u32(offset+16,centralStart);
  return output;
}

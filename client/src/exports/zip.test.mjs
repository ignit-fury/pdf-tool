import test from 'node:test';
import assert from 'node:assert/strict';
import {createStoredZip,crc32} from './zip.mjs';
test('stored ZIP has correct CRC, local/central records and directory offsets',()=>{
  const bytes=new TextEncoder().encode('123456789');assert.equal(crc32(bytes),0xcbf43926);
  const zip=createStoredZip([{filename:'page-0001.png',bytes}]),view=new DataView(zip.buffer);
  assert.equal(view.getUint32(0,true),0x04034b50);assert.equal(view.getUint32(14,true),crc32(bytes));
  const central=30+13+bytes.length;assert.equal(view.getUint32(central,true),0x02014b50);
  assert.equal(view.getUint32(zip.length-22,true),0x06054b50);assert.equal(view.getUint32(zip.length-6,true),central);
});
test('ZIP refuses unsafe/duplicate names, excessive count and budget before allocation',()=>{
  for(const filename of ['../bad.pdf','/bad.pdf','foo/bar.pdf','bad\\file.pdf','é.pdf','bad\n.pdf','a..pdf'])assert.throws(()=>createStoredZip([{filename,bytes:new Uint8Array()}]));
  assert.throws(()=>createStoredZip(Array.from({length:1001},(_,i)=>({filename:`p${i}.pdf`,bytes:new Uint8Array()}))));
  assert.throws(()=>createStoredZip([{filename:'a.pdf',bytes:new Uint8Array()},{filename:'a.pdf',bytes:new Uint8Array()}]));
  assert.throws(()=>createStoredZip([{filename:'a.pdf',bytes:new Uint8Array(1)}],{retainedBytes:300*1024*1024}),{code:'EXPORT_LIMIT'});
});

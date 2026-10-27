/** G6: materialize actual production client split and stored ZIP outputs. */
import fs from 'node:fs/promises';
import path from 'node:path';
import {createHash} from 'node:crypto';
import {splitPdf} from '../client/src/exports/split.mjs';
import {createStoredZip} from '../client/src/exports/zip.mjs';

const manifest=path.resolve(process.argv[2]),directory=path.dirname(manifest);
const data=JSON.parse(await fs.readFile(manifest,'utf8'));
const source='annotations.pdf';
const bytes=new Uint8Array(await fs.readFile(path.join(directory,source)));
const hash=value=>createHash('sha256').update(value).digest('hex');
const before=hash(bytes);
// Explicit physical page map is supplied independently of writer output.
const groups=[[0,1],[2]];
const result=await splitPdf(bytes,groups,{acknowledged:true,retainedBytes:0});
if(hash(bytes)!==before)throw new Error('source bytes mutated');
if(result.files.length!==groups.length)throw new Error('split count');
const outputs=[];
for(const [index,file] of result.files.entries()) {
  await fs.writeFile(path.join(directory,file.filename),file.bytes);
  outputs.push({file:file.filename,filename:file.filename,sha256:hash(file.bytes),
    source,mapping:groups[index],kind:'split',notices:file.notices});
}
const archive=createStoredZip(result.files,{retainedBytes:0});
await fs.writeFile(path.join(directory,'split.zip'),archive);
await fs.writeFile(path.join(directory,'exports.json'),JSON.stringify({...data,outputs,
  archive:{file:'split.zip',sha256:hash(archive)},sourceClientSha256:before},null,2));

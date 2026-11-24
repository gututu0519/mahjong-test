import {constants,copyFileSync,existsSync,mkdirSync,readFileSync,readdirSync,unlinkSync,writeFileSync} from 'node:fs';
import {resolve,dirname} from 'node:path';
import {fileURLToPath} from 'node:url';
import {createHash} from 'node:crypto';

const root=resolve(process.env.GTT_WORKSPACE_ROOT??resolve(dirname(fileURLToPath(import.meta.url)),'../../..'));
const update=resolve(root,'update');
const sha=file=>createHash('sha256').update(readFileSync(file)).digest('hex');
const files=readdirSync(update,{withFileTypes:true}).filter(entry=>entry.isFile()).map(entry=>{
  const match=/^([a-z0-9]+(?:-[a-z0-9]+)*)-(gtt-node-[A-Za-z0-9_-]+)\.(zip|tar\.gz)$/.exec(entry.name);
  if(!match)throw Error('Unrecognized archive: '+entry.name);
  const destination=resolve(update,match[1],entry.name);
  if(existsSync(destination))throw Error('Destination already exists: '+destination);
  return {file:entry.name,directory:match[1],sha256:sha(resolve(update,entry.name))};
});
if(files.length) {
  const report=resolve(root,'other/diagnostics/releases','organize-update-'+new Date().toISOString().replace(/[-:.]/g,''));
  mkdirSync(report,{recursive:true});
  writeFileSync(resolve(report,'planned.json'),JSON.stringify(files,null,2)+'\n',{flag:'wx'});
  for(const item of files) {
    const source=resolve(update,item.file),destination=resolve(update,item.directory,item.file);
    mkdirSync(dirname(destination),{recursive:true});
    copyFileSync(source,destination,constants.COPYFILE_EXCL);
    if(sha(destination)!==item.sha256||sha(source)!==item.sha256)throw Error('Archive checksum changed: '+item.file);
    unlinkSync(source);
  }
  for(const item of files)if(sha(resolve(update,item.directory,item.file))!==item.sha256)throw Error('Final verification failed: '+item.file);
  writeFileSync(resolve(report,'verification.json'),JSON.stringify({verified_at:new Date().toISOString(),count:files.length,categories:new Set(files.map(item=>item.directory)).size,files},null,2)+'\n',{flag:'wx'});
  console.log(JSON.stringify({moved:files.length,categories:new Set(files.map(item=>item.directory)).size,report}));
} else console.log('No flat archives to organize.');

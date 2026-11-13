import {readFileSync,writeFileSync,readdirSync,mkdirSync} from 'node:fs';
import {resolve,dirname,relative,sep} from 'node:path';
import {execFileSync} from 'node:child_process';
import {zipSync,unzipSync} from 'fflate';

export function createZip(directory, prefix, destination) {
  const files={};
  function walk(at) {
    for(const entry of readdirSync(at,{withFileTypes:true}).sort((a,b)=>a.name.localeCompare(b.name))) {
      const file=resolve(at,entry.name);
      if(entry.isSymbolicLink())throw Error('Release ZIP cannot contain resource links: '+file);
      if(entry.isDirectory())walk(file);
      else if(entry.isFile())files[prefix+'/'+relative(directory,file).split(sep).join('/')]=readFileSync(file);
      else throw Error('Unsupported archive entry: '+file);
    }
  }
  walk(directory);
  writeFileSync(destination,zipSync(files,{level:6}),{flag:'wx'});
}

export function artifactPath(release,record,artifact,override) {
  if(!artifact||typeof artifact.file!=='string'||/[\\/]/.test(artifact.file))throw Error('Invalid release archive filename');
  return resolve(override??resolve(release,record.artifact_directory??'.'),artifact.file);
}

export function extractArchive(archive,destination) {
  if(archive.endsWith('.zip')) {
    const files=unzipSync(readFileSync(archive));
    for(const [name,data] of Object.entries(files)) {
      if(name.startsWith('/')||name.includes('\\')||name.includes(':')||name.split('/').some(p=>p==='..'||p==='.'))throw Error('Unsafe ZIP entry: '+name);
      const target=resolve(destination,name);
      if(name.endsWith('/'))mkdirSync(target,{recursive:true});
      else {mkdirSync(dirname(target),{recursive:true});writeFileSync(target,data,{flag:'wx'});}
    }
  } else if(archive.endsWith('.tar.gz'))execFileSync('tar',['-xzf',archive,'-C',destination]);
  else throw Error('Unsupported release archive: '+archive);
}

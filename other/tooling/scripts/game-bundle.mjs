import {readFileSync,readdirSync,lstatSync} from 'node:fs';
import {resolve,relative,sep} from 'node:path';
import {createHash} from 'node:crypto';
import {isDeepStrictEqual} from 'node:util';
import {verifyFrontendBundle} from '../dist/shared/frontend-manifest.js';

export const digest=bytes=>createHash('sha256').update(bytes).digest('hex');
export function safePath(value) {
  if(typeof value!=='string'||!value||/[\\:\x00-\x1f]/.test(value)||value.split('/').some(part=>!part||part==='.'||part==='..'))throw Error('Unsafe bundle path: '+value);
  return value;
}
export function inventory(root) {
  if(lstatSync(root).isSymbolicLink())throw Error('Bundle root must be a real directory: '+root);
  const files=[];
  function visit(at) {
    for(const entry of readdirSync(at,{withFileTypes:true}).sort((a,b)=>a.name.localeCompare(b.name))) {
      const path=resolve(at,entry.name);
      if(lstatSync(path).isSymbolicLink())throw Error('Bundle resource links are not allowed: '+path);
      if(entry.isDirectory())visit(path);
      else if(entry.isFile()) {
        const name=relative(root,path).split(sep).join('/');safePath(name);
        if(/(^|\/)(?:\.env(?:\..*)?|platform\.env|game\.env|admin-bootstrap\.json)$/.test(name))throw Error('Private instance file cannot enter a bundle: '+name);
        const bytes=readFileSync(path);files.push({path:name,size:bytes.length,sha256:digest(bytes)});
      } else throw Error('Unsupported bundle file: '+path);
    }
  }
  visit(root);return files;
}
export function verifyInventory(root,files,ignored=[]) {
  const seen=new Set();
  for(const file of files) {
    safePath(file.path);if(seen.has(file.path))throw Error('Duplicate manifest file: '+file.path);seen.add(file.path);
    const bytes=readFileSync(resolve(root,file.path));
    if(bytes.length!==file.size||digest(bytes)!==file.sha256)throw Error('Bundle checksum mismatch: '+file.path);
  }
  const actual=inventory(root).filter(file=>!ignored.includes(file.path)).map(file=>file.path).sort();
  if(!isDeepStrictEqual(actual,[...seen].sort()))throw Error('Bundle contains unlisted or missing files');
}
export function verifyPair(serve,client,game) {
  const identity=JSON.parse(readFileSync(resolve(serve,'GAME.json'),'utf8'));
  const service=JSON.parse(readFileSync(resolve(serve,'SERVICE.json'),'utf8'));
  const manifest=verifyFrontendBundle(client);
  if(identity.code!==game||manifest.game!==game||service.role!=='game'||service.release!==identity.release)throw Error('Client/service game identity or release mismatch');
  if(service.entry_point!==`tools/${game}.mjs`)throw Error('Select a compute release with its named startup entry');
  if(!/^[A-Za-z0-9][A-Za-z0-9._-]{0,95}$/.test(identity.release))throw Error('Invalid service release');
  // Older compute packages use this exact default in computeServer. The unpack
  // smoke test also requests the actual running service descriptor.
  const contract=identity.descriptor.client_contract??game+':original-v1';
  if(manifest.client_contract!==contract)throw Error('Client/service protocol contract mismatch');
  if(!manifest.bootstrap.some(file=>file.path===`resources/clients/${game}/index.html`))throw Error('Missing private game startup HTML');
  const privateRule=`resources/services/${game}/config/${game}.json`;
  if(!manifest.bootstrap.some(file=>file.path===privateRule))throw Error('Missing frontend bootstrap rule configuration');
  const rules=JSON.parse(readFileSync(resolve(serve,'config/game.json'),'utf8'));
  const privateRules=JSON.parse(readFileSync(resolve(client,'bootstrap',privateRule),'utf8'));
  if(!isDeepStrictEqual(rules,privateRules)||!isDeepStrictEqual(rules,identity.descriptor.config))throw Error('Client bootstrap and compute rule versions differ');
  return {identity,service,manifest,contract};
}

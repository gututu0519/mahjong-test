import {existsSync,readFileSync} from 'node:fs';
import {resolve,dirname} from 'node:path';
import {fileURLToPath} from 'node:url';

export function runtimeData(name: string) {
  const root=resolve(dirname(fileURLToPath(import.meta.url)),'../../..');
  const manifest=resolve(root,'SERVICE.json');
  const directory=existsSync(manifest)?JSON.parse(readFileSync(manifest,'utf8')).data_directory:undefined;
  return resolve(root,directory??'config',name);
}

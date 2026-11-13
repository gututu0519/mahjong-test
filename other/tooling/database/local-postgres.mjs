import { readFileSync, writeFileSync, existsSync, mkdirSync } from 'node:fs';
import { resolve, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { randomBytes } from 'node:crypto';
import { execFileSync } from 'node:child_process';
const root=resolve(dirname(fileURLToPath(import.meta.url)),'../../..');
const file=resolve(root,'gateway/instance/data/postgres-migration.json');
if(existsSync(file)) throw Error('PostgreSQL migration configuration already exists; refusing to overwrite it.');
const suffix=new Date().toISOString().replace(/\D/g,'').slice(0,14), password=randomBytes(32).toString('hex');
const container='gtt-postgres-'+suffix, volume=container+'-data', database='gtt_'+suffix, trial=database+'_trial';
const env=resolve(root,`other/deploy/instance/postgres-container-${suffix}.env`);
mkdirSync(dirname(env),{recursive:true});
writeFileSync(env,`POSTGRES_USER=gtt_owner\nPOSTGRES_PASSWORD=${password}\nPOSTGRES_DB=${database}\n`,{flag:'wx',mode:0o600});
execFileSync('docker',['run','--detach','--pull=never','--name',container,'--restart','unless-stopped','--env-file',env,'--publish','127.0.0.1:15432:5432','--mount',`type=volume,source=${volume},target=/var/lib/postgresql/data`,'postgres:17-alpine','-c','max_connections=250'],{stdio:'pipe'});
for(let i=0;i<60;i++) {
  try {execFileSync('docker',['exec',container,'pg_isready','-U','gtt_owner','-d',database],{stdio:'pipe'});break;}
  catch {if(i===59) throw Error('PostgreSQL startup timed out');await new Promise(r=>setTimeout(r,1000));}
}
execFileSync('docker',['exec',container,'createdb','-U','gtt_owner',trial],{stdio:'pipe'});
writeFileSync(file,JSON.stringify({container,volume,container_env_file:env,host:'127.0.0.1',port:15432,user:'gtt_owner',password,database,trial},null,2)+'\n',{flag:'wx',mode:0o600});
console.log(`Created NEW PostgreSQL 17 container ${container}; databases ${database} and ${trial}; bound to 127.0.0.1:15432.`);

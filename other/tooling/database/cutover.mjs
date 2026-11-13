import pg from 'pg';
import {readFileSync,writeFileSync,existsSync,renameSync,mkdirSync} from 'node:fs';
import {resolve,dirname} from 'node:path';
import {createHash} from 'node:crypto';
import {execFileSync} from 'node:child_process';
import {root,sources} from './inventory.mjs';
import {databaseSettings,readPostgresConfig} from './settings.mjs';
const [action,...args]=process.argv.slice(2), data=resolve(root,'gateway/instance/data');
const sha=p=>createHash('sha256').update(readFileSync(p)).digest('hex');
const fingerprints=()=>sources().flatMap(s=>['','-wal'].filter(suffix=>existsSync(resolve(root,s.path+suffix))).map(suffix=>({path:s.path+suffix,sha256:sha(resolve(root,s.path+suffix))})));
const journal=resolve(data,'postgres-source-fingerprints.json');
if(action==='seal') {
  if(existsSync(journal))throw Error('Source fingerprint journal already exists');
  writeFileSync(journal,JSON.stringify({sealed_at:new Date().toISOString(),files:fingerprints()},null,2),{flag:'wx',mode:0o600});
  console.log('Original SQLite files and WAL sealed for post-switch write detection.');
} else if(action==='check-source') {
  const sealed=JSON.parse(readFileSync(journal,'utf8'));
  for(const f of sealed.files)if(!existsSync(resolve(root,f.path))||sha(resolve(root,f.path))!==f.sha256)throw Error('Original SQLite source changed after cutover: '+f.path);
  console.log(`All ${sealed.files.length} original SQLite/WAL files remain byte-identical to the sealed cutover sources.`);
} else if(action==='activate') {
  const configFile=resolve(data,'postgres.json'), config=readPostgresConfig(configFile);
  const report=JSON.parse(readFileSync(resolve(args[0]),'utf8'));
  if(report.action!=='verify'||report.trial||report.database!==config.connection.database||report.namespaces!==config.sources.length)throw Error('A successful final verification report for this new database is required');
  const marker=resolve(data,'database-active.json');if(existsSync(marker))throw Error('Database is already activated');
  if(!existsSync(journal))throw Error('Seal stopped SQLite sources before activation');
  const client=new pg.Client(config.connection);await client.connect();
  try {
    const imported=(await client.query('SELECT namespace FROM gtt_meta.imports')).rows;
    if(config.sources.some(s=>!imported.some(r=>r.namespace===s.schema)))throw Error('Some namespaces were not imported');
    const nodeFile=resolve(data,'node.json'), old=readFileSync(nodeFile,'utf8'), node=JSON.parse(old);
    writeFileSync(nodeFile+'.before-postgres',old,{flag:'wx',mode:0o600});
    node.postgres_config=configFile;
    writeFileSync(nodeFile+'.pg-next',JSON.stringify(node,null,2)+'\n',{mode:0o600});renameSync(nodeFile+'.pg-next',nodeFile);
    writeFileSync(marker+'.next',JSON.stringify({driver:'postgres',configFile,database:config.connection.database,activated_at:new Date().toISOString(),verification:resolve(args[0])},null,2)+'\n',{flag:'wx',mode:0o600});
    renameSync(marker+'.next',marker);
    console.log('Activated NEW PostgreSQL database '+config.connection.database+' for the Node launchers and gateway configuration.');
  } finally{await client.end();}
} else if(action==='backup') {
  const c=databaseSettings();
  const file=resolve(data,'postgres-backups',c.database+'-'+Date.now()+'.dump');mkdirSync(dirname(file),{recursive:true});
  const bytes=execFileSync('docker',['exec',c.container,'pg_dump','-U',c.user,'-Fc',c.database],{maxBuffer:256*1024*1024});
  writeFileSync(file,bytes,{flag:'wx',mode:0o600});console.log('PostgreSQL backup: '+file);
} else throw Error('Use seal, check-source, activate <verification.json>, or backup');

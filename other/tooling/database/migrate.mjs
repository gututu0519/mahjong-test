import pg from 'pg';
import { DatabaseSync, backup } from 'node:sqlite';
import { readFileSync, writeFileSync, mkdirSync } from 'node:fs';
import { resolve } from 'node:path';
import { createHash, randomBytes } from 'node:crypto';
import { sources, describe, root, quote } from './inventory.mjs';
import { metadata as migrationMetadata, ensureSchema, checksum } from '../../runtime/server/dist/shared/database/migrations.js';
const hash=data=>createHash('sha256').update(data).digest('hex');
const {databaseSettings}=await import('./settings.mjs');
const settings=databaseSettings();
const [action,...args]=process.argv.slice(2), trial=args.includes('--trial');
const connection={...settings.connection,database:trial?settings.trial:settings.database};
const migrationHash=checksum;
const client=new pg.Client({...connection,application_name:'gtt-migration'});
const get=(name)=>{const i=args.indexOf(name);return i<0?null:args[i+1];};
const safe=x=>{if(!/^[a-z][a-z0-9_]{0,62}$/.test(x))throw Error('Invalid PostgreSQL namespace');return quote(x);};
async function metadata() {
  await migrationMetadata(client);
}
async function migrate(source) {
  return ensureSchema(client,source.schema,source.kind);
}
const ordered=table=>table.columns.filter(c=>c.pk).sort((a,b)=>a.pk-b.pk).map(c=>quote(c.name)).join(',')||table.columns.map(c=>quote(c.name)).join(',');
function digest(rows,columns) {
  const h=createHash('sha256');
  for(const row of rows) h.update(JSON.stringify(columns.map(c=>{const v=row[c.name];return v===null?null:/INT/i.test(c.type)?String(v):v;}))+'\n');
  return h.digest('hex');
}
async function importSource(source,directory) {
  const path=resolve(directory,source.snapshot), bytes=readFileSync(path), sha=hash(bytes);
  if(sha!==source.sha256)throw Error('Snapshot checksum mismatch: '+source.schema);
  const previous=(await client.query('SELECT source_sha256 FROM gtt_meta.imports WHERE namespace=$1',[source.schema])).rows[0];
  if(action==='verify'&&!previous)throw Error('Namespace has not been imported: '+source.schema);
  if(previous&&previous.source_sha256!==sha)throw Error('Namespace already imported from another snapshot: '+source.schema);
  const db=new DatabaseSync(path,{readOnly:true});
  const report=[];
  await client.query('BEGIN');
  try {
    await client.query('SET LOCAL search_path TO '+safe(source.schema)+',pg_catalog');
    await client.query('SET CONSTRAINTS ALL DEFERRED');
    const tables=describe(path);
    const triggerTables=source.kind==='game'?['prebet_rounds','game_operations']:[];
    if(!previous) for(const name of triggerTables)await client.query('ALTER TABLE '+quote(name)+' DISABLE TRIGGER USER');
    for(const table of tables) {
      const statement=db.prepare('SELECT * FROM '+quote(table.name)+' ORDER BY '+ordered(table));statement.setReadBigInts(true);
      const rows=statement.all();
      if(!previous) {
        if((await client.query('SELECT COUNT(*) AS n FROM '+quote(table.name))).rows[0].n!=='0')throw Error('Target table is not empty: '+source.schema+'.'+table.name);
        for(let at=0;at<rows.length;at+=250) {
          const batch=rows.slice(at,at+250), values=[];
          const tuples=batch.map(row=>'('+table.columns.map(c=>{values.push(row[c.name]);return '$'+values.length;}).join(',')+')').join(',');
          await client.query(`INSERT INTO ${quote(table.name)} (${table.columns.map(c=>quote(c.name)).join(',')}) VALUES ${tuples}`,values);
        }
        for(const col of table.columns.filter(c=>c.pk&&c.type.toUpperCase()==='INTEGER')) {
          const sequence=(await client.query('SELECT pg_get_serial_sequence($1,$2) AS name',[quote(source.schema)+'.'+quote(table.name),col.name])).rows[0].name;
          if(sequence) {
            let high=rows.reduce((n,r)=>r[col.name]>n?r[col.name]:n,0n);
            if(db.prepare("SELECT 1 FROM sqlite_master WHERE name='sqlite_sequence'").get()) {const s=db.prepare('SELECT seq FROM sqlite_sequence WHERE name=?');s.setReadBigInts(true);const last=s.get(table.name)?.seq??0n;if(last>high)high=last;}
            await client.query('SELECT setval($1,$2,$3)',[sequence,String(high>0n?high:1n),high>0n]);
          }
        }
      }
      const result=await client.query('SELECT * FROM '+quote(table.name)+' ORDER BY '+ordered(table));
      const expected=digest(rows,table.columns), actual=digest(result.rows,table.columns);
      if(rows.length!==result.rows.length||expected!==actual)throw Error('Data verification failed: '+source.schema+'.'+table.name);
      report.push({table:table.name,rows:rows.length,sha256:expected});
    }
    await client.query('SET CONSTRAINTS ALL IMMEDIATE');
    if(!previous) {
      for(const name of triggerTables)await client.query('ALTER TABLE '+quote(name)+' ENABLE TRIGGER USER');
      await client.query('INSERT INTO gtt_meta.imports(namespace,source_sha256,report) VALUES($1,$2,$3)',[source.schema,sha,JSON.stringify(report)]);
    }
    await client.query('COMMIT');
    console.log(`${source.schema}: verified ${report.length} tables / ${report.reduce((n,r)=>n+r.rows,0)} rows${previous?' (already imported)':''}`);
    return report;
  } catch(e) {await client.query('ROLLBACK');throw e;}
  finally {db.close();}
}
if(action==='snapshot') {
  const directory=resolve(root,'gateway/instance/data/postgres-snapshots',new Date().toISOString().replace(/\D/g,'')+'-'+randomBytes(3).toString('hex'));
  mkdirSync(directory,{recursive:true});
  const list=sources();
  for(const source of list) {
    const db=new DatabaseSync(resolve(root,source.path),{readOnly:true});
    source.snapshot=source.schema+'.sqlite3';
    try {await backup(db,resolve(directory,source.snapshot));}finally{db.close();}
    source.sha256=hash(readFileSync(resolve(directory,source.snapshot)));
  }
  writeFileSync(resolve(directory,'manifest.json'),JSON.stringify({created_at:new Date().toISOString(),write_pause_confirmed:args.includes('--writes-paused'),sources:list},null,2));
  console.log(directory);
} else {
  await client.connect();
  await client.query('SELECT pg_advisory_lock(741103,1)');
  try {
    if(action==='status') {
      const meta=(await client.query("SELECT to_regclass('gtt_meta.schema_migrations') AS name")).rows[0].name;
      console.log(JSON.stringify({database:connection.database,migrations:meta?(await client.query('SELECT namespace,version,checksum,applied_at FROM gtt_meta.schema_migrations ORDER BY namespace')).rows:[]},null,2));
    } else if(action==='up'||action==='import'||action==='verify') {
      const directory=get('--snapshot')?resolve(get('--snapshot')):null;
      const manifest=directory?JSON.parse(readFileSync(resolve(directory,'manifest.json'),'utf8')):null;
      if(action!=='up'&&!manifest)throw Error('--snapshot is required');
      if(!trial&&action==='import'&&!manifest.write_pause_confirmed)throw Error('Final import requires a write-paused snapshot');
      if(action!=='verify')await metadata();
      const list=manifest?.sources??sources({includeMissing:true});
      const reports=[];
      for(const source of list) {
        if(action!=='verify')await migrate(source);
        else {
          const applied=(await client.query('SELECT checksum FROM gtt_meta.schema_migrations WHERE namespace=$1 AND version=$2',[source.schema,'0001'])).rows[0];
          if(applied?.checksum!==migrationHash)throw Error('Migration checksum mismatch: '+source.schema);
        }
        if(action!=='up')reports.push({schema:source.schema,tables:await importSource(source,directory)});
      }
      const config={driver:'postgres',...(trial?{connection,isolated:true}:settings.env_file?{env_file:settings.env_file}:{connection}),protocolDirectory:resolve(root,'gateway/instance/data/merchant-protocols'),sources:list.map(s=>({...s,path:resolve(root,s.path)}))};
      const configPath=resolve(root,'gateway/instance/data',trial?'postgres-trial.json':'postgres.json');
      if(action!=='verify')writeFileSync(configPath,JSON.stringify(config,null,2)+'\n',{mode:0o600});
      const reportPath=resolve(root,'other/diagnostics/postgres',`${connection.database}-${action}-${Date.now()}.json`);
      mkdirSync(resolve(root,'other/diagnostics/postgres'),{recursive:true});
      writeFileSync(reportPath,JSON.stringify({database:connection.database,action,trial,completed_at:new Date().toISOString(),migration_checksum:migrationHash,namespaces:list.length,rows:reports.reduce((n,s)=>n+s.tables.reduce((a,t)=>a+t.rows,0),0),reports},null,2)+'\n');
      console.log(`PostgreSQL ${action} complete: ${connection.database}, ${list.length} namespaces. Runtime configuration prepared; NOT activated.`);
      console.log('Verification record: '+reportPath);
    } else throw Error('Use snapshot, up, import, verify, or status');
  } finally {await client.query('SELECT pg_advisory_unlock(741103,1)');await client.end();}
}

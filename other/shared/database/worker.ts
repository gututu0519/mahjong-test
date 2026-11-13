import { parentPort, workerData } from 'node:worker_threads';
import { createRequire } from 'node:module';
import { readFileSync, realpathSync, existsSync } from 'node:fs';
import { resolve, dirname, basename } from 'node:path';
import { createHash } from 'node:crypto';
import { quote, dialect, placeholders, splitSQL } from './sql.js';
import { ensureSchema, verifySchema } from './runner.js';
import { readPostgresConfig } from '../config/environment.js';
const {Pool,types}=createRequire(import.meta.url)('pg');
types.setTypeParser(20,(s: string)=>{const n=Number(s);if(!Number.isSafeInteger(n))throw Error('PostgreSQL integer exceeds JavaScript safe range');return n;});
const config=readPostgresConfig(workerData.config);
const pool=new Pool({...config.connection,max:8,idleTimeoutMillis:5000,connectionTimeoutMillis:10000,application_name:'gtt-node',options:'-c statement_timeout=60000 -c lock_timeout=15000'});
const connections=new Map<number,any>();
const canonical=(path: string)=>{const p=existsSync(path)?realpathSync(path):existsSync(dirname(path))?resolve(realpathSync(dirname(path)),basename(path)):resolve(path);return process.platform==='win32'?p.replaceAll('\\','/').toLowerCase():p;};
const routes=new Map(config.sources.map((s: any)=>[canonical(s.path),s]));
function route(path: string, hint?: string): any {
  const result=routes.get(canonical(path));
  if(result)return result;
  const digest=createHash('sha256').update(canonical(path)).digest('hex').slice(0,24);
  if(config.testMode && config.testRoot && canonical(path).startsWith(canonical(config.testRoot)+'/')) {
    const name=basename(path).toLowerCase(), parent=dirname(path).toLowerCase();
    const kind=name.includes('control')||name==='merchants.sqlite3'?'control':name==='wallet.db'||name==='platform.sqlite3'?'mock':
      parent.endsWith('merchant-protocols')||name.includes('-fe-')?'protocol':hint??(
      parent.includes('local-')||parent.includes('gtt-protocol')||['rabbit.db','mahjong.db','game.sqlite3'].includes(name)?'local':'game'
    );
    return {schema:'test_'+digest,kind,provision:true};
  }
  if(config.protocolDirectory && canonical(dirname(path))===canonical(config.protocolDirectory) && /^[a-z0-9-]+\.sqlite3$/.test(basename(path)))
    return {schema:'protocol_'+digest,kind:'protocol',provision:true};
  throw Object.assign(Error('Database path is not registered for PostgreSQL migration: '+path),{code:'DATABASE_NOT_MIGRATED'});
}
const empty=()=>({rows:[],changes:0,lastInsertRowid:0});
async function columns(c: any, table: string) {
  const [schema,name]=table.includes('.')?table.split('.'):[c.schema,table];
  const actual=c.aliases[schema]??schema;
  const result=await c.client.query(`SELECT a.attnum-1 AS cid,a.attname AS name,format_type(a.atttypid,a.atttypmod) AS type,
    a.attnotnull::int AS notnull,pg_get_expr(d.adbin,d.adrelid) AS dflt_value,
    COALESCE(array_position(i.indkey::smallint[],a.attnum)+1,0) AS pk,a.attidentity AS identity
    FROM pg_attribute a JOIN pg_class t ON t.oid=a.attrelid JOIN pg_namespace n ON n.oid=t.relnamespace
    LEFT JOIN pg_attrdef d ON d.adrelid=t.oid AND d.adnum=a.attnum
    LEFT JOIN pg_index i ON i.indrelid=t.oid AND i.indisprimary
    WHERE n.nspname=$1 AND t.relname=$2 AND a.attnum>0 AND NOT a.attisdropped ORDER BY a.attnum`,[actual,name]);
  return result.rows;
}
async function query(c: any, raw: string, args: any[]=[]): Promise<any> {
  let sql=raw.trim().replace(/;$/,'');
  if(/^PRAGMA\b/i.test(sql)) {
    const match=/table_info\(["']?([\w]+)["']?\)/i.exec(sql);
    if(match) return {...empty(),rows:await columns(c,match[1])};
    if(/^PRAGMA user_version$/i.test(sql)) return {...empty(),rows:[{user_version:1}]};
    return empty();
  }
  if(/^ATTACH DATABASE/i.test(sql)) {const name=/ AS (\w+)$/i.exec(sql)![1];c.aliases[name]=route(args[0]).schema;return empty();}
  if(/^BEGIN(?: IMMEDIATE)?$/i.test(sql)) {
    await c.client.query('BEGIN');c.transaction=true;
    // Same serialization boundary as SQLite's BEGIN IMMEDIATE, across processes.
    for(const schema of [...new Set([c.schema,...Object.values(c.aliases)])].sort())
      await c.client.query('SELECT pg_advisory_xact_lock(hashtext(current_database()),hashtext($1))',[schema]);
    return empty();
  }
  if(/^(COMMIT|ROLLBACK)$/i.test(sql)) {await c.client.query(sql);c.transaction=false;return empty();}
  if(/^CREATE\s+(?:UNIQUE\s+)?(?:TABLE|INDEX|TRIGGER)\b/i.test(sql)) {
    // All DDL belongs to versioned migrations. Startup only verifies required tables.
    const name=/^CREATE TABLE(?: IF NOT EXISTS)?\s+["']?(\w+)/i.exec(sql)?.[1];
    if(name && !(await columns(c,name)).length) throw Object.assign(Error('Missing migrated table '+name),{code:'DATABASE_MIGRATION_REQUIRED'});
    return empty();
  }
  if(/^ALTER TABLE/i.test(sql)) throw Object.assign(Error('Schema changes must be executed by migrations'),{code:'DATABASE_MIGRATION_REQUIRED'});
  if(/\bsqlite_master\b/i.test(sql)) sql=sql.replace(/\bsqlite_master\b/g,"(SELECT tablename AS name,'table' AS type FROM pg_tables WHERE schemaname=current_schema()) AS sqlite_master");
  sql=dialect(sql);
  for(const [alias,schema] of Object.entries(c.aliases)) sql=sql.replace(new RegExp('\\b'+alias+'\\.','g'),quote(String(schema))+'.');
  const insert=/^INSERT(?: OR (IGNORE|REPLACE))? INTO\s+([\w".]+)(?:\s*\(([^)]+)\))?/i.exec(sql);
  let identity: string|undefined;
  if(insert) {
    const table=insert[2].replaceAll('"',''), info=await columns(c,table);
    identity=info.find((x: any)=>x.identity)?.name;
    sql=sql.replace(/^INSERT OR (IGNORE|REPLACE)/i,'INSERT');
    if(insert[1]?.toUpperCase()==='IGNORE') sql+=' ON CONFLICT DO NOTHING';
    if(insert[1]?.toUpperCase()==='REPLACE') {
      const primary=info.filter((x: any)=>x.pk>0).sort((a: any,b: any)=>a.pk-b.pk).map((x: any)=>x.name);
      if(!primary.length) throw Error('REPLACE requires a primary key: '+table);
      const supplied=insert[3]?insert[3].split(',').map(x=>x.trim().replaceAll('"','')):info.map((x: any)=>x.name);
      const updates=supplied.filter((x: string)=>!primary.includes(x));
      sql+=` ON CONFLICT (${primary.map(quote).join(',')}) `+(updates.length?'DO UPDATE SET '+updates.map((x: string)=>`${quote(x)}=excluded.${quote(x)}`).join(','):'DO NOTHING');
    }
    if(identity&&!/\bRETURNING\b/i.test(sql)) sql+=' RETURNING '+quote(identity);
  }
  sql=placeholders(sql,args);
  const result=await c.client.query(sql,args.map(v=>typeof v==='boolean'?Number(v):v));
  return {rows:result.rows,changes:result.rowCount??0,lastInsertRowid:identity?result.rows[0]?.[identity]??0:0};
}
async function dispatch(command: string,value: any) {
  if(command==='open') {
    const source=route(value.path,value.kind), client=await pool.connect();
    try {
      if(source.provision)await ensureSchema(client,source.schema,source.kind);
      await verifySchema(client,source.schema);
      await client.query('SET search_path TO '+quote(source.schema)+', pg_catalog');
      connections.set(value.id,{client,schema:source.schema,aliases:{},transaction:false});return true;
    } catch(e) {client.release();throw e;}
  }
  const c=connections.get(value.id);if(!c)throw Error('Database connection is closed');
  if(command==='close') {if(c.transaction)await c.client.query('ROLLBACK');c.client.release();connections.delete(value.id);return true;}
  if(command==='query')return query(c,value.sql,value.args);
  if(command==='exec') {
    // Trigger bodies contain semicolons and are installed by migration 0001.
    const sql=value.sql.replace(/CREATE TRIGGER[\s\S]*?\bEND\s*;/gi,'');
    for(const statement of splitSQL(sql))await query(c,statement);
    return true;
  }
  throw Error('Unknown database command');
}
parentPort!.on('message',async ({command,value,buffer})=>{
  const flag=new Int32Array(buffer,0,2);
  let result;
  try {result={value:await dispatch(command,value)};}
  catch(error: any){result={error:{message:error.message,code:error.code??'POSTGRES_ERROR'}};}
  let bytes=Buffer.from(JSON.stringify(result));
  if(bytes.length>buffer.byteLength-8)bytes=Buffer.from(JSON.stringify({error:{message:'Database result exceeds response limit',code:'DATABASE_RESULT_TOO_LARGE'}}));
  Buffer.from(buffer,8,bytes.length).set(bytes);Atomics.store(flag,1,bytes.length);Atomics.store(flag,0,1);Atomics.notify(flag,0);
});

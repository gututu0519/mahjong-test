// Import the pre-existing Python/SQLite fixtures into isolated PostgreSQL test
// namespaces. This exercises legacy restoration without changing the fixtures.
import { createRequire } from 'node:module';
import { readFileSync, realpathSync, existsSync } from 'node:fs';
import { resolve } from 'node:path';
import { createHash } from 'node:crypto';
import { DatabaseSync } from 'node:sqlite';
import { ensureSchema } from '../shared/database/runner.js';
import { quote } from '../shared/database/sql.js';
export async function importPostgresFixture(path: string, kind: string) {
  const config=JSON.parse(readFileSync(process.env.GTT_PG_CONFIG!,'utf8'));
  if(!config.testMode)throw Error('Fixture imports require an isolated PostgreSQL test configuration');
  const normalized=process.platform==='win32'?realpathSync(path).replaceAll('\\','/').toLowerCase():realpathSync(path);
  const schema='test_'+createHash('sha256').update(normalized).digest('hex').slice(0,24);
  const {Client}=createRequire(import.meta.url)('pg'), client=new Client(config.connection), db=new DatabaseSync(path,{readOnly:true});
  await client.connect();
  try {
    await ensureSchema(client,schema,kind);
    await client.query('BEGIN');
    await client.query('SET LOCAL search_path TO '+quote(schema)+',pg_catalog');
    const eventTables=kind==='game'?['prebet_rounds','game_operations']:[];
    for(const name of eventTables)await client.query('ALTER TABLE '+quote(name)+' DISABLE TRIGGER USER');
    const tables=db.prepare("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'").all() as any[];
    for(const {name} of tables) {
      const rows=db.prepare('SELECT * FROM '+quote(name)).all();
      if(!rows.length)continue;
      const names=Object.keys(rows[0]);
      for(const row of rows)await client.query(`INSERT INTO ${quote(name)} (${names.map(quote).join(',')}) VALUES (${names.map((_,i)=>'$'+(i+1)).join(',')})`,names.map(n=>row[n]));
      const columns=db.prepare('PRAGMA table_info('+quote(name)+')').all() as any[];
      for(const column of columns.filter(c=>c.pk&&c.type.toUpperCase()==='INTEGER')) {
        const seq=(await client.query('SELECT pg_get_serial_sequence($1,$2) AS name',[quote(schema)+'.'+quote(name),column.name])).rows[0].name;
        if(seq)await client.query(`SELECT setval($1,COALESCE(MAX(${quote(column.name)}),1),COUNT(*)>0) FROM ${quote(name)}`,[seq]);
      }
    }
    await client.query('SET CONSTRAINTS ALL IMMEDIATE');
    for(const name of eventTables)await client.query('ALTER TABLE '+quote(name)+' ENABLE TRIGGER USER');
    await client.query('COMMIT');
  } catch(e){await client.query('ROLLBACK');throw e;}
  finally{db.close();await client.end();}
}
export async function setPostgresWriteFailure(path: string, enabled: boolean) {
  const config=JSON.parse(readFileSync(process.env.GTT_PG_CONFIG!,'utf8'));
  if(!config.testMode)throw Error('Fault injection requires an isolated test database');
  const full=existsSync(path)?realpathSync(path):resolve(path);
  const normalized=process.platform==='win32'?full.replaceAll('\\','/').toLowerCase():full;
  const schema='test_'+createHash('sha256').update(normalized).digest('hex').slice(0,24);
  const {Client}=createRequire(import.meta.url)('pg'), client=new Client(config.connection);await client.connect();
  try {await client.query(`ALTER TABLE ${quote(schema)}.rtp_events `+(enabled?'ADD CONSTRAINT gtt_test_failure CHECK(false) NOT VALID':'DROP CONSTRAINT gtt_test_failure'));}
  finally{await client.end();}
}

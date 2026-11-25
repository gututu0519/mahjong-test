import {createHash} from 'node:crypto';
import {quote} from './sql.js';

export const trialDDL=`
CREATE TABLE trial_links(id TEXT PRIMARY KEY,code TEXT NOT NULL,frontend_id TEXT NOT NULL,service_id TEXT NOT NULL,language TEXT NOT NULL,credits INTEGER NOT NULL,note TEXT NOT NULL,actor TEXT NOT NULL,created_at BIGINT NOT NULL,expires_at BIGINT NOT NULL,disabled INTEGER NOT NULL,starts BIGINT NOT NULL);
CREATE INDEX trial_links_game ON trial_links(code,created_at);
CREATE TABLE trial_sessions(token_hash TEXT PRIMARY KEY,player_id TEXT NOT NULL UNIQUE,link_id TEXT NOT NULL,code TEXT NOT NULL,frontend_id TEXT NOT NULL,service_id TEXT NOT NULL,expires_at BIGINT NOT NULL,balance BIGINT NOT NULL,state_json TEXT NOT NULL);
CREATE TABLE trial_operations(seq BIGINT PRIMARY KEY,player_id TEXT NOT NULL,request_key TEXT NOT NULL,request_json TEXT NOT NULL,candidate_json TEXT NOT NULL,response_json TEXT NOT NULL,created_at BIGINT NOT NULL,UNIQUE(player_id,request_key));
CREATE TABLE trial_counter(id INTEGER PRIMARY KEY,value BIGINT NOT NULL);
INSERT INTO trial_counter VALUES(1,0);`;
const checksum=createHash('sha256').update(trialDDL.replace(/\r\n/g,'\n')).digest('hex');
/** 将试玩邀请及虚拟余额放入独立表，仅在控制命名空间应用 DDL。 */
async function up(client:any,schema:string,kind:string){
  if(!/^[a-z][a-z0-9_]{0,62}$/.test(schema))throw Error('Invalid migration namespace');
  await client.query('BEGIN');
  try{
    await client.query('SELECT pg_advisory_xact_lock(741104,hashtext($1))',[schema]);
    const row=(await client.query('SELECT checksum FROM gtt_meta.schema_migrations WHERE namespace=$1 AND version=$2',[schema,'0002'])).rows[0];
    if(row&&row.checksum!==checksum)throw Error('Applied trial migration checksum changed');
    if(!row){
      if(kind==='control'){await client.query('SET LOCAL search_path TO '+quote(schema)+',pg_catalog');await client.query(trialDDL);}
      await client.query('INSERT INTO gtt_meta.schema_migrations(namespace,version,checksum) VALUES($1,$2,$3)',[schema,'0002',checksum]);
    }
    await client.query('COMMIT');
  }catch(error){await client.query('ROLLBACK');throw error;}
}
export const trialMigration={version:'0002',checksum,up};

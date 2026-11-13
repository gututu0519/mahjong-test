// Append new migration modules here. Never edit an already-applied baseline.
// Each module owns its transaction and namespace advisory lock, and records its
// version/checksum in gtt_meta.schema_migrations only after all DDL succeeds.
import {ensureSchema as baseline, checksum as baselineChecksum, metadata} from './migrations.js';
export {metadata};
export const migrations=[{version:'0001',checksum:baselineChecksum,up:baseline}];
export const checksum=baselineChecksum;
export async function ensureSchema(client: any,schema: string,kind: string) {
  for(const migration of migrations)await migration.up(client,schema,kind);
}
export async function verifySchema(client: any,schema: string) {
  const rows=(await client.query('SELECT version,checksum FROM gtt_meta.schema_migrations WHERE namespace=$1',[schema])).rows;
  for(const migration of migrations) {
    const record=rows.find((r: any)=>r.version===migration.version);
    if(!record)throw Object.assign(Error('PostgreSQL namespace requires migration '+migration.version+': '+schema),{code:'DATABASE_MIGRATION_REQUIRED'});
    if(record.checksum!==migration.checksum)throw Object.assign(Error('PostgreSQL migration checksum mismatch: '+schema+'/'+migration.version),{code:'DATABASE_MIGRATION_CHECKSUM'});
  }
}

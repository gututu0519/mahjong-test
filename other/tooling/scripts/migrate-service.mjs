import {readFileSync} from 'node:fs';
import {resolve,dirname} from 'node:path';
import {fileURLToPath,pathToFileURL} from 'node:url';
import {createRequire} from 'node:module';
import {serviceContext} from './service-context.mjs';
import {readPostgresConfig} from '../dist/shared/config/environment.js';

export async function migrateService(context) {
  if(context.role==='game') {
    console.log('迁移阶段：独立计算服务无玩家数据库，已检查版本、规则文件和认证密钥；不连接平台数据库。');
    return;
  }
  const config=readPostgresConfig(context.environment.GTT_PG_CONFIG,context.environment);
  if(!Array.isArray(config.sources)||!config.sources.length)throw Error('PostgreSQL 配置缺少明确的存储路由 sources');
  const namespaces=new Map();
  for(const source of config.sources) {
    if(namespaces.has(source.schema)&&namespaces.get(source.schema)!==source.kind)throw Error('同一 schema 的迁移类型不一致');
    namespaces.set(source.schema,source.kind);
  }
  const {Client}=createRequire(import.meta.url)('pg');
  const {metadata,ensureSchema,verifySchema}=await import('../dist/shared/database/runner.js');
  const client=new Client({...config.connection,connectionTimeoutMillis:10000,application_name:'gtt-start-migrate',options:'-c lock_timeout=60000'});
  let locked=false;
  try {
    await client.connect();
    await client.query('SELECT pg_advisory_lock(741103,1)');locked=true;
    await metadata(client);
    for(const [schema,kind]of namespaces) {await ensureSchema(client,schema,kind);await verifySchema(client,schema);}
    console.log(`迁移完成：${namespaces.size} 个命名空间已按版本校验；未执行 SQLite 导入或业务数据重置。`);
  } finally {
    try {if(locked)await client.query('SELECT pg_advisory_unlock(741103,1)');}
    finally {await client.end();}
  }
}

if(process.argv[1]&&import.meta.url===pathToFileURL(resolve(process.argv[1])).href) {
  const root=resolve(dirname(fileURLToPath(import.meta.url)),'..');
  try {await migrateService(serviceContext(root,JSON.parse(readFileSync(resolve(root,'SERVICE.json'),'utf8')),process.argv.slice(2)));}
  catch(error){console.error('迁移失败：'+error.message);process.exitCode=1;}
}

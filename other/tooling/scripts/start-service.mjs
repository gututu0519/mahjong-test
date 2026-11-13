import {readFileSync} from 'node:fs';
import {resolve,dirname} from 'node:path';
import {fileURLToPath} from 'node:url';
import {installDependencies,npmExecutable,installationEnvironment} from './install-dependencies.mjs';
import {gameProcessEnvironment} from '../dist/shared/config/environment.js';
const root=resolve(dirname(fileURLToPath(import.meta.url)),'..');
const npm=npmExecutable();
const service=JSON.parse(readFileSync(resolve(root,'SERVICE.json'),'utf8'));
try {
  const [major,minor]=process.versions.node.split('.').map(Number);
  if(major<24||(major===24&&minor<17))throw Error('需要 Node.js 24.17.0 或更新版本');
  console.log('[1/3] 安装锁定的生产依赖');
  await installDependencies(root,{npm,environment:service.role==='game'?installationEnvironment(gameProcessEnvironment(process.env)):process.env});
  console.log('[2/3] 执行版本化迁移');
  const {serviceContext}=await import('./service-context.mjs');
  const {migrateService}=await import('./migrate-service.mjs');
  const context=serviceContext(root,service,process.argv.slice(2));
  await migrateService(context);
  if(service.role==='game')for(const key of Object.keys(process.env))delete process.env[key];
  Object.assign(process.env,context.environment);
  console.log('[3/3] 启动 '+context.action);
  const {main}=await import('../dist/cli.js');await main(context.args);
} catch(error) {console.error('启动流水线失败：'+error.message);process.exitCode=1;}

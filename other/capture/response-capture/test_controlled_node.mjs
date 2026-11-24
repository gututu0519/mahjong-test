// 在内存管道和临时工作区验证控制台，不操作已有业务实例。
import test from 'node:test';
import assert from 'node:assert/strict';
import { EventEmitter } from 'node:events';
import { PassThrough } from 'node:stream';
import { spawnSync } from 'node:child_process';
import { copyFileSync, existsSync, mkdirSync, mkdtempDisposableSync, readdirSync, readFileSync, unlinkSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { installStopBridge } from './controlled_node.mjs';

test('退出桥只响应完整 stop 行，重复请求不重复触发', async () => {
  const host = new EventEmitter(), input = new PassThrough();
  let stops = 0;
  host.on('SIGTERM', () => { stops++; });
  const close = installStopBridge(input, host, () => {});
  input.write('kill\nanything\nsto');
  assert.equal(stops, 0);
  input.write('p\nstop\n');
  assert.equal(stops, 1);
  close();
  input.destroy();
});

test('启动未完成时保留请求，正常退出处理器注册后才发送', async () => {
  const host = new EventEmitter(), input = new PassThrough();
  let stops = 0;
  const close = installStopBridge(input, host, () => {});
  input.write('stop\n');
  assert.equal(stops, 0);
  host.on('SIGTERM', () => { stops++; });
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(stops, 1);
  close();
  input.destroy();
});

test('控制进程断开不会擅自结束业务', async () => {
  const host = new EventEmitter(), input = new PassThrough();
  let stops = 0;
  host.on('SIGTERM', () => { stops++; });
  const close = installStopBridge(input, host, () => {});
  input.end();
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(stops, 0);
  close();
});

test('批处理入口和控制台传入相同的参数、工作目录和旧数据库路由，控制台复用构建', t => {
  const temporary = mkdtempDisposableSync(join(tmpdir(), 'service-entry-'));
  t.after(() => temporary.remove());
  const root = temporary.path;
  const source = resolve(dirname(fileURLToPath(import.meta.url)), '../../..');
  const write = (name, value) => {
    mkdirSync(dirname(join(root, name)), { recursive: true });
    writeFileSync(join(root, name), value);
  };
  const runner = 'other/tooling/run.mjs';
  const bridge = 'other/capture/response-capture/controlled_node.mjs';
  for (const name of [runner, bridge, 'other/capture/response-capture/service_control.mjs']) {
    mkdirSync(dirname(join(root, name)), { recursive: true });
    copyFileSync(join(source, name), join(root, name));
  }
  write('other/tooling/build.mjs', "import {appendFileSync} from 'node:fs'; export function build(){appendFileSync('build-count','1');}");
  const runtime = 'other/runtime/server/';
  write(runtime+'package.json', '{"type":"module"}');
  write(runtime+'dist/.built', '');
  write(runtime+'dist/cli.js', 'export function main(args){console.log(JSON.stringify([args,process.cwd(),process.env.GTT_WORKSPACE_ROOT,process.env.GTT_PG_CONFIG]));}');
  write(runtime+'dist/shared/config/environment.js', 'export const gameProcessEnvironment = e => e, isolatedTestEnvironment = e => e;');
  write(runtime+'tools/start.mjs', 'console.log(JSON.stringify([process.argv.slice(2), process.cwd(), process.env.GTT_WORKSPACE_ROOT, process.env.GTT_PG_CONFIG]));');
  const pg = join(root, 'local-postgres.json');
  write('gateway/instance/data/database-active.json', JSON.stringify({driver:'postgres',configFile:pg}));
  const env = {...process.env};
  for (const key of ['GTT_PLATFORM_ENV_FILE','GTT_PG_CONFIG','GTT_CAPTURE_CONTROL_DIR','GTT_CAPTURE_CONTROL_NONCE']) delete env[key];
  const execute = (script, args) => {
    const result = spawnSync(process.execPath, [script, ...args], {cwd:root, env, encoding:'utf8', timeout:5000, windowsHide:true});
    assert.equal(result.status, 0, result.error?.message || result.stderr);
    return JSON.parse(result.stdout);
  };
  const options = ['--database','isolated.db','--port','31000'];
  const gameDirs = readdirSync(join(source, 'games')).filter(name => existsSync(join(source, 'games', name, 'instance/service.json')));
  const batches = [...gameDirs.map(name => ['games/'+name,name]), ['admin','admin'], ['gateway','gateway'],
    ['other/mock-platform','mock'], ['other/game-api','game-api']];
  for (const [directory, service] of batches) {
    const batch = readFileSync(join(source, directory, 'start.bat'), 'utf8');
    const target = batch.match(/^node\s+"%~dp0([^"]+)"\s+start\s+(\S+)\s+%\*\s*$/im);
    assert.ok(target, directory);
    assert.equal(resolve(source, directory, target[1].replaceAll('\\','/')), resolve(source, runner));
    assert.equal(target[2], service);
    const manual = execute(runner, ['start', service, ...options]);
    assert.deepEqual(manual, [[service,'--database',join(root,'isolated.db'),'--port','31000'], resolve(root,runtime), root, pg]);
    assert.deepEqual(execute(bridge, ['source',service,...options]), manual);
    assert.deepEqual(execute(runner, ['start',service,'--use-built',...options]), manual);
  }
  assert.deepEqual(execute(bridge, ['source','rtp-worker']), [['rtp-worker'],resolve(root,runtime),root,pg]);
  assert.deepEqual(execute(bridge, ['run','cli','buffalo']), [['buffalo'],resolve(root,runtime),root,pg]);
  unlinkSync(join(root,runtime,'dist/.built'));
  const missing = spawnSync(process.execPath, [bridge,'source','admin'], {cwd:root,env,encoding:'utf8',timeout:5000,windowsHide:true});
  assert.equal(missing.status, 1);
  assert.match(missing.stderr, /缺少已编译的运行文件 dist\/\.built/);
  assert.equal(readFileSync(join(root,'build-count'),'utf8'), '1'.repeat(batches.length));
});

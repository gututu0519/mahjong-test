// 每个受控实例使用自身记录目录和随机凭据；控制台重开后仍能请求正常退出。
import { readFileSync, writeFileSync, renameSync, realpathSync, lstatSync } from 'node:fs';
import { resolve, join } from 'node:path';

const initialCommand = [process.execPath, ...process.execArgv, ...process.argv.slice(1)];
const initialDirectory = process.cwd();

export function installFileControl(options = {}) {
  const directory = options.directory ?? process.env.GTT_CAPTURE_CONTROL_DIR;
  const nonce = options.nonce ?? process.env.GTT_CAPTURE_CONTROL_NONCE;
  const chat = options.chat ?? process.env.CODEX_THREAD_ID;
  if (!directory && !nonce) return () => {};
  if (!directory || !/^[a-f0-9]{32,128}$/.test(nonce || '') || !chat)
    throw Error('服务正常退出通道缺少本次归属资料。');
  const folder = resolve(directory);
  if (realpathSync(folder).toLowerCase() !== folder.toLowerCase() || !lstatSync(folder).isDirectory() || lstatSync(folder).isSymbolicLink())
    throw Error('服务正常退出记录目录无效。');
  const host = options.host ?? process;
  const identity = { pid: options.pid ?? process.pid, chat, nonce, cwd: options.cwd ?? initialDirectory,
    command: options.command ?? initialCommand, started: new Date().toISOString(), state: 'ready' };
  const ownerFile = join(folder, 'control-owner.json');
  const requestFile = join(folder, 'stop-request.json');
  let published = false, stopping = false;
  function publish() {
    const pending = join(folder, `control-owner-${identity.pid}.pending`);
    writeFileSync(pending, JSON.stringify(identity), { encoding: 'utf8', flag: 'w' });
    renameSync(pending, ownerFile);
    published = true;
  }
  function poll() {
    if (stopping || !host.listenerCount('SIGTERM')) return;
    if (!published) publish();
    let request;
    try { request = JSON.parse(readFileSync(requestFile, 'utf8')); }
    catch (error) {
      if (error.code === 'ENOENT' || error instanceof SyntaxError) return;
      throw error;
    }
    if (request.pid !== identity.pid || request.chat !== chat || request.nonce !== nonce) return;
    stopping = true;
    identity.state = 'stopping';
    publish();
    clearInterval(timer);
    // 只触发原服务正常关闭逻辑，保留在途响应、钱包事务和任务收尾。
    host.emit('SIGTERM');
  }
  const timer = setInterval(() => {
    try { poll(); } catch (error) { console.error('正常退出通道读取失败：' + error.message); }
  }, options.interval ?? 250);
  timer.unref();
  poll();
  return () => clearInterval(timer);
}

// --import 预加载用于原版适配产物；controlled_node 也可复用同一模块。
if (process.env.GTT_CAPTURE_CONTROL_DIR) installFileControl();

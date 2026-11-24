// 控制台通过专用管道请求正常退出；不向 Windows 子进程发送终止信号。
import { createInterface } from 'node:readline';
import { resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { runWorkspaceTool } from '../../tooling/run.mjs';
import './service_control.mjs';

const entry = fileURLToPath(import.meta.url);

export function installStopBridge(input = process.stdin, host = process, report = console.log) {
  let requested = false, sent = false, closed = false;
  const lines = createInterface({ input, crlfDelay: Infinity });
  function deliver() {
    if (!closed && requested && !sent && host.listenerCount('SIGTERM') > 0) {
      sent = true;
      report('服务控制台：已请求正常退出，等待在途任务结束。');
      host.emit('SIGTERM');
      lines.close();
      input.unref?.();
    }
  }
  function newListener(name) {
    if (name === 'SIGTERM') setImmediate(deliver);
  }
  host.on('newListener', newListener);
  lines.on('line', line => {
    if (line.trim() !== 'stop' || requested) return;
    requested = true;
    if (!host.listenerCount('SIGTERM')) report('服务控制台：正在等待服务安装正常退出处理器。');
    deliver();
  });
  // 控制台关闭或管道断开不代表用户要求停止业务；业务句柄决定进程寿命。
  input.unref?.();
  return () => {
    closed = true;
    host.removeListener('newListener', newListener);
    lines.close();
    input.unref?.();
  };
}

export async function runControlled(args) {
  const [mode, action, ...extra] = args;
  if (mode !== 'source' && !(mode === 'run' && action === 'cli' && extra[0] === 'buffalo'))
    throw Error('控制台仅支持已登记的源码服务入口。');
  if (mode === 'source' && !/^[a-z0-9][a-z0-9-]*$/.test(action || ''))
    throw Error('服务入口名称无效。');
  const closeBridge = installStopBridge();
  try {
    const tool = mode === 'source' ? 'start' : 'cli';
    const [service, ...options] = mode === 'source' ? [action, ...extra] : extra;
    await runWorkspaceTool(tool, [service, '--use-built', ...options]);
    if (process.exitCode) closeBridge();
  } catch (error) {
    closeBridge();
    throw error;
  }
}

if (process.argv[1] && resolve(process.argv[1]) === entry) {
  try {
    await runControlled(process.argv.slice(2));
  } catch (error) {
    console.error('启动流水线失败：' + error.message);
    process.exitCode = 1;
  }
}

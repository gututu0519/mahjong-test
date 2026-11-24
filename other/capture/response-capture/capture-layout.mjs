import { lstatSync, readdirSync } from 'node:fs';
import path from 'node:path';

export const captureArchive = 'other/capture/response-capture/captures';
const sessionId = /^[0-9a-f]{32}$/;

// 值为相对于 captures 的实际批次路径。旧批次的索引文件只用于按名称选择。
export function captureFolders(archive) {
  const folders = new Map();
  if (!lstatSync(archive, { throwIfNoEntry: false })?.isDirectory()) return folders;
  function add(id, directory) {
    if (folders.has(id)) throw new Error('抓取批次 ID 重复：' + id);
    folders.set(id, directory);
  }
  for (const item of readdirSync(archive, { withFileTypes: true })) {
    if (!item.isDirectory()) continue;
    if (sessionId.test(item.name)) {
      add(item.name, item.name);
      continue;
    }
    for (const batch of readdirSync(path.join(archive, item.name), { withFileTypes: true })) {
      if (batch.isDirectory() && sessionId.test(batch.name)) {
        add(batch.name, item.name + '/' + batch.name);
      }
    }
  }
  return folders;
}

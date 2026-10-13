// Produce a query-free inventory; HAR response bodies are not synthesized.
const fs = require('fs');
const path = require('path');
const root = __dirname;
const entries = JSON.parse(fs.readFileSync(path.join(root, 'original.har'), 'utf8')).log.entries;
const resources = new Map();
for (const entry of entries) {
  const url = new URL(entry.request.url);
  if (!['static.eajzzxhro.com', 'm.eajzzxhro.com'].includes(url.hostname)) continue;
  if (entry.request.method !== 'GET') continue;
  const key = url.origin + url.pathname;
  const localPath = url.pathname.replace(/^\/74\//, '/').replace(/^\//, '');
  resources.set(key, { url: key, status: entry.response.status, mimeType: entry.response.content.mimeType,
    bodyIncluded: entry.response.content.text !== undefined, suggestedLocalPath: localPath,
    localExists: fs.existsSync(path.join(root, localPath)) });
}
const report = { note: '建议路径将原站 /74/ 映射到当前本地根目录；其他路径不变。不是完整构建清单，仅为 HAR 已观察请求。',
  entryCount: entries.length, bodyCount: entries.filter(e => e.response.content.text !== undefined).length,
  resources: [...resources.values()] };
fs.writeFileSync(path.join(root, 'diagnostics/har-resources.json'), JSON.stringify(report, null, 2));
console.log({ entries: report.entryCount, bodies: report.bodyCount, uniqueObservedResources: resources.size,
  absentLocalPaths: report.resources.filter(r => !r.localExists).length });

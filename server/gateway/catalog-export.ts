import { check } from "../shared/core.js";
import { gameNames } from "./game-names.js";

const escapeHTML = (v: unknown) => String(v ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"})[c]!);
export function catalogExport(games: any[], format: string, _merchant?: string) {
  check(["html", "csv", "json"].includes(format), "EXPORT_FORMAT_INVALID");
  // Explicit allowlist: never serialize internal game metadata into a download.
  const entries = games.map(g => ({brand: g.brand ?? "", ...gameNames(g.id), id: g.id}));
  const headings = ["游戏品牌", "中文名", "英文名", "接入 ID"];
  let content: string, content_type: string;
  if (format === "json") {
    content_type = "application/json; charset=utf-8";
    content = JSON.stringify({games: entries}, null, 2);
  } else if (format === "csv") {
    content_type = "text/csv; charset=utf-8";
    const cell = (v: unknown) => {
      let text = String(v ?? "");
      if (/^[\s]*[=+\-@]|^[\t\r\n]/.test(text)) text = "'" + text;
      return '"'+text.replace(/"/g,'""')+'"';
    };
    content = "\uFEFF" + [headings, ...entries.map(g => [g.brand, g.title_zh, g.title_en, g.id])].map(row => row.map(cell).join(",")).join("\r\n") + "\r\n";
  } else {
    content_type = "text/html; charset=utf-8";
    const rows = entries.map(g => '<tr><td>'+escapeHTML(g.brand)+'</td><td>'+escapeHTML(g.title_zh)+'</td><td>'+escapeHTML(g.title_en)+'</td><td class="id">'+escapeHTML(g.id)+'</td></tr>').join('');
    content = '<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>游戏目录</title><style>' +
      'body{margin:0;background:#f3f5f2;color:#253d34;font:14px/1.7 system-ui,-apple-system,sans-serif}.document{max-width:880px;margin:40px auto;padding:40px;background:#fff;border:1px solid #dfe7e1;border-radius:16px}h1{font-size:28px;margin:0 0 24px;font-weight:650}table{width:100%;border-collapse:collapse;text-align:left}th{background:#edf4f0;color:#315b49;font-weight:600}th,td{padding:14px 18px;border-bottom:1px solid #e2e8e4}th:last-child,.id{text-align:right;white-space:nowrap}.id{font-family:ui-monospace,monospace}tbody tr:nth-child(even){background:#fafcfb}.empty{text-align:center;padding:40px;color:#6c7a72}tr{break-inside:avoid}@media(max-width:640px){.document{margin:0;padding:24px 16px;border:0;border-radius:0}th,td{padding:12px 8px}}@media print{@page{size:A4;margin:15mm}body{background:#fff}.document{max-width:none;margin:0;padding:0;border:0}thead{display:table-header-group}th{-webkit-print-color-adjust:exact;print-color-adjust:exact}}' +
      '</style></head><body><main class="document"><h1>游戏目录</h1><table><thead><tr>'+headings.map(h=>'<th scope="col">'+h+'</th>').join('')+'</tr></thead><tbody>'+(rows || '<tr><td colspan="4" class="empty">暂无游戏</td></tr>')+'</tbody></table></main></body></html>';
  }
  return {filename:"GTT-Game-Catalog."+format,content_type,content};
}

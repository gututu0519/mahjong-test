// integration.json is the Node contract source; keep all downloads in sync.
import { readFileSync, writeFileSync, existsSync } from "node:fs";
import { fileURLToPath } from "node:url";
const folder = new URL("../config/", import.meta.url);
const doc = JSON.parse(
  readFileSync(new URL("integration.json", folder), "utf8"),
);
const api = JSON.parse(readFileSync(new URL("openapi.json", folder), "utf8"));
api.info.version = doc.version;
api.components.schemas = doc.schemas;
api.paths = Object.fromEntries(
  doc.endpoints.map((e) => {
    const operation = {
      operationId: e.id.replaceAll("-", "_"),
      summary: e.title,
      description: [e.description, ...e.notes].join("\n\n"),
      tags: [e.direction],
      requestBody: {
        required: true,
        content: {
          "application/json": {
            schema: e.request_schema,
            example: e.request_example,
          },
        },
      },
      responses: {
        [e.status]: {
          description: "成功响应",
          content: {
            "application/json": {
              schema: e.response_schema,
              example: e.response_example,
            },
          },
        },
        default: {
          description: "鉴权、参数错误或未完成的结果，按错误码处理",
          content: {
            "application/json": {
              schema: { $ref: "#/components/schemas/Error" },
            },
          },
        },
      },
    };
    if (e.direction !== "商户 → GTT")
      operation.servers = [
        {
          url: e.direction.includes("钱包")
            ? "https://wallet.merchant.example"
            : "https://decision.merchant.example",
          description: "商户提供的服务地址占位符，需替换为实际地址",
        },
      ];
    return [e.path, { post: operation }];
  }),
);
function rows(schema, prefix = "", depth = 0) {
  if (schema.$ref) schema = doc.schemas[schema.$ref.split("/").at(-1)];
  return Object.entries(schema.properties || {}).flatMap(([name, prop]) => {
    const type = prop.type || prop.$ref?.split("/").at(-1) || "object";
    const details = [prop.description];
    if (prop.enum) details.push("允许值：" + prop.enum.join(" / "));
    for (const [key, label] of [
      ["default", "默认"],
      ["minimum", "最小"],
      ["maximum", "最大"],
      ["minLength", "最短"],
      ["maxLength", "最长"],
      ["pattern", "格式"],
    ])
      if (prop[key] !== undefined) details.push(label + "：" + prop[key]);
    const result = [
      [
        prefix + name,
        Array.isArray(type) ? type.join(" / ") : type,
        schema.required?.includes(name) ? "必填" : "可选",
        details.filter(Boolean).join("；") || "—",
      ],
    ];
    let nested = prop.items || prop;
    if (nested.anyOf)
      nested = nested.anyOf.find((v) => v.type !== "null") || {};
    if (depth < 5 && (nested.$ref || nested.properties))
      result.push(
        ...rows(nested, prefix + name + (prop.items ? "[]." : "."), depth + 1),
      );
    return result;
  });
}
const table = (headers, values) =>
  [headers, headers.map(() => "---"), ...values]
    .map(
      (row) =>
        "| " +
        row
          .map((v) => String(v).replaceAll("|", "\\|").replaceAll("\n", "<br>"))
          .join(" | ") +
        " |",
    )
    .join("\n");
const code = (value, language = "json") =>
  "```" +
  language +
  "\n" +
  (typeof value === "string" ? value : JSON.stringify(value, null, 2)) +
  "\n```";
const parts = [
  "# " + doc.title,
  `版本 ${doc.version} · 更新 ${doc.updated} · API origin：${doc.gateway_origin} · 默认 Play origin：${doc.play_origin}`,
  "> 本文档不包含任何商户真实密钥；所有标识、金额和签名向量均为示例。",
];
for (const section of doc.sections) {
  parts.push("## " + section.title, section.summary);
  for (const block of section.blocks) {
    if (block.type === "paragraph") parts.push(block.text);
    else if (block.type === "list")
      parts.push(block.items.map((x, i) => `${i + 1}. ${x}`).join("\n"));
    else if (block.type === "table")
      parts.push(table(block.headers, block.rows));
    else if (block.type === "code")
      parts.push(block.title, code(block.code, block.language));
    else {
      const e = doc.endpoints.find((e) => e.id === block.endpoint_id);
      parts.push(
        "### " + e.title,
        `**${e.method} ${e.path}** · ${e.direction}`,
        e.description,
        Object.keys(e.request_schema.properties || {}).length
          ? table(["请求字段", "类型", "要求", "说明"], rows(e.request_schema))
          : "请求体：空 JSON 对象 `{}`。",
        "请求示例：\n" + code(e.request_example),
        `成功响应 HTTP ${e.status}：\n` + code(e.response_example),
        "响应字段：\n" +
          table(["字段", "类型", "要求", "说明"], rows(e.response_schema)),
      );
      if (e.notes.length) parts.push(e.notes.map((x) => "- " + x).join("\n"));
    }
  }
}
const escapeHTML = (v) => String(v ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"})[c]);
const htmlTable = (headers, values) => `<div class="table-scroll"><table><thead><tr>${headers.map(v => `<th>${escapeHTML(v)}</th>`).join("")}</tr></thead><tbody>${values.map(row => `<tr>${row.map(v => `<td>${escapeHTML(v)}</td>`).join("")}</tr>`).join("")}</tbody></table></div>`;
const htmlCode = (value) => `<pre><code>${escapeHTML(typeof value === "string" ? value : JSON.stringify(value, null, 2))}</code></pre>`;
const htmlEndpoint = (id) => {
  const e = doc.endpoints.find(e => e.id === id);
  return `<article id="api-${escapeHTML(id)}"><h3>${escapeHTML(e.title)}</h3><p>${escapeHTML(e.direction)} · HTTP ${e.status}</p><pre>${escapeHTML(e.method + " " + e.path)}</pre><p>${escapeHTML(e.description)}</p><h4>请求字段</h4>${rows(e.request_schema).length ? htmlTable(["字段","类型","要求","说明"], rows(e.request_schema)) : "<p>请求体为空 JSON 对象 {}。</p>"}<h4>请求示例</h4>${htmlCode(e.request_example)}<h4>响应字段</h4>${htmlTable(["字段","类型","要求","说明"], rows(e.response_schema))}<h4>成功响应 · HTTP ${e.status}</h4>${htmlCode(e.response_example)}<ul>${e.notes.map(n => `<li>${escapeHTML(n)}</li>`).join("")}</ul></article>`;
};
const htmlBlock = (b) => {
  if (b.type === "paragraph") return `<p>${escapeHTML(b.text)}</p>`;
  if (b.type === "table") return htmlTable(b.headers, b.rows);
  if (b.type === "list") return `<ol>${b.items.map(v => `<li>${escapeHTML(v)}</li>`).join("")}</ol>`;
  if (b.type === "code") return `<h4>${escapeHTML(b.title || b.language)}</h4>${htmlCode(b.code)}`;
  return htmlEndpoint(b.endpoint_id);
};
const html = `<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>${escapeHTML(doc.title)} · ${escapeHTML(doc.version)}</title>
<style>body{font:16px/1.7 system-ui,"Microsoft YaHei",sans-serif;color:#172338;background:#f3f5f8;margin:0}main{max-width:1100px;margin:32px auto;padding:36px;background:white;border-radius:12px}h1,h2,h3{line-height:1.35}h2{padding-top:24px;border-top:1px solid #d9e0ea}h3{margin-top:32px}p,li,td{overflow-wrap:anywhere}nav{background:#f3f6fb;padding:16px 24px;border-radius:8px}nav a{display:block;color:#2055a2;text-decoration:none;margin:5px 0}table{border-collapse:collapse;width:100%;font-size:14px;margin:16px 0}th,td{text-align:left;vertical-align:top;border:1px solid #d9e0ea;padding:10px}th{background:#edf2f8}pre{background:#f4f6fa;border:1px solid #d9e0ea;padding:16px;border-radius:6px;white-space:pre-wrap;overflow-wrap:anywhere;font-size:13px}code{font-family:Consolas,monospace}.table-scroll{overflow-x:auto}footer{margin-top:32px;color:#526176}@media(max-width:700px){main{margin:0;padding:20px;border-radius:0}table{min-width:600px}}@media print{body{background:white}main{margin:0;padding:0;max-width:none}nav{break-after:page}h2,h3,h4{break-after:avoid}tr,pre{break-inside:avoid}thead{display:table-header-group}table{min-width:0}a{color:inherit}.table-scroll{overflow:visible}}</style></head><body><main>
<header><h1>${escapeHTML(doc.title)}</h1><p>版本 ${escapeHTML(doc.version)} · 更新 ${escapeHTML(doc.updated)}</p><p>API origin：${escapeHTML(doc.gateway_origin)}<br>默认 Play origin：${escapeHTML(doc.play_origin)}</p><p>本文件可离线阅读，也可通过浏览器打印为 PDF。示例不包含真实密钥。</p></header>
<!-- GTT_CONTEXT -->
<nav aria-label="目录"><strong>目录</strong>${doc.sections.map(s => `<a href="#${escapeHTML(s.id)}">${escapeHTML(s.title)}</a>`).join("")}</nav>
${doc.sections.map(s => `<section id="${escapeHTML(s.id)}"><h2>${escapeHTML(s.title)}</h2><p>${escapeHTML(s.summary)}</p>${s.blocks.map(htmlBlock).join("\n")}</section>`).join("\n")}
<footer>GTT · 规范 ${escapeHTML(doc.version)} · 与接入中心、Markdown 和 OpenAPI 同源生成。</footer></main></body></html>\n`;
for (const [name, content] of [
  ["openapi.json", JSON.stringify(api, null, 2) + "\n"],
  ["guide.md", parts.join("\n\n") + "\n"],
  ["guide.html", html],
]) {
  const path = new URL(name, folder);
  if (process.argv.includes("--check")) {
    if (readFileSync(path, "utf8").replaceAll("\r\n", "\n") !== content)
      throw Error("Stale integration download: " + fileURLToPath(path));
  } else writeFileSync(path, existsSync(path) && readFileSync(path, "utf8").includes("\r\n") ? content.replaceAll("\n", "\r\n") : content);
}

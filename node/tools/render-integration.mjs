// integration.json is the Node contract source; keep both downloads in sync.
import { readFileSync, writeFileSync } from "node:fs";
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
for (const [name, content] of [
  ["openapi.json", JSON.stringify(api, null, 2) + "\n"],
  ["guide.md", parts.join("\n\n") + "\n"],
]) {
  const path = new URL(name, folder);
  if (process.argv.includes("--check")) {
    if (readFileSync(path, "utf8").replaceAll("\r\n", "\n") !== content)
      throw Error("Stale integration download: " + fileURLToPath(path));
  } else writeFileSync(path, readFileSync(path, "utf8").includes("\r\n") ? content.replaceAll("\n", "\r\n") : content);
}

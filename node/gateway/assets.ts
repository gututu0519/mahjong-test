import { readFileSync, realpathSync, statSync } from "node:fs";
import { resolve, relative, extname, basename } from "node:path";
import { runInNewContext } from "node:vm";
import { check } from "../shared/core.js";
export function repairModule(source: string) {
  source = source
    .replace(/^\uFEFF/, "")
    .replace(
      /function\s*\(\s*\)\s*\{\s*return (['"])newState\1;\s*\}/g,
      "function(){return 'newState';}",
    );
  const id = "[A-Za-z_$][\\w$]*";
  const decoder = new RegExp(
    `(var (${id}) = function\\(${id}\\) \\{\\s*var ${id} = ['"]abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789\\+/=['"];\\s*var ${id} = '';?.{0,160}?)(, ${id} = ${id} \\+ \\2;)`,
    "gs",
  );
  source = source.replace(
    decoder,
    (_m, a, _fn, b) =>
      a + b.slice(0, -1) + ".toString().replace(/[\\r\\n]/g, '');",
  );
  const callback = new RegExp(
    `(^[ \\t]*)((?:var |, )(${id}) = ${id}\\(this, function\\(\\) \\{)(.*?)(^[ \\t]*\\}\\);)`,
    "gms",
  );
  source = source.replace(callback, (all, indent, head, name, body, close) => {
    const escaped = name.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    if (
      !new RegExp(
        `return ${escaped}\\[.*\\]\\(\\)\\[.*\\]\\(${escaped}\\)\\[`,
      ).test(body)
    )
      return all;
    return (
      indent +
      head +
      body.replace(
        new RegExp(
          `(^[ \\t]*${id}\\[[^\\n]+?\\] = )[^\\n;]+ \\+ ['"]\\+\\$['"];`,
          "gm",
        ),
        "$1'.+$';",
      ) +
      close
    );
  });
  let registrations = 0;
  runInNewContext(
    source,
    {
      document: { querySelector: () => null, body: {} },
      MutationObserver: class {
        observe() {}
        disconnect() {}
        takeRecords() {
          return [];
        }
      },
      System: {
        register(...args: any[]) {
          if (typeof args[0] === "string") args.shift();
          check(
            Array.isArray(args[0]) && typeof args[1] === "function",
            "MODULE_INVALID",
          );
          registrations++;
        },
      },
    },
    { timeout: 1000 },
  );
  check(registrations > 0, "MODULE_INVALID");
  return source;
}
const mime: any = {
  ".html": "text/html; charset=utf-8",
  ".js": "application/javascript; charset=utf-8",
  ".css": "text/css; charset=utf-8",
  ".json": "application/json",
  ".png": "image/png",
  ".jpg": "image/jpeg",
  ".jpeg": "image/jpeg",
  ".webp": "image/webp",
  ".mp3": "audio/mpeg",
  ".ogg": "audio/ogg",
  ".woff": "font/woff",
  ".woff2": "font/woff2",
  ".ttf": "font/ttf",
  ".wasm": "application/wasm",
  ".bin": "application/octet-stream",
};
export function asset(root: string, url: string) {
  const path = decodeURIComponent(new URL(url, "http://local").pathname);
  check(
    !path.includes("\\") && !path.includes("\0"),
    "NOT_FOUND",
    "Not found",
    404,
  );
  if (path === "/" || path === "/index.html") {
    let html = readFileSync(resolve(root, "index.html"), "utf8");
    check(html.split("xt=i,kt=''").length === 2, "CLIENT_ENTRY_CHANGED");
    html = html.replace(
      "xt=i,kt=''",
      "xt=new URL(i,location.href).href,kt=new URL('.',location.href).href",
    );
    check(html.includes('<script id="main-script"'), "CLIENT_ENTRY_CHANGED");
    return {
      data: Buffer.from(
        html.replace(
          '<script id="main-script"',
          '<script src="/local-auth-bootstrap.js"></script><script src="/local-frame-clock.js"></script><script id="main-script"',
        ),
      ),
      type: mime[".html"],
    };
  }
  let full: string;
  try {
    full = realpathSync(resolve(root, "." + path));
  } catch {
    check(false, "NOT_FOUND", "Not found", 404);
  }
  const rel = relative(realpathSync(root), full!);
  check(
    rel &&
      !rel.startsWith("..") &&
      !rel.split(/[\\/]/).includes("fixtures") &&
      statSync(full!).isFile() &&
      mime[extname(full!).toLowerCase()],
    "NOT_FOUND",
    "Not found",
    404,
  );
  const data = readFileSync(full!);
  return {
    data:
      basename(full!) === "index.js" && rel.split(/[\\/]/).includes("shared")
        ? Buffer.from(repairModule(data.toString("utf8")))
        : data,
    type: mime[extname(full!).toLowerCase()],
  };
}

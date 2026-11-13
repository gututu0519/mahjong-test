import { DatabaseSync } from "node:sqlite";
import { readFileSync, statSync, existsSync, realpathSync } from "node:fs";
import { resolve, extname, relative, isAbsolute } from "node:path";
import { createHash, createHmac, timingSafeEqual } from "node:crypto";
import { repairModule } from "../gateway/assets.js";

export class BytesIO {
  offset = 0;
  constructor(public buffer: Buffer) {}
  read(n?: number) {
    const end = n === undefined ? this.buffer.length : this.offset + n;
    const data = this.buffer.subarray(this.offset, end);
    this.offset += data.length;
    return data;
  }
  close() {}
}
export function mime(path: string) {
  return (
    (
      {
        ".html": "text/html",
        ".js": "application/javascript",
        ".mjs": "application/javascript",
        ".css": "text/css",
        ".json": "application/json",
        ".txt": "text/plain",
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".webp": "image/webp",
        ".gif": "image/gif",
        ".svg": "image/svg+xml",
        ".ico": "image/x-icon",
        ".mp3": "audio/mpeg",
        ".ogg": "audio/ogg",
        ".wav": "audio/wav",
        ".mp4": "video/mp4",
        ".webm": "video/webm",
        ".woff": "font/woff",
        ".woff2": "font/woff2",
        ".ttf": "font/ttf",
        ".wasm": "application/wasm",
        ".xml": "application/xml",
        ".bin": "application/octet-stream",
      } as any
    )[extname(path).toLowerCase()] ?? "application/octet-stream"
  );
}
export function install(p: any) {
  const {
    modules,
    native,
    call,
    attr,
    dict,
    tuple,
    plain,
    from,
    iter,
    item,
    ValueError,
    KeyError,
  } = p;
  const py = (name: string, names: string[], impl: any, defaults: any = {}) =>
    p.fn(
      name,
      { names, kwonly: [], defaults, vararg: null, kwarg: null },
      impl,
    );
  const error = (C: any) =>
    Object.assign(
      native(([m = ""]) => new C(String(m))),
      { __error: C },
    );
  const asBuffer = (x: any) => (Buffer.isBuffer(x) ? x : Buffer.from(x));
  class Row {
    constructor(public values: any) {}
    __getitem__(k: any) {
      if (typeof k === "number") return Object.values(this.values)[k];
      if (!Object.hasOwn(this.values, k)) throw new KeyError(k);
      return this.values[k];
    }
  }
  class Connection {
    db: DatabaseSync;
    row_factory: any;
    constructor(path: any) {
      this.db = new DatabaseSync(String(path));
      this.db.exec("PRAGMA busy_timeout=15000");
    }
    execute(sql: string, params: any = []) {
      const stmt = this.db.prepare(sql);
      const args = Array.from(iter(params)).map(plain);
      let rows: any[] = [],
        changes = 0,
        id: any;
      if (stmt.columns().length)
        rows = stmt.all(...(args as any)).map((r) => new Row(r));
      else {
        const result = stmt.run(...(args as any));
        changes = Number(result.changes);
        id = result.lastInsertRowid;
      }
      let i = 0;
      return {
        fetchone: () => rows[i++] ?? null,
        fetchall: () => rows.slice(i),
        rowcount: changes,
        lastrowid: id,
      };
    }
    executescript(sql: string) {
      this.db.exec(sql);
    }
    commit() {
      this.db.exec("COMMIT");
    }
    rollback() {
      if (this.db.isTransaction) this.db.exec("ROLLBACK");
    }
    close() {
      this.db.close();
    }
  }
  modules.sqlite3 = {
    connect: native(([path]) => new Connection(path)),
    Row,
    IntegrityError: error(Error),
  };
  modules.io = { BytesIO: native(([x]) => new BytesIO(x)) };
  modules.functools = {
    partial: native(([f, ...a], kw) =>
      native((rest, k) => call(f, [...a, ...rest], { ...kw, ...k })),
    ),
    lru_cache: native(() => native(([f]) => f)),
  };
  modules.threading = {
    RLock: () => ({ __enter__: () => null, __exit__: () => false }),
  };
  modules.argparse = {};
  modules.sys = {};
  modules["py.run"] = {
    main: () => {
      throw new Error("Use Node CLI service --service-dir");
    },
  };
  modules.logging = Object.fromEntries(
    ["info", "warning", "error", "exception", "basicConfig", "FileHandler"].map(
      (k) => [
        k,
        native((a) => {
          if (k === "exception") console.error(...a.map(p.str));
          return null;
        }),
      ],
    ),
  );
  modules.html = {
    escape: native(([s], k) =>
      String(s)
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', k.quote === false ? '"' : "&quot;")
        .replaceAll("'", k.quote === false ? "'" : "&#x27;"),
    ),
  };
  modules.mimetypes = {
    guess_type: native(([s]) => tuple([mime(String(s)), null])),
  };
  modules.base64 = {
    b64encode: (b: any) => Buffer.from(asBuffer(b).toString("base64")),
    b64decode: native(([v], k) => {
      const s = Buffer.isBuffer(v) ? v.toString() : String(v);
      if (
        k.validate &&
        !/^(?:[A-Za-z0-9+/]{4})*(?:[A-Za-z0-9+/]{2}==|[A-Za-z0-9+/]{3}=)?$/.test(
          s,
        )
      )
        throw new ValueError("Invalid base64");
      return Buffer.from(s, "base64");
    }),
  };
  modules.hmac = {
    new: (key: Buffer, message: Buffer) => ({
      hexdigest: () => createHmac("sha256", key).update(message).digest("hex"),
    }),
    compare_digest: (a: string, b: string) =>
      a.length === b.length && timingSafeEqual(Buffer.from(a), Buffer.from(b)),
  };
  modules.datetime = {
    timezone: { utc: "UTC" },
    datetime: {
      now: () => ({
        strftime: () => new Date().toISOString().replace(/\.\d{3}Z$/, "Z"),
      }),
    },
  };
  const quote = (s: any) =>
    encodeURIComponent(p.str(s))
      .replace(
        /[!'()*]/g,
        (c) => "%" + c.charCodeAt(0).toString(16).toUpperCase(),
      )
      .replaceAll("%20", "+");
  modules["urllib.parse"] = {
    parse_qs: native(([query], k) => {
      const d = dict();
      for (const [key, v] of new URLSearchParams(
        Buffer.isBuffer(query) ? query.toString() : String(query),
      )) {
        if (v !== "" || k.keep_blank_values) {
          if (!d.has(key)) d.set(key, []);
          d.get(key).push(v);
        }
      }
      return d;
    }),
    urlencode: native(([v], k) => {
      const values =
        v instanceof Map ? [...v] : Array.isArray(v) ? v : Object.entries(v);
      return values
        .flatMap(([key, value]) =>
          k.doseq && Array.isArray(value)
            ? value.map((x) => quote(key) + "=" + quote(x))
            : [quote(key) + "=" + quote(value)],
        )
        .join("&");
    }),
    unquote: (v: any) => decodeURIComponent(String(v)),
    urlsplit: (s: string) => {
      const absolute = /^[a-zA-Z][\w+.-]*:/.test(s),
        u = new URL(s, "http://local");
      return {
        path: absolute ? u.pathname : s.split(/[?#]/)[0],
        query: u.search.slice(1),
        scheme: absolute ? u.protocol.slice(0, -1) : "",
        netloc: absolute ? u.host : "",
        fragment: u.hash.slice(1),
      };
    },
  };
  modules["urllib.error"] = { URLError: error(Error) };
  modules["urllib.request"] = {
    Request: native((a, k) => ({ args: a, ...k })),
    urlopen: () => {
      throw new Error("Cross-service launch must use the async Node transport");
    },
  };
  function regex(pattern: any, flags = 0) {
    return new RegExp(
      String(pattern)
        .replace(/\(\?P<(\w+)>/g, "(?<$1>")
        .replace(/\(\?P=(\w+)\)/g, "\\k<$1>"),
      "g" +
        (flags & 16 ? "s" : "") +
        (flags & 8 ? "m" : "") +
        (flags & 2 ? "i" : ""),
    );
  }
  function matchObject(m: RegExpExecArray) {
    return {
      __getitem__: (k: any) => (typeof k === "number" ? m[k] : m.groups?.[k]),
      group: (k: any = 0) => (typeof k === "number" ? m[k] : m.groups?.[k]),
    };
  }
  const substitute = (
    pattern: any,
    repl: any,
    value: any,
    count = 0,
    flags = 0,
  ) => {
    let n = 0;
    const result = String(value).replace(
      regex(pattern, flags),
      (...args: any[]) => {
        if (count && n++ >= count) return args[0];
        const groupIndex =
          typeof args.at(-1) === "object" ? args.length - 1 : args.length;
        const m: any = args.slice(0, groupIndex - 2);
        m.groups = groupIndex < args.length ? args.at(-1) : undefined;
        if (typeof repl === "function") return call(repl, [matchObject(m)]);
        return String(repl).replace(/\\g<(\w+)>|\\([1-9]\d*)/g, (_, a, b) =>
          a ? (m.groups?.[a] ?? "") : (m[Number(b)] ?? ""),
        );
      },
    );
    return result;
  };
  modules.re = {
    DOTALL: 16,
    MULTILINE: 8,
    IGNORECASE: 2,
    escape: (s: string) => s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"),
    fullmatch: native(([pattern, value]) => {
      const m = regex("^(?:" + pattern + ")$").exec(value);
      return m ? matchObject(m) : null;
    }),
    sub: native(([pattern, repl, value, count = 0], k) =>
      substitute(pattern, repl, value, count, k.flags ?? 0),
    ),
    search: native(([pattern, value, flags = 0]) => {
      const m = regex(pattern, flags).exec(value);
      return m ? matchObject(m) : null;
    }),
    compile: (pattern: any, flags = 0) => ({
      sub: (repl: any, value: any) =>
        substitute(pattern, repl, value, 0, flags),
      search: (value: any) => {
        const m = regex(pattern, flags).exec(value);
        return m ? matchObject(m) : null;
      },
    }),
  };
  function struct(fmt: string, values: any[], buffer?: Buffer) {
    let endian = fmt[0],
      at = 0,
      vi = 0;
    const sizes: any = {
      b: 1,
      B: 1,
      "?": 1,
      h: 2,
      H: 2,
      i: 4,
      I: 4,
      l: 4,
      L: 4,
      q: 8,
      Q: 8,
      f: 4,
      d: 8,
    };
    if (!"<>!@=".includes(endian)) endian = "@";
    else fmt = fmt.slice(1);
    const parts = [...fmt.matchAll(/(\d*)([bB?hHiIlLqQfd])/g)].flatMap((m) =>
      Array(Number(m[1] || 1)).fill(m[2]),
    );
    if (parts.join("").length !== fmt.replace(/\d/g, "").length)
      throw new ValueError("Unsupported struct format");
    const out = buffer ?? Buffer.alloc(parts.reduce((n, t) => n + sizes[t], 0)),
      result: any[] = [];
    const little = endian !== ">" && endian !== "!";
    for (const kind of parts) {
      const size = sizes[kind];
      if (at + size > out.length) throw new ValueError("Invalid struct size");
      const suffix = little ? "LE" : "BE",
        signed = "bhiq l".includes(kind),
        method =
          kind === "d"
            ? "Double"
            : kind === "f"
              ? "Float"
              : size === 8
                ? signed
                  ? "BigInt64"
                  : "BigUInt64"
                : size === 1
                  ? signed
                    ? "Int8"
                    : "UInt8"
                  : (signed ? "Int" : "UInt") + size * 8;
      const key = method + (size === 1 ? "" : suffix);
      if (buffer) {
        const value = (out as any)["read" + key](at);
        result.push(kind === "d" || kind === "f" ? p.float(value) : value);
      } else {
        let v = values[vi++];
        v = size === 8 && kind !== "d" ? BigInt(v) : Number(v);
        (out as any)["write" + key](v, at);
      }
      at += size;
    }
    if (buffer && at !== buffer.length)
      throw new ValueError("Invalid struct size");
    return buffer ? tuple(result) : out;
  }
  modules.struct = {
    pack: native(([fmt, ...values]) => struct(fmt, values)),
    unpack: (fmt: string, bytes: Buffer) => struct(fmt, [], bytes),
  };
  modules["py.adapters.pg.client_modules"] = {
    prepare_module: native(([bytes]) => {
      const repaired = Buffer.from(repairModule(bytes.toString("utf8")));
      return tuple([
        repaired,
        createHash("sha256").update(repaired).digest("hex"),
      ]);
    }),
  };
  // The async transport installs real WebSocket handlers before serving requests.
  for (const name of [
    "py.adapters.tada.life_service",
    "py.adapters.playngo.player_events",
  ])
    modules[name] = { serve: native(([handler]) => handler.__websocket(name)) };
  const baseFields: any = {
    __init__: py(
      "__init__",
      ["self", "context", "directory"],
      (self, ctx, directory) => {
        Object.assign(self, ctx);
        self.directory = directory ?? ctx.directory;
      },
      { directory: null },
    ),
    send_response: py(
      "send_response",
      ["self", "status", "message"],
      (self, status) => {
        self.__status = Number(status);
      },
      { message: null },
    ),
    send_header: py(
      "send_header",
      ["self", "name", "value"],
      (self, name, value) => {
        self.__headers[name] = p.str(value);
      },
    ),
    end_headers: py("end_headers", ["self"], () => null),
    send_error: py(
      "send_error",
      ["self", "status", "message"],
      (self, status, message) => {
        self.__status = status;
        self.__headers["Content-Type"] = "text/plain; charset=utf-8";
        self.__chunks.push(Buffer.from(message ?? "Not found"));
      },
      { message: null },
    ),
    address_string: py(
      "address_string",
      ["self"],
      (self) => self.__remote ?? "127.0.0.1",
    ),
    log_error: py("log_error", ["self", "format", "a", "b"], () => null, {
      a: null,
      b: null,
    }),
    translate_path: py("translate_path", ["self", "path"], (self, path) => {
      const name = decodeURIComponent(String(path).split("?")[0]);
      if (name.includes("\\") || name.includes("\0"))
        throw new ValueError("Invalid path");
      const base = resolve(String(self.directory)),
        target = resolve(base, "." + name),
        rel = relative(base, target);
      if (rel.startsWith("..") || isAbsolute(rel))
        throw new ValueError("Invalid path");
      return target;
    }),
    list_directory: py("list_directory", ["self", "path"], (self) => {
      call(attr(self, "send_error"), [404]);
      return null;
    }),
    send_head: py("send_head", ["self"], (self) => {
      let path = call(attr(self, "translate_path"), [self.path]);
      if (existsSync(path) && statSync(path).isDirectory()) {
        path = resolve(path, "index.html");
      }
      if (!existsSync(path) || !statSync(path).isFile()) {
        call(attr(self, "send_error"), [404]);
        return null;
      }
      const rel = relative(
        realpathSync(String(self.directory)),
        realpathSync(path),
      );
      if (rel.startsWith("..") || isAbsolute(rel)) {
        call(attr(self, "send_error"), [404]);
        return null;
      }
      const bytes = readFileSync(path);
      call(attr(self, "send_response"), [200]);
      call(attr(self, "send_header"), ["Content-Type", mime(path)]);
      call(attr(self, "send_header"), ["Content-Length", String(bytes.length)]);
      call(attr(self, "end_headers"));
      return new BytesIO(bytes);
    }),
    do_GET: py("do_GET", ["self"], (self) => {
      const file = call(attr(self, "send_head"));
      if (file) {
        self.wfile.write(file.read());
        file.close();
      }
    }),
    do_HEAD: py("do_HEAD", ["self"], (self) => {
      const file = call(attr(self, "send_head"));
      if (file) file.close();
    }),
  };
  const Base = p.cls("BaseHTTPRequestHandler", [], baseFields);
  const Http = p.cls("ThreadingHTTPServer", [], {
    __init__: py(
      "__init__",
      ["self", "address", "handler"],
      (self, address, handler) => {
        self.server_address = address;
        self.server_port = address[1];
        self.handler = handler;
      },
    ),
  });
  modules["http.server"] = {
    BaseHTTPRequestHandler: Base,
    SimpleHTTPRequestHandler: Base,
    ThreadingHTTPServer: Http,
  };
  modules["http.cookies"] = {
    SimpleCookie: (initial = "") => {
      const values = dict();
      for (const part of initial.split(";")) {
        const at = part.indexOf("=");
        if (at >= 0)
          values.set(part.slice(0, at).trim(), {
            value: part.slice(at + 1).trim(),
          });
      }
      return {
        load: (s: string) => {
          for (const part of s.split(";")) {
            const at = part.indexOf("=");
            if (at >= 0)
              values.set(part.slice(0, at).trim(), {
                value: part.slice(at + 1).trim(),
              });
          }
        },
        get: (k: string) => values.get(k) ?? null,
        __getitem__: (k: string) => values.get(k),
      };
    },
  };
  p.b.KeyboardInterrupt = error(Error);
}

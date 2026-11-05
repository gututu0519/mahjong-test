import {
  createHash,
  createHmac,
  randomBytes,
  timingSafeEqual,
} from "node:crypto";
import { DatabaseSync } from "node:sqlite";
import { mkdirSync } from "node:fs";
import { dirname, resolve } from "node:path";
export class ServiceError extends Error {
  constructor(
    public code: string,
    message = code,
    public status = 400,
  ) {
    super(message);
  }
}
export function check(
  ok: unknown,
  code: string,
  message = code,
  status = 400,
): asserts ok {
  if (!ok) throw new ServiceError(code, message, status);
}
export const now = () => Math.floor(Date.now() / 1000);
export const hex = (n = 16) => randomBytes(n).toString("hex");
export const token = () => randomBytes(32).toString("base64url");
export const sha = (v: string | Buffer) =>
  createHash("sha256").update(v).digest("hex");
export const clone = <T>(v: T): T => structuredClone(v);
export const equal = (a: string, b: string) =>
  typeof a === "string" &&
  typeof b === "string" &&
  Buffer.byteLength(a) === Buffer.byteLength(b) &&
  timingSafeEqual(Buffer.from(a), Buffer.from(b));
export function encode(v: any): string {
  if (v === null) return "null";
  if (Array.isArray(v)) return "[" + v.map(encode).join(",") + "]";
  if (typeof v === "object")
    return (
      "{" +
      Object.keys(v)
        .sort()
        .map((k) => JSON.stringify(k) + ":" + encode(v[k]))
        .join(",") +
      "}"
    );
  check(
    v !== undefined && (!(typeof v === "number") || Number.isFinite(v)),
    "INVALID_ARGUMENT",
  );
  return JSON.stringify(v);
}
// Python json.dumps(sort_keys=True), including Python's float constants in game configs.
export function pythonJSON(v: any, key = ""): string {
  if (v === null) return "null";
  if (Array.isArray(v))
    return "[" + v.map((x) => pythonJSON(x)).join(", ") + "]";
  if (typeof v === "object")
    return (
      "{" +
      Object.keys(v)
        .sort()
        .map((k) => pythonJSON(k) + ": " + pythonJSON(v[k], k))
        .join(", ") +
      "}"
    );
  if (typeof v === "number" && Number.isInteger(v) && key === "t")
    return v + ".0";
  return JSON.stringify(v).replace(
    /[\u007f-\uffff]/g,
    (c) => "\\u" + c.charCodeAt(0).toString(16).padStart(4, "0"),
  );
}
export function identifier(v: any, name = "identifier"): string {
  check(
    typeof v === "string" && /^[A-Za-z0-9_.:-]{1,128}$/.test(v),
    "INVALID_ARGUMENT",
    name,
  );
  return v;
}
export function amount(v: any): number {
  check(
    Number.isSafeInteger(v) && v >= 0 && v <= 9_000_000_000_000_000,
    "INVALID_ARGUMENT",
    "Invalid integer amount",
  );
  return v;
}
export function limit(v = 20): number {
  check(Number.isInteger(v) && v >= 1 && v <= 100, "INVALID_ARGUMENT");
  return v;
}
export function signature(
  secret: string,
  path: string,
  stamp: string,
  nonce: string,
  body: Buffer | string,
) {
  return createHmac("sha256", secret)
    .update(["POST", path, stamp, nonce, sha(Buffer.from(body))].join("\n"))
    .digest("hex");
}
export function signedHeaders(
  id: string,
  secret: string,
  path: string,
  body: string,
) {
  const stamp = String(now()),
    nonce = hex();
  return {
    "Content-Type": "application/json",
    "X-GTT-Merchant": id,
    "X-GTT-Timestamp": stamp,
    "X-GTT-Nonce": nonce,
    "X-GTT-Signature": signature(secret, path, stamp, nonce, body),
  };
}
// Strict JSON parser: reject duplicate keys, non-finite numbers and unsafe integers.
export function parseJSON(raw: string): any {
  let i = 0;
  const ws = () => {
    while (/\s/.test(raw[i] ?? "") && i < raw.length) i++;
  };
  const str = () => {
    const start = i++;
    while (i < raw.length) {
      if (raw[i++] === '"') return JSON.parse(raw.slice(start, i));
      if (raw[i - 1] === "\\") i++;
    }
    throw new ServiceError("BAD_REQUEST");
  };
  const val = (): any => {
    ws();
    const c = raw[i];
    if (c === '"') return str();
    if (c === "{" || c === "[") {
      i++;
      ws();
      const obj = c === "{" ? Object.create(null) : [],
        end = c === "{" ? "}" : "]";
      if (raw[i] === end) {
        i++;
        return obj;
      }
      while (true) {
        if (c === "{") {
          check(raw[i] === '"', "BAD_REQUEST");
          const k = str();
          ws();
          check(raw[i++] === ":" && !Object.hasOwn(obj, k), "BAD_REQUEST");
          obj[k] = val();
        } else obj.push(val());
        ws();
        if (raw[i] === end) {
          i++;
          return obj;
        }
        check(raw[i++] === ",", "BAD_REQUEST");
        ws();
      }
    }
    const m =
      /^(?:true|false|null|-?(?:0|[1-9]\d*)(?:\.\d+)?(?:[eE][+-]?\d+)?)/.exec(
        raw.slice(i),
      );
    check(m, "BAD_REQUEST");
    i += m[0].length;
    const v = JSON.parse(m[0]);
    check(
      typeof v !== "number" ||
        (Number.isFinite(v) &&
          (!Number.isInteger(v) || Number.isSafeInteger(v))),
      "BAD_REQUEST",
    );
    return v;
  };
  try {
    const out = val();
    ws();
    check(i === raw.length, "BAD_REQUEST");
    return out;
  } catch (e) {
    if (e instanceof ServiceError) throw e;
    throw new ServiceError("BAD_REQUEST");
  }
}
export function object(raw: string) {
  const v = parseJSON(raw);
  check(v && typeof v === "object" && !Array.isArray(v), "BAD_REQUEST");
  return v;
}
export class DB {
  db: DatabaseSync;
  path: string;
  constructor(path: string) {
    this.path = resolve(path);
    mkdirSync(dirname(this.path), { recursive: true });
    this.db = new DatabaseSync(this.path);
    this.db.exec(
      "PRAGMA journal_mode=WAL; PRAGMA foreign_keys=ON; PRAGMA synchronous=FULL; PRAGMA busy_timeout=15000; CREATE TABLE IF NOT EXISTS request_nonces(merchant_id TEXT NOT NULL,nonce TEXT NOT NULL,expires_at INTEGER NOT NULL,PRIMARY KEY(merchant_id,nonce));",
    );
  }
  run(sql: string, ...args: any[]) {
    return this.db
      .prepare(sql)
      .run(...args.map((v) => (typeof v === "boolean" ? Number(v) : v)));
  }
  get(sql: string, ...args: any[]): any {
    return this.db.prepare(sql).get(...args);
  }
  all(sql: string, ...args: any[]): any[] {
    return this.db.prepare(sql).all(...args);
  }
  tx<T>(fn: () => T): T {
    this.db.exec("BEGIN IMMEDIATE");
    try {
      const v = fn();
      check(!(v instanceof Promise), "ASYNC_TRANSACTION");
      this.db.exec("COMMIT");
      return v;
    } catch (e) {
      this.db.exec("ROLLBACK");
      throw e;
    }
  }
  column(table: string, name: string, definition: string) {
    if (
      !this.all("PRAGMA table_info(" + table + ")").some((r) => r.name === name)
    )
      this.db.exec(
        "ALTER TABLE " + table + " ADD COLUMN " + name + " " + definition,
      );
  }
  authenticate(headers: any, path: string, body: Buffer, merchant: any) {
    const id = String(headers["x-gtt-merchant"] ?? ""),
      ts = String(headers["x-gtt-timestamp"] ?? ""),
      nonce = String(headers["x-gtt-nonce"] ?? ""),
      sig = String(headers["x-gtt-signature"] ?? "");
    check(
      merchant?.enabled &&
        /^\d{10}$/.test(ts) &&
        Math.abs(now() - Number(ts)) <= 300 &&
        /^[A-Za-z0-9_-]{16,64}$/.test(nonce),
      "AUTH_INVALID",
      "Invalid authentication",
      401,
    );
    check(
      /^[a-f0-9]{64}$/.test(sig) &&
        equal(sig, signature(merchant.merchant_secret, path, ts, nonce, body)),
      "AUTH_INVALID",
      "Invalid signature",
      401,
    );
    this.tx(() => {
      this.run("DELETE FROM request_nonces WHERE expires_at<?", now());
      check(
        !this.get(
          "SELECT 1 FROM request_nonces WHERE merchant_id=? AND nonce=?",
          id,
          nonce,
        ),
        "AUTH_REPLAY",
        "Nonce already used",
        409,
      );
      this.run(
        "INSERT INTO request_nonces VALUES(?,?,?)",
        id,
        nonce,
        now() + 601,
      );
    });
    return id;
  }
  close() {
    this.db.close();
  }
}
export class Serial {
  private tails = new Map<string, Promise<any>>();
  async run<T>(key: string, fn: () => Promise<T>): Promise<T> {
    const old = this.tails.get(key) ?? Promise.resolve();
    const next = old.catch(() => {}).then(fn);
    this.tails.set(key, next);
    try {
      return await next;
    } finally {
      if (this.tails.get(key) === next) this.tails.delete(key);
    }
  }
}

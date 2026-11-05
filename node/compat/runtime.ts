// Node implementations of the value and standard-library semantics used by the
// migrated modules. No Python interpreter, child process, or source evaluation.
import { readFileSync, existsSync, statSync, mkdirSync } from "node:fs";
import {
  resolve,
  dirname,
  basename,
  extname,
  relative,
  isAbsolute,
} from "node:path";
import { fileURLToPath } from "node:url";
import { createHash, randomBytes, randomUUID } from "node:crypto";
import { ServiceError } from "../shared/core.js";
import { PythonRandom } from "../games/buffalo-win/random.js";
import { install } from "./platform.js";

export const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "../..");
export const sourcePath = (path: string) =>
  resolve(
    process.env.GTT_RESOURCE_ROOT ??
      (existsSync(resolve(ROOT, "resources"))
        ? resolve(ROOT, "resources")
        : resolve(ROOT, "..")),
    path,
  );
export class Float {
  constructor(public value: number) {}
  valueOf() {
    return this.value;
  }
}
export const float = (v: any) => new Float(Number(v));
class Tuple extends Array<any> {}
export const tuple = (v: any[]) => Object.assign(new Tuple(), v);
export class Dict extends Map<any, any> {
  private key(k: any) {
    if (k instanceof Tuple || k instanceof Float || k instanceof Decimal) {
      for (const old of super.keys()) if (equal(old, k)) return old;
    }
    return k;
  }
  get(k: any) {
    return super.get(this.key(k));
  }
  has(k: any) {
    return super.has(this.key(k));
  }
  set(k: any, v: any) {
    return super.set(this.key(k), v);
  }
  delete(k: any) {
    return super.delete(this.key(k));
  }
}
class ValueSet extends Set<any> {
  private key(k: any) {
    if (k instanceof Tuple || k instanceof Float || k instanceof Decimal) {
      for (const old of super.values()) if (equal(old, k)) return old;
    }
    return k;
  }
  has(k: any) {
    return super.has(this.key(k));
  }
  add(k: any) {
    return super.add(this.key(k));
  }
  delete(k: any) {
    return super.delete(this.key(k));
  }
}
export const dict = (pairs: any[] = []) => {
  const d = new Dict();
  for (const [k, v] of pairs) {
    if (k === null) for (const [key, val] of entries(v)) d.set(key, val);
    else d.set(k, v);
  }
  return d;
};
export const kw = (pairs: any[] = []) => Object.fromEntries(dict(pairs));
export const set = (v: any[] = []) => new ValueSet(iter(v));
export function* iter(v: any): Generator<any> {
  if (v instanceof Dict) {
    yield* v.keys();
    return;
  }
  if (v instanceof Set) {
    const a = [...v];
    yield* a.every((x) => typeof x === "number") ? a.sort((x, y) => x - y) : a;
    return;
  }
  if (v?.[Symbol.iterator]) {
    yield* v;
    return;
  }
  throw new TypeError("Object is not iterable");
}
export const entries = (v: any): any[] =>
  v instanceof Map
    ? [...v.entries()]
    : v?.[Symbol.iterator]
      ? Array.from(iter(v))
      : v && typeof v === "object"
        ? Object.entries(v)
        : Array.from(iter(v));
export function truth(v: any): boolean {
  if (v == null || v === false) return false;
  if (v instanceof Float || v instanceof Decimal) return Number(v) !== 0;
  if (typeof v === "number" || typeof v === "bigint")
    return v !== 0 && v !== 0n;
  if (typeof v === "string" || Array.isArray(v) || Buffer.isBuffer(v))
    return v.length > 0;
  if (v instanceof Map || v instanceof Set) return v.size > 0;
  return true;
}
export function or_(...fs: any[]) {
  let v;
  for (const f of fs) {
    v = f();
    if (truth(v)) break;
  }
  return v;
}
export function and_(...fs: any[]) {
  let v;
  for (const f of fs) {
    v = f();
    if (!truth(v)) break;
  }
  return v;
}
export function equal(a: any, b: any): boolean {
  if (a === b) return true;
  if (a instanceof Path && b instanceof Path)
    return resolve(a.value) === resolve(b.value);
  if (
    (a instanceof Float ||
      a instanceof Decimal ||
      typeof a === "number" ||
      typeof a === "boolean" ||
      typeof a === "bigint") &&
    (b instanceof Float ||
      b instanceof Decimal ||
      typeof b === "number" ||
      typeof b === "boolean" ||
      typeof b === "bigint")
  )
    return Number(a) === Number(b);
  if (a instanceof Map && b instanceof Map)
    return (
      a.size === b.size &&
      [...a].every(([k, v]) => b.has(k) && equal(v, b.get(k)))
    );
  if (a instanceof Set && b instanceof Set)
    return (
      a.size === b.size && [...a].every((x) => [...b].some((y) => equal(x, y)))
    );
  if (Array.isArray(a) && Array.isArray(b))
    return (
      a instanceof Tuple === b instanceof Tuple &&
      a.length === b.length &&
      a.every((x, i) => equal(x, b[i]))
    );
  if (Buffer.isBuffer(a) && Buffer.isBuffer(b)) return a.equals(b);
  return false;
}
function order(a: any, b: any): number {
  if (equal(a, b)) return 0;
  if (Array.isArray(a) && Array.isArray(b)) {
    for (let i = 0; i < Math.min(a.length, b.length); i++) {
      const c = order(a[i], b[i]);
      if (c) return c;
    }
    return a.length - b.length;
  }
  return a < b ? -1 : 1;
}
export function contains(v: any, k: any) {
  if (v instanceof Map || v instanceof Set) return v.has(k);
  if (typeof v === "string") return v.includes(k);
  return Array.from(iter(v)).some((x) => equal(x, k));
}
export function compare(ops: string[], values: (() => any)[]) {
  let a = values[0]();
  for (let i = 0; i < ops.length; i++) {
    const b = values[i + 1](),
      op = ops[i];
    const yes =
      op === "Eq"
        ? equal(a, b)
        : op === "NotEq"
          ? !equal(a, b)
          : op === "Is"
            ? a === b
            : op === "IsNot"
              ? a !== b
              : op === "In"
                ? contains(b, a)
                : op === "NotIn"
                  ? !contains(b, a)
                  : op === "Lt"
                    ? order(a, b) < 0
                    : op === "LtE"
                      ? order(a, b) <= 0
                      : op === "Gt"
                        ? order(a, b) > 0
                        : order(a, b) >= 0;
    if (!yes) return false;
    a = b;
  }
  return true;
}
export function unary(op: string, v: any): any {
  if (op === "Not") return !truth(v);
  if (op === "Invert") return ~Number(v);
  if (op === "USub")
    return v instanceof Decimal
      ? new Decimal(-v.n, v.d)
      : v instanceof Float
        ? float(-Number(v))
        : -v;
  return v;
}
export function bin(op: string, a: any, c: any): any {
  if (op === "Div" && a instanceof Path)
    return new Path(resolve(a.value, String(c)));
  if (op === "Add" && Array.isArray(a) && Buffer.isBuffer(c))
    return [...a, ...c];
  if (op === "Add") {
    if (Array.isArray(a) && Array.isArray(c))
      return a instanceof Tuple ? tuple([...a, ...c]) : [...a, ...c];
    if (Buffer.isBuffer(a) && Buffer.isBuffer(c)) return Buffer.concat([a, c]);
    if (typeof a === "string" && typeof c === "string") return a + c;
  }
  if (
    op === "Mult" &&
    (Array.isArray(a) || typeof a === "string" || Buffer.isBuffer(a))
  ) {
    const n = Math.max(0, Number(c));
    if (typeof a === "string") return a.repeat(n);
    if (Buffer.isBuffer(a)) return Buffer.concat(Array(n).fill(a));
    const r = Array.from({ length: n }, () => a).flat();
    return a instanceof Tuple ? tuple(r) : r;
  }
  if (a instanceof Set && c instanceof Set) {
    return set(
      op === "Sub"
        ? [...a].filter((x) => !c.has(x))
        : op === "BitAnd"
          ? [...a].filter((x) => c.has(x))
          : [...a, ...c],
    );
  }
  if (a instanceof Decimal || c instanceof Decimal) {
    const x = decimal(a),
      y = decimal(c);
    if (op === "Add") return new Decimal(x.n * y.d + y.n * x.d, x.d * y.d);
    if (op === "Sub") return new Decimal(x.n * y.d - y.n * x.d, x.d * y.d);
    if (op === "Mult") return new Decimal(x.n * y.n, x.d * y.d);
    if (op === "Div") return new Decimal(x.n * y.d, x.d * y.n);
  }
  if (op === "Mod" && typeof a === "string") {
    let i = 0;
    const vals = Array.isArray(c) ? c : [c];
    return a.replace(/%([.\d]*)([sdrf%])/g, (_, f, t) =>
      t === "%" ? "%" : format(vals[i++], f + (t === "f" ? "f" : "")),
    );
  }
  if (
    ["BitOr", "BitAnd", "BitXor", "LShift", "RShift"].includes(op) ||
    ((typeof a === "bigint" || typeof c === "bigint") &&
      ["Add", "Sub", "Mult", "Mod", "FloorDiv"].includes(op))
  ) {
    const x = BigInt(a),
      y = BigInt(c);
    const value =
      op === "BitOr"
        ? x | y
        : op === "BitAnd"
          ? x & y
          : op === "BitXor"
            ? x ^ y
            : op === "LShift"
              ? x << y
              : op === "RShift"
                ? x >> y
                : op === "Add"
                  ? x + y
                  : op === "Sub"
                    ? x - y
                    : op === "Mult"
                      ? x * y
                      : op === "Mod"
                        ? ((x % y) + y) % y
                        : x / y;
    return value <= BigInt(Number.MAX_SAFE_INTEGER) &&
      value >= BigInt(Number.MIN_SAFE_INTEGER)
      ? Number(value)
      : value;
  }
  const x = Number(a),
    y = Number(c);
  let r: any;
  switch (op) {
    case "Add":
      r = x + y;
      break;
    case "Sub":
      r = x - y;
      break;
    case "Mult":
      r = x * y;
      break;
    case "Div":
      r = x / y;
      break;
    case "FloorDiv":
      r = Math.floor(x / y);
      break;
    case "Mod":
      r = ((x % y) + y) % y;
      break;
    case "Pow":
      r = x ** y;
      break;
    case "BitOr":
      r = BigInt(x) | BigInt(y);
      break;
    case "BitAnd":
      r = BigInt(x) & BigInt(y);
      break;
    case "BitXor":
      r = BigInt(x) ^ BigInt(y);
      break;
    case "LShift":
      r = BigInt(x) << BigInt(y);
      break;
    case "RShift":
      r = BigInt(x) >> BigInt(y);
      break;
    default:
      throw Error("Unknown operator " + op);
  }
  if (typeof r === "bigint")
    return r <= BigInt(Number.MAX_SAFE_INTEGER) &&
      r >= BigInt(Number.MIN_SAFE_INTEGER)
      ? Number(r)
      : r;
  return op === "Div" || a instanceof Float || c instanceof Float
    ? float(r)
    : r;
}
class Slice {
  constructor(
    public start: any,
    public stop: any,
    public step: any,
  ) {}
}
export const slice = (a: any, b: any, c: any) => new Slice(a, b, c);
function indices(n: number, s: Slice) {
  const step = s.step ?? 1;
  assert(step !== 0, "Slice step cannot be zero");
  let start = s.start == null ? (step > 0 ? 0 : n - 1) : Number(s.start),
    stop = s.stop == null ? (step > 0 ? n : -1) : Number(s.stop);
  if (start < 0) start += n;
  if (stop < 0 && s.stop != null) stop += n;
  start = Math.min(Math.max(start, step > 0 ? 0 : -1), step > 0 ? n : n - 1);
  stop = Math.min(Math.max(stop, -1), n);
  const a: any[] = [];
  for (let i = start; step > 0 ? i < stop : i > stop; i += step) a.push(i);
  return a;
}
export function item(v: any, k: any): any {
  if (k instanceof Slice) {
    const out = indices(v.length, k).map((i) => v[i]);
    return typeof v === "string"
      ? out.join("")
      : Buffer.isBuffer(v)
        ? Buffer.from(out)
        : v instanceof Tuple
          ? tuple(out)
          : out;
  }
  if (v instanceof Map) {
    if (!v.has(k)) throw new KeyError(String(k));
    return v.get(k);
  }
  if (v?.__getitem__) return v.__getitem__(k);
  if (Array.isArray(v) || typeof v === "string" || Buffer.isBuffer(v)) {
    let i = Number(k);
    if (i < 0) i += v.length;
    if (i < 0 || i >= v.length) throw new IndexError(String(k));
    return v[i];
  }
  if (v != null && Object.hasOwn(v, k)) return v[k];
  throw new KeyError(String(k));
}
export function setitem(v: any, k: any, value: any) {
  if (v instanceof Map) {
    v.set(k, value);
    return;
  }
  if (k instanceof Slice) {
    const ids = indices(v.length, k),
      vals = Array.from(iter(value));
    if ((k.step ?? 1) === 1)
      v.splice(ids[0] ?? k.start ?? 0, ids.length, ...vals);
    else {
      assert(ids.length === vals.length, "Slice length mismatch");
      ids.forEach((i, j) => (v[i] = vals[j]));
    }
    return;
  }
  if (Array.isArray(v) && k < 0) k += v.length;
  v[k] = value;
}
export function delitem(v: any, k: any) {
  if (v instanceof Map) v.delete(k);
  else if (Array.isArray(v)) {
    if (k instanceof Slice) {
      for (const i of indices(v.length, k).sort((a, b) => b - a))
        v.splice(i, 1);
    } else v.splice(k < 0 ? v.length + k : k, 1);
  } else delete v[k];
}
export const setattr = (v: any, k: string, x: any) => {
  v[k] = x;
};
export const assert = (value: any, message: any = "Assertion failed") => {
  if (!truth(value)) throw new Error(String(message));
};
export const native = (f: (args: any[], kwargs: any) => any) =>
  Object.assign((...args: any[]) => f(args, {}), { __invoke: f });
export function call(f: any, args: any[] = [], kwargs: any = {}) {
  if (f?.__invoke) return f.__invoke(args, kwargs);
  if (typeof f === "function") return f(...args);
  throw new TypeError("Object is not callable: " + String(f));
}
export function fn(name: string, spec: any, impl: any) {
  const f = native((args, k) => {
    const values: any = { ...spec.defaults };
    if (!spec.vararg && args.length > spec.names.length)
      throw new TypeError(name + ": too many arguments");
    spec.names.forEach((n, i) => {
      if (i < args.length) values[n] = args[i];
    });
    const extras: any[] = [];
    for (const [n, v] of Object.entries(k)) {
      if (spec.names.includes(n) || spec.kwonly.includes(n)) {
        if (spec.names.indexOf(n) >= 0 && spec.names.indexOf(n) < args.length)
          throw new TypeError(name + ": duplicate argument " + n);
        values[n] = v;
      } else if (spec.kwarg) extras.push([n, v]);
      else throw new TypeError(name + ": unexpected " + n);
    }
    for (const n of [...spec.names, ...spec.kwonly])
      if (!Object.hasOwn(values, n))
        throw new TypeError(name + ": missing " + n);
    return impl(
      ...spec.names.map((n) => values[n]),
      ...spec.kwonly.map((n) => values[n]),
      ...(spec.vararg ? [tuple(args.slice(spec.names.length))] : []),
      ...(spec.kwarg ? [dict(extras)] : []),
    );
  });
  return Object.assign(f, { __py: true, __name__: name });
}
function lookup(c: any, name: string): any {
  if (Object.hasOwn(c.__fields, name)) return c.__fields[name];
  for (const base of c.__bases) {
    const v = lookup(base, name);
    if (v !== undefined) return v;
  }
  return undefined;
}
export function cls(name: string, bases: any[], fields: any) {
  const c: any = native((args, k) => {
    const obj: any = { __class__: c };
    const init = lookup(c, "__init__");
    if (init) call(init, [obj, ...args], k);
    return obj;
  });
  Object.assign(c, {
    __classType: true,
    __name__: name,
    __bases: bases,
    __fields: fields,
  });
  return c;
}
export const super_ = (c: any, self: any) => ({ __super__: c, __self__: self });
function bound(f: any, self: any) {
  return f?.__static
    ? f
    : f?.__py
      ? native((a, k) => call(f, [self, ...a], k))
      : f;
}
function method(f: (...args: any[]) => any) {
  return native((a, k) => f(...a, k));
}
export function attr(v: any, name: string): any {
  if (v?.__super__) {
    for (const base of v.__super__.__bases) {
      const f = lookup(base, name);
      if (f !== undefined) return bound(f, v.__self__);
    }
  }
  if (v?.__classType) {
    const f = lookup(v, name);
    if (f !== undefined) return f;
  }
  if (v != null && Object.hasOwn(v, name)) return v[name];
  if (v?.__class__) {
    const f = lookup(v.__class__, name);
    if (f !== undefined) return bound(f, v);
  }
  if (v instanceof Map) {
    switch (name) {
      case "get":
        return native(([k, d = null]) => (v.has(k) ? v.get(k) : d));
      case "keys":
        return native(() => new Set(v.keys()));
      case "values":
        return native(() => [...v.values()]);
      case "items":
        return native(() => [...v].map((x) => tuple(x)));
      case "update":
        return native((a, k) => {
          for (const src of [...a, k])
            for (const [key, val] of entries(src)) v.set(key, val);
          return null;
        });
      case "setdefault":
        return native(([k, d = null]) => {
          if (!v.has(k)) v.set(k, d);
          return v.get(k);
        });
      case "pop":
        return native(([k, ...rest]) => {
          if (!v.has(k)) {
            if (rest.length) return rest[0];
            throw new KeyError(k);
          }
          const x = v.get(k);
          v.delete(k);
          return x;
        });
      case "copy":
        return native(() => new Dict(v));
      case "clear":
        return native(() => {
          v.clear();
          return null;
        });
    }
  }
  if (v instanceof Set) {
    switch (name) {
      case "add":
        return native(([x]) => {
          v.add(x);
          return null;
        });
      case "update":
        return native((a) => {
          for (const x of a) for (const y of iter(x)) v.add(y);
          return null;
        });
      case "clear":
        return native(() => {
          v.clear();
          return null;
        });
      case "copy":
        return native(() => set([...v]));
      case "discard":
      case "remove":
        return native(([x]) => {
          if (name === "remove" && !v.has(x)) throw new KeyError(x);
          v.delete(x);
          return null;
        });
      case "difference_update":
        return native((a) => {
          for (const x of a) for (const y of iter(x)) v.delete(y);
          return null;
        });
      case "issubset":
        return native(([x]) => [...v].every((y) => contains(x, y)));
      case "pop":
        return native(() => {
          const x = iter(v).next();
          if (x.done) throw new KeyError("empty set");
          v.delete(x.value);
          return x.value;
        });
    }
  }
  if (Array.isArray(v)) {
    switch (name) {
      case "append":
        return native(([x]) => {
          v.push(x);
          return null;
        });
      case "extend":
        return native(([x]) => {
          v.push(...iter(x));
          return null;
        });
      case "pop":
        return native(([i = -1]) => {
          if (i < 0) i += v.length;
          if (i < 0 || i >= v.length) throw new IndexError("pop");
          return v.splice(i, 1)[0];
        });
      case "insert":
        return native(([i, x]) => {
          v.splice(i, 0, x);
          return null;
        });
      case "count":
        return native(([x]) => v.filter((y) => equal(x, y)).length);
      case "index":
        return native(([x]) => {
          const i = v.findIndex((y) => equal(x, y));
          if (i < 0) throw new ValueError("not in list");
          return i;
        });
      case "remove":
        return native(([x]) => {
          const i = v.findIndex((y) => equal(x, y));
          if (i < 0) throw new ValueError("not in list");
          v.splice(i, 1);
          return null;
        });
      case "copy":
        return native(() => v.slice());
      case "clear":
        return native(() => {
          v.length = 0;
          return null;
        });
    }
  }
  if (typeof v === "string") return stringAttr(v, name);
  if (Buffer.isBuffer(v)) {
    if (name === "join")
      return native(([values]) => {
        const out: any[] = [];
        for (const x of iter(values)) {
          if (out.length) out.push(v);
          out.push(x);
        }
        return Buffer.concat(out);
      });
    if (name === "decode")
      return native(([enc = "utf-8"], k) =>
        new TextDecoder(enc === "utf-8-sig" ? "utf-8" : enc, {
          fatal: k.errors !== "replace",
        }).decode(v),
      );
    if (name === "hex") return native(() => v.toString("hex"));
    if (
      [
        "count",
        "replace",
        "startswith",
        "endswith",
        "split",
        "rstrip",
      ].includes(name)
    )
      return native((a, k) => {
        const result = call(
          stringAttr(v.toString("latin1"), name),
          a.map((x) => (Buffer.isBuffer(x) ? x.toString("latin1") : x)),
          k,
        );
        return typeof result === "string"
          ? Buffer.from(result, "latin1")
          : Array.isArray(result)
            ? result.map((x) => Buffer.from(x, "latin1"))
            : result;
      });
  }
  if (v != null && typeof v[name] === "function")
    return native((a, k) =>
      v[name](...a, ...(Object.keys(k).length ? [k] : [])),
    );
  if (v != null && name in Object(v)) return v[name];
  throw new TypeError(
    "Missing attribute " + name + " on " + String(v?.__class__?.__name__ ?? v),
  );
}
function stringAttr(v: string, name: string) {
  switch (name) {
    case "encode":
      return native(([enc = "utf-8"]) => Buffer.from(v, enc));
    case "join":
      return native(([xs]) => Array.from(iter(xs)).join(v));
    case "startswith":
    case "endswith":
      return native(([x]) =>
        (Array.isArray(x) ? x : [x]).some((s) =>
          name === "startswith" ? v.startsWith(s) : v.endsWith(s),
        ),
      );
    case "split":
      return native(([sep = null, n = -1]) => {
        const a = sep == null ? v.trim().split(/\s+/) : v.split(sep);
        return n >= 0 && a.length > n + 1
          ? [...a.slice(0, n), a.slice(n).join(sep ?? " ")]
          : a;
      });
    case "rsplit":
      return native(([sep, n = -1]) => {
        const a = v.split(sep);
        return n >= 0 && a.length > n + 1
          ? [a.slice(0, -n).join(sep), ...a.slice(-n)]
          : a;
      });
    case "replace":
      return native(([a, c, n = -1]) => {
        let i = 0;
        return v
          .split(a)
          .reduce(
            (s, x, j) => (j === 0 ? x : s + (n < 0 || i++ < n ? c : a) + x),
            "",
          );
      });
    case "lower":
      return native(() => v.toLowerCase());
    case "upper":
      return native(() => v.toUpperCase());
    case "isdecimal":
    case "isdigit":
      return native(() => /^\d+$/.test(v));
    case "count":
      return native(([s]) => v.split(s).length - 1);
    case "strip":
    case "lstrip":
    case "rstrip":
      return native(([chars = null]) => {
        let a = 0,
          c = v.length;
        const match = (x: string) =>
          chars == null ? /\s/.test(x) : chars.includes(x);
        if (name !== "rstrip") while (a < c && match(v[a])) a++;
        if (name !== "lstrip") while (c > a && match(v[c - 1])) c--;
        return v.slice(a, c);
      });
    case "removeprefix":
      return native(([s]) => (v.startsWith(s) ? v.slice(s.length) : v));
    case "removesuffix":
      return native(([s]) => (v.endsWith(s) ? v.slice(0, -s.length) : v));
    case "splitlines":
      return native(() => v.split(/\r?\n/));
    case "format":
      return native((a, k) => {
        let i = 0;
        return v.replace(/\{([^{}]*)\}/g, (_, s) => {
          const [id, spec = ""] = s.split(":");
          return format(
            id === "" ? a[i++] : /^\d+$/.test(id) ? a[Number(id)] : k[id],
            spec,
          );
        });
      });
  }
  throw new TypeError("Unknown string method " + name);
}
export function plain(v: any): any {
  if (v instanceof Float || v instanceof Decimal) return Number(v);
  if (v instanceof Map)
    return Object.fromEntries([...v].map(([k, x]) => [String(k), plain(x)]));
  if (v instanceof Set || Array.isArray(v)) return Array.from(v).map(plain);
  if (Buffer.isBuffer(v)) return v;
  if (v && typeof v === "object")
    return Object.fromEntries(
      Object.entries(v)
        .filter(([k]) => !k.startsWith("__"))
        .map(([k, x]) => [k, plain(x)]),
    );
  return v;
}
export function from(v: any): any {
  if (Array.isArray(v)) return v.map(from);
  if (v && typeof v === "object" && !Buffer.isBuffer(v) && !(v instanceof Map))
    return dict(Object.entries(v).map(([k, x]) => [k, from(x)]));
  return v;
}
export function clone(v: any): any {
  if (v instanceof Float) return float(v.value);
  if (v instanceof Decimal) return new Decimal(v.n, v.d);
  if (v instanceof Map) return dict([...v].map(([k, x]) => [k, clone(x)]));
  if (v instanceof Set) return set([...v].map(clone));
  if (Array.isArray(v))
    return v instanceof Tuple ? tuple(v.map(clone)) : v.map(clone);
  if (Buffer.isBuffer(v)) return Buffer.from(v);
  if (v && typeof v === "object")
    return Object.fromEntries(Object.entries(v).map(([k, x]) => [k, clone(x)]));
  return v;
}
export function jsonLoads(data: any) {
  const text = Buffer.isBuffer(data) ? data.toString("utf8") : String(data);
  let i = 0;
  function parse(): any {
    while (/\s/.test(text[i] ?? "") && i < text.length) i++;
    const c = text[i];
    if (c === '"') {
      const start = i++;
      while (i < text.length) {
        if (text[i++] === '"') break;
        if (text[i - 1] === "\\") i++;
      }
      return JSON.parse(text.slice(start, i));
    }
    if (c === "[") {
      i++;
      const a: any[] = [];
      while (true) {
        while (/\s/.test(text[i] ?? "") && i < text.length) i++;
        if (text[i] === "]") {
          i++;
          return a;
        }
        a.push(parse());
        while (/\s/.test(text[i] ?? "") && i < text.length) i++;
        if (text[i] === ",") {
          i++;
          continue;
        }
        if (text[i] !== "]") throw new ValueError("Invalid JSON");
      }
    }
    if (c === "{") {
      i++;
      const d = new Dict();
      while (true) {
        while (/\s/.test(text[i] ?? "") && i < text.length) i++;
        if (text[i] === "}") {
          i++;
          return d;
        }
        const k = parse();
        while (/\s/.test(text[i] ?? "") && i < text.length) i++;
        if (text[i++] !== ":") throw new ValueError("Invalid JSON");
        if (d.has(k)) throw new ValueError("Duplicate JSON key");
        d.set(k, parse());
        while (/\s/.test(text[i] ?? "") && i < text.length) i++;
        if (text[i] === ",") {
          i++;
          continue;
        }
        if (text[i] !== "}") throw new ValueError("Invalid JSON");
      }
    }
    const m =
      /^(?:true|false|null|-?(?:0|[1-9]\d*)(?:\.\d+)?(?:[eE][+-]?\d+)?)/.exec(
        text.slice(i),
      );
    if (!m) throw new ValueError("Invalid JSON");
    i += m[0].length;
    const x = JSON.parse(m[0]);
    return typeof x === "number" && /[.eE]/.test(m[0]) ? float(x) : x;
  }
  const out = parse();
  if (text.slice(i).trim()) throw new ValueError("Trailing JSON");
  return out;
}
export function jsonDumps(v: any, options: any = {}): string {
  const separators = options.separators ?? [", ", ": "];
  function enc(x: any): string {
    if (x instanceof Float) {
      const n = x.value;
      if (!Number.isFinite(n)) {
        if (options.allow_nan === false)
          throw new ValueError("Non-finite JSON");
        return String(n);
      }
      return Number.isInteger(n)
        ? String(n) + ".0"
        : String(n).replace(/e([+-]?)(\d)$/, "e$10$2");
    }
    if (x instanceof Decimal) throw new TypeError("Decimal is not JSON");
    if (x instanceof Map) {
      let es = [...x];
      if (options.sort_keys) es.sort(([a], [c]) => order(a, c));
      return (
        "{" +
        es
          .map(([k, val]) => enc(String(k)) + separators[1] + enc(val))
          .join(separators[0]) +
        "}"
      );
    }
    if (Array.isArray(x)) return "[" + x.map(enc).join(separators[0]) + "]";
    if (x === undefined) throw new TypeError("Undefined JSON");
    let s = JSON.stringify(x);
    if (typeof x === "string" && options.ensure_ascii !== false)
      s = s.replace(
        /[\u007f-\uffff]/g,
        (c) => "\\u" + c.charCodeAt(0).toString(16).padStart(4, "0"),
      );
    return s;
  }
  return enc(v);
}
export function str(v: any): string {
  if (v == null) return "None";
  if (v === true) return "True";
  if (v === false) return "False";
  if (v instanceof Float)
    return Number.isInteger(v.value) ? String(v.value) + ".0" : String(v.value);
  if (v instanceof Decimal) return v.toString();
  if (v instanceof Error) return v.message;
  if (v instanceof Path) return v.value;
  if (Array.isArray(v))
    return (
      (v instanceof Tuple ? "(" : "[") +
      v
        .map((x) => (typeof x === "string" ? "'" + x + "'" : str(x)))
        .join(", ") +
      (v instanceof Tuple ? ")" : "]")
    );
  return String(v);
}
export function format(v: any, spec = "", conversion = -1): string {
  if (!spec) return str(v);
  const m = /^(?:0?(\d+))?(?:\.(\d+))?([fdx])?$/.exec(spec);
  if (!m) throw new ValueError("Unsupported format " + spec);
  let s =
    m[3] === "f"
      ? Number(v).toFixed(Number(m[2] ?? 6))
      : m[3] === "x"
        ? Number(v).toString(16)
        : str(v);
  if (m[1]) s = s.padStart(Number(m[1]), spec.startsWith("0") ? "0" : " ");
  return s;
}
export class ValueError extends Error {}
export class KeyError extends Error {}
export class IndexError extends Error {}
export class InvalidOperation extends Error {}
export const matches = (error: any, types: any): boolean =>
  Array.isArray(types)
    ? types.some((t) => matches(error, t))
    : types?.__matches
      ? types.__matches(error)
      : types === b.Exception || types === b.BaseException
        ? error instanceof Error
        : types === modules["server.core.contracts"]?.ServiceError
          ? error instanceof ServiceError
          : !!types?.__error && error instanceof types.__error;
const errorType = (C: any) =>
  Object.assign(
    native(([message = ""]) => new C(str(message))),
    { __error: C },
  );
export class Decimal {
  constructor(
    public n: bigint,
    public d = 1n,
  ) {
    if (!d) throw new InvalidOperation("Division by zero");
  }
  valueOf() {
    return Number(this.n) / Number(this.d);
  }
  toString() {
    return String(this.valueOf());
  }
  is_finite() {
    return true;
  }
  to_integral_value() {
    return new Decimal(BigInt(Math.round(this.valueOf())));
  }
}
function decimal(v: any): Decimal {
  if (v instanceof Decimal) return v;
  const m = /^([+-]?)(\d+)(?:\.(\d*))?(?:[eE]([+-]?\d+))?$/.exec(
    String(v instanceof Float ? v.value : v),
  );
  if (!m) throw new InvalidOperation("Invalid decimal");
  const scale = (m[3] ?? "").length - Number(m[4] ?? 0);
  if (Math.abs(scale) > 1000) throw new InvalidOperation("Decimal limit");
  const n = BigInt(m[1] + m[2] + (m[3] ?? ""));
  return scale >= 0
    ? new Decimal(n, 10n ** BigInt(scale))
    : new Decimal(n * 10n ** BigInt(-scale));
}
export class Path {
  value: string;
  memory: any;
  constructor(v: any) {
    if (v instanceof Dict) {
      this.memory = v;
      this.value = "memory.json";
    } else this.value = v instanceof Path ? v.value : String(v);
  }
  toString() {
    return this.value;
  }
  valueOf() {
    return this.value;
  }
  get parent() {
    return new Path(dirname(this.value));
  }
  get parents() {
    const out: any[] = [];
    let d = this.value;
    while (dirname(d) !== d) {
      d = dirname(d);
      out.push(new Path(d));
    }
    return out;
  }
  get parts() {
    return this.value.split(/[\\/]/).filter(Boolean);
  }
  get name() {
    return basename(this.value);
  }
  get suffix() {
    return extname(this.value);
  }
  resolve() {
    return new Path(resolve(this.value));
  }
  with_name(n: string) {
    return new Path(resolve(dirname(this.value), n));
  }
  read_text(..._args: any[]) {
    return this.memory
      ? jsonDumps(this.memory)
      : readFileSync(this.value, "utf8").replace(/^\uFEFF/, "");
  }
  read_bytes() {
    return readFileSync(this.value);
  }
  is_file() {
    return existsSync(this.value) && statSync(this.value).isFile();
  }
  is_relative_to(base: any) {
    const r = relative(String(base), this.value);
    return !r.startsWith("..") && !isAbsolute(r);
  }
  relative_to(base: any) {
    if (!this.is_relative_to(base)) throw new ValueError("Not relative");
    return new Path(relative(String(base), this.value));
  }
  mkdir(k: any = {}) {
    mkdirSync(this.value, { recursive: k.parents ?? false });
    return null;
  }
  as_posix() {
    return this.value.replaceAll("\\", "/");
  }
}
export function context(value: any) {
  if (value?.next) {
    const first = value.next();
    return {
      value: first.value,
      exit: (error: any) => {
        try {
          if (error) value.throw(error);
          else value.next();
          return !!error;
        } catch (e) {
          if (e === error) return false;
          throw e;
        }
      },
    };
  }
  if (value?.__enter__)
    return {
      value: value.__enter__(),
      exit: (error: any) => value.__exit__(error),
    };
  return { value, exit: () => false };
}
function random(seed: any) {
  const r = new PythonRandom(seed instanceof Float ? String(seed.value) : seed),
    choose = (xs: any) => {
      const a = Array.from(iter(xs));
      return a[r.range(a.length)];
    };
  return {
    random: () => float(r.random()),
    randrange: (start: number, stop?: number, step = 1) =>
      stop === undefined
        ? r.range(start)
        : start + step * r.range(Math.ceil((stop - start) / step)),
    randint: (a: number, c: number) => r.int(a, c),
    choice: choose,
    choices: native(([xs, weights = null], k) => {
      const a = Array.from(iter(xs)),
        w = weights ?? k.weights,
        count = k.k ?? 1;
      return Array.from({ length: count }, () =>
        w
          ? r.choice(a as any, w.map(Number))
          : a[Math.floor(r.random() * a.length)],
      );
    }),
    shuffle: (xs: any[]) => {
      for (let i = xs.length - 1; i > 0; i--) {
        const j = r.range(i + 1);
        [xs[i], xs[j]] = [xs[j], xs[i]];
      }
      return null;
    },
    sample: (xs: any, count: number) => {
      const a = Array.from(iter(xs)),
        n = a.length,
        out: any[] = [];
      if (count < 0 || count > n) throw new ValueError("Sample size");
      let size = 21;
      if (count > 5) size += 4 ** Math.ceil(Math.log(count * 3) / Math.log(4));
      if (n <= size) {
        for (let i = 0; i < count; i++) {
          const j = r.range(n - i);
          out.push(a[j]);
          a[j] = a[n - i - 1];
        }
      } else {
        const chosen = new Set();
        for (let i = 0; i < count; i++) {
          let j = r.range(n);
          while (chosen.has(j)) j = r.range(n);
          chosen.add(j);
          out.push(a[j]);
        }
      }
      return out;
    },
  };
}
export const b: any = {};
const built = (name: string, f: (a: any[], k: any) => any) =>
  (b[name] = native(f));
built("str", ([v = ""]) => str(v));
built("int", ([v = 0]) => {
  if (typeof v === "bigint") return v;
  const n = Number(v);
  if (
    !Number.isFinite(n) ||
    (typeof v === "string" && !/^[+-]?\d+$/.test(v.trim()))
  )
    throw new ValueError("Invalid integer");
  return Math.trunc(n);
});
built("float", ([v = 0]) => float(v));
built("bool", ([v = false]) => truth(v));
built("dict", (a, k) =>
  dict([...(a.length ? entries(a[0]) : []), ...Object.entries(k)]),
);
built("list", ([v = []]) => Array.from(iter(v)));
built("tuple", ([v = []]) => tuple(Array.from(iter(v))));
built("set", ([v = []]) => set(v));
built("len", ([v]) =>
  v instanceof Map || v instanceof Set ? v.size : v.length,
);
built("range", (a) => {
  const [start, stop, step] =
    a.length === 1 ? [0, a[0], 1] : [a[0], a[1], a[2] ?? 1];
  assert(step !== 0, "range step");
  const out: any[] = [];
  for (let i = start; step > 0 ? i < stop : i > stop; i += step) out.push(i);
  return out;
});
built("enumerate", ([v, start = 0]) =>
  Array.from(iter(v)).map((x, i) => tuple([i + start, x])),
);
built("zip", (a) => {
  const arrays = a.map((x) => Array.from(iter(x)));
  return Array.from(
    { length: Math.min(...arrays.map((x) => x.length)) },
    (_, i) => tuple(arrays.map((x) => x[i])),
  );
});
built("map", ([f, ...xs]) =>
  Array.from(iter(call(b.zip, xs))).map((x) => call(f, x)),
);
built("sum", ([v, start = 0]) =>
  Array.from(iter(v)).reduce((a, c) => bin("Add", a, c), start),
);
built("all", ([v]) => {
  for (const x of iter(v)) if (!truth(x)) return false;
  return true;
});
built("any", ([v]) => {
  for (const x of iter(v)) if (truth(x)) return true;
  return false;
});
built("iter", ([v]) => iter(v));
built("next", ([v, ...fallback]) => {
  const r = v.next();
  if (r.done) {
    if (fallback.length) return fallback[0];
    throw new ValueError("StopIteration");
  }
  return r.value;
});
built("sorted", ([v], k) =>
  Array.from(iter(v)).sort(
    (a, c) =>
      (k.reverse ? -1 : 1) *
      order(k.key ? call(k.key, [a]) : a, k.key ? call(k.key, [c]) : c),
  ),
);
for (const name of ["min", "max"])
  built(name, (a, k) => {
    const values = a.length === 1 ? Array.from(iter(a[0])) : a;
    if (!values.length) {
      if ("default" in k) return k.default;
      throw new ValueError("Empty sequence");
    }
    return values.reduce((best, x) =>
      (name === "min" ? -1 : 1) *
        order(
          k.key ? call(k.key, [x]) : x,
          k.key ? call(k.key, [best]) : best,
        ) >
      0
        ? x
        : best,
    );
  });
built("abs", ([v]) =>
  v instanceof Float ? float(Math.abs(Number(v))) : Math.abs(Number(v)),
);
built("round", ([v, n = 0]) => {
  const x = Number(v) * 10 ** n,
    f = Math.floor(x),
    r = x - f === 0.5 ? f + (f % 2) : Math.round(x);
  return n ? float(r / 10 ** n) : r;
});
built("ord", ([v]) => v.codePointAt(0));
built("chr", ([v]) => String.fromCodePoint(v));
built("reversed", ([v]) => Array.from(iter(v)).reverse());
built("getattr", ([v, k, ...fallback]) => {
  try {
    return attr(v, k);
  } catch (e) {
    if (fallback.length) return fallback[0];
    throw e;
  }
});
built("hasattr", ([v, k]) => {
  try {
    attr(v, k);
    return true;
  } catch {
    return false;
  }
});
built("bytes", ([v = []]) => Buffer.from(Array.from(iter(v))));
built("bytearray", ([v = []]) => Array.from(iter(v)));
built("staticmethod", ([f]) => Object.assign(f, { __static: true }));
built("type", ([v]) =>
  v instanceof Float
    ? b.float
    : v instanceof Decimal
      ? modules.decimal.Decimal
      : typeof v === "boolean"
        ? b.bool
        : typeof v === "number" || typeof v === "bigint"
          ? b.int
          : typeof v === "string"
            ? b.str
            : v instanceof Dict
              ? b.dict
              : v instanceof Tuple
                ? b.tuple
                : Array.isArray(v)
                  ? b.list
                  : v instanceof Set
                    ? b.set
                    : Buffer.isBuffer(v)
                      ? b.bytes
                      : (v?.__class__ ?? null),
);
built("isinstance", ([v, types]) => {
  const t = call(b.type, [v]);
  return Array.isArray(types) ? types.some((x) => x === t) : types === t;
});
built("print", (a) => {
  console.log(...a.map(str));
  return null;
});
for (const [name, C] of Object.entries({
  ValueError,
  TypeError,
  KeyError,
  IndexError,
  RuntimeError: Error,
  OverflowError: RangeError,
  UnicodeError: TypeError,
  UnicodeDecodeError: TypeError,
  OSError: Error,
  EOFError: Error,
  Exception: Error,
  BaseException: Error,
  BrokenPipeError: Error,
  ConnectionResetError: Error,
}))
  b[name] = errorType(C);
for (const [name, codes] of Object.entries({
  BrokenPipeError: ["EPIPE"],
  ConnectionResetError: ["ECONNRESET"],
  EOFError: ["EOF"],
}))
  b[name].__matches = (e: any) => codes.includes(e?.code);
b.OSError.__matches = (e: any) =>
  typeof e?.code === "string" && /^E[A-Z0-9]+$/.test(e.code);
b.dict.fromkeys = native(([keys, value = null]) =>
  dict(Array.from(iter(keys)).map((k) => [k, value])),
);
export const modules: any = {
  "server.core.contracts": {
    ServiceError: Object.assign(
      native(
        ([code, message, status = 400]) =>
          new ServiceError(code, message, status),
      ),
      { __error: ServiceError },
    ),
    Outcome: native(([state, event, debit_minor, credit_minor]) => ({
      state,
      event,
      debit_minor,
      credit_minor,
    })),
  },
  copy: { deepcopy: native(([v]) => clone(v)) },
  json: {
    loads: native(([v]) => jsonLoads(v)),
    dumps: native(([v], k) => jsonDumps(v, k)),
    load: native(([v]) => jsonLoads(v.read())),
  },
  hashlib: Object.fromEntries(
    ["sha256", "sha1"].map((name) => [
      name,
      native(([v]) => {
        const hash = createHash(name).update(v).digest();
        return { hexdigest: () => hash.toString("hex"), digest: () => hash };
      }),
    ]),
  ),
  math: {
    prod: native(([v]) =>
      Array.from(iter(v)).reduce((a, c) => bin("Mult", a, c), 1),
    ),
  },
  random: { Random: native(([seed]) => random(seed)) },
  decimal: {
    ROUND_CEILING: "ROUND_CEILING",
    ROUND_FLOOR: "ROUND_FLOOR",
    Decimal: native(([v]) => decimal(v)),
    InvalidOperation: errorType(InvalidOperation),
  },
  pathlib: { Path: native(([v]) => new Path(v)) },
  contextlib: { contextmanager: native(([v]) => v) },
  time: { time: () => float(Date.now() / 1000) },
  secrets: {
    token_hex: (n = 32) => randomBytes(n).toString("hex"),
    token_urlsafe: (n = 32) => randomBytes(n).toString("base64url"),
  },
  uuid: { uuid4: () => ({ hex: randomUUID().replaceAll("-", "") }) },
};
install({
  modules,
  b,
  native,
  call,
  fn,
  cls,
  attr,
  setattr,
  dict,
  tuple,
  plain,
  from,
  iter,
  item,
  truth,
  str,
  float,
  Float,
  Dict,
  Path,
  jsonLoads,
  jsonDumps,
  sourcePath,
  ValueError,
  KeyError,
  ServiceError,
});

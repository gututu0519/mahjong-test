import { GAME_CODES, gameCode, gameNumber } from "../../gateway/src/catalog.js";
import { pbkdf2Sync } from "node:crypto";
import { readFileSync } from "node:fs";
import {
  DB,
  check,
  encode,
  sha,
  hex,
  token,
  now,
  identifier,
  limit,
  equal,
  ServiceError,
} from "./core.js";
export const PERMISSIONS: Record<string, string[]> = {
  admin: [
    "merchants.read",
    "merchants.write",
    "keys.rotate",
    "games.read",
    "games.manage",
    "services.read",
    "services.manage",
    "transactions.read",
    "transactions.retry",
    "audit.read",
    "users.manage",
    "rtp.read",
    "rtp.write",
    "rtp.manage",
  ],
  operator: [
    "services.read",
    "merchants.read",
    "games.read",
    "games.manage",
    "transactions.read",
    "transactions.retry",
    "audit.read",
    "rtp.read",
  ],
  viewer: [
    "services.read",
    "merchants.read",
    "games.read",
    "transactions.read",
    "audit.read",
    "rtp.read",
  ],
  merchant_admin: [
    "merchants.read",
    "profile.write",
    "keys.rotate",
    "games.read",
    "transactions.read",
    "transactions.retry",
    "audit.read",
    "users.manage",
    "rtp.read",
    "rtp.write",
  ],
  merchant_operator: [
    "merchants.read",
    "games.read",
    "transactions.read",
    "transactions.retry",
    "audit.read",
    "rtp.read",
  ],
  merchant_viewer: [
    "merchants.read",
    "games.read",
    "transactions.read",
    "audit.read",
    "rtp.read",
  ],
};
export function passwordHash(p: string, salt = hex()) {
  check(
    typeof p === "string" && p.length >= 12 && p.length <= 128,
    "PASSWORD_INVALID",
  );
  return `pbkdf2_sha256$600000$${salt}$${pbkdf2Sync(p, salt, 600000, 32, "sha256").toString("hex")}`;
}
export function passwordMatches(p: any, stored: string) {
  if (typeof p !== "string" || p.length > 128) return false;
  const [algo, n, salt, digest] = stored.split("$");
  check(
    algo === "pbkdf2_sha256" && Number(n) >= 100000 && Number(n) <= 1000000,
    "PASSWORD_FORMAT_INVALID",
  );
  return equal(
    pbkdf2Sync(p, salt, Number(n), 32, "sha256").toString("hex"),
    digest,
  );
}
export function walletOrigin(v: any) {
  check(typeof v === "string" && v.length <= 512, "WALLET_URL_INVALID");
  v = v.trim().replace(/\/$/, "");
  let u: URL;
  try {
    u = new URL(v);
  } catch {
    throw new ServiceError("WALLET_URL_INVALID");
  }
  check(
    !u.username &&
      !u.password &&
      !u.search &&
      !u.hash &&
      u.pathname === "/" &&
      (u.protocol === "https:" ||
        (u.protocol === "http:" &&
          ["127.0.0.1", "localhost", "[::1]"].includes(u.hostname))),
    "WALLET_URL_INVALID",
  );
  return v;
}
export function prebetURL(v: any) {
  check(
    typeof v === "string" && v.length <= 1024 && !/[\x00-\x20]/.test(v),
    "PREBET_CONFIG_INVALID",
  );
  let u: URL;
  try {
    u = new URL(v);
  } catch {
    throw new ServiceError("PREBET_CONFIG_INVALID");
  }
  walletOrigin(u.origin);
  check(
    !u.search &&
      !u.hash &&
      !u.username &&
      !u.password &&
      u.pathname.startsWith("/"),
    "PREBET_CONFIG_INVALID",
  );
  return v;
}
export const WALLET_ACTIONS = [
  "balance",
  "debit",
  "credit",
  "refund",
  "transactions/get",
  "transactions/list",
] as const;
export function walletCallbackURL(value: any) {
  check(
    typeof value === "string" &&
      value.length <= 1024 &&
      !/[\x00-\x20]/.test(value),
    "WALLET_ENDPOINT_INVALID",
    "钱包接口需要完整 HTTPS URL，本机联调可用 HTTP；不允许空格、查询参数或片段。",
  );
  let url: URL;
  try {
    url = new URL(value);
  } catch {
    throw new ServiceError(
      "WALLET_ENDPOINT_INVALID",
      "钱包接口 URL 格式无效。",
    );
  }
  check(
    !url.username && !url.password && !url.search && !url.hash,
    "WALLET_ENDPOINT_INVALID",
    "钱包接口 URL 不能包含账号、密码、查询参数或片段。",
  );
  try {
    walletOrigin(url.origin);
  } catch {
    throw new ServiceError(
      "WALLET_ENDPOINT_INVALID",
      "钱包接口必须使用 HTTPS，仅本机联调地址允许 HTTP。",
    );
  }
  return url.href;
}
export function walletConfiguration(origin: any, endpoints: any = {}) {
  check(
    endpoints &&
      typeof endpoints === "object" &&
      !Array.isArray(endpoints) &&
      Object.keys(endpoints).every((k) => WALLET_ACTIONS.includes(k as any)),
    "WALLET_ENDPOINT_INVALID",
    "存在未知的钱包接口配置。",
  );
  const configured: Record<string, string> = {};
  for (const [key, value] of Object.entries(endpoints)) {
    check(typeof value === "string", "WALLET_ENDPOINT_INVALID");
    if (value.trim()) configured[key] = walletCallbackURL(value.trim());
  }
  const wallet_url =
    origin === "" || origin === undefined ? "" : walletOrigin(origin);
  check(
    wallet_url || WALLET_ACTIONS.every((k) => configured[k]),
    "WALLET_ENDPOINT_REQUIRED",
    "请填写默认钱包地址，或分别填写全部 6 个钱包接口 URL。",
  );
  return { wallet_url, wallet_endpoints: configured };
}
export function walletEndpoint(merchant: any, action: string) {
  check(WALLET_ACTIONS.includes(action as any), "WALLET_ACTION_INVALID");
  return merchant.wallet_endpoints?.[action]
    ? walletCallbackURL(merchant.wallet_endpoints[action])
    : walletOrigin(merchant.wallet_url) + "/wallet/v1/" + action;
}
export const reason = (p: any) => {
  check(
    typeof p.reason === "string" &&
      p.reason.trim().length >= 4 &&
      p.reason.trim().length <= 300,
    "REASON_REQUIRED",
  );
  return p.reason.trim();
};
const username = (v: any) => {
  check(
    typeof v === "string" && /^[A-Za-z0-9_.-]{3,40}$/.test(v),
    "USERNAME_INVALID",
  );
  return v.toLowerCase();
};
const publicGame = (v: any) => {
  check(typeof v === "number" || typeof v === "string", "GAME_ID_INVALID");
  return typeof v === "number" ? gameCode(v) : gameNumber(v);
};
export class Control extends DB {
  rtpDB?: DB;
  dummy = passwordHash("not-a-real-admin-password", "0".repeat(32));
  constructor(path: string, schema: string) {
    super(path, 'control');
    this.db.exec(readFileSync(schema, "utf8"));
    this.column("admin_users", "merchant_id", "TEXT REFERENCES merchants(id)");
    this.column("admin_audit", "merchant_id", "TEXT");
    this.column("merchants", "login_user_id", "TEXT");
    this.db.exec(
      "CREATE UNIQUE INDEX IF NOT EXISTS merchant_login_name ON merchants(lower(name)); CREATE INDEX IF NOT EXISTS audit_merchant_seq ON admin_audit(merchant_id,seq);",
    );
    this.tx(() => {
      this.run(
        "UPDATE merchants SET login_user_id=(SELECT id FROM admin_users WHERE merchant_id=merchants.id AND role='merchant_admin' AND enabled=1 ORDER BY created_at,id LIMIT 1) WHERE login_user_id IS NULL",
      );
      for (const m of this.all("SELECT * FROM merchants")) {
        if (
          !this.get(
            "SELECT 1 FROM merchant_signing_credentials WHERE merchant_id=?",
            m.id,
          )
        )
          this.run(
            "INSERT INTO merchant_signing_credentials VALUES(?,?,?,?,?)",
            m.id,
            m.api_secret,
            "unified",
            m.key_version,
            1,
          );
      }
    });
  }
  migrate(merchants: Record<string, any>) {
    this.tx(() => {
      for (const [id, m] of Object.entries(merchants)) {
        identifier(id, "merchant_id");
        const wallet = walletConfiguration(m.wallet_url, m.wallet_endpoints);
        const secret = m.merchant_secret || hex(32);
        check(
          typeof secret === "string" && /^[a-f0-9]{64}$/.test(secret),
          "MERCHANT_SECRET_INVALID",
        );
        const result = this.run(
          "INSERT OR IGNORE INTO merchants(id,name,enabled,wallet_url,currency,minor_unit,games_json,api_secret,wallet_secret,version,key_version,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
          id,
          m.name ?? id,
          !!m.enabled,
          wallet.wallet_url,
          m.currency,
          m.minor_unit,
          encode(m.games),
          secret,
          secret,
          1,
          1,
          now(),
          now(),
        );
        if (result.changes) {
          this.run(
            "INSERT INTO merchant_wallet_endpoints VALUES(?,?)",
            id,
            encode(wallet.wallet_endpoints),
          );
          this.run(
            "INSERT INTO merchant_signing_credentials VALUES(?,?,?,?,?)",
            id,
            secret,
            "unified",
            1,
            0,
          );
          if (m.pre_payout)
            this.prebet(id, {
              enabled: m.pre_payout.enabled,
              url: m.pre_payout.url ?? "",
            });
          this.audit("system", "merchant.migrate", id);
        }
      }
    });
  }
  audit(
    actor: string,
    action: string,
    target: string,
    outcome = "success",
    details: any = {},
  ) {
    const scope =
      details.merchant_id ??
      (action.startsWith("merchant.")
        ? this.get("SELECT id FROM merchants WHERE id=?", target)?.id
        : null) ??
      this.get(
        "SELECT merchant_id FROM admin_users WHERE username=?",
        action.startsWith("user.") ? target : actor,
      )?.merchant_id ??
      null;
    this.run(
      "INSERT INTO admin_audit(created_at,actor,action,target,outcome,details_json,merchant_id) VALUES(?,?,?,?,?,?,?)",
      now(),
      actor,
      action,
      target,
      outcome,
      encode(details),
      scope,
    );
  }
  gameAvailability(id: number) {
    gameCode(id);
    const row = this.get("SELECT * FROM game_availability WHERE game_id=?", id);
    return row ? {...row, enabled: !!row.enabled} : {game_id:id, enabled:false, version:0, updated_at:0};
  }
  setGameAvailability(actor: string, q: any) {
    gameCode(q.game_id);
    check(typeof q.enabled === "boolean" && Number.isInteger(q.version), "INVALID_ARGUMENT");
    return this.tx(() => {
      const old = this.gameAvailability(q.game_id);
      check(old.version === q.version, "VERSION_CONFLICT", "游戏开放状态已变化，请刷新后重试", 409);
      const next = {...old, enabled:q.enabled, version:old.version+1, updated_at:now()};
      this.run("INSERT INTO game_availability VALUES(?,?,?,?) ON CONFLICT(game_id) DO UPDATE SET enabled=excluded.enabled,version=excluded.version,updated_at=excluded.updated_at", q.game_id, q.enabled, next.version, next.updated_at);
      this.audit(actor,"game.availability.update",String(q.game_id),"success",{before:old,after:next});
      return next;
    });
  }
  row(id: string) {
    return this.get(
      "SELECT m.*,f.enabled AS prebet_enabled,f.url AS prebet_url,s.secret AS signing_secret,s.version AS signing_version,u.username AS login_username,w.endpoints_json FROM merchants m LEFT JOIN merchant_prebet_settings f ON f.merchant_id=m.id LEFT JOIN merchant_signing_credentials s ON s.merchant_id=m.id LEFT JOIN admin_users u ON u.id=m.login_user_id LEFT JOIN merchant_wallet_endpoints w ON w.merchant_id=m.id WHERE m.id=?",
      id,
    );
  }
  value(r: any, priv = false) {
    if (!r) return null;
    const out: any = {};
    for (const k of [
      "id",
      "name",
      "wallet_url",
      "currency",
      "minor_unit",
      "version",
      "key_version",
      "created_at",
      "updated_at",
    ])
      out[k] = r[k];
    return {
      ...out,
      enabled: !!r.enabled,
      wallet_endpoints: JSON.parse(r.endpoints_json ?? "{}"),
      games: JSON.parse(r.games_json).map((v) => (priv ? v : publicGame(v))),
      login_username: r.login_username,
      signing_mode: "unified",
      merchant_key_version: r.signing_version ?? 0,
      merchant_key_fingerprint: r.signing_secret
        ? sha(r.signing_secret).slice(0, 12)
        : null,
      pre_payout: { enabled: !!r.prebet_url?.trim(), url: r.prebet_url ?? "" },
      ...(priv ? { merchant_secret: r.signing_secret } : {}),
    };
  }
  merchant(id: string, priv = false) {
    return this.value(this.row(id), priv);
  }
  merchants() {
    return this.all("SELECT id FROM merchants ORDER BY created_at,id").map(
      (r) => this.merchant(r.id),
    );
  }
  version(p: any, r: any) {
    check(
      Number.isInteger(p.version) && p.version === r.version,
      "VERSION_CONFLICT",
      "配置已被其他操作修改，请刷新页面后重试。",
      409,
    );
  }
  name(v: any, id = "") {
    check(
      typeof v === "string" &&
        v.trim().length >= 1 &&
        v.trim().length <= 80 &&
        !/[\x00-\x1f]/.test(v),
      "NAME_INVALID",
    );
    check(
      !this.get(
        "SELECT 1 FROM merchants WHERE lower(name)=lower(?) AND id<>?",
        v.trim(),
        id,
      ),
      "MERCHANT_NAME_CONFLICT",
      "Name exists",
      409,
    );
    check(
      !this.get(
        "SELECT 1 FROM admin_users WHERE lower(username)=lower(?) AND role LIKE 'merchant_%' AND id<>COALESCE((SELECT login_user_id FROM merchants WHERE id=?),'')",
        v.trim(),
        id,
      ),
      "MERCHANT_NAME_CONFLICT",
      "Name exists",
      409,
    );
    return v.trim();
  }
  prebet(id: string, v: any, transition = false) {
    check(v && typeof v.url === "string" && !("operator_token" in v) && !("secret_key" in v), "PREBET_CONFIG_INVALID");
    const url = v.url.trim();
    if (url) prebetURL(url);
    this.run("INSERT OR REPLACE INTO merchant_prebet_settings VALUES(?,?,?,?,?)", id, !!url, url, "", "");
  }

  saveMerchant(actor: string, p: any, create = false) {
    if (create) {
      check(p.minor_unit === undefined || p.minor_unit === 10000,
        "WALLET_PRECISION_INVALID", "Merchant wallets use minor_unit=10000.");
      p = { ...p, games: p.games === undefined ? GAME_CODES.map((_, i) => i + 1) : p.games, minor_unit: 10000 };
    }
    check((p.signing_mode ?? "unified") === "unified", "SIGNING_MODE_INVALID");
    check(!("merchant_secret" in p), "MERCHANT_SECRET_AUTOMATIC");
    check(!create || !("id" in p), "MERCHANT_ID_AUTOMATIC");
    check(
      typeof p.enabled === "boolean" &&
        Array.isArray(p.games) &&
        p.games.every((v) => Number.isInteger(v) && v >= 1 && v <= 19) &&
        new Set(p.games).size === p.games.length,
      "MERCHANT_INVALID",
    );
    return this.tx(() => {
      let id = create ? "" : identifier(p.id),
        old = create ? null : this.row(id);
      const wallet = walletConfiguration(
          p.wallet_url ?? old?.wallet_url,
          p.wallet_endpoints !== undefined
            ? p.wallet_endpoints
            : JSON.parse(old?.endpoints_json ?? "{}"),
        ),
        origin = wallet.wallet_url;
      if (!create) {
        check(old, "NOT_FOUND", "Merchant not found", 404);
        this.version(p, old);
        check(
          (p.currency ?? old.currency) === old.currency,
          "CURRENCY_IMMUTABLE",
        );
      }
      check(
        create
          ? p.minor_unit === 10000
          : (p.minor_unit ?? old.minor_unit) === old.minor_unit,
        "PRECISION_IMMUTABLE",
        "Wallet precision is set when creating a merchant.",
      );
      const name = this.name(p.name, id);
      let keys: any, login: any;
      if (create) {
        check((p.currency ?? "USD") === "USD", "CURRENCY_INVALID");
        const last = this.get(
            "SELECT COALESCE(MAX(CAST(substr(id,4) AS INTEGER)),0) AS n FROM merchants WHERE id GLOB 'GTT[0-9][0-9][0-9][0-9][0-9][0-9]'",
          ).n,
          num =
            Math.max(
              last,
              this.get(
                "SELECT value FROM control_counters WHERE name='merchant'",
              )?.value ?? 0,
            ) + 1;
        check(num <= 999999, "MERCHANT_ID_EXHAUSTED");
        id = "GTT" + String(num).padStart(6, "0");
        this.run(
          "INSERT INTO control_counters VALUES('merchant',?) ON CONFLICT(name) DO UPDATE SET value=excluded.value",
          num,
        );
        const secret = hex(32),
          password = token(),
          uid = hex();
        this.run(
          "INSERT INTO merchants(id,name,enabled,wallet_url,currency,minor_unit,games_json,api_secret,wallet_secret,version,key_version,created_at,updated_at,login_user_id) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
          id,
          name,
          p.enabled,
          origin,
          "USD",
          10000,
          encode(p.games.map(publicGame)),
          secret,
          secret,
          1,
          1,
          now(),
          now(),
          uid,
        );
        this.run(
          "INSERT INTO merchant_signing_credentials VALUES(?,?,?,?,?)",
          id,
          secret,
          "unified",
          1,
          0,
        );
        this.run(
          "INSERT INTO admin_users VALUES(?,?,?,?,?,?,?,?)",
          uid,
          "owner_" + uid,
          passwordHash(password),
          "merchant_admin",
          1,
          1,
          now(),
          id,
        );
        keys = { merchant_secret: secret };
        login = { name, temporary_password: password };
      } else
        this.run(
          "UPDATE merchants SET name=?,enabled=?,wallet_url=?,games_json=?,version=version+1,updated_at=? WHERE id=?",
          name,
          p.enabled,
          origin,
          encode(p.games.map(publicGame)),
          now(),
          id,
        );
      this.run(
        "INSERT INTO merchant_wallet_endpoints VALUES(?,?) ON CONFLICT(merchant_id) DO UPDATE SET endpoints_json=excluded.endpoints_json",
        id,
        encode(wallet.wallet_endpoints),
      );
      if (create || p.pre_payout)
        this.prebet(id, p.pre_payout ?? { enabled: false, url: "" });
      const result = this.merchant(id);
      this.audit(
        actor,
        create ? "merchant.create" : "merchant.update",
        id,
        "success",
        { before: this.value(old), after: result },
      );
      return { merchant: result, ...(keys ? { keys, login } : {}) };
    });
  }
  prepareMerchantUpdate(id: string, p: any, profileOnly = false) {
    const old = this.row(id);
    check(old, "NOT_FOUND", "Merchant not found", 404);
    this.version(p, old);
    if (profileOnly) {
      check(
        Object.keys(p).every((k) =>
          [
            "id",
            "version",
            "name",
            "wallet_url",
            "wallet_endpoints",
            "pre_payout",
            "confirm_mode_change",
          ].includes(k),
        ) && (p.id ?? id) === id,
        "FORBIDDEN",
        "Profile fields only",
        403,
      );
    } else {
      check(
        (p.signing_mode ?? "unified") === "unified",
        "SIGNING_MODE_INVALID",
      );
      check(!("merchant_secret" in p), "MERCHANT_SECRET_AUTOMATIC");
      check(
        typeof p.enabled === "boolean" &&
          Array.isArray(p.games) &&
          p.games.every((v) => Number.isInteger(v) && v >= 1 && v <= 19) &&
          new Set(p.games).size === p.games.length,
        "MERCHANT_INVALID",
      );
      check(
        (p.currency ?? old.currency) === old.currency,
        "CURRENCY_IMMUTABLE",
      );
      check(
        (p.minor_unit ?? old.minor_unit) === old.minor_unit,
        "PRECISION_IMMUTABLE",
        "Wallet precision is set when creating a merchant.",
      );
    }
    return {
      old,
      name: this.name(profileOnly ? (p.name ?? old.name) : p.name, id),
      ...walletConfiguration(
        p.wallet_url ?? old.wallet_url,
        p.wallet_endpoints !== undefined
          ? p.wallet_endpoints
          : JSON.parse(old.endpoints_json ?? "{}"),
      ),
      enabled: profileOnly ? old.enabled : p.enabled,
      games_json: profileOnly
        ? old.games_json
        : encode(p.games.map(publicGame)),
    };
  }
  profile(actor: string, id: string, p: any) {
    check(
      Object.keys(p).every((k) =>
        [
          "id",
          "version",
          "name",
          "wallet_url",
          "wallet_endpoints",
          "pre_payout",
        ].includes(k),
      ) && (p.id ?? id) === id,
      "FORBIDDEN",
      "Profile fields only",
      403,
    );
    return this.tx(() => {
      const { old, name, wallet_url, wallet_endpoints } =
        this.prepareMerchantUpdate(id, p, true);
      this.run(
        "UPDATE merchants SET name=?,wallet_url=?,version=version+1,updated_at=? WHERE id=?",
        name,
        wallet_url,
        now(),
        id,
      );
      this.run(
        "INSERT INTO merchant_wallet_endpoints VALUES(?,?) ON CONFLICT(merchant_id) DO UPDATE SET endpoints_json=excluded.endpoints_json",
        id,
        encode(wallet_endpoints),
      );
      if (p.pre_payout) this.prebet(id, p.pre_payout);
      const merchant = this.merchant(id);
      this.audit(actor, "merchant.profile.update", id, "success", {
        before: this.value(old),
        after: merchant,
      });
      return { merchant };
    });
  }
  signing(actor: string, p: any, action: string) {
    check(["view", "rotate"].includes(action), "NOT_FOUND", "Not found", 404);
    const id = identifier(p.id),
      why = action === "rotate" ? reason(p) : null;
    return this.tx(() => {
      const row = this.row(id);
      check(row, "NOT_FOUND", "Merchant not found", 404);
      let secret = row.signing_secret;
      if (action === "rotate") {
        this.version(p, row);
        secret = hex(32);
        this.run(
          "UPDATE merchant_signing_credentials SET secret=?,version=version+1 WHERE merchant_id=?",
          secret,
          id,
        );
        this.run(
          "UPDATE merchants SET api_secret=?,wallet_secret=?,key_version=key_version+1,version=version+1,updated_at=? WHERE id=?",
          secret,
          secret,
          now(),
          id,
        );
      }
      const merchant = this.merchant(id);
      this.audit(actor, "merchant.signing." + action, id, "success", {
        reason: why,
        fingerprint: merchant.merchant_key_fingerprint,
      });
      return { merchant, keys: { merchant_secret: secret } };
    });
  }
  userValue(r: any) {
    const m = this.get(
      "SELECT name FROM merchants WHERE login_user_id=?",
      r.id,
    );
    return {
      id: r.id,
      username: r.username,
      role: r.role,
      enabled: !!r.enabled,
      created_at: r.created_at,
      merchant_id: r.merchant_id,
      primary: !!m,
      login_name: m?.name ?? r.username,
    };
  }
  userScope(role: string, mid: any, scope?: string) {
    check(
      !!PERMISSIONS[role] && !!mid === role.startsWith("merchant_"),
      "ROLE_INVALID",
    );
    check(
      !scope || (mid === scope && role.startsWith("merchant_")),
      "FORBIDDEN",
      "Tenant mismatch",
      403,
    );
    check(!mid || this.row(mid), "NOT_FOUND", "Merchant not found", 404);
  }
  createUser(
    actor: string,
    name: string,
    role: string,
    password = token(),
    mid: string | null = null,
    scope?: string,
  ) {
    name = username(name);
    this.userScope(role, mid, scope);
    const hashed = passwordHash(password);
    return this.tx(() => {
      check(
        !this.get("SELECT 1 FROM admin_users WHERE username=?", name) &&
          !(
            role.startsWith("merchant_") &&
            this.get("SELECT 1 FROM merchants WHERE lower(name)=lower(?)", name)
          ),
        "USER_EXISTS",
        "Username exists",
        409,
      );
      const uid = hex();
      this.run(
        "INSERT INTO admin_users VALUES(?,?,?,?,?,?,?,?)",
        uid,
        name,
        hashed,
        role,
        1,
        1,
        now(),
        mid,
      );
      if (role === "merchant_admin")
        this.run(
          "UPDATE merchants SET login_user_id=? WHERE id=? AND login_user_id IS NULL",
          uid,
          mid,
        );
      this.audit(actor, "user.create", name, "success", {
        role,
        merchant_id: mid,
      });
      return {
        user: this.userValue(
          this.get("SELECT * FROM admin_users WHERE id=?", uid),
        ),
        temporary_password: password,
      };
    });
  }
  users(mid?: string) {
    return this.all(
      "SELECT * FROM admin_users" +
        (mid ? " WHERE merchant_id=?" : "") +
        " ORDER BY created_at,username",
      ...(mid ? [mid] : []),
    ).map((r) => this.userValue(r));
  }
  login(name: any, password: any, remote: string, merchantLogin = false) {
    const safe =
        typeof name === "string" && name.length >= 1 && name.length <= 80
          ? name.toLowerCase()
          : "",
      bucket = sha(remote + ":" + safe),
      t = now();
    const result = this.tx(() => {
      const throttle = this.get(
        "SELECT * FROM admin_login_limits WHERE bucket=?",
        bucket,
      );
      check(
        !(throttle && throttle.failures >= 5 && throttle.until_at > t),
        "LOGIN_THROTTLED",
        "Too many attempts",
        429,
      );
      let u = merchantLogin
        ? null
        : this.get(
            "SELECT * FROM admin_users WHERE username=? AND role NOT LIKE 'merchant_%'",
            safe,
          );
      u ??= this.get(
        "SELECT u.* FROM merchants m JOIN admin_users u ON u.id=m.login_user_id WHERE lower(m.name)=lower(?)",
        safe,
      );
      u ??= this.get(
        "SELECT u.* FROM admin_users u JOIN merchants m ON m.id=u.merchant_id WHERE u.username=? AND u.id<>COALESCE(m.login_user_id,'') AND u.role LIKE 'merchant_%'",
        safe,
      );
      const valid = passwordMatches(password, u?.password_hash ?? this.dummy);
      if (
        !u?.enabled ||
        !valid ||
        (u.role.startsWith("merchant_") && !u.merchant_id)
      ) {
        this.run(
          "INSERT OR REPLACE INTO admin_login_limits VALUES(?,?,?)",
          bucket,
          throttle?.until_at > t ? throttle.failures + 1 : 1,
          t + 900,
        );
        this.audit(safe || "anonymous", "auth.login", "", "denied");
        return null;
      }
      this.run("DELETE FROM admin_login_limits WHERE bucket=?", bucket);
      const tok = token(),
        csrf = token();
      this.run(
        "DELETE FROM admin_sessions WHERE expires_at<=? OR last_seen<=?",
        t,
        t - 1800,
      );
      this.run(
        "INSERT INTO admin_sessions VALUES(?,?,?,?,?,?)",
        sha(tok),
        u.id,
        u.auth_version,
        csrf,
        t + 28800,
        t,
      );
      this.audit(u.username, "auth.login", "", "success", { remote });
      return {
        token: tok,
        data: {
          user: this.userValue(u),
          permissions: PERMISSIONS[u.role],
          csrf_token: csrf,
        },
      };
    });
    check(
      result,
      "LOGIN_INVALID",
      "Invalid credentials or disabled account",
      401,
    );
    return result;
  }
  session(tok: string, permission?: string | null, csrf?: string) {
    check(
      typeof tok === "string" && tok.length >= 1 && tok.length <= 128,
      "LOGIN_REQUIRED",
      "Login required",
      401,
    );
    const result = this.tx(() => {
      const r = this.get(
        "SELECT u.*,s.csrf_token,s.expires_at,s.last_seen,s.auth_version AS session_version FROM admin_sessions s JOIN admin_users u ON u.id=s.user_id WHERE s.token_hash=?",
        sha(tok),
      );
      check(
        r?.enabled &&
          r.expires_at > now() &&
          r.last_seen > now() - 1800 &&
          r.auth_version === r.session_version &&
          (!r.role.startsWith("merchant_") || r.merchant_id),
        "LOGIN_REQUIRED",
        "Session expired",
        401,
      );
      check(
        csrf === undefined || equal(csrf, r.csrf_token),
        "CSRF_INVALID",
        "Invalid CSRF token",
        403,
      );
      if (permission && !PERMISSIONS[r.role].includes(permission)) {
        this.audit(r.username, "permission.denied", permission, "denied");
        return null;
      }
      this.run(
        "UPDATE admin_sessions SET last_seen=? WHERE token_hash=?",
        now(),
        sha(tok),
      );
      return {
        user: this.userValue(r),
        permissions: PERMISSIONS[r.role],
        csrf_token: r.csrf_token,
      };
    });
    check(result, "FORBIDDEN", "Permission denied", 403);
    return result;
  }
  logout(tok: string, actor: string) {
    this.tx(() => {
      this.run("DELETE FROM admin_sessions WHERE token_hash=?", sha(tok));
      this.audit(actor, "auth.logout", "");
    });
  }
  changePassword(actor: string, current: any, next: any) {
    const hashed = passwordHash(next);
    this.tx(() => {
      const r = this.get("SELECT * FROM admin_users WHERE username=?", actor);
      check(
        r && passwordMatches(current, r.password_hash),
        "PASSWORD_INVALID",
        "Current password invalid",
        403,
      );
      this.run(
        "UPDATE admin_users SET password_hash=?,auth_version=auth_version+1 WHERE id=?",
        hashed,
        r.id,
      );
      this.audit(actor, "user.password.change", actor);
    });
  }
  updateUser(actor: string, p: any, reset = false, scope?: string) {
    const name = username(p.username);
    return this.tx(() => {
      const r = this.get("SELECT * FROM admin_users WHERE username=?", name);
      check(
        r && (!scope || r.merchant_id === scope),
        "NOT_FOUND",
        "User not found",
        404,
      );
      let password: any;
      if (reset) {
        password = token();
        this.run(
          "UPDATE admin_users SET password_hash=?,auth_version=auth_version+1 WHERE id=?",
          passwordHash(password),
          r.id,
        );
      } else {
        const role = p.role,
          enabled = p.enabled,
          mid = (p.merchant_id ?? r.merchant_id) || null;
        check(typeof enabled === "boolean", "ROLE_INVALID");
        this.userScope(role, mid, scope);
        for (const type of ["admin", "merchant_admin"])
          if (
            r.role === type &&
            r.enabled &&
            (role !== type || !enabled || mid !== r.merchant_id)
          ) {
            const count = this.get(
              "SELECT COUNT(*) AS n FROM admin_users WHERE role=? AND enabled=1" +
                (type === "merchant_admin" ? " AND merchant_id=?" : ""),
              type,
              ...(type === "merchant_admin" ? [r.merchant_id] : []),
            ).n;
            check(
              count > 1,
              "LAST_ADMIN",
              "Keep one enabled administrator",
              409,
            );
          }
        this.run(
          "UPDATE admin_users SET role=?,enabled=?,merchant_id=?,auth_version=auth_version+1 WHERE id=?",
          role,
          enabled,
          mid,
          r.id,
        );
        if (
          r.merchant_id &&
          (role !== "merchant_admin" || !enabled || mid !== r.merchant_id)
        )
          this.run(
            "UPDATE merchants SET login_user_id=(SELECT id FROM admin_users WHERE merchant_id=? AND role='merchant_admin' AND enabled=1 ORDER BY created_at,id LIMIT 1) WHERE id=? AND login_user_id=?",
            r.merchant_id,
            r.merchant_id,
            r.id,
          );
      }
      this.audit(
        actor,
        reset ? "user.password.reset" : "user.update",
        name,
        "success",
        { merchant_id: r.merchant_id },
      );
      return reset ? { temporary_password: password } : { updated: true };
    });
  }
  audits(p: any, mid?: string) {
    const where: string[] = [],
      args: any[] = [];
    if (mid) {
      where.push("merchant_id=?");
      args.push(mid);
    }
    for (const k of ["actor", "action", "target"])
      if (p[k]) {
        check(
          typeof p[k] === "string" && p[k].length <= 128,
          "INVALID_ARGUMENT",
        );
        where.push(k + "=?");
        args.push(p[k]);
      }
    if (p.before_seq) {
      check(
        Number.isSafeInteger(p.before_seq) && p.before_seq > 0,
        "INVALID_ARGUMENT",
      );
      where.push("seq<?");
      args.push(p.before_seq);
    }
    return this.all(
      "SELECT * FROM admin_audit" +
        (where.length ? " WHERE " + where.join(" AND ") : "") +
        " ORDER BY seq DESC LIMIT ?",
      ...args,
      limit(p.limit ?? 50),
    ).map(({ details_json, merchant_id, ...r }) => ({
      ...r,
      details: JSON.parse(details_json),
    }));
  }
}

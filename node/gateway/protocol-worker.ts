import { parentPort, workerData } from "node:worker_threads";
import { DatabaseSync } from "node:sqlite";
import * as py from "../compat/runtime.js";
import { buildLocal, handlerFor, method } from "../services/local.js";
import { encode, sha, now, check, ServiceError } from "../shared/core.js";

const { code, database } = workerData,
  { app } = await buildLocal(py.sourcePath("services/" + code), {
    database,
    port: 0,
  });
const db = new DatabaseSync(database);
db.exec(
  "PRAGMA journal_mode=WAL; CREATE TABLE IF NOT EXISTS merchant_mirror(player_id TEXT PRIMARY KEY,seq INTEGER NOT NULL);",
);
let active = "",
  synced: any = null;
function rpc(command: string, args: any[]) {
  const memory = new SharedArrayBuffer(32 * 1024 * 1024),
    flag = new Int32Array(memory, 0, 2);
  parentPort!.postMessage({ rpc: true, command, args, memory });
  const outcome = Atomics.wait(flag, 0, 0, 120000);
  if (outcome === "timed-out")
    throw new ServiceError(
      "GATEWAY_TIMEOUT",
      "Settlement is pending; retry the same request.",
      503,
    );
  const reply = JSON.parse(
    Buffer.from(memory, 8, Atomics.load(flag, 1)).toString(),
  );
  if (reply.error)
    throw new ServiceError(
      reply.error.code,
      reply.error.message,
      reply.error.status,
    );
  return reply.data;
}
function apply(value: any) {
  const { snapshot, mirror } = value,
    pid = mirror.player_id;
  db.exec("BEGIN IMMEDIATE");
  try {
    db.prepare(
      "INSERT INTO players VALUES(?,?,?) ON CONFLICT(id) DO UPDATE SET balance_minor=excluded.balance_minor",
    ).run(pid, snapshot.wallet.balance_minor, now());
    db.prepare("INSERT OR REPLACE INTO sessions VALUES(?,?,?)").run(
      sha(active),
      pid,
      mirror.expires_at,
    );
    db.prepare("INSERT OR REPLACE INTO game_states VALUES(?,?,?)").run(
      pid,
      code,
      encode(snapshot.raw_state),
    );
    let seq = Number(
      db.prepare("SELECT seq FROM merchant_mirror WHERE player_id=?").get(pid)
        ?.seq ?? 0,
    );
    for (const o of mirror.operations) {
      const c = JSON.parse(o.candidate_json),
        r = JSON.parse(o.response_json);
      r.game_id = code;
      db.prepare(
        "INSERT OR REPLACE INTO spins(id,player_id,game_id,round_id,request_key,request_json,response_json,state_json,ruleset_id,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
      ).run(
        o.seq,
        pid,
        code,
        c.event.round_id,
        o.request_key,
        o.request_json,
        encode(r),
        encode(c.state),
        c.ruleset_id,
        o.created_at,
      );
      seq = Math.max(seq, o.seq);
    }
    db.prepare("INSERT OR REPLACE INTO merchant_mirror VALUES(?,?)").run(
      pid,
      seq,
    );
    db.exec("COMMIT");
  } catch (e) {
    db.exec("ROLLBACK");
    throw e;
  }
  synced = snapshot;
  return snapshot;
}
function sync(tok: string) {
  check(
    tok === active,
    "SESSION_INVALID",
    "Use the signed launch session",
    401,
  );
  if (synced) return synced;
  const local = db
    .prepare(
      "SELECT p.id,m.seq FROM sessions s JOIN players p ON p.id=s.player_id LEFT JOIN merchant_mirror m ON m.player_id=p.id WHERE s.token_hash=?",
    )
    .get(sha(tok));
  return apply(rpc("sync", [tok, Number(local?.seq ?? 0)]));
}
const player = py.attr(app.service.sessions, "_player");
app.service.sessions._player = py.native(([connection, tok]) => {
  sync(tok);
  return py.call(player, [connection, tok]);
});
app.service.wallet = py.native(([tok]) => py.from(sync(tok).wallet));
app.service.state = py.native(([tok, gid]) => {
  check(gid === code, "SESSION_GAME_MISMATCH");
  return py.from(sync(tok).state);
});
app.service.history = py.native(([tok, limit = 20]) => {
  sync(tok);
  return py.from(rpc("history", [tok, limit]));
});
app.service.spin = py.native(([tok, gid, key, previous, bet]) => {
  check(gid === code, "SESSION_GAME_MISMATCH");
  sync(tok);
  const row = db
    .prepare("SELECT seq FROM merchant_mirror WHERE player_id=?")
    .get(synced.wallet.player_id);
  const result = rpc("spin", [
    tok,
    key,
    previous,
    py.plain(bet),
    Number(row?.seq ?? 0),
  ]);
  apply(result);
  return py.from({ ...result.result, game_id: code });
});
app.service.create_session = py.native(() => {
  const value = sync(active);
  return py.from({
    ...value.wallet,
    token: active,
    expires_at: value.expires_at,
  });
});
parentPort!.on("message", (message) => {
  const { id, request } = message;
  active = request.token;
  synced = null;
  try {
    app.server_port = request.port;
    app.server_address = py.tuple(["127.0.0.1", request.port]);
    const req: any = {
      url: request.url,
      method: request.method,
      headers: {
        ...request.headers,
        ...(request.headers.origin
          ? { origin: "http://" + request.headers.host }
          : {}),
      },
      socket: { remoteAddress: "127.0.0.1" },
    };
    const handler = handlerFor(app, req, Buffer.from(request.body ?? []));
    method(
      handler,
      request.method === "POST"
        ? "do_POST"
        : request.method === "HEAD"
          ? "do_HEAD"
          : "do_GET",
    );
    parentPort!.postMessage({
      id,
      status: handler.__status,
      headers: handler.__headers,
      body: Buffer.concat(handler.__chunks),
    });
  } catch (e) {
    const error =
      e instanceof ServiceError
        ? e
        : new ServiceError("GAME_UNAVAILABLE", "Game request failed", 500);
    parentPort!.postMessage({
      id,
      error: { code: error.code, message: error.message, status: error.status },
    });
  }
});
parentPort!.postMessage({ ready: true });

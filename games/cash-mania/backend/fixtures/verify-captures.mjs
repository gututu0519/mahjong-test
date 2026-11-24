// 只读复核本游戏的原站抓取，输出计数和本地请求序号，原始账户及交易信息不出现在报告中。
import assert from "node:assert/strict";
import { existsSync, readFileSync } from "node:fs";
import { dirname, resolve, relative, isAbsolute, sep } from "node:path";
import { fileURLToPath } from "node:url";
import { captureArchive, captureFolders } from "../../../../other/capture/response-capture/capture-layout.mjs";
import * as p from "../../../../other/runtime/server/dist/compat/runtime.js";
import * as protocol from "../../../../other/runtime/server/dist/migrated/py/adapters/pg/protocol.js";
import { decodeTransaction, encodeTransaction, pack, roundPresentation, SALT } from "../../../../other/runtime/server/dist/migrated/py/adapters/pg/cash_mania.js";
import { evaluateBoard, normalizeBet } from "../../../../other/runtime/server/dist/migrated/py/games/cash_mania/engine.js";

const here = dirname(fileURLToPath(import.meta.url));
const root = resolve(here, "../../../..");
const config = JSON.parse(readFileSync(resolve(root, "games/cash-mania/instance/config/cash-mania.json"), "utf8"));
const captures = resolve(root, captureArchive);
const paths = process.argv.slice(2);
const dirs = paths.length ? paths.map(p => resolve(p))
  : Array.from(captureFolders(captures).values(), folder => resolve(captures, folder));
const seen = new Map();
const close = (a, b) => Number.isFinite(a) && Number.isFinite(b) && Math.abs(a - b) < 1e-6;
const reports = [];
for (const dir of dirs) {
  const file = resolve(dir, "manifest.json");
  if (!existsSync(file)) { if (paths.length) throw new Error("指定目录缺少 manifest.json"); continue; }
  const report = { capture: dir.split(sep).pop(), complete: 0, duplicate: 0, ordinary: 0, wins: 0,
    nudge: 0, respin: 0, free: 0, purchase: 0, otherState: 0, gwt: {}, blankFinalCells: Array(9).fill(0), incomplete: [], invalid: [] };
  const { rows } = JSON.parse(readFileSync(file, "utf8"));
  for (const row of rows) {
    const url = new URL(row.url);
    if (url.hostname !== "api.mmga1.com" || url.pathname !== "/game-api/cash-mania/v4/Spin" || row.method !== "POST") continue;
    if (row.state !== "complete" || row.status !== 200) { report.incomplete.push(row.id); continue; }
    let step = "读取请求和响应";
    try {
      const body = resolve(dir, row.body), within = relative(dir, body);
      assert.ok(!isAbsolute(within) && !within.startsWith(".." + sep) && within !== ".." && body.endsWith(".bin"));
      const request = readFileSync(body.slice(0, -4) + ".request.bin"), response = readFileSync(body);
      step = "传输往返";
      const [rq, seed] = p.call(protocol.unpack, [request, null, SALT]);
      const [raw] = p.call(protocol.unpack, [response, seed, SALT]);
      assert.deepEqual(pack(raw, seed), response);
      step = "交易字段往返";
      const tx = decodeTransaction(raw), betRequest = p.plain(p.call(protocol.decode_request, [rq]));
      assert.equal(typeof tx.sid, "string"); assert.equal(typeof tx.psid, "string");
      const check = decodeTransaction(encodeTransaction(tx));
      for (const key of ["rl", "rv", "orl", "orv", "rsrl", "rsrv", "nfp", "gwt", "st", "nst", "wp", "fs"]) assert.deepEqual(check[key], tx[key]);
      const id = JSON.stringify([tx.sid, tx.psid]), signature = JSON.stringify([tx, betRequest.cs, betRequest.ml]);
      if (seen.has(id)) { assert.equal(seen.get(id), signature); report.duplicate++; continue; }
      const purchase = Boolean(tx.fb || Array.from(p.iter(p.call(protocol.fields, [rq]))).some(([n, w, v]) => n === 24 && w === 0 && v));
      if (tx.fs) report.free++;
      if (purchase) report.purchase++;
      if (tx.st === 1 && tx.nst === 1 && !tx.fs && !purchase) {
        step = "普通局金额、中奖线和钱包";
        const data = roundPresentation(tx), bet = normalizeBet(config, { cs: betRequest.cs, ml: betRequest.ml });
        for (const board of [tx.rl, tx.orl, tx.rsrl].filter(Boolean)) {
          assert.ok([0, 2, 3, 5, 6, 8].every(i => board[i] > 0), "上下行出现空符号");
        }
        tx.rl.forEach((symbol, i) => { if (symbol === 0) report.blankFinalCells[i]++; });
        const scored = evaluateBoard(config, data.board, bet), win = tx.tw || 0;
        assert.equal(bet.level, tx.ml); assert.ok(close(bet.coin_minor / 100, tx.cs));
        assert.ok(close(tx.tb, tx.cs * tx.ml * 10) && close(tx.tbb, tx.tb));
        assert.ok(data.reel_values.every((v, i) => close(v, scored.values[i])));
        assert.ok(close(win * 100, scored.win_minor));
        assert.deepEqual(tx.wp, win ? { "1": [1, 4, 7] } : undefined);
        if (win) assert.ok(close(tx.lw?.["1"], win));
        assert.ok(close(tx.blab || 0, (tx.blb || 0) - tx.tb) && close(tx.bl || 0, (tx.blab || 0) + win) && close(tx.np || 0, win - tx.tb));
        report.ordinary++;
        if (win > 0) report.wins++;
        if (data.nudge_from_position) report.nudge++;
        if (data.respin_board) report.respin++;
        report.gwt[tx.gwt] = (report.gwt[tx.gwt] || 0) + 1;
      } else report.otherState++;
      seen.set(id, signature); report.complete++;
    } catch { report.invalid.push({ request: row.id, check: step }); }
  }
  if (report.complete || report.incomplete.length || report.invalid.length || report.duplicate) reports.push(report);
}
console.log(JSON.stringify(reports, null, 2));
if (!reports.length || reports.some(report => report.invalid.length)) process.exitCode = 1;

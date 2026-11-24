// 只读解码原站普通局；仅输出聚合约束和本地请求编号，不输出会话、局号或钱包。
// --write 只更新本游戏的脱敏证据 JSON，不修改原始抓取。
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { existsSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, isAbsolute, relative, resolve, sep } from "node:path";
import { fileURLToPath } from "node:url";
import { captureArchive, captureFolders } from "../../../../other/capture/response-capture/capture-layout.mjs";
import * as p from "../../../../other/runtime/server/dist/compat/runtime.js";
import * as protocol from "../../../../other/runtime/server/dist/migrated/py/adapters/pg/protocol.js";
import { decodeTransaction, pack, SALT } from "../../../../other/runtime/server/dist/migrated/py/adapters/pg/cash_mania.js";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "../../../..");
const captureRoot = resolve(root, captureArchive);
const args = process.argv.slice(2), write = args.includes("--write");
const requested = args.filter(arg => arg !== "--write");
const dirs = requested.length ? requested.map(path => resolve(path))
  : Array.from(captureFolders(captureRoot).values(), folder => resolve(captureRoot, folder));
const sideValues = [0, 1, 5, 10, 50, 100], middleValues = [0, 1, 2, 3, 5, 10, 15, 20, 30, 40, 50, 100];
const sides = [0, 1, 2, 6, 7, 8], middle = [3, 4, 5], seen = new Set();
const close = (a, b) => Number.isFinite(a) && Number.isFinite(b) && Math.abs(a - b) < 1e-6;
const same = (a, b) => JSON.stringify(a) === JSON.stringify(b);
const increment = (map, value) => { const key = typeof value === "string" ? value : JSON.stringify(value); map[key] = (map[key] || 0) + 1; };
const differences = (a, b) => a.map((value, index) => value === b[index] ? null : index).filter(index => index != null);
const group = () => ({ count: 0, positive_payout: 0, zero_payout: 0, single_base_wager: 0, wallet_equation: 0, final_payout_equation: 0, all_board_values: 0, state_pairs: {}, constraints: {}, changed_positions: {}, original_middle_symbols: {}, final_middle_symbols: {}, references: [] });
const report = {
  game: "cash-mania", provider_id: 1682240,
  scope: "原始普通 Spin 请求响应的脱敏聚合；计数不代表原厂概率或 RTP。",
  sources: [], complete_spins: 0, ordinary_spins: 0, duplicate_spins: 0, unclassified_spins: 0,
  both_features: 0, free_spins: 0, purchase_spins: 0, nudge: group(), respin: group(), nfp_values: {},
  client_source: {
    raw_relative_path: "other/capture/response-capture/captures/6cac619dd9ed4048bf86e1585274b2e1/bodies/000665.js",
    decoded_relative_path: "other/diagnostics/cash-mania/client-main-decoded.js",
    findings: [
      { lines: "4057,4068-4089", statement: "GameTransactionModel 将 orl/orv、rsrl/rsrv、nfp 分别映射为原始盘面、重转盘面和挪轴位置；缺少原始盘面时回退到最终盘面。" },
      { lines: "13050-13066", statement: "UISpinState.setSlotResult 复制原始盘面后，把中轴三格换成最终盘面；若存在重转盘面，则初停左右两列改用 rsrl/rsrv；nfp 作为动画参数传入。" },
      { lines: "6852-6854,6909-6916", statement: "nfp 首项值 5 选择 land_os_down，再接 feat_down_shake；最终中格非空时以 feat_down_snap 收尾。其他方向及失败分支仅有客户端静态代码，未获本批交易证据。" },
      { lines: "13071-13095,11433-11444", statement: "初停和可选挪轴结束后才执行两侧重转；playRespin 保持中轴，先启动左轴、0.3 秒后启动右轴、1 秒后调用左右停轴到最终盘面。" },
    ],
  },
  implementation_boundary: [
    "可以在普通最终中奖盘面确定后，用独立的本地表现模型选择已观察到的挪轴或两侧重转，并生成符合相应约束的中间盘面。",
    "中间盘面不得增加投注、独立派彩或更改最终盘面；最终结果与结算不受表现选择影响。",
    "本地触发权重和中间盘面分布是实现选择，不能用样本频率冒充原厂概率。",
    "样本中两种表现互斥、全为中奖且挪轴位置全为 5；没有证据证明原厂所有情况下都满足这些限制。",
    "不得把 nfp=5 解释为中轴数组直接平移一格；已观察原始中轴与最终中轴不满足该映射。",
    "免费旋转、购买、最大赢额终止、另一挪轴方向、失败表现、两类共存和原厂概率仍需额外证据。",
  ],
};
function score(board, tx) {
  return board[1] && board[1] === board[7] ? sideValues[board[1]] * tx.cs * tx.ml * (middleValues[board[4]] || 0) : 0;
}
function valuesAgree(board, values, tx) {
  return Array.isArray(board) && board.length === 9 && Array.isArray(values) && values.length === 9 && board.every((symbol, index) => {
    const expected = middle.includes(index) ? (symbol === 12 || symbol === 13 ? 1 : middleValues[symbol]) : sideValues[symbol] * tx.cs * tx.ml;
    return close(values[index], expected);
  });
}
function constraint(target, name, value) { if (value) target.constraints[name] = (target.constraints[name] || 0) + 1; else target.constraints[name] ??= 0; }
function accumulate(target, tx, label, request) {
  target.count++;
  target[(tx.tw || 0) > 0 ? "positive_payout" : "zero_payout"]++;
  target.single_base_wager += Number(close(tx.tb, tx.cs * tx.ml * 10) && close(tx.tbb, tx.tb));
  target.wallet_equation += Number(close(tx.blab || 0, (tx.blb || 0) - tx.tb) && close(tx.bl || 0, (tx.blab || 0) + (tx.tw || 0)));
  target.final_payout_equation += Number(close(tx.tw || 0, score(tx.rl, tx)));
  target.all_board_values += Number(valuesAgree(tx.rl, tx.rv, tx) && (!tx.orv || valuesAgree(tx.orl, tx.orv, tx)) && (!tx.rsrv || valuesAgree(tx.rsrl, tx.rsrv, tx)));
  increment(target.state_pairs, [tx.st, tx.nst]);
  increment(target.final_middle_symbols, tx.rl.slice(3, 6));
  target.references.push({ capture: label, request });
}
for (const dir of dirs) {
  const manifest = resolve(dir, "manifest.json");
  if (!existsSync(manifest)) { if (requested.length) throw new Error("指定抓取目录缺少清单"); continue; }
  const source = { capture: dir.split(sep).pop(), complete_spins: 0, incomplete_requests: [], invalid_requests: [] };
  for (const row of JSON.parse(readFileSync(manifest, "utf8")).rows) {
    const url = new URL(row.url);
    if (url.hostname !== "api.mmga1.com" || url.pathname !== "/game-api/cash-mania/v4/Spin" || row.method !== "POST") continue;
    if (row.state !== "complete" || row.status !== 200) { source.incomplete_requests.push(row.id); continue; }
    try {
      const body = resolve(dir, row.body), within = relative(dir, body);
      assert.ok(!isAbsolute(within) && within !== ".." && !within.startsWith(".." + sep) && body.endsWith(".bin"));
      const [rq, seed] = p.call(protocol.unpack, [readFileSync(body.slice(0, -4) + ".request.bin"), null, SALT]);
      const response = readFileSync(body), [raw] = p.call(protocol.unpack, [response, seed, SALT]);
      assert.deepEqual(pack(raw, seed), response);
      const tx = decodeTransaction(raw), key = JSON.stringify([tx.sid, tx.psid]);
      assert.equal(typeof tx.sid, "string"); assert.equal(typeof tx.psid, "string");
      if (seen.has(key)) { report.duplicate_spins++; continue; }
      seen.add(key); report.complete_spins++; source.complete_spins++;
      const purchase = Boolean(tx.fb || Array.from(p.iter(p.call(protocol.fields, [rq]))).some(([id, kind, value]) => id === 24 && kind === 0 && value));
      if (tx.fs) report.free_spins++;
      if (purchase) report.purchase_spins++;
      if (tx.st !== 1 || tx.nst !== 1 || tx.fs || purchase) { report.unclassified_spins++; continue; }
      report.ordinary_spins++;
      if (tx.nfp && tx.rsrl) report.both_features++;
      if (tx.nfp) {
        const target = report.nudge;
        accumulate(target, tx, source.capture, row.id);
        increment(report.nfp_values, tx.nfp);
        increment(target.original_middle_symbols, tx.orl.slice(3, 6));
        increment(target.changed_positions, differences(tx.orl, tx.rl));
        constraint(target, "original_and_final_side_columns_identical", sides.every(index => tx.orl[index] === tx.rl[index] && close(tx.orv[index], tx.rv[index])));
        constraint(target, "original_center_empty", tx.orl[4] === 0 && tx.orv[4] === 0);
        constraint(target, "final_center_nonzero", tx.rl[4] > 0 && tx.rv[4] > 0);
        constraint(target, "side_middle_symbols_equal_and_nonzero", tx.rl[1] > 0 && tx.rl[1] === tx.rl[7]);
        constraint(target, "original_payout_zero", close(score(tx.orl, tx), 0));
        constraint(target, "no_respin_fields", !tx.rsrl && !tx.rsrv);
        constraint(target, "source_position_equals_final_center", tx.orl[5] === tx.rl[4]);
      }
      if (tx.rsrl) {
        const target = report.respin;
        accumulate(target, tx, source.capture, row.id);
        increment(target.original_middle_symbols, tx.rsrl.slice(3, 6));
        increment(target.changed_positions, differences(tx.rsrl, tx.rl));
        constraint(target, "original_board_equals_final", same(tx.orl, tx.rl));
        constraint(target, "middle_column_identical", middle.every(index => tx.rsrl[index] === tx.rl[index] && close(tx.rsrv[index], tx.rv[index])));
        constraint(target, "intermediate_side_middle_symbols_distinct", tx.rsrl[1] !== tx.rsrl[7]);
        constraint(target, "intermediate_side_middle_symbols_nonzero", tx.rsrl[1] > 0 && tx.rsrl[7] > 0);
        constraint(target, "final_side_middle_symbols_equal_and_nonzero", tx.rl[1] > 0 && tx.rl[1] === tx.rl[7]);
        constraint(target, "exactly_one_side_middle_symbol_changed", Number(tx.rsrl[1] !== tx.rl[1]) + Number(tx.rsrl[7] !== tx.rl[7]) === 1);
        constraint(target, "intermediate_payout_zero", close(score(tx.rsrl, tx), 0));
        constraint(target, "no_nudge_fields", !tx.nfp && !tx.orv);
      }
    } catch { source.invalid_requests.push(row.id); }
  }
  if (source.complete_spins || source.incomplete_requests.length || source.invalid_requests.length) report.sources.push(source);
}
const rawMain = resolve(root, report.client_source.raw_relative_path);
if (existsSync(rawMain)) report.client_source.sha256 = createHash("sha256").update(readFileSync(rawMain)).digest("hex");
const serialized = JSON.stringify(report, null, 2) + "\n";
if (!report.complete_spins || report.sources.some(source => source.invalid_requests.length)) process.exitCode = 1;
if (write) {
  assert.ok(!process.exitCode, "发现不可解码的完整回包，未更新证据文件");
  writeFileSync(resolve(root, "games/cash-mania/docs/普通局特殊表现证据.json"), serialized, "utf8");
  console.log(JSON.stringify({ written: "games/cash-mania/docs/普通局特殊表现证据.json", complete: report.complete_spins, nudge: report.nudge.count, respin: report.respin.count }));
} else console.log(serialized);

import { test } from "node:test";
import assert from "node:assert/strict";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import {
  Control,
  WALLET_ACTIONS,
  walletConfiguration,
  walletEndpoint,
} from "../gateway/control.js";
import { Wallet } from "../gateway/wallet.js";
import { body, server, success, listen } from "../shared/http.js";
import { signature } from "../shared/core.js";

test("all wallet callbacks use independent full URLs and sign the actual request path", async (t) => {
  const dir = mkdtempSync(join(tmpdir(), "gtt-wallet-urls-")),
    schema = resolve("config/control.sql"),
    control = new Control(join(dir, "control.db"), schema);
  const calls: any[] = [];
  const paths = [
    "/partner/funds",
    "/account/stake",
    "/rewards/settle",
    "/cancel-bet",
    "/ledger/lookup",
    "/ledger/search",
  ];
  const receipts = new Map<string, any>();
  let responseUnit: any = undefined;
  const handler = async (req: any, res: any) => {
    const raw = await body(req),
      q = JSON.parse(raw.toString()),
      merchant = control.merchant(String(req.headers["x-gtt-merchant"]), true);
    assert.equal(req.method, "POST");
    control.authenticate(req.headers, req.url, raw, merchant);
    const index = paths.indexOf(req.url),
      action =
        index < 0 ? req.url.slice("/wallet/v1/".length) : WALLET_ACTIONS[index];
    assert.ok(WALLET_ACTIONS.includes(action));
    calls.push({
      action,
      path: req.url,
      host: req.headers.host,
      nonce: req.headers["x-gtt-nonce"],
      q,
    });
    assert.equal(Object.hasOwn(q, "minor_unit"), false);
    if (index >= 0)
      assert.notEqual(
        req.headers["x-gtt-signature"],
        signature(
          merchant.merchant_secret,
          "/wallet/v1/" + action,
          req.headers["x-gtt-timestamp"],
          req.headers["x-gtt-nonce"],
          raw,
        ),
      );
    let data: any = {
      player_id: q.player_id,
      currency: q.currency,
      balance_minor: 100000,
      transactions: [],
      ...(responseUnit === undefined ? {} : { minor_unit: responseUnit }),
    };
    if (["debit", "credit", "refund"].includes(action)) {
      data = {
        ...data,
        transaction_id: q.transaction_id,
        status: "applied",
        amount_minor: q.amount_minor,
        applied_minor: q.amount_minor,
        balance_before_minor: 100000,
        balance_minor:
          100000 + (action === "debit" ? -q.amount_minor : q.amount_minor),
      };
      data = receipts.get(q.transaction_id) ?? data;
      receipts.set(q.transaction_id, data);
    }
    success(res, data);
  };
  const a = server(handler),
    b = server(handler),
    ports = [await listen(a), await listen(b)];
  t.after(async () => {
    for (const s of [a, b]) {
      s.closeAllConnections();
      await new Promise<void>((ok) => s.close(() => ok()));
    }
    control.close();
    rmSync(dir, { recursive: true, force: true });
  });
  const endpoints = Object.fromEntries(
    WALLET_ACTIONS.map((action, i) => [
      action,
      `http://127.0.0.1:${ports[i % 2]}${paths[i]}`,
    ]),
  );
  const merchant = control.saveMerchant(
    "test",
    {
      name: "custom callbacks",
      enabled: true,
      games: [1],
      minor_unit: 10000,
      wallet_endpoints: endpoints,
    },
    true,
  ).merchant;
  assert.equal(merchant.wallet_url, "");
  assert.deepEqual(merchant.wallet_endpoints, endpoints);
  const wallet = new Wallet(control),
    identity = { player_id: "p1", currency: "USD", minor_unit: 10000 };
  for (const [i, action] of WALLET_ACTIONS.entries()) {
    await wallet.call(merchant.id, action, {
      ...identity,
      transaction_id: action.replaceAll("/", "-"),
      round_id: "round-1",
      reference_id: "debit",
      amount_minor: 1000,
    });
    assert.equal(calls.at(-1).path, paths[i]);
    assert.equal(calls.at(-1).host, `127.0.0.1:${ports[i % 2]}`);
  }
  const again = await wallet.call(merchant.id, "debit", {
    ...identity,
    transaction_id: "debit",
    round_id: "round-1",
    reference_id: "debit",
    amount_minor: 1000,
  });
  assert.equal(again.balance_minor, 99000);
  assert.equal(again.minor_unit, 10000);
  assert.equal(receipts.size, 3);
  assert.notEqual(calls[1].nonce, calls.at(-1).nonce);
  const second = new Control(join(dir, "control.db"), schema);
  assert.deepEqual(second.merchant(merchant.id).wallet_endpoints, endpoints);
  second.close();
  control.profile("test", merchant.id, {
    version: merchant.version,
    wallet_url: `http://127.0.0.1:${ports[0]}`,
    wallet_endpoints: { balance: endpoints.balance },
  });
  await wallet.call(merchant.id, "credit", {
    ...identity,
    transaction_id: "credit-2",
    round_id: "round-1",
    reference_id: "debit",
    amount_minor: 1000,
  });
  assert.equal(calls.at(-1).path, "/wallet/v1/credit");
  await wallet.call(merchant.id, "balance", identity);
  assert.equal(calls.at(-1).path, paths[0]);
  const current = control.merchant(merchant.id);
  assert.throws(
    () =>
      control.profile("test", merchant.id, {
        version: current.version,
        wallet_url: "",
      }),
    { code: "WALLET_ENDPOINT_REQUIRED" },
  );
  assert.deepEqual(control.merchant(merchant.id), current);
  control.profile("test", merchant.id, {
    version: current.version,
    wallet_endpoints: {},
  });
  assert.equal(
    walletEndpoint(control.merchant(merchant.id), "balance"),
    `http://127.0.0.1:${ports[0]}/wallet/v1/balance`,
  );
  const payload = {...identity, resolution_minor_unit:100, resolution:{basis_minor:200,actual_credit_minor:350}};
  const savedPayload = structuredClone(payload);
  await wallet.call(merchant.id, "balance", payload);
  assert.deepEqual(payload, savedPayload);
  assert.equal(calls.at(-1).q.resolution_minor_unit,10000);
  assert.deepEqual(calls.at(-1).q.resolution,{basis_minor:20000,actual_credit_minor:35000});
  responseUnit = 10000;
  assert.equal((await wallet.call(merchant.id,"balance",{player_id:"p1",currency:"USD"})).minor_unit,10000);
  for (const invalid of [100, 0, "10000", null]) {
    responseUnit = invalid;
    await assert.rejects(wallet.call(merchant.id,"balance",identity),{code:"WALLET_UNCERTAIN"});
  }
});

test("wallet endpoint validation preserves transport constraints and rejects incomplete configuration", () => {
  assert.deepEqual(walletConfiguration("https://wallet.example", {}), {
    wallet_url: "https://wallet.example",
    wallet_endpoints: {},
  });
  for (const value of [
    "/relative",
    "https://wallet.example/pay?token=x",
    "https://wallet.example/pay#fragment",
    "https://user:secret@wallet.example/pay",
    "http://wallet.example/pay",
    "file:///tmp/pay",
    "https://wallet.example/a b",
  ])
    assert.throws(
      () => walletConfiguration("https://wallet.example", { balance: value }),
      value,
    );
  assert.throws(() => walletConfiguration("", {}), {
    code: "WALLET_ENDPOINT_REQUIRED",
  });
  assert.throws(
    () =>
      walletConfiguration("https://wallet.example", {
        unknown: "https://wallet.example/a",
      }),
    { code: "WALLET_ENDPOINT_INVALID" },
  );
  assert.throws(
    () => walletConfiguration("https://wallet.example", { balance: 3 }),
    { code: "WALLET_ENDPOINT_INVALID" },
  );
  assert.throws(() => walletConfiguration("https://wallet.example", null), {
    code: "WALLET_ENDPOINT_INVALID",
  });
});

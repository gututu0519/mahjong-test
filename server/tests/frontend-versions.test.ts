import { test } from "node:test";
import assert from "node:assert/strict";
import {
  mkdtempSync,
  mkdirSync,
  copyFileSync,
  writeFileSync,
  readFileSync,
  rmSync,
} from "node:fs";
import { join, resolve } from "node:path";
import { tmpdir } from "node:os";
import { execFileSync } from "node:child_process";
import { request } from "node:http";
import { Control } from "../gateway/control.js";
import { Provider } from "../gateway/provider.js";
import { GameClient } from "../gateway/game-client.js";
import { gatewayServer } from "../gateway/http.js";
import { adminServer } from "../gateway/admin.js";
import { computeServer } from "../services/compute.js";
import { platformServer } from "../services/platform.js";
import { listen } from "../shared/http.js";
import { readFrontendManifest } from "../shared/frontend-manifest.js";
import { pathToFileURL } from "node:url";
import { runInNewContext } from "node:vm";

async function fixture(t: any) {
  const dir = mkdtempSync(join(tmpdir(), "frontend-versions-")),
    source = join(dir, "source"),
    installed = join(dir, "installed");
  mkdirSync(join(source, "fixtures"), { recursive: true });
  for (const name of [
    "index.html",
    "local-auth-bootstrap.js",
    "local-frame-clock.js",
    "fixtures/auth-metadata.json",
    "fixtures/game-rule.json",
  ])
    copyFileSync(resolve("../clients/buffalo-win", name), join(source, name));
  mkdirSync(join(source, "assets"), { recursive: true });
  writeFileSync(join(source, "private.json"), '{"secret":"ROOT_PRIVATE"}');
  writeFileSync(join(source, "assets/marker.json"), '{"version":"old"}');
  writeFileSync(
    join(source, "fixtures/secret.json"),
    '{"secret":"PRIVATE_SENTINEL"}',
  );
  mkdirSync(join(source, "diagnostics/profile"), { recursive: true });
  writeFileSync(
    join(source, "diagnostics/profile/secret.json"),
    '{"secret":"PRIVATE_PROFILE"}',
  );
  const control = new Control(
    join(dir, "control.db"),
    resolve("config/control.sql"),
  );
  const created = control.saveMerchant(
      "test",
      {
        name: "frontend-merchant",
        enabled: true,
        wallet_url: "http://127.0.0.1:8111",
        games: [1],
      },
      true,
    ),
    mid = created.merchant.id;
  const config: any = {
    environment: "development",
    game_services_mode: "remote",
    frontend_releases_directory: installed,
    game_database: join(dir, "games.db"),
    platform_database: join(dir, "wallet.db"),
    gateway_origin: "http://127.0.0.1",
    sandbox_merchant: mid,
    sandbox_player: "p1",
    sandbox_balance_minor: 100000000,
  };
  const servers = new Set<any>();
  const { server: wallet } = platformServer(config, control);
  servers.add(wallet);
  const wp = await listen(wallet);
  control.saveMerchant("test", {
    ...control.merchant(mid),
    wallet_url: "http://127.0.0.1:" + wp,
  });
  control.setGameAvailability("test", {
    game_id: 1,
    enabled: true,
    version: 0,
  });
  const secret = "frontend-test-key-".repeat(4),
    game = computeServer(
      "buffalo-win",
      resolve("../services/buffalo-win/config/buffalo-win.json"),
      secret,
      { release: "backend-auto-build-v1" },
    );
  servers.add(game);
  const gp = await listen(game);
  let p: Provider,
    gateway: any,
    port = 0;
  const start = async () => {
    p = new Provider(
      config.game_database,
      control,
      new GameClient("http://127.0.0.1:1", secret, {}),
      resolve("config/game.sql"),
      config.gateway_origin,
    );
    p.enableGames(config);
    await p.initialize();
    gateway = gatewayServer(p, config, resolve("../clients/buffalo-win"));
    servers.add(gateway);
    port = await listen(gateway, port);
    p.playOrigin = config.gateway_origin = "http://127.0.0.1:" + port;
  };
  await start();
  const backend = await p!.multi!.remote!.register("test", {
    code: "buffalo-win",
    origin: "http://127.0.0.1:" + gp,
    secret,
  });
  assert.equal(backend.release, "backend-auto-build-v1");
  await p!.multi!.remote!.activate("test", { id: backend.id, revision: 0 });
  const stop = async (server: any) => {
    server.closeAllConnections();
    await new Promise<void>((ok) => server.close(() => ok()));
    servers.delete(server);
  };
  const f: any = {
    dir,
    source,
    installed,
    control,
    config,
    mid,
    created,
    servers,
    get p() {
      return p!;
    },
    get versions() {
      return p!.multi!.frontends;
    },
    get port() {
      return port;
    },
    build: () => {
      const result = JSON.parse(
        execFileSync(
          process.execPath,
          [
            resolve("tools/build-frontend.mjs"),
            "--game",
            "buffalo-win",
            "--source",
            source,
            "--output",
            join(dir, "builds"),
          ],
          { encoding: "utf8", windowsHide: true },
        ),
      );
      execFileSync(
        process.execPath,
        [
          resolve("tools/install-frontend.mjs"),
          result.bundle,
          "--destination",
          installed,
        ],
        { windowsHide: true, stdio: "pipe" },
      );
      return { ...result, bundle: result.release };
    },
    launch: async () => p!.launch(mid, { game_id: 1, player_id: "p1" }),
    restart: async () => {
      await gateway.protocolPool.close();
      await stop(gateway);
      p!.close();
      await start();
    },
    http: (host: string, path: string) =>
      new Promise<any>((ok, fail) => {
        const req = request(
          { host: "127.0.0.1", port, path, headers: { host }, agent: false },
          (res) => {
            const chunks: Buffer[] = [];
            res.on("data", (b) => chunks.push(b));
            res.on("end", () =>
              ok({
                status: res.statusCode,
                headers: res.headers,
                body: Buffer.concat(chunks).toString(),
              }),
            );
          },
        );
        req.on("error", fail);
        req.end();
      }),
  };
  t.after(async () => {
    await gateway.protocolPool.close();
    for (const server of [...servers]) await stop(server);
    p!.close();
    control.close();
    rmSync(dir, { recursive: true, force: true });
  });
  return f;
}

test("frontend builds generate a new immutable version every time, without publishing private bootstrap or browser profiles", async (t) => {
  const f = await fixture(t),
    first = f.build(),
    second = f.build();
  assert.notEqual(first.release, second.release);
  assert.equal(first.content_hash, second.content_hash);
  const m = readFrontendManifest(join(f.installed, first.release));
  assert.ok(m.files.some((row) => row.path === "assets/marker.json"));
  assert.ok(
    !m.files.some(
      (row) =>
        row.path.endsWith(".html") ||
        row.path === "private.json" ||
        row.path.includes("fixtures") ||
        row.path.includes("diagnostics"),
    ),
  );
  assert.ok(!m.bootstrap.some((row) => row.path.endsWith("secret.json")));
  assert.ok(m.bootstrap.some((row) => row.path.endsWith("index.html")));
  const registered = f.versions.register("test", { bundle: first.bundle });
  assert.equal(registered.id, first.release);
  assert.throws(
    () => f.versions.activate("test", { id: first.release, revision: 0 }),
    { code: "FRONTEND_NOT_VERIFIED" },
  );
  writeFileSync(
    join(f.installed, first.release, "objects/assets/marker.json"),
    "corrupted",
  );
  await assert.rejects(f.versions.probe("test", first.release), {
    code: "FRONTEND_FILE_CHANGED",
  });
});

test("a frontend switch changes new sessions while old pages and assets stay pinned across gateway restart", async (t) => {
  const f = await fixture(t),
    old = f.build();
  f.versions.register("test", { bundle: old.bundle });
  await f.versions.probe("test", old.release);
  f.versions.activate("test", { id: old.release, revision: 0 });
  const a = await f.launch(),
    aURL = new URL(a.launch_url),
    token = aURL.searchParams.get("ops")!;
  assert.ok(aURL.hostname.includes(old.release));
  const page = await f.http(aURL.host, aURL.pathname + aURL.search);
  assert.equal(page.status, 200, page.body);
  assert.match(page.body, /local-auth-bootstrap/);
  const asset = await f.http(aURL.host, "/assets/marker.json");
  assert.equal(asset.status, 200);
  assert.match(asset.body, /old/);
  assert.match(asset.headers["cache-control"], /immutable/);
  writeFileSync(join(f.source, "assets/marker.json"), '{"version":"new"}');
  const next = f.build();
  f.versions.register("test", { bundle: next.bundle });
  await f.versions.probe("test", next.release);
  f.versions.activate("test", { id: next.release, revision: 1 });
  assert.throws(
    () => f.versions.activate("test", { id: old.release, revision: 1 }),
    { code: "VERSION_CONFLICT" },
  );
  const b = await f.launch(),
    bURL = new URL(b.launch_url);
  assert.ok(bURL.hostname.includes(next.release));
  assert.match((await f.http(aURL.host, "/assets/marker.json")).body, /old/);
  assert.match((await f.http(bURL.host, "/assets/marker.json")).body, /new/);
  assert.equal((await f.http(bURL.host, "/?ops=" + token)).status, 403);
  assert.notEqual(
    (await f.http(aURL.host, "/fixtures/secret.json?ops=" + token)).status,
    200,
  );
  await f.restart();
  assert.equal(
    (await f.http(aURL.host, aURL.pathname + aURL.search)).status,
    200,
  );
  assert.match((await f.http(aURL.host, "/assets/marker.json")).body, /old/);
  f.versions.activate("test", { id: old.release, revision: 2 });
  assert.ok(
    new URL((await f.launch()).launch_url).hostname.includes(old.release),
  );
  assert.throws(() => f.versions.retire("test", old.release), {
    code: "FRONTEND_VERSION_ACTIVE",
  });
});

test("frontend management is platform-only and registration reads generated versions instead of accepting handwritten numbers", async (t) => {
  const f = await fixture(t),
    build = f.build();
  const admin = f.control.createUser("test", "frontend-admin", "admin");
  const app = adminServer(
    f.p,
    f.config,
    resolve("frontend/admin"),
    resolve("config"),
  );
  f.servers.add(app);
  const origin = "http://127.0.0.1:" + (await listen(app));
  const login = async (username: string, password: string, tenant = false) => {
    const response = await fetch(
      origin + `/api/${tenant ? "merchant" : "admin"}/login`,
      {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ username, password }),
      },
    );
    const result: any = await response.json();
    assert.equal(response.status, 200);
    return {
      cookie: response.headers.get("set-cookie")!.split(";")[0],
      csrf: result.data.csrf_token,
    };
  };
  const a = await login("frontend-admin", admin.temporary_password),
    m = await login(
      f.created.login.name,
      f.created.login.temporary_password,
      true,
    );
  const post = (path: string, q: any, s: any) =>
    fetch(origin + path, {
      method: "POST",
      headers: {
        "content-type": "application/json",
        cookie: s.cookie,
        "x-gtt-csrf": s.csrf,
      },
      body: JSON.stringify(q),
    });
  const response = await post(
    "/api/admin/frontends/register",
    { bundle: build.bundle },
    a,
  );
  assert.equal(response.status, 200, await response.clone().text());
  assert.equal(((await response.json()) as any).data.id, build.release);
  for (const action of [
    "list",
    "candidates",
    "register",
    "probe",
    "activate",
    "retire",
  ])
    assert.equal(
      (await post("/api/merchant/frontends/" + action, {}, m)).status,
      403,
    );
  assert.equal(
    (
      await post(
        "/api/admin/frontends/activate",
        { id: build.release, revision: 0 },
        { ...a, csrf: "wrong" },
      )
    ).status,
    403,
  );
  assert.throws(() => f.versions.register("test", { bundle: "../outside" }), {
    code: "FRONTEND_BUNDLE_INVALID",
  });
});

test("frontend publication uploads public files only, checks private bucket protections, and never overwrites differing objects", async (t) => {
  const f = await fixture(t),
    build = f.build(),
    { publishFrontend } = await import(
      pathToFileURL(resolve("tools/publish-frontend.mjs")).href
    );
  const objects = new Map<string, any>();
  let puts = 0,
    blocked = false;
  const run = (operation: string, args: string[]) => {
    const value = (key: string) => args[args.indexOf(key) + 1];
    if (operation === "get-public-access-block")
      return {
        PublicAccessBlockConfiguration: {
          BlockPublicAcls: !blocked,
          IgnorePublicAcls: true,
          BlockPublicPolicy: true,
          RestrictPublicBuckets: true,
        },
      };
    if (operation === "get-bucket-ownership-controls")
      return {
        OwnershipControls: {
          Rules: [{ ObjectOwnership: "BucketOwnerEnforced" }],
        },
      };
    if (operation === "get-bucket-versioning") return { Status: "Enabled" };
    if (operation === "get-bucket-encryption")
      return {
        ServerSideEncryptionConfiguration: {
          Rules: [
            { ApplyServerSideEncryptionByDefault: { SSEAlgorithm: "AES256" } },
          ],
        },
      };
    if (operation === "head-object") {
      const object = objects.get(value("--key"));
      if (!object) throw Error("NotFound");
      return object;
    }
    if (operation === "put-object") {
      assert.equal(value("--if-none-match"), "*");
      assert.equal(value("--expected-bucket-owner"), "123456789012");
      const bytes = readFileSync(value("--body"));
      objects.set(value("--key"), {
        ContentLength: bytes.length,
        ChecksumSHA256: value("--checksum-sha256"),
        ContentType: value("--content-type"),
        CacheControl: value("--cache-control"),
        Metadata: JSON.parse(value("--metadata")),
        bytes,
      });
      puts++;
      return {};
    }
    throw Error("Unexpected cloud operation " + operation);
  };
  const options = {
    bundle: join(f.installed, build.release),
    bucket: "test-private-frontend",
    owner: "123456789012",
    run,
  };
  blocked = true;
  assert.throws(() => publishFrontend(options), /protections/);
  assert.equal(puts, 0);
  blocked = false;
  const receipt = publishFrontend(options);
  assert.equal(receipt.status, "passed");
  assert.equal(receipt.bootstrap_uploaded, false);
  assert.ok(
    [...objects.keys()].every(
      (key) =>
        key.startsWith(`releases/buffalo-win/${build.release}/`) &&
        !key.split("/").includes("bootstrap") &&
        !key.split("/").includes("fixtures"),
    ),
  );
  assert.ok(
    ![...objects.values()].some(
      (o) =>
        o.bytes.includes("PRIVATE_SENTINEL") ||
        o.bytes.includes("PRIVATE_PROFILE"),
    ),
  );
  const count = puts;
  publishFrontend(options);
  assert.equal(puts, count);
  objects.values().next().value.ChecksumSHA256 = "tampered";
  assert.throws(() => publishFrontend(options), /refusing overwrite/);
  assert.equal(puts, count);
});

test("version CDN routing keeps assets in immutable S3 prefixes and preserves authentication on dynamic requests", async () => {
  const { renderFrontendEdge } = await import(
    pathToFileURL(resolve("tools/render-frontend-edge.mjs")).href
  );
  const code = renderFrontendEdge({
    host_suffix: ".play.example.com",
    assets_origin_id: "version-assets-root",
    assets_domain: "private-assets.s3.us-east-1.amazonaws.com",
    dynamic_origin_id: "application",
    dynamic_tls_name: "origin.example.com",
  });
  const calls: any[] = [],
    box: any = {
      cf: {
        selectRequestOriginById: (...args: any[]) => calls.push(args),
        updateRequestOrigin: (...args: any[]) => calls.push(args),
      },
    };
  runInNewContext(
    code.replace(/^import cf[^\n]*\n/, "") + "\nthis.handler=handler;",
    box,
  );
  const version = "fe-20261113000000000-12345678-abcdef",
    host = version + "-g1.play.example.com";
  const request = (uri: string, method = "GET") => ({
    uri,
    method,
    headers: {
      host: { value: host },
      authorization: { value: "Bearer private-session" },
    },
    cookies: { session: { value: "private" } },
    querystring: { ops: { value: "private-session" } },
  });
  const asset = box.handler({ request: request("/assets/picture.png") });
  assert.equal(
    asset.uri,
    `/releases/buffalo-win/${version}/assets/picture.png`,
  );
  assert.equal(asset.headers.authorization, undefined);
  assert.equal(Object.keys(asset.querystring).length, 0);
  assert.equal(Object.keys(asset.cookies).length, 0);
  assert.equal(calls[0][0], "version-assets-root");
  calls.length = 0;
  const dynamic = box.handler({
    request: request("/game-api/buffalo-win/v2/Spin", "POST"),
  });
  assert.equal(dynamic.headers.authorization.value, "Bearer private-session");
  assert.equal(dynamic.querystring.ops.value, "private-session");
  assert.equal(calls[0][0], "application");
  calls.length = 0;
  box.handler({ request: request("/fixtures/auth-metadata.json") });
  assert.equal(calls[0][0], "application");
  assert.equal(
    box.handler({ request: request("/%2e%2e/secret.json") }).statusCode,
    404,
  );
});

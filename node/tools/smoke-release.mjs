import { mkdtempSync, readFileSync, writeFileSync, rmSync } from "node:fs";
import { resolve, join } from "node:path";
import { tmpdir } from "node:os";
import { execFileSync, spawn } from "node:child_process";
import { createHash } from "node:crypto";
import assert from "node:assert/strict";

const release = resolve(process.argv[2] ?? "");
const record = JSON.parse(readFileSync(join(release, "release.json"), "utf8"));
const dir = mkdtempSync(join(tmpdir(), "gtt-node-release-"));
const children = [];
const sha = (b) => createHash("sha256").update(b).digest("hex");
const configPath = join(dir, "runtime/config.json");
function start(name, action, extra = []) {
  return new Promise((ok, fail) => {
    const child = spawn(
      process.execPath,
      ["dist/cli.js", action, "--config", configPath, ...extra],
      {
        cwd: join(dir, name),
        windowsHide: true,
        stdio: ["ignore", "pipe", "pipe"],
      },
    );
    children.push(child);
    let output = "";
    const timer = setTimeout(
      () => fail(new Error(`${action} startup timeout: ${output}`)),
      20000,
    );
    const exited = (code) => {
      clearTimeout(timer);
      fail(new Error(`${action} exited ${code}: ${output}`));
    };
    child.once("error", fail);
    child.once("exit", exited);
    child.stderr.on("data", (chunk) => {
      output += chunk;
    });
    child.stdout.on("data", (chunk) => {
      output += chunk;
      const match = /listening on 127\.0\.0\.1:(\d+)/.exec(output);
      if (match) {
        clearTimeout(timer);
        child.off("exit", exited);
        ok({ port: Number(match[1]), pid: child.pid });
      }
    });
  });
}
async function request(port, path, init = {}) {
  return fetch(`http://127.0.0.1:${port}${path}`, {
    ...init,
    signal: AbortSignal.timeout(10000),
  });
}
try {
  for (const artifact of record.artifacts) {
    const archive = join(release, artifact.file);
    assert.equal(sha(readFileSync(archive)), artifact.sha256);
    execFileSync("tar", ["-xzf", archive, "-C", dir]);
    const manifest = JSON.parse(
      readFileSync(join(dir, artifact.name, "release-manifest.json"), "utf8"),
    );
    for (const file of manifest.files) {
      const bytes = readFileSync(join(dir, artifact.name, file.path));
      assert.equal(bytes.length, file.size);
      assert.equal(sha(bytes), file.sha256);
      assert.ok(
        !/(?:^|\/)(?:node_modules|tests|runtime)(?:\/|$)|\.(?:py|sqlite3|sqlite|db)$/.test(
          file.path,
        ),
        file.path,
      );
    }
  }
  execFileSync(
    process.execPath,
    ["dist/cli.js", "init", "--config", configPath],
    { cwd: join(dir, "gateway"), windowsHide: true, stdio: "pipe" },
  );
  const config = JSON.parse(readFileSync(configPath, "utf8"));
  config.ports = { gateway: 0, admin: 0, buffalo: 0 };
  writeFileSync(configPath, JSON.stringify(config));
  const game = await start("buffalo-win", "buffalo");
  config.game_origin = `http://127.0.0.1:${game.port}`;
  writeFileSync(configPath, JSON.stringify(config));
  const gateway = await start("gateway", "gateway");
  const admin = await start("gateway", "admin");
  assert.equal(new Set([game.pid, gateway.pid, admin.pid]).size, 3);
  assert.equal((await request(game.port, "/health")).status, 401);
  assert.equal(
    (
      await request(game.port, "/health", {
        headers: { authorization: `Bearer ${config.internal_secret}` },
      })
    ).status,
    200,
  );
  for (const port of [gateway.port, admin.port])
    assert.equal((await request(port, "/health")).status, 200);
  const html = await request(gateway.port, "/");
  assert.equal(html.status, 200);
  assert.match(await html.text(), /local-auth-bootstrap/);
  assert.equal(
    (await request(gateway.port, "/fixtures/auth-metadata.json")).status,
    404,
  );
  for (const path of ["/", "/merchant/", "/admin.js", "/admin.css"])
    assert.equal((await request(admin.port, path)).status, 200, path);
  const credentials = JSON.parse(
    readFileSync(join(dir, "runtime/admin-bootstrap.json"), "utf8"),
  );
  const login = await request(admin.port, "/api/admin/login", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({
      username: credentials.username,
      password: credentials.password,
    }),
  });
  assert.equal(login.status, 200);
  assert.ok((await login.json()).data.csrf_token);
  execFileSync(
    process.execPath,
    ["dist/cli.js", "rtp-worker", "--once", "--config", configPath],
    {
      cwd: join(dir, "gateway"),
      windowsHide: true,
      stdio: "pipe",
      timeout: 20000,
    },
  );
  const allChecks = [];
  if (record.artifacts.some((a) => a.name === "all-services")) {
    const allRoot = join(dir, "all-services");
    for (const spec of JSON.parse(
      readFileSync(join(allRoot, "SERVICES.json"), "utf8"),
    )) {
      const service = await start("all-services", "service", [
        "--service-dir",
        join(allRoot, "resources/services", spec.id),
        "--database",
        join(dir, "runtime", spec.id + ".sqlite3"),
        "--port",
        "0",
      ]);
      const health = await request(service.port, "/health");
      assert.equal(health.status, 200);
      assert.equal((await health.json()).service_id, spec.id);
      if (spec.id !== "game-api") {
        const launch = await request(
          service.port,
          `/api/v1/games/${spec.id}/launch`,
          {
            method: "POST",
            headers: { "content-type": "application/json" },
            body: '{"language":"en"}',
          },
        );
        assert.equal(launch.status, 201, await launch.clone().text());
        const data = await launch.json();
        let link = new URL(data.launch_url, `http://127.0.0.1:${service.port}`);
        const page = await fetch(link, { signal: AbortSignal.timeout(5000) });
        assert.equal(page.status, 200, spec.id);
        assert.match(
          await page.text(),
          /<html|<!doctype/i,
          spec.id + " " + link.href,
        );
        assert.equal(
          (await request(service.port, "/fixtures/auth-metadata.json")).status,
          404,
        );
      }
      allChecks.push(spec.id);
      const child = children.find((c) => c.pid === service.pid);
      await new Promise((ok) => {
        child.once("exit", ok);
        child.kill();
      });
    }
    execFileSync(
      process.execPath,
      ["dist/cli.js", "sandbox-init", "--config", configPath],
      { cwd: allRoot, windowsHide: true, stdio: "pipe" },
    );
    const sandbox = JSON.parse(readFileSync(configPath, "utf8"));
    sandbox.ports.platform = 0;
    writeFileSync(configPath, JSON.stringify(sandbox));
    const platform = await start("all-services", "platform");
    assert.equal((await request(platform.port, "/")).status, 200);
    assert.equal((await request(platform.port, "/sandbox/status")).status, 200);
  }
  writeFileSync(
    join(release, "verification.json"),
    JSON.stringify(
      {
        build_id: record.build_id,
        verified_at: new Date().toISOString(),
        node: process.version,
        migrated_services: allChecks,
        checks: [
          "archive-sha256",
          "unpacked-file-sha256",
          "no-python-or-development-runtime",
          "isolated-bootstrap",
          "three-distinct-node-processes",
          "internal-auth",
          "gateway-health-and-html",
          "fixtures-private",
          "admin-and-merchant-entries",
          "admin-login",
          "rtp-worker-once",
          ...(allChecks.length
            ? [
                "20-isolated-service-processes",
                "19-original-game-launch-pages",
                "native-mock-platform",
              ]
            : []),
        ],
      },
      null,
      2,
    ),
    { flag: "wx" },
  );
  console.log(
    "Clean unpack verification passed: gateway, Buffalo, admin, RTP worker, and all packaged services.",
  );
} finally {
  await Promise.all(
    children.map(
      (child) =>
        new Promise((ok) => {
          if (child.exitCode !== null || child.signalCode !== null) return ok();
          child.once("exit", ok);
          child.kill();
        }),
    ),
  );
  // dir is exclusively the mkdtemp directory created by this script, never user input.
  rmSync(dir, { recursive: true, force: true });
}

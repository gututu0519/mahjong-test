import { mkdtempSync, readFileSync, writeFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { resolve, join, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import { execFileSync, spawn } from "node:child_process";
import { createServer } from "node:net";
import assert from "node:assert/strict";
const root = resolve(dirname(fileURLToPath(import.meta.url)), ".."),
  repo = resolve(root, ".."),
  dir = mkdtempSync(join(tmpdir(), "gtt-start-")),
  children = [];
async function start(action, args) {
  return new Promise((ok, fail) => {
    const child = spawn(
      process.execPath,
      [join(root, "tools/start.mjs"), action, ...args],
      { cwd: repo, windowsHide: true, stdio: ["ignore", "pipe", "pipe"] },
    );
    children.push(child);
    let output = "";
    const timer = setTimeout(
      () => fail(Error("Startup timeout: " + output)),
      20000,
    );
    child.once("error", fail);
    child.once("exit", (code) => {
      clearTimeout(timer);
      fail(Error("Exited " + code + ": " + output));
    });
    child.stdout.on("data", (v) => {
      output += v;
      const re =
        action === "gateway"
          ? /gateway Node service listening on 127\.0\.0\.1:(\d+)/
          : /Node service listening on 127\.0\.0\.1:(\d+)/;
      const m = re.exec(output);
      if (m) {
        clearTimeout(timer);
        ok({ child, port: Number(m[1]) });
      }
    });
    child.stderr.on("data", (v) => (output += v));
  });
}
async function stop(child) {
  if (child.exitCode !== null || child.signalCode !== null) return;
  await new Promise((ok) => {
    child.once("exit", ok);
    child.kill();
  });
}
try {
  const local = await start("fortune-rabbit", [
    "--port",
    "0",
    "--database",
    join(dir, "local.sqlite3"),
  ]);
  assert.equal(
    (await fetch("http://127.0.0.1:" + local.port + "/health")).status,
    200,
  );
  await stop(local.child);
  const reservation = createServer();
  await new Promise((ok) => reservation.listen(0, "127.0.0.1", ok));
  const computePort = reservation.address().port;
  await new Promise((ok) => reservation.close(ok));
  const configPath = join(dir, "config.json");
  execFileSync(
    process.execPath,
    [join(root, "dist/cli.js"), "init", "--config", configPath],
    { cwd: root, windowsHide: true, stdio: "pipe" },
  );
  const config = JSON.parse(readFileSync(configPath, "utf8"));
  config.game_services_mode="embedded";
  config.ports.gateway = 0;
  config.ports.buffalo = computePort;
  config.game_origin = "http://127.0.0.1:" + computePort;
  writeFileSync(configPath, JSON.stringify(config));
  const gateway = await start("gateway", ["--config", configPath]);
  assert.equal(
    (await fetch("http://127.0.0.1:" + gateway.port + "/health")).status,
    200,
  );
  await stop(gateway.child);
  let stopped = false;
  for (let i = 0; i < 50; i++) {
    try {
      await fetch(config.game_origin + "/health", {
        signal: AbortSignal.timeout(300),
      });
    } catch {
      stopped = true;
      break;
    }
    await new Promise((ok) => setTimeout(ok, 100));
  }
  assert.ok(stopped, "Compute child must exit after supervisor is terminated");
  console.log(
    "Original Node launchers passed: service, gateway and compute child cleanup.",
  );
} finally {
  for (const child of children) await stop(child);
  rmSync(dir, { recursive: true, force: true });
}

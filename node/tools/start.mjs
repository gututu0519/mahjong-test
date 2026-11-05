import {
  existsSync,
  readFileSync,
  readdirSync,
  statSync,
  openSync,
  closeSync,
  unlinkSync,
  writeFileSync,
  mkdirSync,
} from "node:fs";
import { resolve, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import { execFileSync, spawn } from "node:child_process";

const root = resolve(dirname(fileURLToPath(import.meta.url)), ".."),
  repo = resolve(root, "..");
const [action, ...extra] = process.argv.slice(2);
function newest(at) {
  let time = 0;
  for (const entry of readdirSync(at, { withFileTypes: true })) {
    if (
      ["node_modules", "dist", "runtime", "fixtures", ".git"].includes(
        entry.name,
      )
    )
      continue;
    const path = resolve(at, entry.name);
    if (entry.isDirectory()) time = Math.max(time, newest(path));
    else if (/\.(ts|json)$/.test(entry.name))
      time = Math.max(time, statSync(path).mtimeMs);
  }
  return time;
}
async function build() {
  const compiler = resolve(root, "node_modules/typescript/bin/tsc");
  if (!existsSync(compiler))
    throw Error("Run npm ci in node/ before starting services.");
  const stamp = resolve(root, "dist/.built"),
    lock = resolve(root, "runtime/build.lock");
  mkdirSync(dirname(lock), { recursive: true });
  for (let i = 0; i < 240; i++) {
    if (
      existsSync(stamp) &&
      Number(readFileSync(stamp, "utf8")) >= newest(root)
    )
      return;
    let fd;
    try {
      fd = openSync(lock, "wx");
    } catch (e) {
      if (e.code !== "EEXIST") throw e;
      await new Promise((ok) => setTimeout(ok, 250));
      continue;
    }
    try {
      execFileSync(process.execPath, [compiler], {
        cwd: root,
        stdio: "inherit",
        windowsHide: true,
      });
      writeFileSync(stamp, String(Date.now()));
      return;
    } finally {
      closeSync(fd);
      unlinkSync(lock);
    }
  }
  throw Error(
    "Build lock is still held. Check the other build; remove runtime/build.lock only if its process has stopped.",
  );
}
await build();
const { main } = await import("../dist/cli.js");
const auxiliary = {
  gateway: "gateway",
  admin: "admin",
  mock: "platform",
  platform: "platform",
  "admin-init": "admin-init",
  launch: "launch",
  transactions: "transactions",
  retry: "retry",
  "rtp-worker": "rtp-worker",
};
if (Object.hasOwn(auxiliary, action)) {
  const { legacyConfig } = await import("../dist/services/legacy-config.js");
  const at = extra.indexOf("--config");
  const configPath =
      at >= 0
        ? resolve(extra[at + 1])
        : existsSync(resolve(repo, "services/gtt-gateway/data/sandbox.json"))
          ? legacyConfig(repo)
          : resolve(root, "runtime/config.json"),
    config = JSON.parse(readFileSync(configPath, "utf8"));
  // Old gateway was a single process. Supervise its new compute child so its
  // original one-click entry remains usable and exits without an orphan child.
  let child;
  if (action === "gateway") {
    try {
      const r = await fetch(config.game_origin + "/health", {
        headers: { authorization: "Bearer " + config.internal_secret },
        signal: AbortSignal.timeout(1000),
      });
      if (!r.ok)
        throw Error("An incompatible process occupies the compute port.");
    } catch (e) {
      if (e.message === "An incompatible process occupies the compute port.")
        throw e;
      child = spawn(
        process.execPath,
        [resolve(root, "dist/cli.js"), "buffalo", "--config", configPath],
        { stdio: ["inherit", "inherit", "inherit", "ipc"], windowsHide: true },
      );
      let ready = false;
      for (let i = 0; i < 100; i++) {
        if (child.exitCode !== null)
          throw Error("Compute child failed to start.");
        try {
          const r = await fetch(config.game_origin + "/health", {
            headers: { authorization: "Bearer " + config.internal_secret },
            signal: AbortSignal.timeout(500),
          });
          if (r.ok) {
            ready = true;
            break;
          }
        } catch {}
        await new Promise((ok) => setTimeout(ok, 100));
      }
      if (!ready) {
        child.kill();
        throw Error("Compute startup timed out.");
      }
    }
  }
  if (child) {
    process.once("exit", () => child.kill());
    process.once("SIGINT", () => child.kill());
    process.once("SIGTERM", () => child.kill());
    child.once("exit", (code) => {
      if (code && process.exitCode === undefined) {
        console.error("Compute child exited:", code);
        process.exitCode = 1;
        process.emit("SIGTERM");
      }
    });
  }
  try {
    await main([auxiliary[action], "--config", configPath, ...extra]);
  } catch (e) {
    child?.kill();
    throw e;
  }
} else {
  if (!/^[a-z0-9-]+$/.test(action ?? ""))
    throw Error("Supply one service directory name.");
  await main([
    "service",
    "--service-dir",
    resolve(repo, "services", action),
    ...extra,
  ]);
}

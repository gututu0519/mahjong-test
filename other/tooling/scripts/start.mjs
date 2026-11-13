import {
  existsSync,
  readFileSync,
} from "node:fs";
import { resolve, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import { spawn } from "node:child_process";

const root = resolve(dirname(fileURLToPath(import.meta.url)), ".."),
  repo = resolve(root, "..");
const [action, ...extra] = process.argv.slice(2);
// The workspace launcher builds the relocated sources before invoking this
// staged runtime tool. Never run tsc against generated runtime directories.
if (!existsSync(resolve(root, 'dist/.built')))
  throw Error('Run node other/tooling/run.mjs start <service> from the workspace.');
const { main } = await import("../dist/cli.js");
const {platformEnvironment,readPlatformConfig}=await import('../dist/shared/config/environment.js');
const envAt=extra.indexOf('--env-file');
const env=platformEnvironment(envAt>=0?extra[envAt+1]:undefined);
if(env.GTT_PLATFORM_ENV_FILE)process.env.GTT_PLATFORM_ENV_FILE=env.GTT_PLATFORM_ENV_FILE;
if(env.GTT_PG_CONFIG)process.env.GTT_PG_CONFIG=env.GTT_PG_CONFIG;
const auxiliary = {
  gateway: "gateway",
  games: "games",
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
        : env.GTT_CONFIG_FILE ? resolve(env.GTT_CONFIG_FILE)
        : existsSync(resolve(repo, "services/gtt-gateway/data/sandbox.json"))
          ? legacyConfig(repo)
          : resolve(repo, "services/gtt-gateway/data/node.json"),
    config = readPlatformConfig(configPath,env.GTT_PLATFORM_ENV_FILE);
  // Old gateway was a single process. Supervise its new compute child so its
  // original one-click entry remains usable and exits without an orphan child.
  let child;
  if (action === "gateway" && config.game_services_mode === "embedded") {
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

import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { resolve, dirname } from "node:path";
import { spawn, type ChildProcess } from "node:child_process";
import { components, ROOT } from "../../tooling/cli.js";
import { GAME_CODES } from "../../../gateway/src/catalog.js";
import { check, hex } from "../core.js";
import { sourcePath } from "../compat/runtime.js";
import {readGameEnvironment,gameProcessEnvironment,integer} from '../config/environment.js';

// Development convenience only. Production runs each game with its own service
// supervisor; the gateway never starts, stops or hosts a game engine.
export async function runLocalGames(config: any) {
  check(config.environment !== "production", "LOCAL_GAMES_FORBIDDEN");
  const { provider, control } = await components({
    ...config,
    game_services_mode: "remote",
  });
  const registry = provider.multi!.remote!;
  const descriptors = JSON.parse(
    readFileSync(resolve(ROOT, "config/game-descriptors.json"), "utf8"),
  );
  const children: ChildProcess[] = [];
  const keys = resolve(dirname(config.merchant_database), "game-service-keys");
  mkdirSync(keys, { recursive: true });
  let stopping = false;
  const stop = () => {
    if (stopping) return;
    stopping = true;
    for (const child of children) child.kill();
    provider.close();
    control.close();
  };
  process.once("SIGINT", stop);
  process.once("SIGTERM", stop);
  try {
    for (let i = 0; i < GAME_CODES.length; i++) {
      const code = GAME_CODES[i];
      const release = descriptors[code].ruleset_id.replace(
        /[^A-Za-z0-9._-]/g,
        "-",
      );
      const envFile=sourcePath(`services/${code}/releases/${release}.env`);
      const instance=existsSync(envFile)?readGameEnvironment(envFile,{}):{};
      check(!instance.GAME_ID||instance.GAME_ID===code,'GAME_SERVICE_MISMATCH');
      check(!instance.GAME_RELEASE||instance.GAME_RELEASE===release,'GAME_RELEASE_CONFIG_CONFLICT');
      const port=integer(instance.GAME_PORT??String((config.game_service_base_port??8211)+i),'GAME_PORT',1);
      const host=instance.GAME_BIND??'127.0.0.1';
      const keyfile = instance.GAME_SECRET_FILE??resolve(keys, code + ".key");
      if (!existsSync(keyfile))
        writeFileSync(keyfile, hex(32), { flag: "wx", mode: 0o600 });
      const secret = readFileSync(keyfile, "utf8").trim();
      const origin = `http://${host.includes(':')?'['+host+']':host}:` + port;
      let live = false;
      try {
        await registry.request(
          {
            id: "",
            code,
            release,
            origin,
            secret,
            status: "ready",
            descriptor: null,
          },
          "describe",
        );
        live = true;
      } catch (error: any) {
        if (error.code !== "GAME_UNAVAILABLE") throw error;
      }
      if (!live) {
        const child = spawn(
          process.execPath,
          [
            resolve(ROOT, "dist/cli.js"),
            "game",
            "--game-id",
            code,
            "--game-config",
            instance.GAME_CONFIG??sourcePath(`services/${code}/config/${code}.json`),
            "--secret-file",
            keyfile,
            "--port",
            String(port),
            "--release",
            release,
            '--host',host,
            ...(existsSync(envFile)?['--env-file',envFile]:[]),
          ],
          { stdio: ["ignore", "inherit", "inherit", "ipc"], windowsHide: true,env:gameProcessEnvironment(process.env) },
        );
        children.push(child);
        let ready = false;
        for (let attempt = 0; attempt < 100; attempt++) {
          check(
            child.exitCode === null,
            "GAME_START_FAILED",
            code + " failed to start",
          );
          try {
            await registry.request(
              {
                id: "",
                code,
                release,
                origin,
                secret,
                status: "ready",
                descriptor: null,
              },
              "describe",
            );
            ready = true;
            break;
          } catch {}
          await new Promise((ok) => setTimeout(ok, 100));
        }
        check(ready, "GAME_START_TIMEOUT", code + " startup timed out");
      }
      let registered = control.get(
        "SELECT id FROM game_service_releases WHERE code=? AND release=?",
        code,
        release,
      );
      if (!registered)
        registered = await registry.register("local-launcher", {
          code,
          release,
          origin,
          secret,
        });
      else {
        const old = registry.release(registered.id);
        check(
          old.origin === origin && old.secret === secret,
          "GAME_RELEASE_CONFIG_CONFLICT",
          "已注册版本的地址或密钥不一致，请在平台后台核对",
        );
      }
      if (!control.get("SELECT 1 FROM game_service_routes WHERE code=?", code))
        await registry.activate("local-launcher", {
          id: registered.id,
          revision: 0,
        });
    }
    console.log(
      "19 independent game services ready; ports " +
        (config.game_service_base_port ?? 8211) +
        "–" +
        ((config.game_service_base_port ?? 8211) + 18),
    );
    await new Promise<void>((ok) => {
      process.once("SIGINT", ok);
      process.once("SIGTERM", ok);
    });
  } finally {
    stop();
  }
}

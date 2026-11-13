import { readFileSync, writeFileSync, mkdirSync, existsSync } from "node:fs";
import { resolve, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import { check, hex, encode, signedHeaders, object } from "../shared/core.js";
import { listen, fetchBounded } from "../shared/http.js";
import { accessLog } from "../shared/logging.js";
import { platformEnvironment, readPlatformConfig, readGameEnvironment, gameProcessEnvironment, integer } from '../shared/config/environment.js';
export const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "..");
export async function components(c: any) {
  if(c.postgres_config)process.env.GTT_PG_CONFIG=resolve(c.postgres_config);
  c = {...c,game_services_mode:c.game_services_mode??"remote"};
  const { Control } = await import("../shared/control.js");
  const { Provider } = await import("../../gateway/src/provider.js");
  const { GameClient } = await import("../../gateway/src/game-client.js");
  const control = new Control(
      c.merchant_database,
      resolve(ROOT, "config/control.sql"),
    ),
    game = new GameClient(
      c.game_origin ?? (c.game_services_mode === "remote" ? "http://127.0.0.1:1" : undefined),
      c.internal_secret ?? "",
      JSON.parse(
        readFileSync(
          c.game_config ?? resolve(ROOT, "config/buffalo-win.json"),
          "utf8",
        ),
      ),
    ),
    provider = new Provider(
      c.game_database,
      control,
      game,
      resolve(ROOT, "config/game.sql"),
      c.public_origins?.play ?? c.gateway_origin,
      resolve(ROOT, "config/rtp-models.json"),
    );
  provider.enableGames(c);
  await provider.initialize();
  return { control, provider, game };
}
export async function main(args = process.argv.slice(2)) {
  if (process.channel)
    process.once("disconnect", () => process.emit("SIGTERM"));
  const action = args[0],
    arg = (name: string, fallback: string) => {
      const at = args.indexOf(name);
      return at < 0 ? fallback : args[at + 1];
    };
  const serviceFile=resolve(ROOT,'SERVICE.json');
  if(existsSync(serviceFile)) {
    const service=JSON.parse(readFileSync(serviceFile,'utf8'));
    check(service.commands.includes(action),'SERVICE_PACKAGE_MISMATCH',`此交付包属于 ${service.role}，请使用对应服务的独立交付包`);
  }
  const envFile=arg('--env-file','')||undefined;
  const platformEnv=action==='game'?{}:platformEnvironment(envFile);
  if(platformEnv.GTT_PLATFORM_ENV_FILE)process.env.GTT_PLATFORM_ENV_FILE=platformEnv.GTT_PLATFORM_ENV_FILE;
  if(platformEnv.GTT_PG_CONFIG)process.env.GTT_PG_CONFIG=platformEnv.GTT_PG_CONFIG;
  const path = resolve(arg("--config", platformEnv.GTT_CONFIG_FILE??resolve(ROOT, "../services/gtt-gateway/data/node.json")));
  if (action === "service") {
    const { buildLocal } = await import("../shared/services/local.js");
    const directory = arg("--service-dir", "");
    check(directory, "SERVICE_DIRECTORY_REQUIRED");
    const portArg = arg("--port", "");
    const dbArg = arg("--database", "");
    const app = await buildLocal(resolve(directory), {
      ...(portArg ? { port: Number(portArg) } : {}),
      ...(dbArg ? { database: resolve(dbArg) } : {}),
    });
    accessLog(app.server, resolve(directory, "logs/service.log"));
    const port = await listen(
      app.server,
      portArg ? Number(portArg) : app.spec.port,
    );
    console.log(`${app.spec.id} Node service listening on 127.0.0.1:${port}`);
    process.on("SIGINT", () => app.server.close());
    process.on("SIGTERM", () => app.server.close());
    return;
  }
  if (action === "game") {
    const overrides: Record<string,string>={};
    for(const [flag,key]of Object.entries({'--game-id':'GAME_ID','--release':'GAME_RELEASE','--game-config':'GAME_CONFIG','--secret-file':'GAME_SECRET_FILE','--host':'GAME_BIND','--port':'GAME_PORT','--client-contract':'GAME_CLIENT_CONTRACT','--state-contract':'GAME_STATE_CONTRACT'})) {
      const at=args.indexOf(flag);if(at>=0)overrides[key]=args[at+1];
    }
    const env=readGameEnvironment(envFile,{...process.env,...overrides});
    const clean=gameProcessEnvironment(env);
    for(const key of Object.keys(process.env))if(!(key in clean))delete process.env[key];
    Object.assign(process.env,clean);
    const { computeServer } = await import("../shared/services/compute.js");
    const secretFile = arg("--secret-file", env.GAME_SECRET_FILE??"");
    check(secretFile, "INTERNAL_KEY_FILE_REQUIRED");
    const manifestPath=resolve(ROOT,"GAME.json");
    const manifest=existsSync(manifestPath)?JSON.parse(readFileSync(manifestPath,"utf8")):null;
    const id = arg("--game-id", env.GAME_ID??manifest?.code??""),
      configuration = arg("--game-config", env.GAME_CONFIG??resolve(ROOT,'config/game.json'));
    check(configuration, "GAME_CONFIG_REQUIRED");
    if(manifest)check(manifest.code===id,"GAME_PACKAGE_MISMATCH");
    const s = computeServer(
      id,
      resolve(configuration),
      readFileSync(secretFile, "utf8").trim(),
      {release:arg("--release",env.GAME_RELEASE??"")||manifest?.release||undefined,clientContract:arg("--client-contract",env.GAME_CLIENT_CONTRACT??"")||undefined,stateContract:arg("--state-contract",env.GAME_STATE_CONTRACT??"")||undefined},
    );
    const host=arg("--host",env.GAME_BIND??"127.0.0.1");
    const port = await listen(s, integer(arg("--port", env.GAME_PORT??"8214"),'GAME_PORT'),host);
    console.log(`${id} Node compute listening on ${host}:${port}`);
    process.on("SIGINT", () => s.close());
    process.on("SIGTERM", () => s.close());
    return;
  }
  if (action === "init") {
    const { Control } = await import("../shared/control.js");
    check(
      !existsSync(path),
      "CONFIG_EXISTS",
      "Existing configuration preserved",
    );
    const dir = dirname(path);
    mkdirSync(dir, { recursive: true });
    const c: any = {
      environment: "development",
      game_services_mode:"remote",
      merchant_database: resolve(dir, "merchants.sqlite3"),
      game_database: resolve(dir, "gtt.sqlite3"),
      game_origin: "http://127.0.0.1:8113",
      gateway_origin: "http://127.0.0.1:8110",
      internal_secret: hex(32),
      client_root: existsSync(resolve(ROOT, "resources/clients/buffalo-win"))
        ? resolve(ROOT, "resources/clients/buffalo-win")
        : existsSync(resolve(ROOT, "clients/buffalo-win"))
        ? resolve(ROOT, "clients/buffalo-win")
        : resolve(ROOT, "../clients/buffalo-win"),
      ports: { gateway: 8110, admin: 8112, buffalo: 8113 },
    };
    if(platformEnv.GTT_PLATFORM_ENV_FILE||platformEnv.GTT_INTERNAL_SECRET!==undefined) {
      check(typeof platformEnv.GTT_INTERNAL_SECRET==='string'&&platformEnv.GTT_INTERNAL_SECRET.length>=32,'CONFIG_INVALID','Set GTT_INTERNAL_SECRET in the platform environment');
      delete c.internal_secret;
      if(platformEnv.GTT_PLATFORM_ENV_FILE)c.env_file=platformEnv.GTT_PLATFORM_ENV_FILE;
    }
    if(platformEnv.GTT_PG_CONFIG)c.postgres_config=platformEnv.GTT_PG_CONFIG;
    const control = new Control(
      c.merchant_database,
      resolve(ROOT, "config/control.sql"),
    );
    check(!control.users().length, "ADMIN_EXISTS");
    const account = control.createUser("system", "admin", "admin");
    writeFileSync(
      resolve(dir, "admin-bootstrap.json"),
      JSON.stringify(
        {
          username: account.user.username,
          password: account.temporary_password,
          url: "http://127.0.0.1:8112/",
        },
        null,
        2,
      ),
      { flag: "wx", mode: 0o600 },
    );
    writeFileSync(path, JSON.stringify(c, null, 2), {
      flag: "wx",
      mode: 0o600,
    });
    control.close();
    console.log("Initialized Node configuration:", path);
    console.log(
      "Administrator credentials file:",
      resolve(dir, "admin-bootstrap.json"),
    );
    return;
  }
  check(
    [
      "gateway",
      "games",
      "admin",
      "buffalo",
      "rtp-worker",
      "platform",
      "sandbox-init",
      "admin-init",
      "launch",
      "transactions",
      "retry",
    ].includes(action),
    "ACTION_INVALID",
    "Use init, buffalo, gateway, admin, rtp-worker",
  );
  const c = readPlatformConfig(path,envFile);
  if(c.env_file)process.env.GTT_PLATFORM_ENV_FILE=c.env_file;
  if(c.postgres_config)process.env.GTT_PG_CONFIG=resolve(c.postgres_config);
  if(action === "games") {
    const {runLocalGames}=await import("../shared/services/local-game-services.js");
    await runLocalGames(c);
    return;
  }
  if (["admin-init", "launch", "transactions", "retry"].includes(action)) {
    const { Control } = await import("../shared/control.js");
    const control = new Control(
      c.merchant_database,
      resolve(ROOT, "config/control.sql"),
    );
    try {
      if (action === "admin-init") {
        check(!control.users().length, "ADMIN_EXISTS");
        const target = resolve(dirname(path), "admin-bootstrap.json");
        check(!existsSync(target), "BOOTSTRAP_EXISTS");
        const result = control.createUser(
          "system",
          arg("--username", "admin"),
          "admin",
        );
        writeFileSync(
          target,
          JSON.stringify(
            {
              username: result.user.username,
              password: result.temporary_password,
              url: `http://127.0.0.1:${c.ports?.admin ?? 8112}/`,
            },
            null,
            2,
          ),
          { flag: "wx", mode: 0o600 },
        );
        console.log("Administrator credentials file:", target);
        return;
      }
      check(c.environment !== "production", "SANDBOX_FORBIDDEN");
      const merchant = control.merchant(c.sandbox_merchant, true);
      check(merchant, "SANDBOX_CONFIG_REQUIRED");
      const endpoint =
        action === "launch"
          ? "/gtt/v1/games/launch"
          : action === "transactions"
            ? "/gtt/v1/transactions/list"
            : "/gtt/v1/transactions/retry";
      const payload =
        action === "launch"
          ? {
              player_id: c.sandbox_player,
              game_id: Number(arg("--game-id", "1")),
              language: arg("--language", "en"),
              ...(c.sandbox_external_username
                ? { external_username: c.sandbox_external_username }
                : {}),
            }
          : action === "transactions"
            ? { limit: 100 }
            : { operation_id: arg("--operation-id", "") };
      const raw = encode(payload),
        response = await fetchBounded(
          c.gateway_origin + endpoint,
          {
            method: "POST",
            headers: signedHeaders(
              merchant.id,
              merchant.merchant_secret,
              endpoint,
              raw,
            ),
            body: raw,
            timeout: 10000,
          },
          1048576,
        ),
        result = object(response.body);
      check(
        response.status < 300 && !result.error,
        result.error?.code ?? "GATEWAY_UNAVAILABLE",
      );
      console.log(
        action === "launch"
          ? new URL(result.data.launch_url, c.gateway_origin).href
          : JSON.stringify(result.data),
      );
      return;
    } finally {
      control.close();
    }
  }
  check(
    typeof c.internal_secret === "string" && c.internal_secret.length >= 32,
    "CONFIG_INVALID",
  );
  if (c.environment === "production") {
    check(
      !c.merchants && !Object.keys(c).some((k) => k.startsWith("sandbox_")),
      "CONFIG_INVALID",
    );
    for (const field of ["merchant_database", "game_database", "client_root"])
      check(
        typeof c[field] === "string" && resolve(c[field]) === c[field],
        "CONFIG_INVALID",
      );
  }
  if (action === "platform" || action === "sandbox-init") {
    check(c.environment !== "production", "SANDBOX_FORBIDDEN");
    const { Control } = await import("../shared/control.js");
    const control = new Control(
      c.merchant_database,
      resolve(ROOT, "config/control.sql"),
    );
    if (action === "sandbox-init") {
      check(
        !c.sandbox_merchant,
        "SANDBOX_EXISTS",
        "Existing simulator settings preserved",
      );
      check(
        !existsSync(resolve(dirname(path), "merchant-demo-bootstrap.json")),
        "BOOTSTRAP_EXISTS",
      );
      const port = c.ports?.platform ?? 8111;
      const created = control.saveMerchant(
        "system",
        {
          name: "Node Demo Merchant",
          enabled: true,
          wallet_url: `http://127.0.0.1:${port}`,
          games: Array.from({ length: 19 }, (_, i) => i + 1),
          minor_unit: 10000,
          pre_payout: {
            enabled: true,
            url: `http://127.0.0.1:${port}/api/v1/callbacks/gtt/preBetDecision`,
          },
        },
        true,
      );
      Object.assign(c, {
        sandbox_merchant: created.merchant.id,
        sandbox_player: "demo-player",
        sandbox_external_username: "demo-platform-player",
        sandbox_balance_minor: 20000000,
        platform_database: resolve(dirname(path), "platform.sqlite3"),
      });
      c.ports = { ...c.ports, platform: port };
      writeFileSync(
        resolve(dirname(path), "merchant-demo-bootstrap.json"),
        JSON.stringify(created, null, 2),
        { flag: "wx", mode: 0o600 },
      );
      const persisted=JSON.parse(readFileSync(path,'utf8'));
      for(const key of ['sandbox_merchant','sandbox_player','sandbox_external_username','sandbox_balance_minor','platform_database'])persisted[key]=c[key];
      if(!c.env_file)persisted.ports={...persisted.ports,platform:port};
      writeFileSync(path, JSON.stringify(persisted, null, 2), { mode: 0o600 });
      control.close();
      console.log("Initialized Node simulator configuration.");
      return;
    }
    const { platformServer } = await import("../shared/services/platform.js");
    const app = platformServer(c, control);
    accessLog(
      app.server,
      resolve(
        c.log_directories?.platform ??
          c.log_directory ??
          resolve(dirname(path), "logs/platform"),
        "service.log",
      ),
    );
    const host=c.hosts?.platform??'127.0.0.1';
    const port = await listen(app.server, c.ports?.platform ?? 8111,host);
    console.log("Platform Node service listening on "+host+":" + port);
    app.server.once("close", () => control.close());
    process.on("SIGTERM", () => app.server.close());
    process.on("SIGINT", () => app.server.close());
    return;
  }
  if (action === "buffalo") {
    const { gameServer } = await import("../../games/buffalo-win/backend/native/service.js");
    const gameConfig = JSON.parse(
        readFileSync(
          c.game_config ?? resolve(ROOT, "config/buffalo-win.json"),
          "utf8",
        ),
      ),
      s = gameServer(gameConfig, c.internal_secret);
    const port = await listen(s, c.ports?.buffalo ?? 8113);
    console.log("Buffalo Node service listening on 127.0.0.1:" + port);
    process.on("SIGTERM", () => s.close());
    process.on("SIGINT", () => s.close());
    return;
  }
  const { control, provider } = await components(c);
  if (action === "rtp-worker") {
    const { runWorker } = await import("../../games/buffalo-win/backend/native/worker.js");
    await runWorker(provider, args.includes("--once"));
    provider.close();
    control.close();
    return;
  }
  const s =
    action === "gateway"
      ? (await import("../../gateway/src/http.js")).gatewayServer(provider, c, c.client_root)
      : (await import("../../admin/backend/admin.js")).adminServer(
          provider,
          c,
          resolve(ROOT, "frontend/admin"),
          resolve(ROOT, "config"),
        );
  accessLog(
    s,
    resolve(
      c.log_directories?.[action] ??
        c.log_directory ??
        resolve(dirname(path), "logs", action),
      "service.log",
    ),
  );
  const port = await listen(
    s,
    c.ports?.[action] ?? (action === "gateway" ? 8110 : 8112),
    c.hosts?.[action]??'127.0.0.1',
  );
  console.log(action + " Node service listening on "+(c.hosts?.[action]??'127.0.0.1')+":" + port);
  let closing = false;
  const stop = () => {
    if (closing) return;
    closing = true;
    s.close(() => {
      provider.close();
      control.close();
    });
  };
  process.on("SIGTERM", stop);
  process.on("SIGINT", stop);
}
if (
  process.argv[1] &&
  resolve(process.argv[1]) === fileURLToPath(import.meta.url)
)
  main().catch((e) => {
    console.error(e.code ?? e.name, e.message);
    process.exitCode = 1;
  });

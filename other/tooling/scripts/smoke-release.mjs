import { mkdtempSync, readFileSync, writeFileSync, rmSync, existsSync } from "node:fs";
import { resolve, join } from "node:path";
import { tmpdir } from "node:os";
import { execFileSync, spawn } from "node:child_process";
import { createHash } from "node:crypto";
import assert from "node:assert/strict";
import {artifactPath,extractArchive} from './archive.mjs';

const release = resolve(process.argv[2] ?? "");
const record = JSON.parse(readFileSync(join(release, "release.json"), "utf8"));
const reportOption=process.argv.indexOf('--verification-name');
const reportName=reportOption>=0?process.argv[reportOption+1]:'verification.json';
if(!/^[A-Za-z0-9][A-Za-z0-9._-]*\.json$/.test(reportName??''))throw Error('Invalid verification report filename');
if(existsSync(join(release,reportName)))throw Error('Verification record exists; supply --verification-name with a new JSON filename');
const archiveOption=process.argv.indexOf('--archives');
const archiveOverride=archiveOption>=0?resolve(process.argv[archiveOption+1]):undefined;
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
    if(record.format>=2) {
      const expected=artifact.name==='gateway'?'zip':'tar.gz';
      assert.equal(artifact.format,expected);
      assert.equal(artifact.file,`${artifact.name}-${record.build_id}.${expected}`);
    }
    const archive = artifactPath(release,record,artifact,archiveOverride);
    assert.equal(sha(readFileSync(archive)), artifact.sha256);
    extractArchive(archive,dir);
    const manifest = JSON.parse(
      readFileSync(join(dir, artifact.name, "release-manifest.json"), "utf8"),
    );
    for (const file of manifest.files) {
      const bytes = readFileSync(join(dir, artifact.name, file.path));
      assert.equal(bytes.length, file.size);
      assert.equal(sha(bytes), file.sha256);
      assert.ok(
        !/(?:^|\/)(?:tests|runtime)(?:\/|$)|\.(?:py|sqlite3|sqlite|db)$/.test(
          file.path,
        ),
        file.path,
      );
      if(file.path.startsWith('node_modules/')) {
        assert.ok(Object.keys(record.runtime_dependencies?.packages??{}).some(name=>file.path.startsWith('node_modules/'+name+'/')), 'Undeclared runtime dependency: '+file.path);
        assert.ok(!/node_modules\/(?:typescript|@types)\//.test(file.path));
      }
    }
  }
  execFileSync(
    process.execPath,
    ["dist/cli.js", "init", "--config", configPath],
    { cwd: join(dir, "gateway"), windowsHide: true, stdio: "pipe" },
  );
  const config = JSON.parse(readFileSync(configPath, "utf8"));
  config.ports = { gateway: 0, admin: 0, buffalo: 0 };
  if(record.topology?.admin) {
    for(const path of ['frontend','clients','dist/gateway/admin.js','dist/gateway/catalog-export.js','dist/services/platform.js'])assert.equal(existsSync(join(dir,'gateway',path)),false,'Unexpected gateway payload: '+path);
    assert(existsSync(join(dir,'gateway','resources/clients/buffalo-win/fixtures/auth-metadata.json')));
    // Existing installations may still point at the former package-local path.
    config.client_root=join(dir,'gateway','clients/buffalo-win');
  }
  writeFileSync(configPath, JSON.stringify(config));
  const game = await start("buffalo-win", "buffalo");
  config.game_origin = `http://127.0.0.1:${game.port}`;
  writeFileSync(configPath, JSON.stringify(config));
  const gateway = await start("gateway", "gateway");
  const admin = await start(record.topology?.admin??"gateway", "admin");
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
  const session=(await login.json()).data;
  assert.ok(session.csrf_token);
  const adminHeaders={"content-type":"application/json",cookie:login.headers.get("set-cookie").split(";")[0],"x-gtt-csrf":session.csrf_token};
  const adminPost=async(action,q)=>{
    const response=await request(admin.port,"/api/admin/"+action,{method:"POST",headers:adminHeaders,body:JSON.stringify(q)});
    const value=await response.json();assert.equal(response.status,200,JSON.stringify(value));return value.data;
  };
  const keyfile=join(dir,"runtime/game-service.key");writeFileSync(keyfile,config.internal_secret);
  assert.equal((await adminPost("frontends/list",{})).games.length,19);
  assert.deepEqual((await adminPost("frontends/candidates",{})).builds,[]);
  const independentGames=[];
  for(const name of record.topology?.games??[]) {
    const spec=JSON.parse(readFileSync(join(dir,name,"GAME.json"),"utf8"));
    const instance=await start(name,"game",["--game-id",spec.code,"--game-config","config/game.json","--secret-file",keyfile,"--port","0"]);
    const registered=await adminPost("services/register",{code:spec.code,origin:`http://127.0.0.1:${instance.port}`,secret:config.internal_secret});
    assert.equal(registered.release,spec.release);
    await adminPost("services/activate",{id:registered.id,revision:0});
    const invoke=async(action,payload)=>{
      const response=await request(instance.port,"/v1/"+action,{method:"POST",headers:{"content-type":"application/json",authorization:"Bearer "+config.internal_secret},body:JSON.stringify(payload)});
      const value=await response.json();assert.equal(response.status,200,JSON.stringify(value));return value.data;
    };
    const initial=await invoke("initial",{seed:"release-smoke"});
    const bet=await invoke("normalize",{bet:spec.descriptor.sample_bet});
    const step={state:initial,bet,seed:"release-smoke",operation_id:"4096"};
    assert.deepEqual(await invoke("step",step),await invoke("step",step));
    const health=await (await request(gateway.port,"/health")).json();
    assert.equal(health.games.find(g=>g.code===spec.code).engine_version,spec.descriptor.version);
    independentGames.push(spec.code);
  }
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
    const platform = await start(record.topology?.mock_platform??"all-services", "platform");
    assert.equal((await request(platform.port, "/")).status, 200);
    assert.equal((await request(platform.port, "/sandbox/status")).status, 200);
  }
  writeFileSync(
    join(release, reportName),
    JSON.stringify(
      {
        build_id: record.build_id,
        verified_at: new Date().toISOString(),
        node: process.version,
        migrated_services: allChecks,
        independent_game_services:independentGames,
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
          ...(independentGames.length?["19-game-archives-independent-processes","admin-game-service-registration-and-switch","remote-deterministic-step"]:[]),
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

// Bridge an offline calibration batch into the local control plane. It never
// launches a game, calls a merchant wallet, or changes an existing round.
import { readFileSync, existsSync } from "node:fs";
import { resolve, join } from "node:path";
import { setTimeout as delay } from "node:timers/promises";
import { components } from "../dist/cli.js";
import { hex, now, encode } from "../dist/shared/core.js";
const args = process.argv.slice(2),
  opt = (key) => args[args.indexOf(key) + 1];
for (const key of ["--config", "--directory", "--games"])
  if (!args.includes(key)) throw Error("Missing " + key);
const config = JSON.parse(readFileSync(resolve(opt("--config")), "utf8"));
if (
  config.environment === "production" ||
  !["127.0.0.1", "localhost", "[::1]"].includes(
    new URL(config.game_origin).hostname,
  )
)
  throw Error("Local calibration import only");
const folder = resolve(opt("--directory")),
  ids = opt("--games").split(",").map(Number),
  target = Number(args.includes("--target-bp") ? opt("--target-bp") : 9600),
  resume = args.includes("--resume-offline");
if (!Number.isInteger(target) || target < 8000 || target > 9900)
  throw Error("Invalid target RTP");
if (ids.some((id) => !Number.isInteger(id) || id < 2 || id > 19))
  throw Error("Invalid game IDs");
const { provider: p, control } = await components(config),
  lease = "offline-" + hex(),
  jobs = new Map();
try {
  p.tx(() => {
    for (const gid of ids) {
      let job = p.get(
        "SELECT * FROM rtp_jobs WHERE game_id=? AND target_bp=? AND status IN ('queued','running')",
        gid,
        target,
      );
      if (
        job?.status === "running" &&
        !(resume && job.lease?.startsWith("offline-"))
      )
        throw Error("Game already has an active calibration: " + gid);
      const id = job?.id ?? hex();
      if (job?.status === "running") {
        p.run(
          "UPDATE rtp_jobs SET status='running',lease=?,updated_at=? WHERE id=?",
          lease,
          now(),
          id,
        );
      } else if (!job)
        p.run(
          "INSERT INTO rtp_jobs VALUES(?,?,?,?,?,?,?,?,?,?,?)",
          id,
          target,
          "queued",
          "system",
          "{}",
          null,
          null,
          null,
          now(),
          now(),
          gid,
        );
      jobs.set(gid, id);
      p.rtp.event("system", "rtp.calibration.offline", "", {
        game_id: gid,
        job_id: id,
        target_bp: target,
      });
    }
  });
  while (jobs.size) {
    let progress;
    try {
      progress = JSON.parse(
        readFileSync(join(folder, "progress.json"), "utf8"),
      );
    } catch {}
    if (
      progress &&
      (progress.target_bp !== target ||
        Date.now() - Date.parse(progress.updated_at) > 120000)
    )
      throw Error(
        "Batch target mismatch or progress stale; worker leases will expire",
      );
    for (const [gid, id] of jobs) {
      const path = join(folder, `game-${gid}.json`),
        item = progress?.games?.[gid];
      // Pending offline games remain ordinary queued jobs until the batch
      // actually starts them. Never take a running job from the normal worker.
      if (!item && !existsSync(path)) continue;
      const owned = p.tx(() => {
        const job = p.get("SELECT * FROM rtp_jobs WHERE id=?", id);
        if (job?.status === "queued") {
          p.run(
            "UPDATE rtp_jobs SET status='running',lease=?,updated_at=? WHERE id=?",
            lease,
            now(),
            id,
          );
          return true;
        }
        return job?.status === "running" && job.lease === lease;
      });
      if (!owned) {
        console.log(
          JSON.stringify({ game_id: gid, status: "handled_by_worker" }),
        );
        jobs.delete(gid);
        continue;
      }
      p.run(
        "UPDATE rtp_jobs SET updated_at=?,progress_json=? WHERE id=? AND lease=?",
        now(),
        encode(item ?? {}),
        id,
        lease,
      );
      if (existsSync(path)) {
        let report;
        try {
          report = JSON.parse(readFileSync(path, "utf8"));
        } catch {
          continue;
        }
        try {
          if (report.game_id !== gid || report.target_bp !== target)
            throw Error("Mismatched calibration report");
          const model = p.rtp.importModel(report);
          p.rtp.publish("system", {
            model_id: model,
            reason: "Independent complete-round calibration passed",
          });
          p.run(
            "UPDATE rtp_jobs SET status='ready',result_id=?,updated_at=? WHERE id=? AND lease=?",
            model,
            now(),
            id,
            lease,
          );
          console.log(
            JSON.stringify({ game_id: gid, status: "ready", model_id: model }),
          );
          jobs.delete(gid);
        } catch (e) {
          p.run(
            "UPDATE rtp_jobs SET status='failed',error=?,updated_at=? WHERE id=? AND lease=?",
            String(e).slice(0, 500),
            now(),
            id,
            lease,
          );
          console.log(
            JSON.stringify({
              game_id: gid,
              status: "failed",
              error: String(e),
            }),
          );
          jobs.delete(gid);
          process.exitCode = 1;
        }
      } else if (item?.status === "failed") {
        p.run(
          "UPDATE rtp_jobs SET status='failed',error=?,updated_at=? WHERE id=? AND lease=?",
          String(item.error).slice(0, 500),
          now(),
          id,
          lease,
        );
        jobs.delete(gid);
        process.exitCode = 1;
      }
    }
    if (jobs.size) await delay(3000);
  }
} finally {
  p.close();
  control.close();
}

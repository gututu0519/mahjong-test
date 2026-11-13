import { Worker } from "node:worker_threads";
import { setTimeout as delay } from "node:timers/promises";
import { now, hex, encode, check } from "../../../../other/shared/core.js";
import type { Provider } from "../../../../gateway/src/provider.js";
export async function runWorker(p: Provider, once = false) {
  let stop = false;
  const stopFn = () => {
    stop = true;
  };
  process.on("SIGTERM", stopFn);
  process.on("SIGINT", stopFn);
  do {
    const lease = hex(),
      wid = String(process.pid),
      job = p.tx(() => {
        p.run(
          "INSERT INTO rtp_workers VALUES(?,?,?) ON CONFLICT(id) DO UPDATE SET updated_at=excluded.updated_at,processes=excluded.processes",
          wid,
          now(),
          1,
        );
        p.run(
          "UPDATE rtp_jobs SET status='queued',lease=NULL WHERE status='running' AND updated_at<?",
          now() - 600,
        );
        const j = p.get(
          "SELECT * FROM rtp_jobs WHERE status='queued' ORDER BY created_at LIMIT 1",
        );
        if (j)
          p.run(
            "UPDATE rtp_jobs SET status='running',lease=?,updated_at=? WHERE id=?",
            lease,
            now(),
            j.id,
          );
        return j;
      });
    if (job) {
      const worker = new Worker(
        new URL(
          job.game_id === 1 ? "./calibration.js" : "../round-model.js",
          import.meta.url,
        ),
        {
          workerData: {
            config: p.description.config,
            target: job.target_bp,
            roundModel: job.game_id !== 1,
            gameId: job.game_id,
          },
        },
      );
      let heartbeat: any;
      try {
        const report: any = await new Promise((ok, fail) => {
          heartbeat = setInterval(() => {
            try {
              check(!stop, "WORKER_STOPPED");
              const changed = p.run(
                "UPDATE rtp_jobs SET updated_at=? WHERE id=? AND lease=?",
                now(),
                job.id,
                lease,
              ).changes;
              check(changed, "WORKER_LEASE_LOST");
              p.run(
                "UPDATE rtp_workers SET updated_at=? WHERE id=?",
                now(),
                wid,
              );
            } catch (e) {
              fail(e);
            }
          }, 10000);
          worker.on("message", (m) => {
            try {
              if (m.error) throw new Error(m.error);
              if (m.result) ok(m.result);
              else if (m.progress) {
                const changed = p.run(
                  "UPDATE rtp_jobs SET progress_json=?,updated_at=? WHERE id=? AND lease=?",
                  encode(m.progress),
                  now(),
                  job.id,
                  lease,
                ).changes;
                check(changed, "WORKER_LEASE_LOST");
              }
            } catch (e) {
              fail(e);
            }
          });
          worker.once("error", fail);
          worker.once("exit", (code) => {
            if (code) fail(new Error("Calibration worker exited"));
          });
        });
        check(
          p.get("SELECT 1 FROM rtp_jobs WHERE id=? AND lease=?", job.id, lease),
          "WORKER_LEASE_LOST",
        );
        const id = p.rtp.importModel(report, job.game_id !== 1);
        p.tx(() => {
          check(
            p.run(
              "UPDATE rtp_jobs SET status='ready',result_id=?,updated_at=? WHERE id=? AND lease=?",
              id,
              now(),
              job.id,
              lease,
            ).changes,
            "WORKER_LEASE_LOST",
          );
          p.rtp.event("system", "rtp.calibration.ready", "", {
            model_id: id,
            job_id: job.id,
          });
        });
      } catch (e) {
        p.run(
          "UPDATE rtp_jobs SET status='failed',error=?,updated_at=? WHERE id=? AND lease=?",
          String(e).slice(0, 500),
          now(),
          job.id,
          lease,
        );
      } finally {
        clearInterval(heartbeat);
        await worker.terminate();
      }
    }
    if (!once && !job && !stop) await delay(5000);
  } while (!once && !stop);
  process.removeListener("SIGTERM", stopFn);
  process.removeListener("SIGINT", stopFn);
}

import { Worker } from "node:worker_threads";
import { mkdirSync, writeFileSync, readFileSync, existsSync } from "node:fs";
import { resolve, join } from "node:path";
const args = process.argv.slice(2),
  option = (key, fallback) =>
    args.includes(key) ? args[args.indexOf(key) + 1] : fallback;
const target = Number(option("--target-bp", "9600")),
  concurrency = Number(option("--parallel", "3"));
const ids = option(
  "--games",
  Array.from({ length: 18 }, (_, i) => i + 2).join(","),
)
  .split(",")
  .map(Number);
if (
  !Number.isInteger(target) ||
  target < 8000 ||
  target > 9900 ||
  !Number.isInteger(concurrency) ||
  concurrency < 1 ||
  concurrency > 8 ||
  ids.some((id) => !Number.isInteger(id) || id < 2 || id > 19)
)
  throw Error("Invalid calibration arguments");
const folder = resolve(
  option("--output", `diagnostics/rtp-calibration/${target}`),
);
mkdirSync(folder, { recursive: true });
const status = {},
  workers = new Set();
const save = () =>
  writeFileSync(
    join(folder, "progress.json"),
    JSON.stringify(
      {
        target_bp: target,
        updated_at: new Date().toISOString(),
        games: status,
      },
      null,
      2,
    ) + "\n",
  );
const pending = ids.filter((id) => {
  const path = join(folder, `game-${id}.json`);
  if (existsSync(path)) {
    const report = JSON.parse(readFileSync(path));
    if (
      report.game_id === id &&
      report.target_bp === target &&
      report.format === 2
    ) {
      status[id] = { status: "ready", seconds: report.seconds };
      return false;
    }
  }
  return true;
});
const stop = () => {
  for (const worker of workers) worker.terminate();
  save();
  process.exitCode = 1;
};
process.on("SIGINT", stop);
process.on("SIGTERM", stop);
async function run() {
  while (pending.length) {
    const id = pending.shift();
    status[id] = { status: "running", started_at: new Date().toISOString() };
    save();
    await new Promise((done) => {
      const worker = new Worker(
        new URL("../dist/games/round-model.js", import.meta.url),
        { workerData: { roundModel: true, gameId: id, target } },
      );
      workers.add(worker);
      let ended = false,
        last = 0;
      const finish = (error) => {
        if (ended) return;
        ended = true;
        if (error) {
          status[id] = {
            ...status[id],
            status: "failed",
            error: String(error),
          };
          process.exitCode = 1;
        }
        save();
        workers.delete(worker);
        worker.terminate();
        done();
      };
      worker.on("message", (m) => {
        if (m.progress) {
          status[id] = { ...status[id], ...m.progress };
          if (Date.now() - last > 3000) {
            save();
            last = Date.now();
          }
        } else if (m.result) {
          writeFileSync(
            join(folder, `game-${id}.json`),
            JSON.stringify(m.result, null, 2) + "\n",
          );
          status[id] = {
            status: "ready",
            seconds: m.result.seconds,
            modes: Object.keys(m.result.modes).length,
          };
          finish();
        } else if (m.error) finish(m.error);
      });
      worker.on("error", finish);
      worker.on("exit", (code) => {
        if (!ended) finish("Worker exited " + code);
      });
    });
  }
}
await Promise.all(Array.from({ length: concurrency }, run));
save();
console.log(JSON.stringify(status));

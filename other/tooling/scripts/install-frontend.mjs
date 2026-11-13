import { existsSync, mkdirSync, cpSync, readFileSync } from "node:fs";
import { resolve, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import { verifyFrontendBundle } from "../dist/shared/frontend-manifest.js";
const repo = resolve(dirname(fileURLToPath(import.meta.url)), "../.."),
  args = process.argv.slice(2);
if (!args[0]) throw Error("Supply the generated frontend bundle directory");
const source = resolve(args[0]),
  m = verifyFrontendBundle(source);
const root = resolve(
  args.includes("--destination")
    ? args[args.indexOf("--destination") + 1]
    : resolve(repo, "services/gtt-gateway/data/frontend-releases"),
);
mkdirSync(root, { recursive: true });
const target = resolve(root, m.release);
if (existsSync(target)) {
  if (
    readFileSync(resolve(target, "manifest.json"), "utf8") !==
    readFileSync(resolve(source, "manifest.json"), "utf8")
  )
    throw Error("Existing immutable frontend version differs");
  verifyFrontendBundle(target);
} else
  cpSync(source, target, { recursive: true, errorOnExist: true, force: false });
console.log(
  JSON.stringify({ release: m.release, game: m.game, installed: target }),
);

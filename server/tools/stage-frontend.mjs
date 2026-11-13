import { execFileSync } from "node:child_process";
import { resolve, dirname } from "node:path";
import { fileURLToPath } from "node:url";
const root = resolve(dirname(fileURLToPath(import.meta.url)), ".."),
  args = process.argv.slice(2);
const built = JSON.parse(
  execFileSync(
    process.execPath,
    [resolve(root, "tools/build-frontend.mjs"), ...args],
    { encoding: "utf8", windowsHide: true },
  ),
);
const installed = JSON.parse(
  execFileSync(
    process.execPath,
    [resolve(root, "tools/install-frontend.mjs"), built.bundle],
    { encoding: "utf8", windowsHide: true },
  ),
);
console.log(JSON.stringify({ ...built, ...installed, activated: false }));

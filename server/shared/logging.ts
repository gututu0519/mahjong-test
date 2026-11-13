import { appendFileSync, mkdirSync } from "node:fs";
import { dirname } from "node:path";
import type { Server } from "node:http";

export function accessLog(server: Server, file: string) {
  mkdirSync(dirname(file), { recursive: true });
  const write = (value: string) =>
    appendFileSync(file, new Date().toISOString() + " " + value + "\n");
  server.once("listening", () => write("Node service started"));
  server.once("close", () => write("Node service stopped"));
  server.on("request", (req, res) => {
    const start = performance.now();
    res.once("finish", () => {
      // Query strings carry launch tokens; headers and request/response bodies may
      // contain credentials. Only the route, status and duration belong here.
      const path = String(req.url ?? "/")
        .split("?")[0]
        .replace(/[\r\n\x00-\x1f]/g, "");
      write(
        `${req.method} ${path} ${res.statusCode} ${Math.round(performance.now() - start)}ms`,
      );
    });
  });
}

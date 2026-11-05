import { createServer, IncomingMessage, ServerResponse } from "node:http";
import { ServiceError, check, object } from "./core.js";
export async function body(req: IncomingMessage, max = 16384) {
  let size = 0;
  const chunks: Buffer[] = [];
  for await (const chunk of req) {
    size += chunk.length;
    check(size <= max, "BODY_TOO_LARGE", "Request too large", 413);
    chunks.push(chunk);
  }
  return Buffer.concat(chunks);
}
export async function jsonBody(req: IncomingMessage, max = 16384) {
  check(
    req.headers["content-type"]?.split(";")[0] === "application/json",
    "CONTENT_TYPE",
  );
  return object(utf8(await body(req, max)));
}
export function utf8(value: Buffer) {
  try {
    return new TextDecoder("utf-8", { fatal: true, ignoreBOM: true }).decode(
      value,
    );
  } catch {
    throw new ServiceError("JSON_INVALID", "Invalid UTF-8", 400);
  }
}
export function send(
  res: ServerResponse,
  status: number,
  value: any,
  headers: any = {},
) {
  const data = Buffer.from(
    typeof value === "string" ? value : JSON.stringify(value),
  );
  res.writeHead(status, {
    "Content-Type": "application/json; charset=utf-8",
    "Content-Length": data.length,
    "Cache-Control": "no-store",
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    ...headers,
  });
  res.end(data);
}
export function success(
  res: ServerResponse,
  data: any,
  status = 200,
  headers = {},
) {
  send(res, status, { data, error: null }, headers);
}
export function server(
  fn: (req: IncomingMessage, res: ServerResponse) => Promise<any>,
) {
  return createServer((req, res) => {
    fn(req, res).catch((e) => {
      if (res.headersSent) {
        res.destroy();
        return;
      }
      const safe =
        e instanceof ServiceError
          ? e
          : new ServiceError(
              "SERVICE_UNAVAILABLE",
              "Request failed; inspect service logs",
              503,
            );
      if (!(e instanceof ServiceError)) console.error(e.stack);
      send(res, safe.status, {
        data: null,
        error: { code: safe.code, message: safe.message },
      });
    });
  });
}
export async function listen(s: ReturnType<typeof server>, port = 0) {
  await new Promise<void>((ok, fail) => {
    s.once("error", fail);
    s.listen(port, "127.0.0.1", ok);
  });
  return (s.address() as any).port as number;
}
export async function fetchBounded(url: string, init: any = {}, max = 65536) {
  const response = await fetch(url, {
    ...init,
    redirect: "manual",
    signal: AbortSignal.timeout(init.timeout ?? 3000),
  });
  const reader = response.body?.getReader();
  let size = 0;
  const chunks: Buffer[] = [];
  if (reader)
    try {
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        size += value.length;
        if (size > max) throw new Error("Response too large");
        chunks.push(Buffer.from(value));
      }
    } finally {
      await reader.cancel();
    }
  return {
    status: response.status,
    headers: response.headers,
    body: Buffer.concat(chunks).toString("utf8"),
  };
}

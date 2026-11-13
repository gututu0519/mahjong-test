import { createHash } from "node:crypto";
import type { IncomingMessage } from "node:http";
import type { Duplex } from "node:stream";
import * as p from "../compat/runtime.js";
import { decode } from "../migrated/py/adapters/jili/wire.js";
import { check } from "../core.js";

// Preserves the shipped clients' authenticated read-only life-service and
// SignalR channels. Unknown platform actions retain their original rejection.
export function websocket(
  kind: string,
  handler: any,
  req: IncomingMessage,
  socket: Duplex,
  head: Buffer,
  authenticate?: (token: string) => Promise<unknown>,
  expectedOrigin?: string,
) {
  const signalr = kind.endsWith("player_events"),
    key = String(req.headers["sec-websocket-key"] ?? "");
  check(
    req.headers.origin === (expectedOrigin ?? "http://" + req.headers.host) &&
      req.headers.upgrade?.toLowerCase() === "websocket" &&
      req.headers["sec-websocket-version"] === "13" &&
      /^[A-Za-z0-9+/]{22}==$/.test(key) &&
      Buffer.from(key, "base64").length === 16,
    "WEBSOCKET_INVALID",
  );
  if (signalr) p.call(p.attr(handler, "token"));
  const accept = createHash("sha1")
    .update(key + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11")
    .digest("base64");
  socket.write(
    "HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Accept: " +
      accept +
      "\r\n\r\n",
  );
  let buffer = Buffer.alloc(0),
    token: string | null = null,
    protocol: string | null = null,
    closed = false;
  const send = (opcode: number, data: Buffer) => {
    const header = Buffer.alloc(data.length < 126 ? 2 : 4);
    header[0] = 128 | opcode;
    if (data.length < 126) header[1] = data.length;
    else {
      header[1] = 126;
      header.writeUInt16BE(data.length, 2);
    }
    socket.write(Buffer.concat([header, data]));
  };
  const end = (code = 1008) => {
    if (closed) return;
    closed = true;
    const data = Buffer.alloc(2);
    data.writeUInt16BE(code);
    send(8, data);
    socket.end();
  };
  const handle = async (opcode: number, data: Buffer) => {
    if (opcode === 8) {
      send(8, data);
      closed = true;
      socket.end();
      return;
    }
    if (opcode === 9) {
      send(10, data);
      return;
    }
    if (opcode === 10) return;
    if (signalr) {
      if (protocol === null) {
        const hello = JSON.parse(data.toString().replace(/\x1e$/, ""));
        check(
          ["json", "messagepack"].includes(hello.protocol) &&
            hello.version === 1,
          "PROTOCOL_INVALID",
        );
        protocol = hello.protocol;
        send(1, Buffer.from("{}\x1e"));
      } else if (protocol === "json") {
        for (const part of data.toString().split("\x1e")) {
          if (!part) continue;
          const msg = JSON.parse(part);
          if (msg.type === 6) send(1, Buffer.from('{"type":6}\x1e'));
          else if (msg.invocationId)
            send(
              1,
              Buffer.from(
                JSON.stringify({
                  type: 3,
                  invocationId: msg.invocationId,
                  ...(msg.target === "RefreshFeatureStates"
                    ? {}
                    : { error: "Unsupported platform operation." }),
                }) + "\x1e",
              ),
            );
        }
      } else if (data.equals(Buffer.from([2, 145, 6]))) send(2, data);
      else throw Error("Unsupported operation");
    } else if (token === null) {
      check(opcode === 2, "PROTOCOL_INVALID");
      const info = p.call(decode, [
        p.dict([["token", p.tuple([4, "string", false])]]),
        data,
        p.dict(),
      ]);
      token = p.item(info, "token");
      if (authenticate) await authenticate(token!);
      else p.call(p.attr(handler.server.service, "wallet"), [token]);
      send(1, Buffer.from('{"error":0}'));
    } else {
      if (authenticate) await authenticate(token!);
      else p.call(p.attr(handler.server.service, "wallet"), [token]);
      check(opcode === 1, "PROTOCOL_INVALID");
      const msg = JSON.parse(data.toString());
      check(msg && msg.cmdType === -1, "PROTOCOL_INVALID");
    }
  };
  const receive = async (chunk: Buffer) => {
    if (closed) return;
    buffer = Buffer.concat([buffer, chunk]);
    try {
      while (buffer.length >= 2) {
        const a = buffer[0],
          b = buffer[1],
          opcode = a & 15;
        check(!(a & 112) && a & 128 && b & 128, "FRAME_INVALID");
        let length = b & 127,
          offset = 2;
        if (length === 126) {
          if (buffer.length < 4) return;
          length = buffer.readUInt16BE(2);
          offset = 4;
        } else if (length === 127) {
          if (buffer.length < 10) return;
          const n = buffer.readBigUInt64BE(2);
          check(n <= 16384n, "FRAME_TOO_LARGE");
          length = Number(n);
          offset = 10;
        }
        check(
          length <= 16384 && (opcode < 8 || length <= 125),
          "FRAME_TOO_LARGE",
        );
        if (buffer.length < offset + 4 + length) return;
        const mask = buffer.subarray(offset, offset + 4),
          data = Buffer.from(buffer.subarray(offset + 4, offset + 4 + length));
        buffer = buffer.subarray(offset + 4 + length);
        for (let i = 0; i < data.length; i++) data[i] ^= mask[i % 4];
        await handle(opcode, data);
        if (closed) return;
      }
    } catch {
      end();
    }
  };
  const timer = setTimeout(() => socket.destroy(), 90000);
  let queue = Promise.resolve();
  socket.on("data", (chunk) => {
    timer.refresh();
    queue = queue.then(() => receive(chunk));
  });
  socket.on("end", () => socket.destroy());
  socket.on("error", () => socket.destroy());
  socket.on("close", () => clearTimeout(timer));
  if (head.length) queue = queue.then(() => receive(head));
}

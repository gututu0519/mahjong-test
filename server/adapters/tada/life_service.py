"""Authenticated local life-service bootstrap for the original TaDa client.

The client sends LifeServiceInitInfo protobuf and waits for {"error":0}.
Only authentication and heartbeat are implemented here; platform operations
are explicitly unsupported rather than acknowledged as successful.
"""
import base64
import hashlib
import json
import struct

from server.adapters.jili.wire import decode
from server.core.contracts import ServiceError


def serve(handler):
    headers = handler.headers
    if headers.get('Origin') != 'http://' + headers.get('Host', ''):
        raise ServiceError('ORIGIN_REJECTED', 'Invalid WebSocket origin.', 403)
    key = headers.get('Sec-WebSocket-Key', '')
    try:
        valid_key = len(base64.b64decode(key, validate=True)) == 16
    except ValueError:
        valid_key = False
    if (not valid_key or headers.get('Upgrade', '').lower() != 'websocket'
            or 'upgrade' not in [v.strip() for v in headers.get('Connection', '').lower().split(',')]
            or headers.get('Sec-WebSocket-Version') != '13'):
        raise ServiceError('INVALID_REQUEST', 'Invalid WebSocket handshake.', 400)
    handler.send_response(101)
    handler.send_header('Upgrade', 'websocket')
    handler.send_header('Connection', 'Upgrade')
    handler.send_header('Sec-WebSocket-Accept', base64.b64encode(hashlib.sha1(
        (key + '258EAFA5-E914-47DA-95CA-C5AB0DC85B11').encode()).digest()).decode())
    handler.end_headers()
    handler.close_connection = True
    handler.connection.settimeout(90)

    def read(count):
        data = handler.rfile.read(count)
        if len(data) != count:
            raise EOFError()
        return data

    def send(opcode, payload):
        header = bytes([0x80 | opcode])
        header += bytes([len(payload)]) if len(payload) < 126 else b'\x7e' + struct.pack('!H', len(payload))
        handler.wfile.write(header + payload)
        handler.wfile.flush()

    token = None
    try:
        while True:
            first, second = read(2)
            opcode, length = first & 15, second & 127
            if first & 0x70 or not first & 0x80 or not second & 0x80:
                raise ValueError('Unsupported frame')
            if length == 126:
                length = struct.unpack('!H', read(2))[0]
            elif length == 127:
                length = struct.unpack('!Q', read(8))[0]
            if length > 16384 or (opcode >= 8 and length > 125):
                raise ValueError('Oversized frame')
            mask, payload = read(4), read(length)
            payload = bytes(value ^ mask[i % 4] for i, value in enumerate(payload))
            if opcode == 8:
                send(8, payload)
                break
            if opcode == 9:
                send(10, payload)
                continue
            if opcode == 10:
                continue
            if token is None:
                if opcode != 2:
                    raise ValueError('Expected initialization')
                # Field 4 is the token in the shipped LifeServiceInitInfo encoder.
                info = decode({'token': (4, 'string', False)}, payload, {})
                token = info.get('token', '')
                handler.server.service.wallet(token)
                send(1, b'{"error":0}')
            else:
                handler.server.service.wallet(token)
                if opcode != 1:
                    raise ValueError('Expected JSON command')
                message = json.loads(payload)
                # Heartbeat is read-only. No mail, activity or rewards are fabricated.
                if not isinstance(message, dict) or message.get('cmdType') != -1:
                    send(8, struct.pack('!H', 1008) + b'Unsupported platform operation')
                    break
    except (ServiceError, ValueError, UnicodeError):
        send(8, struct.pack('!H', 1008))
    except (OSError, EOFError):
        pass

"""Read-only SignalR channel for an account without attached promotions."""
import base64
import hashlib
import json
import struct

from server.core.contracts import ServiceError


def serve(handler):
    handler.token()
    h = handler.headers
    key = h.get('Sec-WebSocket-Key','')
    try:
        valid = len(base64.b64decode(key,validate=True)) == 16
    except ValueError:
        valid = False
    if not valid or h.get('Origin') != 'http://'+h.get('Host','') or h.get('Sec-WebSocket-Version') != '13':
        raise ServiceError('REQUEST_INVALID','Invalid WebSocket request.',400)
    handler.send_response(101)
    handler.send_header('Upgrade','websocket')
    handler.send_header('Connection','Upgrade')
    handler.send_header('Sec-WebSocket-Accept',base64.b64encode(hashlib.sha1((key+'258EAFA5-E914-47DA-95CA-C5AB0DC85B11').encode()).digest()).decode())
    handler.end_headers()
    handler.close_connection = True
    handler.connection.settimeout(90)

    def read(n):
        x=handler.rfile.read(n)
        if len(x)!=n:
            raise EOFError()
        return x

    def send(opcode,data):
        header=bytes([128|opcode])+(bytes([len(data)]) if len(data)<126 else b'\x7e'+struct.pack('!H',len(data)))
        handler.wfile.write(header+data)
        handler.wfile.flush()

    protocol=None
    try:
        while True:
            a,b=read(2)
            opcode,n=a&15,b&127
            if a&112 or not a&128 or not b&128:
                raise ValueError('Unsupported frame')
            if n==126:
                n=struct.unpack('!H',read(2))[0]
            elif n==127:
                n=struct.unpack('!Q',read(8))[0]
            if n>16384 or opcode>=8 and n>125:
                raise ValueError('Oversized frame')
            mask,data=read(4),read(n)
            data=bytes(v^mask[i%4] for i,v in enumerate(data))
            if opcode==8:
                send(8,data)
                return
            if opcode==9:
                send(10,data)
                continue
            if opcode==10:
                continue
            if protocol is None:
                hello=json.loads(data.rstrip(b'\x1e'))
                protocol=hello.get('protocol')
                if protocol not in ('json','messagepack') or hello.get('version')!=1:
                    raise ValueError('Unknown protocol')
                send(1,b'{}\x1e')
            elif protocol=='json':
                for part in data.split(b'\x1e'):
                    if not part:
                        continue
                    message=json.loads(part)
                    if message.get('type')==6:
                        send(1,b'{"type":6}\x1e')
                    elif message.get('invocationId'):
                        reply=dict(type=3,invocationId=message['invocationId'])
                        if message.get('target') != 'RefreshFeatureStates':
                            reply['error']='Unsupported platform operation.'
                        send(1,(json.dumps(reply)+'\x1e').encode())
            elif data==b'\x02\x91\x06':
                send(2,data)
            else:
                raise ValueError('Unsupported platform operation')
    except (OSError,EOFError):
        pass
    except (ValueError,UnicodeError):
        send(8,struct.pack('!H',1008))

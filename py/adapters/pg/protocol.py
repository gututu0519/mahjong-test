"""Mahjong 74 binary transport, verified against the bundled XHRHelper.

The client uses unbounded BigInt xorshift (not truncated xorshift64), then
Fisher-Yates and one inserted seed byte. Responses use the request's seed.
"""
import struct

GAME_SALT = 11  # sum of digits of game index 74


def swaps(length, seed, salt=GAME_SALT):
    a, b = seed + salt, seed + salt + 1
    for i in range(length - 1, 0, -1):
        x, y = a, b
        a = y
        x ^= x << 23
        x ^= x >> 17
        x ^= y
        x ^= y >> 26
        b = x
        yield i, (x + y) % (i + 1)


def unpack(data, seed=None, salt=GAME_SALT):
    if not 2 <= len(data) <= 16384:
        raise ValueError('Invalid binary message length')
    pos = salt % (len(data) - 1)
    if seed is None:
        seed = data[pos]
    raw = bytearray(data[:pos] + data[pos + 1:])
    for i, j in reversed(list(swaps(len(raw), seed, salt))):
        raw[i], raw[j] = raw[j], raw[i]
    return bytes(raw), seed


def pack(raw, seed, salt=GAME_SALT):
    if not raw or not 0 <= seed <= 255:
        raise ValueError('Invalid binary message')
    data = bytearray(raw)
    for i, j in swaps(len(data), seed, salt):
        data[i], data[j] = data[j], data[i]
    data.insert(salt % len(data), seed)
    return bytes(data)


def varint(value):
    value &= (1 << 64) - 1
    out = bytearray()
    while value > 127:
        out.append((value & 127) | 128)
        value >>= 7
    out.append(value)
    return bytes(out)


def read_varint(raw, pos):
    value = 0
    for shift in range(0, 70, 7):
        if pos >= len(raw):
            raise ValueError('Truncated varint')
        byte = raw[pos]
        pos += 1
        if shift == 63 and byte > 1:
            raise ValueError('Oversized varint')
        value |= (byte & 127) << shift
        if byte < 128:
            return value, pos
    raise ValueError('Oversized varint')


def fields(raw):
    """Yield (field number, wire type, payload), preserving unknown fields."""
    pos = 0
    while pos < len(raw):
        tag, pos = read_varint(raw, pos)
        number, wire = tag >> 3, tag & 7
        if not number:
            raise ValueError('Invalid field number')
        if wire == 0:
            value, pos = read_varint(raw, pos)
        else:
            if wire == 2:
                size, pos = read_varint(raw, pos)
            elif wire in (1, 5):
                size = 8 if wire == 1 else 4
            else:
                raise ValueError('Unsupported wire type')
            if pos + size > len(raw):
                raise ValueError('Truncated field')
            value, pos = raw[pos:pos + size], pos + size
        yield number, wire, value


def field(number, wire, value):
    tag = varint(number << 3 | wire)
    if wire == 0:
        return tag + varint(value)
    return tag + (varint(len(value)) if wire == 2 else b'') + value


def patch(raw, replacements):
    """Replace complete encoded fields while preserving all other wire data."""
    out = b''.join(field(n, w, v) for n, w, v in fields(raw) if n not in replacements)
    return out + b''.join(replacements.values())


def text_field(number, value):
    return field(number, 2, value.encode())


def double_field(number, value):
    return field(number, 1, struct.pack('<d', float(value)))


def decode_request(raw):
    types = {1: ('atk', 2), 2: ('btt', 0), 3: ('pf', 0), 5: ('id', 2),
             12: ('wk', 2), 21: ('cs', 1), 22: ('ml', 0),
             24: ('fb', 0), 31: ('ab', 0)}
    result = {}
    for number, wire, value in fields(raw):
        if number not in types:
            raise ValueError('Unsupported Spin parameter')
        name, expected = types[number]
        if wire != expected or name in result:
            raise ValueError('Invalid Spin parameter')
        result[name] = (value.decode('utf-8') if wire == 2 else
                        struct.unpack('<d', value)[0] if wire == 1 else value)
    return result

"""Small schema-driven protobuf codec for the captured Super Ace messages."""
import struct


def varint(value):
    value = int(value) & ((1 << 64) - 1)
    result = bytearray()
    while value > 127:
        result.append((value & 127) | 128)
        value >>= 7
    result.append(value)
    return bytes(result)


def read_varint(data, offset):
    result = 0
    for shift in range(0, 70, 7):
        if offset >= len(data):
            raise ValueError('Truncated varint')
        byte = data[offset]
        offset += 1
        result |= (byte & 127) << shift
        if byte < 128:
            return result, offset
    raise ValueError('Oversized varint')


def fields(data):
    offset = 0
    while offset < len(data):
        tag, offset = read_varint(data, offset)
        number, wire = tag >> 3, tag & 7
        if not number:
            raise ValueError('Invalid protobuf field')
        if wire == 0:
            value, offset = read_varint(data, offset)
        elif wire in (1, 2, 5):
            if wire == 2:
                length, offset = read_varint(data, offset)
            else:
                length = 8 if wire == 1 else 4
            end = offset + length
            if end > len(data):
                raise ValueError('Truncated protobuf value')
            value, offset = data[offset:end], end
        else:
            raise ValueError('Unsupported protobuf wire type')
        yield number, wire, value


def encode(schema, value, schemas):
    result = bytearray()
    for key, (number, kind, repeated) in schema.items():
        if key not in value or value[key] is None:
            continue
        values = value[key] if repeated else [value[key]]
        for item in values:
            if kind in ('int32', 'uint32', 'int64', 'bool'):
                wire, payload = 0, varint(item)
            elif kind in ('double', 'float'):
                wire = 1 if kind == 'double' else 5
                payload = struct.pack('<d' if wire == 1 else '<f', item)
            else:
                wire = 2
                payload = (item.encode('utf-8') if kind == 'string' else bytes(item) if kind == 'bytes'
                           else encode(schemas[kind], item, schemas))
                payload = varint(len(payload)) + payload
            result += varint(number * 8 + wire) + payload
    return bytes(result)


def scalar(kind, value):
    if kind == 'bool':
        return bool(value)
    bits = {'int32': 32, 'int64': 64}.get(kind)
    if bits:
        value &= (1 << bits) - 1
        return value - (1 << bits) if value >= (1 << (bits - 1)) else value
    return value


def decode(schema, data, schemas):
    reverse = {v[0]: (k, v[1], v[2]) for k, v in schema.items()}
    result = {k: [] for k, (_, _, repeated) in schema.items() if repeated}
    for number, wire, value in fields(bytes(data)):
        if number not in reverse:
            continue
        key, kind, repeated = reverse[number]
        if repeated and wire == 2 and kind in ('int32', 'uint32', 'int64', 'bool', 'double', 'float'):
            packed, offset = [], 0
            while offset < len(value):
                if kind in ('double', 'float'):
                    size = 8 if kind == 'double' else 4
                    packed.append(struct.unpack('<d' if size == 8 else '<f', value[offset:offset+size])[0])
                    offset += size
                else:
                    item, offset = read_varint(value, offset)
                    packed.append(scalar(kind, item))
            result[key].extend(packed)
            continue
        if kind in ('int32', 'uint32', 'int64', 'bool'):
            if wire != 0:
                raise ValueError('Incorrect scalar wire type')
            item = scalar(kind, value)
        elif kind in ('double', 'float'):
            if wire != (1 if kind == 'double' else 5):
                raise ValueError('Incorrect floating point wire type')
            item = struct.unpack('<d' if kind == 'double' else '<f', value)[0]
        elif wire != 2:
            raise ValueError('Incorrect message wire type')
        elif kind == 'string':
            item = value.decode('utf-8')
        elif kind == 'bytes':
            item = list(value)
        else:
            item = decode(schemas[kind], value, schemas)
        if repeated:
            result[key].append(item)
        else:
            result[key] = item
    return result

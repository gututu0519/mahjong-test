"""Schema-driven PG protobuf messages, including packed arrays and map entries."""
import struct
from .protocol import fields, field, read_varint, double_field, text_field


def scalar(number, kind, value, types):
    if kind in ('int32', 'int64', 'uint32', 'uint64', 'bool'):
        return field(number, 0, int(value))
    if kind == 'double':
        return double_field(number, value)
    if kind == 'string':
        return text_field(number, value)
    if kind == 'bytes':
        return field(number, 2, value)
    if kind == 'Int32List' and isinstance(value, list):
        value = {'__value': value}
    return field(number, 2, encode(value, types, kind))


def encode(data, types, name='__root__'):
    out = []
    for key, spec in types[name]['fields'].items():
        value = data.get(key)
        if value is None:
            continue
        n, kind = spec['id'], spec['type']
        if 'keyType' in spec:
            for k in sorted(value, key=int):
                entry = scalar(1, spec['keyType'], int(k), types) + scalar(2, kind, value[k], types)
                out.append(field(n, 2, entry))
        elif spec.get('rule') == 'repeated':
            out.extend(scalar(n, kind, item, types) for item in value)
        else:
            out.append(scalar(n, kind, value, types))
    return b''.join(out)


def decode(raw, types, name='__root__'):
    specs = {s['id']: (k, s) for k, s in types[name]['fields'].items()}
    result = {}
    def value(kind, wire, data):
        if kind == 'double':
            return struct.unpack('<d', data)[0]
        if kind == 'string':
            return data.decode('utf-8')
        if kind == 'bytes':
            return data
        if kind in types:
            child = decode(data, types, kind)
            return child.get('__value', []) if kind == 'Int32List' else child
        if kind == 'int32' and data >= 1 << 31:
            return (data & 0xffffffff) - (1 << 32)
        return data
    for n, wire, data in fields(raw):
        if n not in specs:
            continue
        key, spec = specs[n]
        kind = spec['type']
        if 'keyType' in spec:
            entry = {n: (w, v) for n, w, v in fields(data)}
            k = value(spec['keyType'], *entry.get(1, (0, 0)))
            v = value(kind, *entry.get(2, (0, 0)))
            result.setdefault(key, {})[str(k)] = v
        elif spec.get('rule') == 'repeated':
            items = result.setdefault(key, [])
            if wire == 2 and kind in ('int32', 'uint32', 'int64', 'uint64', 'bool'):
                pos = 0
                while pos < len(data):
                    v, pos = read_varint(data, pos)
                    items.append(value(kind, 0, v))
            else:
                items.append(value(kind, wire, data))
        else:
            result[key] = value(kind, wire, data)
    return result

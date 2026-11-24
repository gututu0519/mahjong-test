"""在原始样本位深下重排 Adam7 七遍扫描线，保留调色板和透明度。"""
import struct
import zlib

SIGNATURE = b"\x89PNG\r\n\x1a\n"
ADAM7 = ((0,0,8,8),(4,0,8,8),(0,4,4,8),(2,0,4,4),(0,2,2,4),(1,0,2,2),(0,1,1,2))
CHANNELS = {0:1, 2:3, 3:1, 4:2, 6:4}
DEPTHS = {0:(1,2,4,8,16), 2:(8,16), 3:(1,2,4,8), 4:(8,16), 6:(8,16)}
MAX_RAW = 64 << 20


def chunks(data):
    if not data.startswith(SIGNATURE):
        raise ValueError("缺少 PNG 标记")
    pos = len(SIGNATURE)
    while pos + 12 <= len(data):
        length, kind = struct.unpack_from(">I4s", data, pos)
        end = pos + 12 + length
        if end > len(data) or zlib.crc32(data[pos+4:end-4]) != struct.unpack_from(">I", data, end-4)[0]:
            raise ValueError("PNG 数据损坏")
        yield kind, data[pos+8:end-4]
        pos = end
        if kind == b"IEND" and not length and pos == len(data):
            return
    raise ValueError("PNG 结尾无效")


def chunk(kind, payload):
    return struct.pack(">I", len(payload)) + kind + payload + struct.pack(">I", zlib.crc32(kind + payload))


def unfilter(mode, row, previous, step):
    if not mode:
        return
    if mode not in (1,2,3,4):
        raise ValueError("PNG 行过滤器无效")
    for i, filtered in enumerate(row):
        left = row[i-step] if i >= step else 0
        up = previous[i]
        if mode == 1:
            predictor = left
        elif mode == 2:
            predictor = up
        elif mode == 3:
            predictor = (left + up) // 2
        else:
            corner = previous[i-step] if i >= step else 0
            target = left + up - corner
            a, b, c = abs(target-left), abs(target-up), abs(target-corner)
            predictor = left if a <= b and a <= c else up if b <= c else corner
        row[i] = (filtered + predictor) & 255


def subset(full, small, start, stride, count, bits, scatter):
    if bits >= 8:
        size = bits // 8
        for channel in range(size):
            lane = slice(start*size + channel, None, stride*size)
            if scatter:
                full[lane] = small[channel::size]
            else:
                small[channel::size] = full[lane]
        return
    mask = (1 << bits) - 1
    src, dst = (small, full) if scatter else (full, small)
    for i in range(count):
        outer = (start+i*stride)*bits
        inner = i*bits
        a, b = (inner, outer) if scatter else (outer, inner)
        val = (src[a//8] >> (8-bits-a%8)) & mask
        dst[b//8] |= val << (8-bits-b%8)


def passes(width, height, interlace):
    for x, y, dx, dy in ADAM7 if interlace else ((0,0,1,1),):
        if x < width and y < height:
            yield x, y, dx, dy, (width-x+dx-1)//dx


def decode(compressed, width, height, bits, interlace):
    line_bytes = (width*bits+7)//8
    layout = list(passes(width, height, interlace))
    total = sum((1+(n*bits+7)//8) * len(range(y,height,dy)) for _,y,_,dy,n in layout)
    if total > MAX_RAW or height > 100000 or width > 200000 or width*height > 32_000_000:
        raise ValueError("PNG 像素规模超过转换上限")
    decoder = zlib.decompressobj()
    data = decoder.decompress(compressed, total+1)
    if len(data) != total or not decoder.eof or decoder.unused_data:
        raise ValueError("PNG 解压长度不匹配")
    rows = [bytearray(line_bytes) for _ in range(height)]
    offset = 0
    for x,y,dx,dy,count in layout:
        size = (count*bits+7)//8
        previous = bytearray(size)
        for target in range(y,height,dy):
            row = bytearray(data[offset+1:offset+1+size])
            unfilter(data[offset], row, previous, max(1,bits//8))
            subset(rows[target],row,x,dx,count,bits,True)
            previous = row
            offset += size+1
    return rows


def convert_png(raw):
    blocks = list(chunks(raw))
    if not blocks or blocks[0][0] != b"IHDR" or len(blocks[0][1]) != 13:
        raise ValueError("PNG 文件头无效")
    header = blocks[0][1]
    width,height,depth,color,compression,filtering,interlace = struct.unpack(">IIBBBBB", header)
    if not width or not height or depth not in DEPTHS.get(color,()) or compression or filtering or interlace not in (0,1):
        raise ValueError("PNG 参数不受支持")
    kinds = [k for k,_ in blocks]
    if b"acTL" in kinds or b"IDAT" not in kinds or kinds.count(b"IHDR") != 1 or kinds.count(b"IEND") != 1:
        raise ValueError("PNG 含动画或图像块不完整")
    first = kinds.index(b"IDAT")
    last = first + kinds.count(b"IDAT")
    if any(k != b"IDAT" for k in kinds[first:last]) or (color == 3 and b"PLTE" not in kinds[:first]):
        raise ValueError("PNG 图像块顺序或调色板有误")
    bits = CHANNELS[color]*depth
    try:
        rows = decode(b"".join(data for _,data in blocks[first:last]),width,height,bits,interlace)
    except zlib.error:
        raise ValueError("PNG 图像无法解码") from None
    if interlace:
        return raw
    encoder = zlib.compressobj(8)
    output = bytearray()
    for x,y,dx,dy,count in passes(width,height,1):
        for target in range(y,height,dy):
            row = bytearray((count*bits+7)//8)
            subset(rows[target],row,x,dx,count,bits,False)
            output.extend(encoder.compress(b"\0"+row))
    output.extend(encoder.flush())
    if decode(output,width,height,bits,1) != rows:
        raise ValueError("Adam7 转换后像素不一致")
    updated = [(b"IHDR",header[:-1]+b"\1"),*blocks[1:first],(b"IDAT",bytes(output)),*blocks[last:]]
    return SIGNATURE + b"".join(chunk(k,v) for k,v in updated)

#!/usr/bin/env python3
"""Lay out a supported MKA model and its fixed layer schedule for Tang SDRAM."""

import argparse
from hashlib import sha256
import json
from pathlib import Path
import struct
import zlib

WORDS = struct.Struct("<IIII")
EMBED, NORM, MATRIX, ROTARY, STORE_KV, ATTENTION, ADD, SILU, CLASSIFIER, HALT = range(1, 11)
X, N, Q, K, V, A, O, GATE, UP, SCORES = 0, 128, 256, 384, 448, 512, 640, 768, 1152, 1536
CACHE_BASE = 0x220000
HEAD_OPERATION = 0x100


def nibble_group(data):
    codes = bytearray(16)
    for j in range(32):
        quartet, lane = divmod(j, 4)
        shift = (quartet % 2)*4 + lane
        code = sum(((data[plane*4 + quartet//2] >> shift) & 1) << plane for plane in range(4))
        codes[j//2] |= code << (4*(j % 2))
    return codes


def pack(source):
    header = struct.unpack_from("<32I", source)
    if (source[:8] != b"M61AI01\0" or header[2:4] != (1, len(source)) or
            header[31] != zlib.crc32(source[:124]) or header[29] != zlib.crc32(source[128:])):
        raise ValueError("Invalid MKA package or CRC")
    layers, hidden, hidden_ff, heads, kv_heads, dim, vocab, context, bos, _, epsilon = header[4:15]
    if (hidden, hidden_ff, heads, kv_heads, dim, context) != (128, 384, 4, 2, 32, 1024):
        raise ValueError("Tang pipeline uses 128/384 channels, 4/2 heads of 32 and 1024 positions")
    if not 0 < layers <= 10 or not 0 < vocab < 65536:
        raise ValueError("Model dimensions exceed the reserved SDRAM layout")

    image = bytearray(32)
    offsets = []
    for index in range(layers*11+2):
        rows, cols, bits, layout, data, scale, size, scale_size = struct.unpack_from("<8I", source, header[15]+index*32)
        if data+size > len(source) or scale+scale_size > len(source):
            raise ValueError("Tensor exceeds the MKA package")
        offsets.append(len(image)//4)
        if bits == 32 and not scale_size and size % 4 == 0:
            image += source[data:data+size]
        elif (bits == 4 and layout in (0, 256) and cols % 32 == 0 and
              size == rows*cols//2 and scale_size == rows*cols//16):
            for group in range(rows*cols//32):
                group_data = source[data+group*16:data+(group+1)*16]
                image += nibble_group(group_data) if layout else group_data
                image += struct.pack("<f", struct.unpack_from("<e", source, scale+group*2)[0])
        else:
            raise ValueError(f"Unsupported tensor {index}, bits={bits}, layout={layout}")

    rotary = len(image)//4
    table_size = context*dim*4
    if header[26]+table_size > len(source):
        raise ValueError("Rotary table exceeds the MKA package")
    image += source[header[26]:header[26]+table_size]
    schedule = len(image)//4

    def op(code, source=0, destination=0, address=0, width=0, rows=0):
        image.extend(WORDS.pack(code, source | destination << 16, address, width | rows << 16))

    op(EMBED, destination=X, address=offsets[0], width=128)
    for layer in range(layers):
        base = 2+layer*11
        cache = CACHE_BASE//4 + layer*context*128
        op(NORM, X, N, offsets[base], 128, 1)
        op(MATRIX, N, Q, offsets[base+1], 128, 128)
        op(MATRIX, N, K, offsets[base+2], 128, 64)
        op(MATRIX, N, V, offsets[base+3], 128, 64)
        op(NORM, Q, Q, offsets[base+4], 32, 4)
        op(NORM, K, K, offsets[base+5], 32, 2)
        op(ROTARY, Q, Q, rotary, 32, 4)
        op(ROTARY, K, K, rotary, 32, 2)
        op(STORE_KV, K, address=cache, width=128)
        op(ATTENTION, Q, A, cache, 32, 4)
        op(MATRIX, A, O, offsets[base+6], 128, 128)
        op(ADD, O, X, width=128)
        op(NORM, X, N, offsets[base+7], 128, 1)
        op(MATRIX, N, GATE, offsets[base+8], 128, 384)
        op(MATRIX, N, UP, offsets[base+9], 128, 384)
        op(SILU, UP, GATE, width=384)
        op(MATRIX, GATE, O, offsets[base+10], 384, 128)
        op(ADD, O, X, width=128)
    op(NORM | HEAD_OPERATION, X, N, offsets[1], 128, 1)
    op(CLASSIFIER | HEAD_OPERATION, N, address=offsets[0], width=128, rows=vocab)
    op(HALT)
    if len(image) > CACHE_BASE:
        raise ValueError("Transposed weights collide with the KV cache")
    struct.pack_into("<8I", image, 0, 0x32474e54, vocab, context, epsilon, schedule,
                     (len(image)//4-schedule)//4, bos, zlib.crc32(source))
    return image, dict(layers=layers, vocab=vocab, context=context, bos=bos,
                       model_sha256=sha256(source).hexdigest(), image_bytes=len(image),
                       image_crc32=f"{zlib.crc32(image):08x}", kv_base=CACHE_BASE,
                       kv_bytes=layers*context*512)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("model", type=Path)
    parser.add_argument("image", type=Path)
    parser.add_argument("--picocalc", action="store_true", help="Wrap the image as /AI/MODEL.TNG for MK61AI")
    args = parser.parse_args()
    source = args.model.read_bytes()
    image, metadata = pack(source)
    args.image.parent.mkdir(parents=True, exist_ok=True)
    if args.picocalc:
        header_crc, = struct.unpack_from("<I", source, 124)
        image.extend(struct.pack("<4sIII", b"MKT1", header_crc, len(source), zlib.crc32(image)))
    args.image.write_bytes(image)
    if not args.picocalc:
        args.image.with_suffix(".json").write_text(json.dumps(metadata, indent=2)+"\n")
    print(json.dumps(metadata, indent=2))


if __name__ == "__main__":
    main()

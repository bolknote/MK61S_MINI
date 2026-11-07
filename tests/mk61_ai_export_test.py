#!/usr/bin/env python3
"""Independent package/tied-vocabulary and tokenizer checks; host only."""
import argparse
import ctypes as C
import hashlib
import json
from pathlib import Path
import random
import statistics
import struct
import zlib


def package(path):
    raw = path.read_bytes();h = struct.unpack_from("<32I", raw)
    assert raw[:8] == b"M61AI01\0" and h[3] == len(raw)
    assert h[29] == zlib.crc32(raw[128:]) and h[31] == zlib.crc32(raw[:124])
    tensors = [struct.unpack_from("<8I", raw, h[15] + i * 32) for i in range(2 + 11 * h[4])]
    return raw, h, tensors


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--base", type=Path, required=True)
    p.add_argument("--models", type=Path, required=True)
    p.add_argument("--tokenizer", type=Path, required=True)
    p.add_argument("--library", type=Path, required=True)
    p.add_argument("--cases", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    from tokenizers import Tokenizer
    lib = C.CDLL(str(a.library.resolve()))
    lib.mk_ai_open.argtypes = [C.c_void_p, C.c_uint]
    lib.mk_ai_encode.argtypes = [C.c_char_p, C.c_void_p, C.c_uint, C.POINTER(C.c_uint), C.c_int]
    lib.mk61ai_pack_q4_planes32.argtypes = [C.c_void_p, C.c_void_p]
    base, header, tensors = package(a.base)
    tasks = [json.loads(s)["task"] for s in a.cases.read_text().splitlines() if s]
    rng = random.Random(610613)
    alphabet = list("абвгдеёжзийклмнопрстуфхцчшщъыьэюя ABCxyz0123\n\t.,:!?+-=/<>\'") + ["é", "😀", "漢", "١", "\u00a0", "\u0301"]
    samples = ["", "Привет!", "<write>60611050</write><run/>", "<patch>00:60 01:61</patch><run/>",
               "ё е\u0308 й и\u0306 Á A\u030A", *tasks]
    samples += ["".join(rng.choices(alphabet, k=rng.randrange(1, 120))) for _ in range(300)]
    variants = [("full-lut", a.base, a.tokenizer)]
    variants += [(name, a.models / name / "MODEL.MKA", a.tokenizer if name == "full-nibble" else a.models / name / "MODEL.tokenizer.json")
                 for name in ("full-nibble", "vocab4096-lut", "vocab2048-lut")]
    report = {};base_task_tokens = 0
    for name, path, tokenizer_path in variants:
        raw, h, ts = package(path)
        assert h[4:10] == header[4:10] and h[11:15] == header[11:15]
        assert len(ts) == len(tensors)
        checked_groups = 0
        for i, (original, current) in enumerate(zip(tensors, ts)):
            rows, cols, bits, grid, data, scale, size, scales = current
            assert cols == original[1] and bits == original[2]
            assert rows == (h[10] if i == 0 else original[0])
            assert raw[scale:scale + scales] == base[original[5]:original[5] + scales]
            old = base[original[4]:original[4] + size]
            new = raw[data:data + size]
            if grid == original[3]:
                assert new == old
            else:
                assert bits == 4 and grid == 0 and original[3] == 256
                packed = C.create_string_buffer(new);reordered = C.create_string_buffer(16)
                for at in range(0, size, 16):
                    lib.mk61ai_pack_q4_planes32(C.byref(packed, at), reordered)
                    assert reordered.raw == old[at:at + 16]
                    checked_groups += 1
        # NFC tables, character classes and every precomputed RoPE value stay
        # identical; only the embedding/head and tokenizer tables may shrink.
        for field, count, width in ((20, 21, 24), (22, 23, 12), (24, 25, 12)):
            assert h[count] == header[count]
            assert raw[h[field]:h[field] + h[count] * width] == base[header[field]:header[field] + header[count] * width]
        rope_size = h[11] * h[9] * 4
        assert raw[h[26]:h[26] + rope_size] == base[header[26]:header[26] + rope_size]
        oracle = Tokenizer.from_file(str(tokenizer_path))
        memory = C.create_string_buffer(raw)
        assert lib.mk_ai_open(memory, len(raw)) == 0
        native_cases = 0
        def encode(text, bos=True):
            out = (C.c_ushort * 2048)();n = C.c_uint()
            assert lib.mk_ai_encode(text.encode(), out, 2048, C.byref(n), bos) == 0
            return list(out[:n.value])
        for text in samples:
            for bos in (False, True):
                expected = oracle.encode(text, add_special_tokens=bos).ids
                assert encode(text, bos) == expected, (name, repr(text))
                assert all(token < h[10] for token in expected)
                native_cases += 1
        lengths = [len(encode(task, False)) for task in tasks]
        if name == "full-lut": base_task_tokens = sum(lengths)
        report[name] = dict(bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest(), vocab=h[10],
                            parameters=3017984 - (header[10] - h[10]) * h[5],
                            native_tokenizer_oracle_cases=native_cases, nibble_groups_checked=checked_groups,
                            task_tokens=sum(lengths), task_token_ratio=sum(lengths) / base_task_tokens,
                            mean_task_tokens=statistics.mean(lengths), max_task_tokens=max(lengths))
    a.output.write_text(json.dumps(dict(passed=True, variants=report, scope="Host tokenizer/package identity and token cost; no device speed claim"), indent=2) + "\n")
    print(json.dumps(report))


if __name__ == "__main__": main()

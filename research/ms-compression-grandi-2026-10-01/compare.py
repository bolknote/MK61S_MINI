"""Codecs tailored to the original Grundy byte stream, without rewriting it.

The Python decoders validate the exact original bytes. An optional real-core
runner verifies only the arithmetic reader for the packed input stream. That
reader is not a native Huffman decoder or a complete self-extractor.
"""
from collections import Counter
from heapq import heapify, heappop, heappush
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
SOURCE = HERE / "original.raw"
RAW = SOURCE.read_bytes()
assert len(RAW) == 49 and RAW[26] == 1 and RAW[-2:] == b"\x51\x00"
sys.path.insert(0, str(ROOT / "tools/elite"))
from assembler import Assembler, bcd

# Preserve the many digit commands. Five frequent commands get one nibble;
# F introduces one of five rare commands. E encodes the repeated pair 01 01.
COMMON = (0x11, 0x49, 0x50, 0x51, 0x5E)
RARE = (0x0D, 0x0E, 0x14, 0x30, 0x35)
ONE = {b: b for b in range(9)} | {b: 9+i for i, b in enumerate(COMMON)}


def nibble_encode(data, pairs):
    result = []
    i = 0
    while i < len(data):
        if pairs and data[i:i+2] == b"\x01\x01":
            result.append(14)
            i += 2
            continue
        value = data[i]
        if value in ONE:
            result.append(ONE[value])
        else:
            result.extend((15, RARE.index(value)))
        i += 1
    return result


def nibble_decode(symbols, pairs):
    result = bytearray()
    i = 0
    while i < len(symbols):
        s = symbols[i]
        i += 1
        if s < 9:
            result.append(s)
        elif s < 14:
            result.append(COMMON[s-9])
        elif s == 14 and pairs:
            result.extend(b"\x01\x01")
        else:
            assert s == 15 and i < len(symbols)
            result.append(RARE[symbols[i]])
            i += 1
    return bytes(result)


def huffman_codes(data):
    frequencies = Counter(data)
    lengths = {s: 0 for s in frequencies}
    heap = [(count, i, (s,)) for i, (s, count)
            in enumerate(sorted(frequencies.items()))]
    heapify(heap)
    serial = len(heap)
    while len(heap) > 1:
        a, b = heappop(heap), heappop(heap)
        for s in a[2] + b[2]:
            lengths[s] += 1
        heappush(heap, (a[0]+b[0], serial, a[2]+b[2]))
        serial += 1
    codes = {}
    code = previous = 0
    for s in sorted(frequencies, key=lambda s: (lengths[s], s)):
        length = lengths[s]
        code <<= length - previous
        codes[s] = f"{code:0{length}b}"
        code += 1
        previous = length
    return codes


def huffman_decode(bits, codes):
    inverse = {v: k for k, v in codes.items()}
    word = ""
    result = bytearray()
    for bit in bits:
        word += str(bit)
        if word in inverse:
            result.append(inverse[word])
            word = ""
    assert not word
    return bytes(result)


def pack_stream(symbols, radix, width):
    """First symbol is the least significant field for cheap /radix reads."""
    assert radix**width <= 100000000
    return [sum(s * radix**i for i, s in enumerate(symbols[j:j+width]))
            for j in range(0, len(symbols), width)]


def unpack_stream(words, radix, width, length):
    result = []
    for word in words:
        for _ in range(width):
            result.append(word % radix)
            word //= radix
    return result[:length]


def packed_bytes(symbols, bits):
    stream = "".join(f"{s:0{bits}b}" for s in symbols)
    stream += "0" * (-len(stream) % 8)
    return bytes(int(stream[i:i+8], 2) for i in range(0, len(stream), 8))


def native_reader(radix):
    a = Assembler()
    m = a.module(0, f"least-significant base-{radix} stream field")
    # / leaves the original input in X2. Store the integer quotient directly
    # back in R9, restore the original with '.', and subtract radix*quotient.
    # No other data register is needed; using frac(n/radix) loses low bits.
    m.label("next").ld(9).op("enter").n(radix).op("/", "int").st(9)
    m.raw(0x0A).ld(9).op("*", "-", "stop").jump("next")
    banks, info = a.link()
    return banks[0][:info["banks"]["0"]["used"]]


def read_native(runner, label, symbols, radix, width):
    words = pack_stream(symbols, radix, width)
    code = native_reader(radix)
    decoded = []
    total_steps = 0
    for i, word in enumerate(words):
        folder = HERE / "native" / label / f"word-{i}"
        folder.mkdir(parents=True, exist_ok=True)
        init = bytes(map(int, str(word))) + bytes((0x49, 0x50, 0x1F, 0x51, *bcd(24*112)))
        (folder / "autoexec.m61").write_text(
            f"reinit\nhin 0000 {init.hex()}\nhin {24*112:04d} {code.hex()}\nrun\n")
        count = min(width, len(symbols)-i*width)
        commands = "dump\n" + "run\n" * count
        completed = subprocess.run([str(runner), str(folder)], input=commands,
                                   capture_output=True, text=True, check=True,
                                   timeout=30)
        states = [json.loads(line) for line in completed.stdout.splitlines()]
        assert len(states) == count+1, (label, i, completed.stdout)
        assert states[0]["regs"][9] == word
        remaining = word
        for state in states[1:]:
            assert not state["error"] and not state["running"], state
            remaining, symbol = divmod(remaining, radix)
            assert state["x"] == symbol and state["regs"][9] == remaining, (label, i, state)
            decoded.append(symbol)
            total_steps += state["steps"]
        (folder / "states.json").write_text(json.dumps(states, indent=2) + "\n")
    assert decoded == list(symbols)
    return decoded, dict(reader_bytes=len(code), reader_hex=code.hex(" "),
                         words=len(words), symbols=len(decoded), core_steps=total_steps)


def main(runner=None):
    frequency = Counter(RAW)
    codes = huffman_codes(RAW)
    bits = list(map(int, "".join(codes[b] for b in RAW)))
    assert huffman_decode(bits, codes) == RAW
    nibbles = nibble_encode(RAW, False)
    full_pair_nibbles = nibble_encode(RAW, True)
    assert nibble_decode(nibbles, False) == nibble_decode(full_pair_nibbles, True) == RAW
    # The final BP 00 operand is zero, as is the rest of the 63-byte output
    # window. A zero-filled destination does not require that last field in
    # the stream. Keep an explicit codec contract for this single-byte suffix.
    assert RAW[-1] == 0
    pair_nibbles = nibble_encode(RAW[:-1], True)
    assert nibble_decode(pair_nibbles, True) + b"\0" == RAW
    base100_words = pack_stream(list(RAW), 100, 4)
    assert bytes(unpack_stream(base100_words, 100, 4, len(RAW))) == RAW
    huffman_words = pack_stream(bits, 2, 26)
    nibble_words = pack_stream(pair_nibbles, 16, 6)
    assert unpack_stream(huffman_words, 2, 26, len(bits)) == bits
    assert unpack_stream(nibble_words, 16, 6, len(pair_nibbles)) == pair_nibbles
    (HERE / "original.raw").write_bytes(RAW)
    (HERE / "huffman.bin").write_bytes(packed_bytes(bits, 1))
    (HERE / "nibble-pairs.bin").write_bytes(packed_bytes(pair_nibbles, 4))
    (HERE / "nibble-pairs-full.bin").write_bytes(packed_bytes(full_pair_nibbles, 4))
    # Explicit symbols, ordered by canonical-code length. The six group
    # counts are stored as three bytes, with one four-bit count per length.
    ordered = sorted(codes, key=lambda s: (len(codes[s]), s))
    counts = [sum(len(c) == length for c in codes.values()) for length in range(1, 7)]
    assert all(c < 16 for c in counts)
    huffman_table = bytes(ordered) + packed_bytes(counts, 4)
    (HERE / "huffman-table.bin").write_bytes(huffman_table)
    (HERE / "nibble-map.bin").write_bytes(bytes(COMMON+RARE))
    report = dict(
        source=str(SOURCE), source_sha256=hashlib.sha256(RAW).hexdigest(),
        original_bytes=len(RAW), distinct_bytes=len(frequency),
        huffman=dict(bits=len(bits), packed_bytes=(len(bits)+7)//8,
                     numeric_words=huffman_words, numeric_record_bytes=7*len(huffman_words),
                     explicit_canonical_table_bytes=len(huffman_table),
                     data_plus_table_bytes=(len(bits)+7)//8+len(huffman_table),
                     codebook=[dict(byte=f"{s:02X}", count=frequency[s], code=codes[s])
                               for s in sorted(codes)]),
        nibble=dict(nibbles=len(nibbles), packed_bytes=(len(nibbles)+1)//2),
        nibble_pairs_full=dict(nibbles=len(full_pair_nibbles),
                               packed_bytes=(len(full_pair_nibbles)+1)//2),
        nibble_pairs=dict(nibbles=len(pair_nibbles), packed_bytes=(len(pair_nibbles)+1)//2,
                          numeric_words=nibble_words, numeric_record_bytes=7*len(nibble_words),
                          explicit_non_digit_map_bytes=10,
                          implicit_suffix_hex="00", destination_must_be_zero_filled=True,
                          pair_code="E -> 01 01, implemented by decoder",
                          encoded="".join(f"{s:X}" for s in pair_nibbles)),
        base100=dict(opcode_bytes_per_8_digit_number=4, numeric_words=base100_words,
                     numeric_record_bytes=7*len(base100_words)),
        verification=dict(host_exact_round_trips=True, native_self_extractor=False),
    )
    if runner:
        native_bits, bit_report = read_native(runner, "huffman", bits, 2, 26)
        native_nibbles, nibble_report = read_native(runner, "nibble-pairs", pair_nibbles, 16, 6)
        assert huffman_decode(native_bits, codes) == RAW
        assert nibble_decode(native_nibbles, True) + b"\0" == RAW
        # Check the maximum eight-digit binary container and every nibble.
        read_native(runner, "bit-boundary", [1]*26, 2, 26)
        read_native(runner, "nibble-alphabet", list(range(16)), 16, 6)
        report["verification"].update(
            real_core_arithmetic_readers=True,
            decoded_input_bits=bit_report["symbols"], decoded_input_nibbles=nibble_report["symbols"],
            input_read_on_core_then_decoded_on_host_matches_original=True)
        report["huffman"]["native_reader"] = bit_report
        report["nibble_pairs"]["native_reader"] = nibble_report
    (HERE / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main(Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else None)

"""Program-specific codec search; all payloads decode to the same 49 bytes.

Tables are measured separately from streams. A smaller stream is a candidate,
not proof of a smaller native self-extractor. Native writing remains separate.
"""
from collections import Counter
from heapq import heapify, heappop, heappush
from itertools import combinations
import json
import math
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'tmp/ms-compression-grandi-2026-10-01'))
from compare import RAW, pack_stream, unpack_stream, read_native


def prefix_codes(seq, radix):
    frequencies = Counter(seq)
    # Full r-ary trees require n = 1 mod (r-1). Zero-weight leaves do not
    # contribute to the stream or the serialized dictionary of real symbols.
    heap = [(v, i, k) for i, (k, v) in enumerate(sorted(frequencies.items()))]
    serial = len(heap)
    padding = (1-len(heap)) % (radix-1)
    for _ in range(padding):
        heap.append((0, serial, None))
        serial += 1
    heapify(heap)
    while len(heap) > 1:
        nodes = [heappop(heap) for _ in range(radix)]
        heappush(heap, (sum(n[0] for n in nodes), serial, [n[2] for n in nodes]))
        serial += 1
    codes = {}
    def walk(node, code):
        if isinstance(node, list):
            for digit, child in enumerate(node):
                walk(child, code+(digit,))
        elif node is not None:
            codes[node] = code
    walk(heap[0][2], ())
    return codes


def prefix_decode(stream, codes):
    inverse = {v: k for k, v in codes.items()}
    result = []
    code = ()
    for field in stream:
        code += (field,)
        if code in inverse:
            result.append(inverse[code])
            code = ()
    assert not code
    return result


def canonical_codes(codes, radix):
    result = {}
    value = previous = 0
    for token in sorted(codes, key=lambda t:(len(codes[t]),t)):
        length = len(codes[token])
        value *= radix ** (length-previous)
        digits = [0]*length
        n = value
        for i in range(length-1,-1,-1):
            n, digits[i] = divmod(n,radix)
        assert not n
        result[token] = tuple(digits)
        previous = length
        value += 1
    return result


def dense_radix(stream, radix):
    # Fixed field count is part of each program-specific codec contract.
    # Non-power-of-two radices are an integer ordinal, not one fixed-width
    # bit field per symbol. Native register grouping is measured separately.
    n = sum(s*radix**i for i,s in enumerate(stream))
    width = ((radix**len(stream)-1).bit_length()+7)//8
    payload = n.to_bytes(width,'little')
    actual = []
    n = int.from_bytes(payload,'little')
    for _ in stream:
        n,s = divmod(n,radix)
        actual.append(s)
    assert not n and actual == list(stream)
    return payload


def canonical_table(codes):
    depth = max(map(len,codes.values()))
    counts = [sum(len(c)==i for c in codes.values()) for i in range(1,depth+1)]
    nibble_counts = max(counts)<16
    header = bytes((counts[i] | ((counts[i+1] if i+1<len(counts) else 0)<<4))
                   for i in range(0,len(counts),2)) if nibble_counts else bytes(counts)
    tokens = sorted(codes, key=lambda t:(len(codes[t]),t))
    body = bytearray()
    for t in tokens:
        assert all(b<128 for b in t)
        if len(t)>1: body.append(0x80|len(t))
        body.extend(t)
    # The depth, count width and number of source fields are fixed format
    # parameters; a generic file header would have to carry them separately.
    encoded = header+body
    recovered = []
    i = len(header)
    while i < len(encoded):
        length = 1
        if encoded[i]&128:
            length = encoded[i]&127; i += 1
        recovered.append(tuple(encoded[i:i+length])); i += length
    assert recovered == tokens
    return encoded, dict(max_code_length=depth,count_bits=4 if nibble_counts else 8,
                         length_counts=counts)


def greedy_pairs(seq, count):
    seq = [(s,) for s in seq]
    for _ in range(count):
        counts = Counter((a+b) for a,b in zip(seq, seq[1:]))
        if not counts:
            break
        pair = max(counts, key=lambda p: (counts[p]*(len(p)-1), counts[p], -len(p), p))
        if counts[pair] < 2:
            break
        result = []
        i = 0
        while i < len(seq):
            if i+1 < len(seq) and seq[i]+seq[i+1] == pair:
                result.append(pair)
                i += 2
            else:
                result.append(seq[i])
                i += 1
        if result == seq:
            break
        seq = result
    return seq


def byte_round_trip(tokens):
    return bytes(b for token in tokens for b in token)


def prefix_variant(data, radix, merges, suffix=b''):
    tokens = greedy_pairs(data, merges)
    codes = canonical_codes(prefix_codes(tokens, radix),radix)
    stream = [c for token in tokens for c in codes[token]]
    decoded = prefix_decode(stream, codes)
    assert byte_round_trip(decoded)+suffix == RAW
    width = 0
    while radix**(width+1) <= 100000000:
        width += 1
    words = pack_stream(stream, radix, width)
    assert prefix_decode(unpack_stream(words, radix, width, len(stream)), codes) == tokens
    bits = len(stream)*math.log2(radix)
    # An explicit tree stores radix children per internal node, each one
    # byte: 0..radix-1 cannot conflict with leaf marker 0x80. The phrase
    # dictionary uses a byte length and raw bytes per phrase. This is an
    # intentionally concrete representation, not a table-size lower bound.
    nodes = {code[:i] for code in codes.values() for i in range(len(code))}
    phrase_bytes = sum(len(t)+(len(t)>1) for t in codes)
    tree_bytes = len(nodes)*radix
    dense = dense_radix(stream,radix)
    table, table_info = canonical_table(codes)
    row = dict(family=f'prefix-{radix}', merges=merges, tokens=len(tokens),
               fields=len(stream), radix=radix, bits=round(bits, 3),
               dense_bytes=len(dense), dense_hex=dense.hex(), register_count=len(words),
               register_bytes=7*len(words), phrase_bytes=phrase_bytes,
               explicit_tree_bytes=tree_bytes,
               dense_plus_explicit_table=math.ceil(bits/8-1e-10)+phrase_bytes+tree_bytes,
               canonical_table_bytes=len(table), canonical_table_hex=table.hex(),
               canonical_table_parameters=table_info,
               dense_plus_canonical_table=len(dense)+len(table),
               numeric_words=words, implicit_suffix=suffix.hex(),
               codes=[dict(phrase=bytes(t).hex(), code=list(c)) for t,c in sorted(codes.items())])
    return row, stream, codes


def lz_variant(data, literal_bits, distance_bits, length_bits):
    max_distance = (1 << distance_bits)
    max_length = (1 << length_bits)+1
    cost = [0]*(len(data)+1)
    choice = [None]*len(data)
    for i in range(len(data)-1, -1, -1):
        cost[i] = 1+literal_bits+cost[i+1]
        choice[i] = ('literal', data[i])
        for distance in range(1, min(i, max_distance)+1):
            n = 0
            while n < min(max_length, len(data)-i) and data[i+n] == data[i+n-distance]:
                n += 1
            for length in range(2, n+1):
                c = 1+distance_bits+length_bits+cost[i+length]
                if c < cost[i]:
                    cost[i] = c
                    choice[i] = ('copy', distance, length)
    decoded = bytearray()
    operations = []
    while len(decoded) < len(data):
        op = choice[len(decoded)]
        operations.append(op)
        if op[0] == 'literal':
            decoded.append(op[1])
        else:
            for _ in range(op[2]):
                decoded.append(decoded[-op[1]])
    assert decoded == data
    return dict(family='lz', literal_bits=literal_bits, distance_bits=distance_bits,
                length_bits=length_bits, bits=cost[0], dense_bytes=(cost[0]+7)//8,
                dictionary_bytes=0, max_distance=max_distance,
                max_length=max_length, operations=operations)


def nibble_dp(data, macros, common):
    costs = [0]*(len(data)+1)
    choice = [None]*len(data)
    common = set(common)
    for i in range(len(data)-1, -1, -1):
        b = data[i]
        costs[i] = (1 if b < 9 or b in common else 2)+costs[i+1]
        choice[i] = (b,)
        for phrase in macros:
            if data[i:i+len(phrase)] == bytes(phrase) and 1+costs[i+len(phrase)] < costs[i]:
                costs[i] = 1+costs[i+len(phrase)]
                choice[i] = phrase
    tokens = []
    i = 0
    while i < len(data):
        token = choice[i]
        tokens.append(token)
        i += len(token)
    assert byte_round_trip(tokens) == data
    return costs[0], tokens


def macro_search(data, suffix=b''):
    non_digits = sorted({b for b in data if b >= 9})
    repeated = []
    for length in range(2, 9):
        for phrase, count in Counter(tuple(data[i:i+length])
                                     for i in range(len(data)-length+1)).items():
            if count >= 2:
                repeated.append(phrase)
    repeated = sorted(repeated, key=lambda p: (-len(p), p))
    results = []
    # Exhaust all dictionaries over every repeated substring of length 2..8,
    # with 0..6 phrase slots and all allocations of the remaining direct slots.
    for k in range(7):
        sets = list(combinations(repeated, k))
        layer = []
        for macros in sets:
            best = None
            for common in combinations(non_digits, 6-k):
                fields, tokens = nibble_dp(data, macros, common)
                if best is None or fields < best[0]:
                    best = fields, common, tokens
            fields, common, tokens = best
            table = 1+len(non_digits)+sum(1+len(m) for m in macros)
            dense = (fields+1)//2
            row = dict(family='nibble-macros', macros=[bytes(p).hex() for p in macros],
                       direct_non_digits=[f'{b:02x}' for b in common],
                       nibbles=fields, dense_bytes=dense,
                       explicit_table_bytes=table, dense_plus_explicit_table=dense+table,
                       register_count=(fields+5)//6, register_bytes=7*((fields+5)//6),
                       implicit_suffix=suffix.hex(),
                       search='exhaustive')
            assert byte_round_trip(tokens)+suffix == RAW
            layer.append((fields, dense+table, macros, row))
        layer.sort(key=lambda x: (x[0],x[1],x[2]))
        results += [x[3] for x in layer[:12]]
    return dict(repeated_phrases=len(repeated),
                dictionary_sets=sum(math.comb(len(repeated),k) for k in range(7)),
                direct_slot_allocations=sum(math.comb(len(repeated),k)*math.comb(len(non_digits),6-k)
                                            for k in range(7)),
                candidates=results)


def branch_stream(data):
    seq = []
    addresses = []
    offsets = []
    i = 0
    while i < len(data):
        b = data[i]
        seq.append(b)
        if b in (0x51, 0x5E):
            target = data[i+1]
            addresses.append(target)
            decimal_target = (target>>4)*10+(target&15)
            offsets.append(decimal_target-i)
            i += 2
        else:
            i += 1
    result = bytearray()
    j = 0
    for b in seq:
        result.append(b)
        if b in (0x51, 0x5E):
            result.append(addresses[j]); j += 1
    assert result == data
    return bytes(seq), addresses, offsets


def main(runner=None):
    prefix = []
    native = {}
    for radix in (2,4,10,16):
        for merges in range(9):
            row, stream, codes = prefix_variant(RAW[:-1], radix, merges, b'\0')
            prefix.append(row)
    # The original five branch operands are listed in execution-source order.
    # Four forward deltas fit one decimal digit each; final BP 00 is implicit.
    stripped, addresses, offsets = branch_stream(RAW)
    assert offsets == [7,5,9,7,-47]
    branch_alphabet = sorted(set(stripped))
    assert len(branch_alphabet) == 16
    branch = dict(family='branch-aware-nibbles', instruction_fields=len(stripped),
                  dense_bytes=(len(stripped)+1)//2, alphabet=[f'{b:02x}' for b in branch_alphabet],
                  non_digit_map_bytes=sum(b>=9 for b in branch_alphabet),
                  operand_bytes=addresses, relative_offsets=offsets,
                  relative_offset_nibbles=4, relative_offset_bytes=2,
                  fixed_last_target=0,
                  dense_plus_maps_and_offsets=(len(stripped)+1)//2+7+2)
    for radix in (2,10):
        tokens = []
        i=0
        while i < len(stripped):
            if stripped[i:i+2] == b'\1\1': tokens.append((1,1)); i+=2
            else: tokens.append((stripped[i],)); i+=1
        codes = prefix_codes(tokens, radix)
        stream = [s for t in tokens for s in codes[t]]
        assert byte_round_trip(prefix_decode(stream,codes)) == stripped
        branch[f'prefix_{radix}'] = dict(fields=len(stream), tokens=len(tokens),
                                         distinct=len(codes),
                                         bits=round(len(stream)*math.log2(radix),3),
                                         register_count=math.ceil(len(stream)/(26 if radix==2 else 8)))
    macro = macro_search(RAW[:-1], b'\0')
    lz = [lz_variant(RAW[:-1],7,d,l) for d in range(1,7) for l in range(1,5)]
    for row in lz:
        row['register_count']=(row['bits']+25)//26
        row['register_bytes']=row['register_count']*7
        row['implicit_suffix']='00'
        row['remaining_native_code_for_strict_byte_win']=48-row['dense_bytes']
    if runner:
        # Choose the best decimal stream for ordinary 8-digit containers.
        decimal = min((r for r in prefix if r['radix']==10),
                      key=lambda r:(r['register_count'],r['fields'],r['phrase_bytes']))
        row, stream, codes = prefix_variant(RAW[:-1],10,decimal['merges'],b'\0')
        actual, info = read_native(runner,'decimal-prefix-search',stream,10,8)
        assert byte_round_trip(prefix_decode(actual,codes))+b'\0' == RAW
        native['decimal_prefix'] = info | dict(merges=row['merges'], numeric_words=row['numeric_words'])
        row,stream,codes=prefix_variant(RAW[:-1],4,0,b'\0')
        actual,info=read_native(runner,'quaternary-prefix-search',stream,4,13)
        assert byte_round_trip(prefix_decode(actual,codes))+b'\0'==RAW
        native['quaternary_prefix']=info | dict(numeric_words=row['numeric_words'])
    report = dict(original_bytes=len(RAW), implicit_zero_suffix=True,
                   prefix_candidates=prefix, nibble_search=macro,
                   branch_aware=branch, lz_candidates=lz, native=native,
                   full_native_self_extractors=0)
    (HERE/'search.json').write_text(json.dumps(report,indent=2)+'\n')
    winners = dict(
        prefix_dense=sorted(prefix,key=lambda r:(r['dense_bytes'],r['phrase_bytes']))[:4],
        prefix_registers=sorted(prefix,key=lambda r:(r['register_count'],r['fields'],r['phrase_bytes']))[:4],
        prefix_canonical=sorted(prefix,key=lambda r:r['dense_plus_canonical_table'])[:4],
        macro_dense=sorted(macro['candidates'],key=lambda r:(r['dense_bytes'],r['explicit_table_bytes']))[:4],
        macro_with_table=sorted(macro['candidates'],key=lambda r:r['dense_plus_explicit_table'])[:4],
        lz=sorted(lz,key=lambda r:(r['dense_bytes'],r['bits']))[:4],
        branch_aware=branch, native=native)
    (HERE/'winners.json').write_text(json.dumps(winners,indent=2)+'\n')
    print(json.dumps(winners,indent=2))


if __name__ == '__main__':
    main(Path(sys.argv[1]).resolve() if len(sys.argv)>1 else None)

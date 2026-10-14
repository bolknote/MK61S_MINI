"""Instruction-aware codecs, preserving every original command and address.

Finite searches enumerate the documented dictionaries, not all compressors.
Constants describing a codec's shape belong to its decoder, not the payload.
"""
from collections import Counter
from itertools import combinations
import json
from pathlib import Path
import sys

from search import (RAW, branch_stream, prefix_codes, canonical_codes,
                    canonical_table, dense_radix, prefix_decode,
                    greedy_pairs, byte_round_trip, nibble_dp)
from compare import pack_stream, read_native

HERE = Path(__file__).resolve().parent
SEQ, ADDRESSES, OFFSETS = branch_stream(RAW)
ALPHABET = sorted(set(SEQ))


def restore(seq, structural=False):
    result = bytearray()
    branches = []
    for b in seq:
        position = len(result)
        result.append(b)
        if b in (0x51,0x5e):
            branches.append((position,b))
            result.append(0)
    for j,(position,b) in enumerate(branches):
        if structural:
            # This source has two unnested conditional/else blocks. Each
            # conditional skips to just after the following BP; every
            # forward BP skips to the next STOP. The final BP returns to 00.
            if b == 0x5e:
                target = next(p+2 for p,op in branches if p>position and op==0x51)
            elif j == len(branches)-1:
                target = 0
            else:
                target = next(p for p in range(position+2,len(result)) if result[p]==0x50)
        else:
            target = position+OFFSETS[j] if j<4 else 0
        result[position+1]=(target//10)*16+target%10
    assert bytes(result) == RAW
    return bytes(result)


def repeated_phrases():
    return sorted({tuple(t) for length in range(2,9)
                   for t,count in Counter(SEQ[i:i+length]
                                          for i in range(len(SEQ)-length+1)).items()
                   if count>=2},key=lambda p:(-len(p),p))


def source_row(fields, radix, table, label):
    width = {2:26,4:13,10:8,16:6}[radix]
    payload=dense_radix(fields,radix)
    words=pack_stream(fields,radix,width)
    return dict(family=label,fields=len(fields),radix=radix,
                packed_bytes=len(payload),payload_hex=payload.hex(),
                table_bytes=len(table),table_hex=table.hex(),
                with_explicit_offsets=len(payload)+len(table)+2,
                with_structural_addresses=len(payload)+len(table),
                input_registers=len(words),input_register_bytes=7*len(words),
                numeric_words=words)


def dictionary_codec(tokens, macros, common, radix):
    escape=radix-1
    direct=[(b,) for b in common]+list(macros)
    rare=[(b,) for b in ALPHABET if b not in common]
    assert len(direct)<=escape and len(rare)<=radix
    codes={t:(i,) for i,t in enumerate(direct)}
    codes.update({t:(escape,i) for i,t in enumerate(rare)})
    fields=[d for t in tokens for d in codes[t]]
    assert byte_round_trip(prefix_decode(fields,codes))==SEQ
    restore(byte_round_trip(prefix_decode(fields,codes)))
    restore(byte_round_trip(prefix_decode(fields,codes)),True)
    return fields,codes


def nibble_family():
    repeated=repeated_phrases()
    non_digits=sorted(set(SEQ)-set(range(9)))
    rows=[]; allocations=0
    for k in range(7):
        layer=[]
        for macros in combinations(repeated,k):
            best=None
            for common in combinations(non_digits,6-k):
                allocations+=1
                fields,tokens=nibble_dp(SEQ,macros,common)
                if best is None or fields<best[0]:best=fields,common,tokens
            count,common,tokens=best
            direct={b:b for b in range(9)}
            direct.update({b:9+i for i,b in enumerate(common)})
            phrases={p:(9+len(common)+i,) for i,p in enumerate(macros)}
            rare=[b for b in non_digits if b not in common]
            codes={(b,):(v,) for b,v in direct.items()}
            codes.update({(b,):(15,i) for i,b in enumerate(rare)})
            codes.update(phrases)
            fields=[d for t in tokens for d in codes[t]]
            assert len(fields)==count
            decoded=byte_round_trip(prefix_decode(fields,codes))
            restore(decoded);restore(decoded,True)
            # Digits 0..8 are identities. Direct rare-symbol ordering and
            # macro lengths are explicit; the decoder knows their counts.
            table=bytes(common)+bytes(rare)
            for p in macros:table+=bytes((len(p),))+bytes(p)
            row=source_row(fields,16,table,'branch-nibble-macros')
            row.update(macros=[bytes(p).hex() for p in macros],
                       direct_common=[f'{b:02x}' for b in common],
                       codes=[dict(token=bytes(t).hex(),code=list(c)) for t,c in codes.items()])
            layer.append(row)
        rows+=sorted(layer,key=lambda r:(r['with_explicit_offsets'],r['fields']))[:6]
    return dict(allocations=allocations,repeated_phrases=len(repeated),
                best_total=sorted(rows,key=lambda r:r['with_explicit_offsets'])[:6],
                best_stream=sorted(rows,key=lambda r:(r['packed_bytes'],r['table_bytes']))[:6])


def decimal_family():
    repeated=repeated_phrases()
    n=len(SEQ)
    rows=[];allocations=0
    # Nine direct decimal tokens and one escape. With <=3 macro tokens,
    # all remaining single bytes fit the ten possible escape followers.
    for k in range(4):
        best=[]
        for macros in combinations(repeated,k):
            matches=[[] for _ in SEQ]
            for p in macros:
                for i in range(n-len(p)+1):
                    if SEQ[i:i+len(p)]==bytes(p):matches[i].append(len(p))
            optimum=None
            for common in combinations(ALPHABET,9-k):
                allocations+=1
                costs=[0]*(n+1)
                direct=set(common)
                for i in range(n-1,-1,-1):
                    c=(1 if SEQ[i] in direct else 2)+costs[i+1]
                    for length in matches[i]:c=min(c,1+costs[i+length])
                    costs[i]=c
                if optimum is None or costs[0]<optimum[0]:optimum=costs[0],common
            count,common=optimum
            # Reconstruct only the selected parse after the full allocation
            # search, rather than writing millions of transient candidates.
            costs=[0]*(n+1);choice=[None]*n
            for i in range(n-1,-1,-1):
                costs[i]=(1 if SEQ[i] in common else 2)+costs[i+1];choice[i]=(SEQ[i],)
                for p in macros:
                    if SEQ[i:i+len(p)]==bytes(p) and 1+costs[i+len(p)]<costs[i]:
                        costs[i]=1+costs[i+len(p)];choice[i]=p
            tokens=[];i=0
            while i<n:tokens.append(choice[i]);i+=len(choice[i])
            fields,codes=dictionary_codec(tokens,macros,common,10)
            assert count==len(fields)
            table=bytes(common)+bytes(b for b in ALPHABET if b not in common)
            for p in macros:table+=bytes((len(p),))+bytes(p)
            row=source_row(fields,10,table,'branch-decimal-macros')
            row.update(macros=[bytes(p).hex() for p in macros],
                       direct_common=[f'{b:02x}' for b in common],
                       codes=[dict(token=bytes(t).hex(),code=list(c)) for t,c in codes.items()])
            best.append(row)
        rows+=sorted(best,key=lambda r:(r['input_registers'],r['fields'],r['table_bytes']))[:6]
    return dict(allocations=allocations,search='exhaustive within <=3 macro tokens',
                best_registers=sorted(rows,key=lambda r:(r['input_registers'],r['fields'],r['table_bytes']))[:6],
                best_total=sorted(rows,key=lambda r:r['with_explicit_offsets'])[:6])


def main(runner=None):
    restore(SEQ);restore(SEQ,True)
    plain_fields=[ALPHABET.index(b) for b in SEQ]
    plain_table=bytes(b for b in ALPHABET if b>=9)
    plain=source_row(plain_fields,16,plain_table,'branch-fixed-16-symbols')
    plain['codes']=[dict(token=bytes((b,)).hex(),code=[i]) for i,b in enumerate(ALPHABET)]
    offset_payload=bytes((OFFSETS[0]|OFFSETS[1]<<4,OFFSETS[2]|OFFSETS[3]<<4))
    (HERE/'branch-nibbles.bin').write_bytes(bytes.fromhex(plain['payload_hex']))
    (HERE/'branch-alphabet.bin').write_bytes(plain_table)
    (HERE/'branch-offsets.bin').write_bytes(offset_payload)
    package=bytes.fromhex(plain['payload_hex'])+plain_table+offset_payload
    (HERE/'branch-package.bin').write_bytes(package)
    (HERE/'branch-structural.bin').write_bytes(package[:-2])
    # Read the real serialized package, not the unencoded source arrays.
    n=int.from_bytes(package[:22],'little');alphabet=list(range(9))+list(package[22:29]);seq=[]
    for _ in SEQ:n,d=divmod(n,16);seq.append(alphabet[d])
    assert not n
    deltas=[d for b in package[29:] for d in (b&15,b>>4)]
    assert deltas==OFFSETS[:4]
    restore(bytes(seq));restore(bytes(seq),True)
    prefix=[]
    for radix in (2,4,10,16):
        for merges in range(4):
            tokens=greedy_pairs(SEQ,merges)
            codes=canonical_codes(prefix_codes(tokens,radix),radix)
            fields=[d for t in tokens for d in codes[t]]
            restore(byte_round_trip(prefix_decode(fields,codes)))
            table,info=canonical_table(codes)
            row=source_row(fields,radix,table,f'branch-prefix-{radix}')
            row.update(merges=merges,table_parameters=info,
                       codes=[dict(token=bytes(t).hex(),code=list(c)) for t,c in codes.items()])
            prefix.append(row)
    nibble=nibble_family()
    print('nibble completed',nibble['allocations'],flush=True)
    decimal=decimal_family()
    print('decimal completed',decimal['allocations'],flush=True)
    native={}
    if runner:
        for label,row in [('branch-decimal',decimal['best_registers'][0]),
                          ('branch-nibble',nibble['best_stream'][0])]:
            codes={tuple(bytes.fromhex(c['token'])):tuple(c['code']) for c in row['codes']}
            # Decode the serialized ordinal to feed exactly the same symbols
            # to the real ROM arithmetic reader.
            n=int.from_bytes(bytes.fromhex(row['payload_hex']),'little');fields=[]
            for _ in range(row['fields']):n,d=divmod(n,row['radix']);fields.append(d)
            actual,info=read_native(runner,label,fields,row['radix'],8 if row['radix']==10 else 6)
            restore(byte_round_trip(prefix_decode(actual,codes)))
            native[label]=info
    report=dict(original_bytes=len(RAW),instruction_bytes=len(SEQ),
                relative_offsets=OFFSETS,relative_offset_bytes=2,
                structural_rule_host_round_trip=True,
                plain_nibbles=plain,
                prefix=prefix,nibble=nibble,decimal=decimal,native=native,
                full_native_self_extractors=0)
    (HERE/'branch-search.json').write_text(json.dumps(report,indent=2)+'\n')
    for label,rows in [('prefix',sorted(prefix,key=lambda r:r['with_explicit_offsets'])[:4]),
                       ('nibble',nibble['best_total'][:3]),
                       ('decimal',decimal['best_registers'][:3])]:
        print(label,json.dumps([{k:v for k,v in r.items() if k not in ('codes','payload_hex','table_hex','numeric_words')} for r in rows]),flush=True)


if __name__=='__main__':
    main(Path(sys.argv[1]).resolve() if len(sys.argv)>1 else None)

#!/usr/bin/env python3
"""Qualify actual ARM binary64 sqrt/exp and compare instruction counts."""
import argparse
from decimal import Decimal, localcontext
import hashlib
import json
import math
from pathlib import Path
import random
import statistics
import struct
from native_eabi_m0_arm_self_test import Machine, bits, real, ordered

ROOT = Path(__file__).resolve().parents[1]
INF = 0x7FF0000000000000
SIGN = 1 << 63
FRACTION = (1 << 52)-1
LEGACY = {
    'sqrt': [0x3FD0000000000001,0x3FE0000000000000,0x3FCFFFFFFFFFFFFF,0x3FFFFFFFFFFFFFFF,
             0x3FD0000000000000,0x3FF0000000000001,0x3FF0000000000000,0x3FDFFFFFFFFFFFFF,
             0x3FE0000000000001,0x3FEFFFFFFFFFFFFF,0x4000000000000001,0x4000000000000000],
    'exp': [0xBFE0000000000001,0xBFF0000000000001,0xBFEFFFFFFFFFFFFF,0xBFE0000000000000,
            0x4000000000000001,0x4000000000000000,0x401740B4CC34DE80,0xBFF0000000000000,
            0x3FF0000000000000,0xBFDFFFFFFFFFFFFF,0x3FDFFFFFFFFFFFFF,0x3FFFFFFFFFFFFFFF,
            0x3FD0000000000001,0x3FEFFFFFFFFFFFFF,0x3FE0000000000000,0x3FE0000000000001,
            0x3FD0000000000000,0x3FF0000000000001,0x3FCFFFFFFFFFFFFF],
}


def reference(op, a):
    m = a & (SIGN-1)
    if m > INF:
        return a | (1 << 51)
    if op == 'sqrt':
        if not m:
            return a
        if m == INF:
            return a if not a & SIGN else a | (1 << 51)
        if a & SIGN:
            return INF | (1 << 51)
        e = (a >> 52)-1023
        s = (a & FRACTION) | (1 << 52)
        if not a >> 52:
            shift = 53-a.bit_length()
            s = a << shift
            e = -1022-shift
        n = s << (52+(e & 1))
        q = math.isqrt(n)
        q += n-q*q > q
        return ((e//2+1022) << 52)+q
    x = real(a)
    if x >= 1024:
        return INF
    if x <= -1024:
        return 0
    with localcontext() as context:
        context.prec = 100
        return bits(float(Decimal(x).exp()))


def profile_corpus():
    rng = random.Random(0x5A7E6140)
    groups = []
    for op in ('sqrt', 'exp'):
        groups.append((op, 'legacy', LEGACY[op]))
    groups += [('sqrt', 'normal_exponents', [rng.randrange(1 << 52, INF) for _ in range(256)]),
               ('sqrt', 'normalized', [bits(1.)+rng.randrange(2 << 52) for _ in range(256)])]
    for lo, hi in [(-8.,8.),(-700.,700.)]:
        groups.append(('exp', 'small_range' if lo == -8. else 'normal_exponents',
                       [bits(rng.uniform(lo, hi)) for _ in range(256)]))
    edges = []
    for e in (1023,1024):
        for i in range(256):
            a = (e << 52)+(i << 44)
            edges.extend((a-1,a,a+1))
    groups.append(('sqrt', 'segment_edges', edges))
    return groups


def qualify_corpus(samples):
    rng = random.Random(0x61405A7E)
    roots = [rng.randrange(1, INF) for _ in range(samples)]
    for e in (1,2,1022,1023,1024,2045,2046):
        for i in range(257):
            a = (e << 52)+(i << 44)
            roots += [v for v in (a-1,a,a+1) if 0 < v < INF]
    for i in range(samples//4):
        q = (1 << 52) | rng.getrandbits(52)
        n = (2*q+1)**2
        odd = int(n >= 1 << 107)
        s = (n+(1 << (53+odd))) >> (54+odd)
        a = ((1023+odd) << 52)+s-(1 << 52)
        roots += [a-1,a,a+1]
    for i in range(53):
        roots += [v for v in ((1 << i)-1,1 << i,(1 << i)+1) if v]
    special = [0,SIGN,1,2,3,FRACTION,SIGN|1,bits(-1.),INF-1,SIGN|(INF-1),INF,SIGN|INF,
               INF|1,INF|(1 << 51)|12345,SIGN|INF|1,SIGN|INF|(1 << 51)|12345]
    roots += special
    exps = [bits(rng.uniform(-746.,710.)) for _ in range(samples)]
    exps += [rng.getrandbits(64) for _ in range(samples//2)]
    exps += special
    with localcontext() as context:
        context.prec = 100
        step = Decimal(2).ln()/512
        for i in range(512):
            for k in (-1023,-1,0,1,1023):
                for midpoint in (Decimal(0),Decimal('0.5')):
                    a = bits(float((k*512+i+midpoint)*step))
                    exps += [v for v in (a-1,a,a+1) if 0 <= v <= 0xFFFFFFFFFFFFFFFF]
        for x in [-745.1332191019412,-708.3964185322641,709.782712893384,0.,2.**-28,-2.**-28]:
            a = bits(x)
            exps += [v for v in range(max(0,a-8),min(0xFFFFFFFFFFFFFFFF,a+8)+1)]
    return {'sqrt': roots, 'exp': exps}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--owned-elf', type=Path, required=True)
    parser.add_argument('--baseline-elf', type=Path)
    parser.add_argument('--qfplib-elf', type=Path)
    parser.add_argument('--samples', type=int, default=10000)
    parser.add_argument('--qualification', action='store_true')
    parser.add_argument('--require-fewer-instructions', action='store_true',
                        help='Require every profiled stream mean below Qfplib; not a cycle/timing assertion')
    parser.add_argument('--json', type=Path, required=True)
    args = parser.parse_args()
    paths = {'OWN': args.owned_elf}
    if args.baseline_elf:
        paths['BASE'] = args.baseline_elf
    if args.qfplib_elf:
        paths['QFP'] = args.qfplib_elf
    hashes = {key:hashlib.sha256(path.read_bytes()).hexdigest() for key,path in paths.items()}
    machines = {name: Machine(path, True) for name, path in paths.items()}
    groups = []
    for op, name, inputs in profile_corpus():
        rows = []
        counts = {key: [] for key in machines}
        worst = {key: 0 for key in machines}
        for a in inputs:
            expected = reference(op,a)
            results = {}
            for key, machine in machines.items():
                symbol = 'qfp_d'+op if key == 'QFP' else f'_ZN12compact_math{len(op)}{op}Ed'
                result, _, n = machine.call(symbol, a, count=True)
                ulp = abs(ordered(result)-ordered(expected))
                if key != 'QFP':
                    assert ulp <= (0 if op == 'sqrt' else 4), (op,name,key,hex(a),hex(result),hex(expected),ulp)
                worst[key] = max(worst[key],ulp)
                counts[key].append(n)
                results[key] = {'result':f'{result:016X}','instructions':n,'ulp':ulp}
            rows.append({'input':f'{a:016X}','reference':f'{expected:016X}','implementations':results})
        stats = {key:{'mean':statistics.mean(v),'min':min(v),'max':max(v),'worst_ulp':worst[key]}
                 for key,v in counts.items()}
        groups.append({'operation':op,'name':name,'stats':stats,'cases':rows})
        print(op,name,{key:round(v['mean'],3) for key,v in stats.items()},flush=True)
        if args.require_fewer_instructions:
            assert 'QFP' in stats and stats['OWN']['mean'] < stats['QFP']['mean'], (op,name,stats)
    qualification = {}
    owned = machines['OWN']
    if args.qualification:
        for op, inputs in qualify_corpus(args.samples).items():
            digest = hashlib.sha256()
            worst = 0
            for a in inputs:
                expected = reference(op,a)
                result = owned.call(f'_ZN12compact_math{len(op)}{op}Ed',a)[0]
                ulp = abs(ordered(result)-ordered(expected))
                assert ulp <= (0 if op == 'sqrt' else 4), (op,hex(a),hex(result),hex(expected),ulp)
                worst = max(worst,ulp)
                digest.update(struct.pack('<QQQ',a,expected,result))
            qualification[op] = {'status':'PASS','cases':len(inputs),'worst_ulp':worst,'sha256':digest.hexdigest()}
            print('qualification',op,qualification[op],flush=True)
    state = struct.pack('<7I',17,3,0,0,5,2,3)
    owned.uc.mem_write(0xD0000060,state)
    for op, _, inputs in profile_corpus():
        for a in inputs[:32]:
            owned.call(f'_ZN12compact_math{len(op)}{op}Ed',a)
            assert bytes(owned.uc.mem_read(0xD0000060,len(state))) == state
    assert hashes == {key:hashlib.sha256(path.read_bytes()).hexdigest() for key,path in paths.items()}, 'ELF changed during qualification'
    report = {'status':'PASS','elf_sha256':hashes,
              'groups':groups,'qualification':qualification,'sio_pending_state_preserved':True,
              'oracle':'sqrt: exact integer square inequalities; exp: Decimal precision 100; specials bitwise.',
              'abi':'Every scalar call checks R4-R11/SP, bounded stack writes and pending SIO state.',
              'note':'Executed ARM instructions, not RP2040 cycles or microseconds. Production ROM CLZ/memory intrinsics are functionally modeled by Machine.'}
    args.json.parent.mkdir(parents=True,exist_ok=True)
    args.json.write_text(json.dumps(report,indent=2)+'\n')


if __name__ == '__main__':
    main()

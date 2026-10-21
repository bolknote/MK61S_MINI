#!/usr/bin/env python3
"""Qualify actual ARMv6-M binary64 results with directed MPFR intervals."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import random
import struct

from m0_mpfr_oracle import Oracle, bits, real
from native_eabi_m0_arm_self_test import Machine, nan

ROOT=Path(__file__).resolve().parents[1]
SIGN=1<<63
INF=0x7FF0000000000000
OPERATIONS=('sqrt','sin','cos','tan','atan','asin','acos','ln','log10','exp','pow','fma')


def corpus(name,samples):
    rng=random.Random(0xC0128000+sum(map(ord,name)))
    special=[0,SIGN,1,2,3,SIGN|1,0xFFFFFFFFFFFFF,0x10000000000000,
             bits(1.),bits(-1.),INF-1,SIGN|(INF-1),INF,SIGN|INF,INF|1,SIGN|INF|1,
             INF|(1<<51)|13,SIGN|INF|(1<<51)|13]
    if name=='fma':
        triples=[(a,b,c) for a in special for b in special for c in special]
        triples += [tuple(rng.getrandbits(64) for _ in range(3)) for _ in range(samples)]
        for _ in range(samples):
            a=(rng.randrange(1,2047)<<52)|rng.getrandbits(52)
            b=(rng.randrange(1,2047)<<52)|rng.getrandbits(52)
            z=real(a)*real(b)
            if math.isfinite(z):triples.append((a,b,bits(-z)))
        return list(dict.fromkeys(triples))
    inputs=special+[rng.getrandbits(64) for _ in range(samples)]
    if name in ('asin','acos'):
        inputs += [bits(rng.uniform(-1,1)) for _ in range(samples)]
        for x in (-1.,-.5,-2.**-26,2.**-26,.5,1.):
            inputs += range(bits(x)-4,bits(x)+5)
    elif name in ('ln','log10'):
        inputs += [bits(rng.uniform(.5,2.)) for _ in range(samples)]
        for e in (1,2,1022,1023,1024,2045,2046):
            for j in range(257):
                b=(e<<52)+(j<<44)
                inputs += [v for v in (b-1,b,b+1) if 0<=v<INF]
    elif name in ('sin','cos','tan'):
        inputs += [bits(rng.uniform(-1024,1024)) for _ in range(samples)]
        for j in range(806):
            for offset in (0.,.5):
                b=bits((j+offset)/1024.)
                inputs += [v for v in (b-1,b,b+1) if v>=0]
        for j in range(-64,65):
            b=bits(j*math.pi/2)
            inputs += [v for v in range(max(0,b-4),b+5) if v<1<<64]
        for x in [2.**e for e in (-32,-27,-18,-16,-14,-13,-10,-6,20)]:
            b=bits(x)
            inputs += range(b-8,b+9)
            inputs += [v|SIGN for v in range(b-8,b+9)]
    elif name=='atan':
        inputs += [bits(rng.uniform(-64,64)) for _ in range(samples)]
        for j in range(129):
            b=bits(j/64.)
            inputs += [v for v in (b-1,b,b+1) if v>=0]
    elif name=='exp':
        inputs += [bits(rng.uniform(-746,710)) for _ in range(samples)]
        for x in (-745.1332191019412,-708.3964185322641,709.782712893384,0.,2.**-28,-2.**-28):
            b=bits(x)
            inputs += range(max(0,b-16),b+17)
    if name!='pow':
        return [(v,) for v in dict.fromkeys(inputs)]
    pairs=[(a,b) for a in special for b in special]
    pairs += [(rng.getrandbits(64),rng.getrandbits(64)) for _ in range(samples)]
    pairs += [(bits(rng.uniform(.01,10)),bits(rng.uniform(-100,100))) for _ in range(samples)]
    for x in (2.**-1022,.5,1.,2.,10.,-1.,-2.):
        for y in (-1075.,-1024.,-53.,-.5,0.,.5,1.,2.,3.,53.,1024.):
            pairs.append((bits(x),bits(y)))
    return list(dict.fromkeys(pairs))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--elf',type=Path,required=True)
    parser.add_argument('--samples',type=int,default=10000)
    parser.add_argument('--operations',nargs='+',choices=OPERATIONS,default=OPERATIONS)
    parser.add_argument('--audit',action='store_true',help='Record mismatches instead of stopping; never reports PASS on a mismatch')
    parser.add_argument('--json',type=Path,required=True)
    args=parser.parse_args()
    sha=hashlib.sha256(args.elf.read_bytes()).hexdigest()
    machine=Machine(args.elf,True)
    oracle=Oracle()
    report={}
    for name in args.operations:
        inputs=corpus(name,args.samples);digest=hashlib.sha256();failures=[]
        symbol='mk61_m0_fma' if name=='fma' else f'_ZN12compact_math{len(name)}{name}E'+('dd' if name=='pow' else 'd')
        for arguments in inputs:
            expected=oracle.reference(name,*arguments)
            result=(machine.call(symbol,*arguments[:2],c=arguments[2]) if name=='fma' else machine.call(symbol,*arguments))[0]
            # Payload/sign choices may differ, but an operation must quiet
            # a NaN result, including one originating from a signalling NaN.
            same=(nan(result) and bool(result&(1<<51))) if nan(expected) else result==expected
            if not same:
                failure=dict(arguments=[f'{v:016X}' for v in arguments],expected=f'{expected:016X}',result=f'{result:016X}')
                if not args.audit:raise AssertionError((name,failure))
                failures.append(failure)
            digest.update(struct.pack('<'+'Q'*(len(arguments)+2),*arguments,expected,result))
        report[name]=dict(status='FAIL' if failures else 'PASS',cases=len(inputs),wrong_rounding=len(failures),
                          examples=failures[:16],sha256=digest.hexdigest())
        print(name,report[name],flush=True)
    assert sha==hashlib.sha256(args.elf.read_bytes()).hexdigest(),'ELF changed during qualification'
    result=dict(status='FAIL' if any(v['wrong_rounding'] for v in report.values()) else 'PASS',
                elf_sha256=sha,mpfr=oracle.version,oracle='Directed MPFR bounds; both endpoints round to the same binary64 (RNE).',
                operations=report,abi='Every call verifies R4-R11, SP, bounded stack writes.',
                semantics='RNE return values; errno and floating exception flags are not implemented.',
                nan_result_policy='NaN results must be quiet; payload and sign are unspecified.',
                known_limitations=[
                    'An undecided owned 1024-bit pow refinement still traps; all-input totality is unproved.'
                    if 'mk61_m0_pow_rescue' in machine.elf.symbols else
                    'The upstream pow guard after its 256-bit pass traps on an unknown worst case.'
                ] if 'pow' in args.operations else [],
                scope='Finite corpus, not an exhaustive proof over every binary64 input.')
    args.json.parent.mkdir(parents=True,exist_ok=True)
    args.json.write_text(json.dumps(result,indent=2)+'\n')
    if result['status']!='PASS':raise SystemExit(1)


if __name__=='__main__':main()

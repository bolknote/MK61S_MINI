#!/usr/bin/env python3
"""Check exact bounded pow against MPFR for every supported exponent."""
import argparse
from pathlib import Path
from fractions import Fraction
import ctypes
import hashlib
import json
import math
import random
import struct
import subprocess
import sys

root=Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--source-root',type=Path,default=root)
parser.add_argument('--output',type=Path,required=True)
args=parser.parse_args()
source=args.source_root.resolve();work=args.output.resolve();work.mkdir(parents=True,exist_ok=True)
sys.path.insert(0,str(root/'tests'))
from m0_mpfr_oracle import Oracle
bits=lambda x:struct.unpack('<Q',struct.pack('<d',x))[0]
real=lambda x:struct.unpack('<d',struct.pack('<Q',x))[0]
fixture=work/'exact-host.cpp';fixture.write_text('#include "native_eabi_m0_pow_exact.inc"\n')
library=work/('exact-host.dylib' if sys.platform=='darwin' else 'exact-host.so')
subprocess.run(['c++','-std=c++17','-O2','-Wall','-Wextra','-Werror','-fPIC','-dynamiclib' if sys.platform=='darwin' else '-shared',
    '-I'+str(source/'code'),str(fixture),'-o',str(library)],check=True)
lib=ctypes.CDLL(str(library.resolve()));f=lib.mk61_m0_pow_exact_small
f.argtypes=[ctypes.c_uint64,ctypes.c_uint64,ctypes.POINTER(ctypes.c_uint64)];f.restype=ctypes.c_int
oracle=Oracle();rng=random.Random(0xE7AC70);pairs=set()
exponents={Fraction(sign*p,1<<k) for sign in (-1,1) for p in range(1,131) for k in range(8)}
exponents={y for y in exponents if max(53*y.numerator,54*y.denominator)<=6912
           and (y>0 or 53*abs(y.numerator)+54*y.denominator<=6912)}
assert len(exponents)==1041
for y in exponents:
    bases=[1,0x0010000000000000,0x3FEFFFFFFFFFFFFF,0x3FF0000000000001,0x7FEFFFFFFFFFFFFF]
    if abs(y.numerator)>32 or y.denominator>32:
        bases=[bases[rng.randrange(len(bases))]]
    for x in bases:
        pairs.add((x,bits(float(y))))
    pairs.add((rng.randrange(1,0x7FF0000000000000),bits(float(y))))
for x in [2.,3.,9.,81.,.0625,1.,1.+2.**-26]:
    for y in exponents:
        if abs(y.numerator)<=32 and y.denominator<=32:
            pairs.add((bits(x),bits(float(y))))
for k in range(6):
    for p in [1,3,17,31,32]:
        y=Fraction(p,1<<k)
        for sign in [-1,1]:
            for target in [-1075.,-1074.,-1022.,1023.,1024.]:
                try:x=2.**(target/float(sign*y))
                except OverflowError:continue
                if not x or not math.isfinite(x):continue
                for delta in [-1,0,1]:
                    xb=bits(x)+delta
                    if 0<xb<0x7FF0000000000000:pairs.add((xb,bits(float(sign*y))))
digest=hashlib.sha256();calls=0
for index,(x,y) in enumerate(sorted(pairs)):
    want=oracle.reference('pow',x,y)
    infinity=0x7FF0000000000000
    yq=Fraction(real(y))
    hints=[min(want,infinity-1),max(0,want-1)]
    if (abs(yq.numerator)<=32 and yq.denominator<=32) or index%127==0:
        hints += [0xBAD0BAD0BAD0BAD0,min(infinity-1,want+1),0,rng.getrandbits(64)]
    for hint in dict.fromkeys(hints):
        out=ctypes.c_uint64(hint);ok=f(x,y,ctypes.byref(out));calls+=1
        assert ok and out.value==want,(index,hex(x),hex(y),hex(hint),ok,hex(out.value),hex(want))
        digest.update(struct.pack('<5Q',x,y,hint,out.value,want))
    if index%500==0:print('PASS',index+1,'/',len(pairs),flush=True)
extra=[(1.5,4096.),(1.5,-4096.),(.75,4096.),(.75,-4096.),(1.25,130.),
       (.75,-700.),(1.5,385/128),(2.**-1024,537/512),(2.**-1024,4301/4096)]
for x,y in extra:
    a,b=bits(x),bits(y)
    want=oracle.reference('pow',a,b)
    hint=max(0,want-1)
    out=ctypes.c_uint64(hint)
    assert f(a,b,ctypes.byref(out)) and out.value==want,(x,y,want,out.value)
    digest.update(struct.pack('<5Q',a,b,hint,out.value,want))
rejected=[]
for x,y in [(1.25,0.),(1.25,6913.),(1.25,1./8192),(1.25,math.nextafter(.5,1.)),
            (1.25,float('inf')),(1.25,float('nan')),(1.5,4362.),
            (math.nextafter(1.,2.),133.),(1.25,1./256)]:
    out=ctypes.c_uint64(0xBAD0BAD0BAD0BAD0)
    assert not f(bits(x),bits(y),ctypes.byref(out)) and out.value==0xBAD0BAD0BAD0BAD0,(x,y,out.value)
    rejected.append((x,y))
report=dict(status='PASS',cases=len(pairs)+len(extra),hinted_calls=calls+len(extra),exponents=len(exponents),
    input_specific_cases=len(extra),rejected_cases=len(rejected),
    wrong_rounding=0,source_sha256=hashlib.sha256((source/'code/native_eabi_m0_pow_exact.inc').read_bytes()).hexdigest(),
    mpfr=oracle.version,result_sha256=digest.hexdigest(),
    scope='Native implementation versus directed MPFR across the arbitrary-base exponent domain and additional cases with small odd coefficients. The corpus includes positive/negative powers, subnormal/overflow neighborhoods, exact roots, ties, nearby hints and selected distant/invalid hints.')
(work/'host.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2),flush=True)

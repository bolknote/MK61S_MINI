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
exponents=set(Fraction(sign*p,1<<k) for sign in [-1,1] for p in range(1,33) for k in range(6))
for y in exponents:
    for x in [1,0x0010000000000000,0x3FEFFFFFFFFFFFFF,0x3FF0000000000001,0x7FEFFFFFFFFFFFFF]:
        pairs.add((x,bits(float(y))))
    pairs.add((rng.randrange(1,0x7FF0000000000000),bits(float(y))))
for x in [2.,3.,9.,81.,.0625,1.,1.+2.**-26]:
    for y in exponents:pairs.add((bits(x),bits(float(y))))
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
    hints=[0xBAD0BAD0BAD0BAD0,min(want,infinity-1),max(0,want-1),
           min(infinity-1,want+1),0,rng.getrandbits(64)]
    for hint in dict.fromkeys(hints):
        out=ctypes.c_uint64(hint);ok=f(x,y,ctypes.byref(out));calls+=1
        assert ok and out.value==want,(index,hex(x),hex(y),hex(hint),ok,hex(out.value),hex(want))
        digest.update(struct.pack('<5Q',x,y,hint,out.value,want))
    if index%500==0:print('PASS',index+1,'/',len(pairs),flush=True)
rejected=[]
for y in [0.,33.,65.,1./64,math.nextafter(.5,1.),float('inf'),float('nan')]:
    out=ctypes.c_uint64(0xBAD0BAD0BAD0BAD0)
    assert not f(bits(1.25),bits(y),ctypes.byref(out)) and out.value==0xBAD0BAD0BAD0BAD0
    rejected.append(bits(y))
report=dict(status='PASS',cases=len(pairs),hinted_calls=calls,exponents=len(exponents),rejected_exponents=len(rejected),
    wrong_rounding=0,source_sha256=hashlib.sha256((source/'code/native_eabi_m0_pow_exact.inc').read_bytes()).hexdigest(),
    mpfr=oracle.version,result_sha256=digest.hexdigest(),
    scope='Native implementation versus directed MPFR across every supported exponent and positive/negative powers, subnormal/overflow neighborhoods, exact roots, ties and random binary64 bases. Each result is also checked with near, distant and invalid input hints. Complete domain correctness rests on the exact integer argument, not this finite corpus.')
(work/'host.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2),flush=True)

#!/usr/bin/env python3
"""Check pow's directed kernel and exact boundary helpers independently."""
import argparse
import ctypes
from fractions import Fraction
import hashlib
import json
import math
from pathlib import Path
import random
import shutil
import struct
import subprocess
import sys

from m0_mpfr_oracle import Oracle
from qualify_m0_pow_worst import parse_token

ROOT=Path(__file__).resolve().parents[1]


def bits(x):return struct.unpack('<Q',struct.pack('<d',float(x)))[0]
def real(x):return struct.unpack('<d',struct.pack('<Q',x))[0]


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--samples',type=int,default=2000)
    p.add_argument('--corpus',type=Path)
    p.add_argument('--cxx',default='c++')
    a=p.parse_args();a.output.mkdir(parents=True,exist_ok=True)
    compiler=shutil.which(a.cxx);assert compiler,a.cxx
    library=a.output/('interval.dylib' if sys.platform=='darwin' else 'interval.so')
    subprocess.run([compiler,'-std=c++17','-O2','-Wall','-Wextra','-Werror','-fPIC',
        '-dynamiclib' if sys.platform=='darwin' else '-shared','-I'+str(ROOT/'code'),
        str(ROOT/'tests/fixtures/m0_pow_interval_host.cpp'),'-o',str(library)],check=True)
    lib=ctypes.CDLL(str(library.resolve()));oracle=Oracle();rng=random.Random(0x5121024)
    pairs=[]
    for _ in range(a.samples):
        x=(rng.randrange(1,2047)<<52)|rng.getrandbits(52)
        pairs.append((x,bits(rng.uniform(-740,700)/math.log(real(x)))))
    for x in (1,2,3,0xFFFFFFFFFFFFF,0x10000000000000,0x3FEFFFFFFFFFFFFF,0x3FF0000000000001,0x7FEFFFFFFFFFFFFF):
        for y in (.25,.5,.75,1.5,-.5,-3.,17.125,2.**-100,2.**60):pairs.append((x,bits(y)))
    for x in (2.,3.,5.,9.,81.,.0625):
        for y in (.25,.5,1.,2.,3.,4.,7.,17.,33.,-.5,-3.):pairs.append((bits(x),bits(y)))
    pairs += [(bits(2.),bits(y)) for y in (-1075.,-1074.,-1073.,1023.,1024.)]
    corpus_sample=0
    if a.corpus:
        position=0
        for line in a.corpus.read_text().splitlines():
            line=line.split('#',1)[0].strip()
            if not line:continue
            position+=1
            if position>25 and position%997:continue
            x,y=(parse_token(v) for v in line.split(','))
            if not 0<x<0x7FF0000000000000 or (y&0x7FFFFFFFFFFFFFFF)>=0x7FF0000000000000:continue
            pairs.append((x,y));corpus_sample+=1
    results={}
    for precision in (512,1024):
        function=getattr(lib,'pow_interval'+str(precision))
        function.argtypes=[ctypes.c_uint64,ctypes.c_uint64,ctypes.POINTER(ctypes.c_uint64)];function.restype=ctypes.c_int
        digest=hashlib.sha256()
        for index,(x,y) in enumerate(pairs):
            out=ctypes.c_uint64();ok=function(x,y,ctypes.byref(out));expected=oracle.reference('pow',x,y)
            assert ok and out.value==expected,(precision,index,hex(x),hex(y),ok,hex(out.value),hex(expected))
            digest.update(struct.pack('<4Q',x,y,out.value,expected))
        results[str(precision)]=dict(pow_cases=len(pairs),wrong_rounding=0,rejections=0,sha256=digest.hexdigest())
        print('PASS',precision,'pow',len(pairs),flush=True)
        pack=getattr(lib,'pow_interval_pack'+str(precision));pack.argtypes=[ctypes.POINTER(ctypes.c_uint16),ctypes.c_int];pack.restype=ctypes.c_uint64
        n=precision//16+4
        inputs=[(rng.randrange(1<<(precision-1),1<<(precision+1)),rng.randrange(-1200,1101)) for _ in range(10000)]
        for v in (1<<(precision-1),1<<precision,(1<<precision)+(1<<(precision-53)),(1<<(precision+1))-(1<<(precision-52)),(1<<(precision+1))-1):
            for delta in (-1,0,1):
                for scale in (-1075,-1074,-1023,-1022,1023,1024):inputs.append((v+delta,scale))
        for v in (1,3,9**17,(1<<54)-1):
            for scale in (-1075,-1074,0,960,1023):inputs.append((v<<precision,scale))
        for value,scale in inputs:
            words=(ctypes.c_uint16*n)(*((value>>(16*i))&65535 for i in range(n)))
            got=pack(words,scale);e=scale-precision
            exact=Fraction(value<<e) if e>=0 else Fraction(value,1<<-e)
            try:expected=bits(float(exact))
            except OverflowError:expected=0x7FF0000000000000
            assert got==expected,(precision,hex(value),scale,hex(got),hex(expected))
        results[str(precision)]['exact_fraction_packer_cases']=len(inputs)
    root=lib.pow_interval_root;root.argtypes=[ctypes.c_uint64];root.restype=ctypes.c_uint64
    values=[rng.getrandbits(53) for _ in range(100000)]+[0,1,(1<<53)-1]
    for bit in range(27):
        q=1<<bit;values += [v for v in (q*q-1,q*q,q*q+1) if 0<=v<1<<53]
    for value in values:assert root(value)==math.isqrt(value),value
    product=lib.pow_interval_product;product.argtypes=[ctypes.c_uint64,ctypes.c_uint64,ctypes.POINTER(ctypes.c_uint64)];product.restype=ctypes.c_int
    for _ in range(100000):
        x=rng.getrandbits(rng.randrange(1,55));y=rng.getrandbits(rng.randrange(1,54));out=ctypes.c_uint64();ok=product(x,y,ctypes.byref(out));exact=x*y
        assert bool(ok)==(exact<1<<54) and (not ok or out.value==exact),(x,y,ok,out.value)
    report=dict(status='PASS',precisions=results,exact_integer_roots=len(values),exact_capped_products=100000,corpus_sample_cases=corpus_sample,
        source_sha256={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in (ROOT/'code/native_eabi_m0_pow_interval.inc',ROOT/'code/native_eabi_m0_pow_interval_table.inc')},
        scope='Native host code, directed MPFR for positive magnitude, Python exact integer roots/products, and independent Fraction-to-binary64 packing. Finite tests, not all-input totality.')
    (a.output/'result.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2),flush=True)


if __name__=='__main__':main()

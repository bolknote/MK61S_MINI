"""Deterministic finite coverage; no failing or slow input is filtered."""
import random
from oracles import integer_cast,integer_binary,round_ratio,decode

S32=1<<31;I32=0x7f800000;S64=1<<63;I64=0x7ff0000000000000
F32=[0,S32,1,2,3,0x7ffffe,0x7fffff,0x800000,0x800001,0x3f000000,
     0x3f7fffff,0x3f800000,0x3f800001,0x40000000,0x7f7ffffe,0x7f7fffff,
     I32,I32|S32,I32|1,I32|0x400001,I32|S32|1,I32|S32|0x400001]
F64=[0,S64,1,2,0xfffffffffffff,0x10000000000000,0x3fefffffffffffff,
     0x3ff0000000000000,0x3ff0000000000001,0x4000000000000000,
     I64-1,I64,I64|S64,I64|1,I64|0x8000000000001,I64|S64|1,I64|S64|0x8000000000001]

def unique(items):return list(dict.fromkeys(items))

def float_pairs():
    rng=random.Random(0xF10A7)
    values=[(a,b) for a in F32 for b in F32]
    for e in range(256):
        for f in [0,1,0x400000,0x7fffff]:
            a=(e<<23)|f
            for d in [0,1,23,24,25,126]:
                b=(max(0,e-d)<<23)|rng.getrandbits(23)
                values.extend([(a,b),(a,b|S32)])
            for d in [-1,0,1]:
                b=min(0x7fffffff,max(0,a+d))
                values.extend([(a,b|S32),(a|S32,b)])
    values.extend((rng.getrandbits(32),rng.getrandbits(32)) for _ in range(4096))
    # Deliberate half-way addition and opposite tiny perturbations.
    for e in range(24,254):
        for f in [0,1,0x3fffff,0x7ffffe,0x7fffff]:
            a=(e<<23)|f;b=(e-24)<<23
            values.extend([(a,b),(a,b-1),(a,b+1),(a|S32,b|S32)])
    return unique(values)

def float_values():
    rng=random.Random(0xF32A11);v=list(F32)
    for e in range(256):
        for f in [0,1,2,0x3fffff,0x400000,0x7ffffd,0x7ffffe,0x7fffff]:
            v.extend([(e<<23)|f,S32|(e<<23)|f])
    for k in range(23):
        for d in [-2,-1,0,1,2]:
            a=max(0,(1<<k)+d);v.extend([a,a|S32])
    v.extend(rng.getrandbits(32) for _ in range(4096))
    # Integer conversion thresholds and both sides of every unit binade.
    for k in range(33):
        a=round_ratio(1,1,k,32)
        for d in range(-8,9):v.extend([a+d,(a+d)|S32])
    return unique(v)

def sqrt_values():
    v=float_values();rng=random.Random(0x5A7F32)
    for e in [127,128]:
        for segment in range(129):
            a=(e<<23)+(segment<<16)
            v.extend(a+d for d in range(-8,9))
    for _ in range(1024):
        r=rng.randrange(1<<23,1<<24)
        midpoint_square=round_ratio((2*r+1)**2,1,-48,32)
        v.extend([midpoint_square-1,midpoint_square,midpoint_square+1])
    return unique(v)

def integer_values():
    rng=random.Random(0x1A72F);v=[0,1,0x7fffffff,0x80000000,0xffffffff]
    for k in range(32):
        for d in range(-8,9):
            a=(1<<k)+d
            if 0<=a<1<<32:v.extend([a,(-a)&0xffffffff])
    for shift in range(1,9):
        for _ in range(128):
            q=rng.randrange(1<<23,1<<24)
            for d in [-1,0,1]:
                a=(q<<shift)+(1<<(shift-1))+d
                if a<1<<32:v.extend([a,(-a)&0xffffffff])
    v.extend(rng.getrandbits(32) for _ in range(4096))
    return unique(v)

def double_values():
    rng=random.Random(0xD02F);v=list(F64)
    for e in range(2048):
        for f in [0,1,0x8000000000000,0xfffffffffffff]:
            v.extend([(e<<52)|f,S64|(e<<52)|f])
    # Every binary32 exponent; exact midpoint and adjacent binary64 inputs.
    for e in range(255):
        for f in [0,1,0x3fffff,0x7ffffe,0x7fffff]:
            a=(e<<23)|f
            if a+1>=I32:continue
            lo=integer_cast(a,32,64);hi=integer_cast(a+1,32,64)
            sl,nl,el=decode(lo,64);sh,nh,eh=decode(hi,64);base=min(el,eh)
            mid=round_ratio((nl<<(el-base))+(nh<<(eh-base)),1,base-1,64)
            for d in [-1,0,1]:v.extend([mid+d,(mid+d)|S64])
    v.extend(rng.getrandbits(64) for _ in range(4096))
    return unique(v)

def fma_triples():
    rng=random.Random(0xF6A2040);one=0x3ff0000000000000
    v=[(a,b,c) for a in F64 for b in F64 for c in F64]
    for e in range(2048):
        a=(e<<52)|rng.getrandbits(52)
        v.extend([(a,one,0),(a,one,a^S64),(a,one+1,a^S64),(a|S64,one-1,a)])
    for _ in range(4096):
        v.append(tuple(rng.getrandbits(64) for _ in range(3)))
        a=(rng.randrange(1,2047)<<52)|rng.getrandbits(52)
        b=(rng.randrange(1,2047)<<52)|rng.getrandbits(52)
        product=integer_binary('mul',a,b,64)
        if product<I64:
            for d in [-1,0,1]:
                c=min(I64-1,max(0,product+d))^S64
                v.append((a,b,c))
    # Exact product is a binary64 midpoint; an arbitrarily tiny c decides side.
    a=one+(1<<25);b=one+(1<<26)
    for c in [0,1,2,0xfffffffffffff,0x10000000000000,0x3c90000000000000]:
        for signs in range(8):v.append((a^(S64 if signs&1 else 0),b^(S64 if signs&2 else 0),c^(S64 if signs&4 else 0)))
    # Alignment/jam distances, retained-bit carries and cancellation edges.
    for delta in [0,1,2,20,21,22,23,31,32,52,53,54,63,64,65,104,105,106,107,125,126,127,128,129,511,1023,1074,2097]:
        for _ in range(32):
            e=rng.randrange(1,2047);a=(e<<52)|rng.getrandbits(52);b=one|rng.getrandbits(52)
            c=(max(0,e-delta)<<52)|rng.getrandbits(52)
            v.extend([(a,b,c),(a,b,c|S64),(c,one,a|S64)])
    v.extend([(I64-1,one+1,(I64-1)|S64),
              (0x10000000000000,one-1,1),(1,0x3fe0000000000000,0),
              (1,0x3fe0000000000000,1),(1,0x3fe0000000000000,S64)])
    return unique(v)

"""Independent exact conversion/IEEE and high-precision ln/atan qualification."""
from decimal import Decimal, localcontext
import hashlib
import math
import random
import struct
from native_eabi_m0_arm_self_test import bits,real,f_bits,f_real,ordered
from profile_m0_trig import PI

SIGN=1<<63
INF=0x7FF0000000000000
MASK=(1<<64)-1


def atan_reference(a):
    magnitude=a&(SIGN-1)
    if magnitude>INF:return a|(1<<51)
    if not magnitude:return a
    with localcontext() as context:
        context.prec=110
        if magnitude==INF:result=PI/2
        else:
            x=Decimal(abs(real(a)));invert=x>1
            if invert:x=1/x
            scale=1
            while x>Decimal('0.0625'):
                x=x/(1+(1+x*x).sqrt());scale*=2
            term=total=x;z=-x*x;i=1
            while abs(term)>Decimal('1e-105'):
                term*=z;total+=term/(2*i+1);i+=1
            result=total*scale
            if invert:result=PI/2-result
        return bits(float(-result if a&SIGN else result))


def log_reference(a,base10=False):
    magnitude=a&(SIGN-1)
    if magnitude>INF:return a|(1<<51)
    if not magnitude:return SIGN|INF
    if a&SIGN:return INF|(1<<51)
    if magnitude==INF:return INF
    with localcontext() as context:
        context.prec=110;x=Decimal(real(a))
        return bits(float(x.log10() if base10 else x.ln()))


def qualify(machine,samples):
    rng=random.Random(0x6140F011);counts={};digests={};worst={};examples={}
    def check(name,a,b,expected,width=64,result_width=64,max_ulp=0):
        got=machine.call(name,a,b,width=width)[0]&((1<<result_width)-1)
        nan=lambda x:(x&((1<<(result_width-1))-1))>((0x7FF0000000000000) if result_width==64 else 0x7F800000)
        if max_ulp and nan(expected):assert nan(got),(name,hex(a),hex(got),hex(expected))
        else:
            if max_ulp and (expected&(SIGN-1)) in (0,INF):
                assert got==expected,(name,hex(a),'special result',hex(got),hex(expected))
            error=abs(ordered(got)-ordered(expected)) if max_ulp else int(got!=expected)
            assert error<=max_ulp,(name,hex(a),hex(b),hex(got),hex(expected),error)
            if error>worst.get(name,0):examples[name]={'input':f'{a:016X}','reference':f'{expected:016X}','result':f'{got:016X}'}
            worst[name]=max(worst.get(name,0),error)
        counts[name]=counts.get(name,0)+1
        digests.setdefault(name,hashlib.sha256()).update(struct.pack('<QQQQ',a,b,expected,got))
    integers=[0,1,MASK,1<<63,(1<<63)-1]
    integers += [(s*(1<<i)+d)&MASK for i in range(64) for s in (-1,1) for d in (-1,0,1)]
    for shift in range(1,12):
        for q in ((1<<52),(1<<52)+1,(1<<53)-1):
            integers += [((q<<shift)+d)&MASK for d in (0,(1<<(shift-1))-1,1<<(shift-1),(1<<(shift-1))+1,(1<<shift)-1)]
    integers += [rng.getrandbits(64) for _ in range(samples)]
    for a in integers:
        check('__aeabi_l2d',a,0,bits(float(a-(1<<64) if a>>63 else a)))
        check('__aeabi_ul2d',a,0,bits(float(a)))
    floats=[(s<<31)|(e<<23)|f for s in (0,1) for e in (0,1,2,126,127,128,253,254,255)
            for f in (0,1,2,0x3FFFFF,0x400000,0x7FFFFE,0x7FFFFF)]
    floats += [rng.getrandbits(32) for _ in range(samples)]
    for a in floats:
        magnitude=a&0x7FFFFFFF
        expected=((a&0x80000000)<<32)|INF|((a&0x7FFFFF)<<29)|(1<<51) if magnitude>0x7F800000 else bits(f_real(a))
        check('__aeabi_f2d',a,0,expected,width=32)
    edge=[0,SIGN,1,SIGN|1,0xFFFFFFFFFFFFF,0x10000000000000,INF,SIGN|INF,INF|1,SIGN|INF|1,
          INF|(1<<51)|12345,SIGN|INF|(1<<51)|12345,INF-1,SIGN|(INF-1)]
    for e in (873,874,875,896,897,898,1022,1023,1053,1054,1075,1085,1086,1087,1150,1151):
        for f in (0,1,(1<<28)-1,1<<28,(1<<28)+1,(1<<29)-1,1<<29,(1<<52)-(1<<28),(1<<52)-1):
            edge.extend(((e<<52)|f,SIGN|(e<<52)|f))
    values=edge+[rng.getrandbits(64) for _ in range(samples)]
    for a in values:
        magnitude=a&(SIGN-1)
        expected=((a>>32)&0x80000000)|0x7F800000|((a&((1<<52)-1))>>29)|0x400000 if magnitude>INF else f_bits(real(a))
        check('__aeabi_d2f',a,0,expected,result_width=32)
        x=real(a)
        m=0 if math.isnan(x) else MASK if math.isinf(x) or abs(x)>=2.**64 else int(abs(x))
        signed_limit=0x80000000 if a&SIGN else 0x7FFFFFFF
        q=min(m,signed_limit);signed32=(-q if a&SIGN else q)&0xFFFFFFFF
        check('__aeabi_d2iz',a,0,signed32,result_width=32)
        check('__aeabi_d2lz',a,0,(-m if a&SIGN else m)&MASK)
    comparisons=[(a,b) for a in edge[:14]+[bits(-1.),bits(1.)] for b in edge[:14]+[bits(-1.),bits(1.)]]
    comparisons += [(rng.getrandbits(64),rng.getrandbits(64)) for _ in range(samples)]
    tests=[('eq',lambda a,b:a==b),('lt',lambda a,b:a<b),('le',lambda a,b:a<=b),
           ('ge',lambda a,b:a>=b),('gt',lambda a,b:a>b),('un',lambda a,b:math.isnan(a) or math.isnan(b))]
    for a,b in comparisons:
        for name,test in tests:check('__aeabi_dcmp'+name,a,b,int(test(real(a),real(b))),result_width=32)
    print('conversion/comparison qualification',sum(counts.values()),flush=True)
    logs=[rng.randrange(1,INF) for _ in range(samples)]
    logs += [bits(rng.uniform(63/64,65/64)) for _ in range(samples//4)]
    for e in (1,1022,1023,1024,2046):
        for j in range(257):
            a=(e<<52)+(j<<44)
            logs += [v for v in range(a-1,a+2) if 0<v<INF]
    for x in (63/64,65/64,1.,1+2.**-27,1-2.**-27,1+2.**-20,1-2.**-20):
        a=bits(x);logs+=list(range(a-5,a+6))
    for j in range(-128,129):
        for offset in (0.,.5):
            a=bits(1+(j+offset)/8192)
            logs+=list(range(a-3,a+4))
    logs += edge[:14]
    for i,a in enumerate(logs):
        check('_ZN12compact_math2lnEd',a,0,log_reference(a),max_ulp=1)
        if i<samples//10:check('_ZN12compact_math5log10Ed',a,0,log_reference(a,True),max_ulp=2)
        if (i+1)%25000==0:print('ln qualification',i+1,'/',len(logs),flush=True)
    angles=[rng.getrandbits(64) for _ in range(samples)]
    angles += [bits(rng.uniform(-32,32)) for _ in range(samples//2)]
    for j in range(1,65):
        for x in (j/64,1/(j/64)):
            a=bits(x);angles+=list(range(a-3,a+4));angles += [v|SIGN for v in range(a-3,a+4)]
    for x in (1/64,1.,64.,2.**-27):
        a=bits(x);angles+=list(range(a-5,a+6));angles += [v|SIGN for v in range(a-5,a+6)]
    angles+=edge[:14]
    for i,a in enumerate(angles):
        check('_ZN12compact_math4atanEd',a,0,atan_reference(a),max_ulp=1)
        if (i+1)%25000==0:print('atan qualification',i+1,'/',len(angles),flush=True)
    print('qualification complete',counts,'worst',worst,flush=True)
    return {name:{'cases':n,'worst_error':worst.get(name,0),'worst_example':examples.get(name),
                  'sha256':digests[name].hexdigest()} for name,n in counts.items()}

"""Independent binary64 qualification of M4 kernels, including IEEE edges."""
from pathlib import Path
import hashlib
import math
import random
import struct
from compact_math_arm_self_test import NAMES,bits,value,distance
from profile_m0_trig import qualification as trig_inputs,oracle as trig_reference
from profile_m0_math import qualify_corpus as sqrt_exp_inputs,reference as sqrt_exp_reference
from m0_remaining_oracle import log_reference,atan_reference

SIGN=1<<63
INF=0x7FF0000000000000

def qualify(machine,samples):
    counts={};worst={};digests={};examples={}
    def check(op,a,b,expected,limit=4):
        got=machine.call(NAMES.index(op),a,b)[0]
        m=expected&(SIGN-1);error=0
        if m>INF:assert math.isnan(value(got)),(op,hex(a),hex(got),'NaN')
        elif m in (0,INF):assert got==expected,(op,hex(a),hex(b),hex(got),hex(expected))
        else:
            error=distance(got,expected)
            assert math.isfinite(value(got)) and error<=limit,(op,hex(a),hex(b),hex(got),hex(expected),error)
        counts[op]=counts.get(op,0)+1
        if error>worst.get(op,0):examples[op]={'input':f'{a:016X}','b':f'{b:016X}','reference':f'{expected:016X}','result':f'{got:016X}'}
        worst[op]=max(worst.get(op,0),error)
        digests.setdefault(op,hashlib.sha256()).update(struct.pack('<QQQQ',a,b,expected,got))
    fixture=Path(__file__).parent/'fixtures/compact_math_binary64.tsv'
    vectors=0
    for line in fixture.read_text().splitlines():
        if not line or line.startswith('#'):continue
        op,a,b,c=line.split();check(op,int(a,16),int(b,16),int(c,16),0 if op=='sqrt' else 4);vectors+=1
    print('independent public fixtures',vectors,flush=True)
    angles=trig_inputs(samples)
    for i,a in enumerate(angles):
        for op,gold in zip(('sin','cos','tan'),trig_reference(a)):check(op,a,0,gold)
        if (i+1)%25000==0:print('M4 trig qualification',i+1,'/',len(angles),worst,flush=True)
    rng=random.Random(0x61404A11)
    edge=[0,SIGN,1,SIGN|1,(1<<52)-1,1<<52,INF-1,SIGN|(INF-1),INF,SIGN|INF,INF|1,SIGN|INF|1,
        INF|(1<<51)|12345,SIGN|INF|(1<<51)|12345]
    logs=[rng.randrange(1,INF) for _ in range(samples)]
    logs += [bits(rng.uniform(63/64,65/64)) for _ in range(samples//4)]
    for e in (1,1022,1023,1024,2046):
        for j in range(257):
            a=(e<<52)+(j<<44);logs += [v for v in range(a-1,a+2) if 0<v<INF]
    for j in range(-128,129):
        for d in (0.,.5):
            a=bits(1+(j+d)/8192);logs += list(range(a-3,a+4))
    for x in (63/64,65/64,1.,1+2.**-27,1-2.**-27,1+2.**-20,1-2.**-20):
        a=bits(x);logs+=list(range(a-5,a+6))
    logs+=edge
    for i,a in enumerate(logs):
        check('ln',a,0,log_reference(a),1)
        check('log10',a,0,log_reference(a,True),2)
        if (i+1)%25000==0:print('M4 ln/log10 qualification',i+1,'/',len(logs),flush=True)
    angles=[rng.getrandbits(64) for _ in range(samples)]
    angles += [bits(rng.uniform(-32,32)) for _ in range(samples//2)]
    for j in range(1,65):
        for x in (j/64,1/(j/64)):
            a=bits(x);angles+=list(range(a-3,a+4));angles += [v|SIGN for v in range(a-3,a+4)]
    for x in (1/64,1.,64.,2.**-27):
        a=bits(x);angles+=list(range(a-5,a+6));angles += [v|SIGN for v in range(a-5,a+6)]
    angles+=edge
    for i,a in enumerate(angles):
        check('atan',a,0,atan_reference(a),1)
        if (i+1)%25000==0:print('M4 atan qualification',i+1,'/',len(angles),flush=True)
    for op,inputs in sqrt_exp_inputs(samples).items():
        for i,a in enumerate(inputs):
            check(op,a,0,sqrt_exp_reference(op,a),0 if op=='sqrt' else 1)
            if (i+1)%25000==0:print('M4 '+op+' qualification',i+1,'/',len(inputs),flush=True)
    return {op:{'cases':n,'worst_ulp':worst[op],'worst_example':examples.get(op),
        'sha256':digests[op].hexdigest()} for op,n in counts.items()}

#!/usr/bin/env python3
"""Actual ARM sin/cos/tan + int32 conversion: accuracy and instruction counts."""
import argparse
from decimal import Decimal, localcontext, ROUND_HALF_EVEN
import hashlib
import json
import math
from pathlib import Path
import random
import statistics
import struct
from native_eabi_m0_arm_self_test import Machine, bits, real, ordered

ROOT=Path(__file__).resolve().parents[1]
SIGN=1<<63
INF=0x7FF0000000000000
QFP_TRIG_LIMIT=1024.


def pi_value():
    with localcontext() as context:
        context.prec=430
        def atan_inverse(n):
            x=Decimal(1)/n;z=x*x;term=x;total=x;i=1
            while abs(term)>Decimal('1e-425'):
                term=-term*z
                total+=term/(2*i+1);i+=1
            return total
        return 16*atan_inverse(5)-4*atan_inverse(239)


PI=pi_value()


def oracle(a):
    magnitude=a&(SIGN-1)
    if magnitude>INF:
        q=a|(1<<51);return (q,q,q)
    if magnitude==INF:
        return (INF|(1<<51),)*3
    if not magnitude:
        return (a,bits(1.),a)
    x=real(a)
    with localcontext() as context:
        context.prec=400 if abs(x)>1e20 else 100
        half=PI/2
        n=(Decimal(x)/half).to_integral_value(rounding=ROUND_HALF_EVEN)
        r=Decimal(x)-n*half
        z=-r*r
        st=s=r;ct=c=Decimal(1)
        for i in range(1,50):
            st=st*z/((2*i)*(2*i+1));s+=st
            ct=ct*z/((2*i-1)*(2*i));c+=ct
        quadrant=int(n)&3
        s,c=((s,c),(c,-s),(-s,-c),(-c,s))[quadrant]
        return tuple(bits(float(v)) for v in (s,c,s/c))


def corpora():
    data=json.loads((ROOT/'tests/fixtures/m0_trig_legacy.json').read_text())['inputs']
    groups=[(op.replace('_double',''),'legacy',[int(v,16) for v in values])
            for op,values in data.items() if op!='int32_to_double']
    groups.append(('i2d','legacy',[int(v,16) for v in data['int32_to_double']]))
    rng=random.Random(0x6140C05)
    for label,limit in [('reduced',math.pi/4),('ordinary',32.),('medium',1e6)]:
        inputs=[bits(rng.uniform(-limit,limit)) for _ in range(128)]
        groups += [(op,label,inputs) for op in ('sin','cos','tan')]
    wide_rng=random.Random(0x61401024)
    wide=[bits(wide_rng.uniform(-QFP_TRIG_LIMIT,QFP_TRIG_LIMIT)) for _ in range(128)]
    groups += [(op,'qfplib_range',wide) for op in ('sin','cos','tan')]
    groups += [('i2d','random',[rng.getrandbits(32) for _ in range(512)]),
               ('i2d','small',[(i&0xFFFFFFFF) for i in range(-128,129)])]
    return groups


def qualification(samples):
    rng=random.Random(0xC06140)
    inputs=[bits(rng.uniform(-1e6,1e6)) for _ in range(samples)]
    inputs += [rng.getrandbits(64) for _ in range(samples//2)]
    with localcontext() as context:
        context.prec=100
        for n in list(range(-64,65))+[rng.randrange(-667000,667000) for _ in range(samples//8)]:
            a=bits(float(Decimal(n)*PI/2))
            inputs += [v for v in range(max(0,a-2),min((1<<64)-1,a+2)+1)]
        # Exercise the Q95 rounding certificate's fallback, whose low word
        # depends only on the quadrant. Use a separate high-precision pi.
        pi2_q95=int(PI/2*(1<<95))
        for n in range(1,667545):
            low=(-n*pi2_q95)&0xFFFFFFFF
            if min(low,0xFFFFFFFF-low)<=n:
                for offset in (Decimal('0.3'),Decimal('0.7')):
                    a=bits(float(Decimal(n)*PI/2+offset))
                    inputs.extend((a,a|SIGN))
    for i in range(16,806):
        for offset in (0.,.5):
            a=bits((i+offset)/1024)
            inputs += [v for v in range(a-1,a+2)]
            inputs += [(v|SIGN) for v in range(a-1,a+2)]
    for a in (bits(1/64),bits(2.**-27),bits(math.pi/4),bits(2.**20),bits(-1/64)):
        inputs+=list(range(a-8,a+9))
    inputs += [0,SIGN,1,2,3,SIGN|1,0xFFFFFFFFFFFFF,0x10000000000000,
               INF-1,SIGN|(INF-1),INF,SIGN|INF,INF|1,INF|(1<<51)|13,SIGN|INF|123]
    return inputs


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--owned-elf',type=Path,required=True)
    p.add_argument('--baseline-elf',type=Path)
    p.add_argument('--qfplib-elf',type=Path)
    p.add_argument('--qualification',action='store_true')
    p.add_argument('--samples',type=int,default=10000)
    p.add_argument('--require-fewer-instructions',action='store_true')
    p.add_argument('--json',type=Path,required=True)
    args=p.parse_args()
    paths={'OWN':args.owned_elf}
    if args.baseline_elf:paths['BASE']=args.baseline_elf
    if args.qfplib_elf:paths['QFP']=args.qfplib_elf
    hashes={k:hashlib.sha256(v.read_bytes()).hexdigest() for k,v in paths.items()}
    machines={k:Machine(v,True) for k,v in paths.items()}
    cache={}
    def reference(a):
        if a not in cache:cache[a]=oracle(a)
        return cache[a]
    def symbol(op,key):
        if op=='i2d':return 'qfp_int2double' if key=='QFP' else '__aeabi_i2d'
        return 'qfp_d'+op if key=='QFP' else f'_ZN12compact_math3{op}Ed'
    groups=[]
    for op,name,inputs in corpora():
        outside=sum(abs(real(a))>QFP_TRIG_LIMIT for a in inputs) if op!='i2d' else 0
        rows=[];counts={k:[] for k in paths};worst={k:0 for k in paths}
        for a in inputs:
            expected=bits(float(a-(1<<32) if a>>31 else a)) if op=='i2d' else reference(a)[('sin','cos','tan').index(op)]
            values={}
            for key,m in machines.items():
                got,_,n=m.call(symbol(op,key),a,width=32 if op=='i2d' else 64,count=True)
                ulp=abs(ordered(got)-ordered(expected))
                if key!='QFP':assert ulp<=(0 if op=='i2d' else 4),(op,name,key,hex(a),hex(got),hex(expected),ulp)
                worst[key]=max(worst[key],ulp);counts[key].append(n)
                values[key]={'result':f'{got:016X}','instructions':n,'ulp':ulp}
            rows.append({'input':f'{a:016X}','reference':f'{expected:016X}','implementations':values})
        stats={key:{'mean':statistics.mean(v),'min':min(v),'max':max(v),'worst_ulp':worst[key]} for key,v in counts.items()}
        groups.append({'operation':op,'stream':name,'stats':stats,'cases':rows,
                       'qfplib_outside_documented_domain':outside,
                       'qfplib_speed_comparison_eligible':not outside})
        print(op,name,{k:round(v['mean'],3) for k,v in stats.items()},flush=True)
        if args.require_fewer_instructions and not outside:
            assert stats['OWN']['mean']<stats['QFP']['mean'],(op,name,stats)
    result={}
    owned=machines['OWN']
    if args.qualification:
        inputs=qualification(args.samples)
        worst={op:0 for op in ('sin','cos','tan')};digests={op:hashlib.sha256() for op in worst}
        examples={}
        for i,a in enumerate(inputs):
            for op,expected in zip(('sin','cos','tan'),reference(a)):
                got=owned.call(symbol(op,'OWN'),a)[0]
                ulp=abs(ordered(got)-ordered(expected))
                assert ulp<=4,(op,hex(a),hex(got),hex(expected),ulp)
                if ulp>worst[op]:
                    examples[op]={'input':f'{a:016X}','reference':f'{expected:016X}','result':f'{got:016X}'}
                    if 'BASE' in machines:
                        old=machines['BASE'].call(symbol(op,'BASE'),a)[0]
                        examples[op]['baseline_result']=f'{old:016X}'
                        examples[op]['baseline_ulp']=abs(ordered(old)-ordered(expected))
                worst[op]=max(worst[op],ulp);digests[op].update(struct.pack('<QQQ',a,expected,got))
            if (i+1)%10000==0:print('qualification',i+1,'/',len(inputs),worst,flush=True)
        result={op:{'cases':len(inputs),'worst_ulp':worst[op],'worst_example':examples.get(op),
                    'sha256':digests[op].hexdigest()} for op in worst}
        rng=random.Random(0x6140AB1);count=0
        ints=[0,1,0x7FFFFFFF,0x80000000,0xFFFFFFFF]
        ints += [(v+d)&0xFFFFFFFF for i in range(32) for v in (1<<i,(-1<<i)&0xFFFFFFFF) for d in (-1,0,1)]
        ints += [rng.getrandbits(32) for _ in range(args.samples*2)]
        for a in ints:
            owned.exact('__aeabi_i2d',a,0,bits(float(a-(1<<32) if a>>31 else a)),32,64)
            owned.exact('__aeabi_ui2d',a,0,bits(float(a)),32,64);count+=2
        result['integer_conversion']={'cases':count,'bitwise_exact':True}
        for i in range(args.samples):
            a,b=rng.getrandbits(64),rng.getrandbits(64)
            if i%3==0:b&=0xFFFFFFFF
            product=a*b;q,tail=divmod(product,1<<62)
            q+=tail>1<<61 or (tail==1<<61 and (q&1))
            owned.exact('mk61_m0_mul_q62',a,b,q)
        result['q62_product']={'cases':args.samples,'bitwise_exact':True}
        packed=[(1<<i)+d for i in range(55,63) for d in range(-8,9)]
        for shift in range(3,11):
            for q in ((1<<52),(1<<52)+1,(1<<53)-1):
                packed.extend((q<<shift)+(1<<(shift-1))+d for d in (-1,0,1))
        packed += [rng.randrange(1<<55,(1<<62)+1) for _ in range(args.samples)]
        for q in packed:
            for sign in (0,SIGN):
                owned.exact('mk61_m0_trig_pack',q,sign,bits(float(q)*2.**-62)^sign)
        result['q62_pack']={'cases':2*len(packed),'bitwise_exact':True}
        print('qualification result',result,flush=True)
    state=struct.pack('<7I',17,3,0,0,5,2,3)
    owned.uc.mem_write(0xD0000060,state)
    for op,name,inputs in corpora():
        for a in inputs[:8]:
            owned.call(symbol(op,'OWN'),a,width=32 if op=='i2d' else 64)
            assert bytes(owned.uc.mem_read(0xD0000060,len(state)))==state
    assert hashes=={k:hashlib.sha256(v.read_bytes()).hexdigest() for k,v in paths.items()}
    report={'status':'PASS','elf_sha256':hashes,'groups':groups,'qualification':result,
            'sio_pending_state_preserved':True,'abi':'Every call checks R4-R11/SP and bounded stack/SIO writes.',
            'oracle':'Independent Decimal Machin pi (430 digits), 100/400-digit reduction and Taylor sin/cos; tan is the high-precision quotient. Integer products/conversions use exact Python integers.',
            'qfplib_documented_trig_domain':'README.md: double-precision trigonometric functions require -1024 <= x <= 1024. Wider streams are diagnostics only and excluded from the speed gate.',
            'note':'Executed ARM instruction counts, not RP2040 cycles or timings. Qfplib may have substantially larger trig ULP error; counts do not imply equal accuracy.'}
    args.json.parent.mkdir(parents=True,exist_ok=True)
    args.json.write_text(json.dumps(report,indent=2)+'\n')


if __name__=='__main__':main()

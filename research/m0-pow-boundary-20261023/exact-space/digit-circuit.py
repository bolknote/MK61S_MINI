"""Exact integer-power digit oracle with a bounded memo cache, feasibility only.

No firmware changes. A work cap declines an experiment explicitly; it never
substitutes a numerical answer. Python big integers supply a test oracle,
not the digit algorithm's power computation.
"""
from collections import OrderedDict
from fractions import Fraction as F
import hashlib
import json
import math
from pathlib import Path
import random
import struct
import time

WORK=Path(__file__).resolve().parent
RADIX=1<<16
MASK=RADIX-1


class WorkLimit(Exception):pass


class Digits:
    def __init__(self,capacity=32,budget=200000):
        self.capacity=capacity;self.budget=budget;self.memo=OrderedDict()
        self.requests=self.columns=self.products=self.cache_hits=0
        self.maximum_depth=self.maximum_carry_bits=self.maximum_accumulator_bits=self.cache_peak=0
    def tick(self):
        if self.requests+self.columns+self.products>self.budget:raise WorkLimit()
    @staticmethod
    def width(base,exponent):
        # A safe (occasionally one-limb loose) integer-power upper bound.
        return (base.bit_length()*exponent+15)//16 if exponent else 1
    def digit(self,base,exponent,index,depth=0):
        self.requests+=1;self.tick();self.maximum_depth=max(self.maximum_depth,depth)
        assert base>=0 and exponent>=0
        if index<0 or index>=self.width(base,exponent):return 0
        key=(base,exponent,index)
        if key in self.memo:
            self.cache_hits+=1;value=self.memo.pop(key);self.memo[key]=value;return value
        if exponent==0:value=int(index==0)
        elif exponent==1:value=(base>>(16*index))&MASK
        else:
            left=exponent-1 if exponent&1 else exponent//2
            right=1 if exponent&1 else left
            na,nb=self.width(base,left),self.width(base,right)
            carry=0;value=0
            for column in range(index+1):
                self.columns+=1;self.tick()
                accumulator=carry
                for i in range(max(0,column-nb+1),min(column,na-1)+1):
                    self.products+=1;self.tick()
                    a=self.digit(base,left,i,depth+1)
                    b=self.digit(base,right,column-i,depth+1)
                    accumulator+=a*b
                value=accumulator&MASK;carry=accumulator>>16
                self.maximum_carry_bits=max(self.maximum_carry_bits,carry.bit_length())
                self.maximum_accumulator_bits=max(self.maximum_accumulator_bits,accumulator.bit_length())
        if self.capacity:
            self.memo[key]=value
            while len(self.memo)>self.capacity:self.memo.popitem(last=False)
            self.cache_peak=max(self.cache_peak,len(self.memo))
        return value
    def shifted_digit(self,base,exponent,shift,index):
        whole,part=divmod(shift,16);k=index-whole
        low=self.digit(base,exponent,k)
        return ((low<<part)&MASK)|(self.digit(base,exponent,k-1)>>(16-part) if part else 0)
    def compare(self,a,p,ae,b,q,be):
        assert a>0 and b>0 and p>=0 and q>=0
        # Remove the shared dyadic scale before comparing nonnegative
        # integers. Both powers retain the same radix-column invariant.
        common=min(ae,be);ae-=common;be-=common
        lower_a=(a.bit_length()-1)*p+ae;upper_a=a.bit_length()*p+ae
        lower_b=(b.bit_length()-1)*q+be;upper_b=b.bit_length()*q+be
        if p and q and upper_a<=lower_b:return -1
        if p and q and upper_b<=lower_a:return 1
        top=(max(upper_a,upper_b)+15)//16
        for index in range(top,-1,-1):
            x=self.shifted_digit(a,p,ae,index);y=self.shifted_digit(b,q,be,index)
            if x!=y:return (x>y)-(x<y)
        return 0
    def facts(self):
        return {name:getattr(self,name) for name in ['requests','columns','products','cache_hits','maximum_depth',
            'maximum_carry_bits','maximum_accumulator_bits','cache_peak']}


def bulk_power(base,exponent):
    """The existing exact-small strategy: retain limbs and multiply by64-bit base."""
    words=[1];products=0;peak=1
    for _ in range(exponent):
        result=[0]*(len(words)+4)
        for j in range(4):
            factor=(base>>(16*j))&MASK;carry=0
            for i,word in enumerate(words):
                v=word*factor+result[i+j]+carry
                result[i+j]=v&MASK;carry=v>>16;products+=1
            result[len(words)+j]=carry
        while len(result)>1 and not result[-1]:result.pop()
        words=result;peak=max(peak,len(words))
    value=sum(word<<(16*i) for i,word in enumerate(words))
    assert value==pow(base,exponent)
    return value,dict(limb_products=products,peak_retained_limbs=peak,peak_retained_bytes=2*peak)


def verify_small():
    rng=random.Random(0x2316C117);cases=0;digest=hashlib.sha256();maximum_depth=0
    for _ in range(160):
        a,b=rng.randrange(1,1<<16),rng.randrange(1,1<<16)
        p,q=rng.randrange(1,25),rng.randrange(1,25)
        ae,be=rng.randrange(-60,61),rng.randrange(-60,61)
        oracle=Digits(capacity=32,budget=1000000)
        exact_a=pow(a,p);exact_b=pow(b,q)
        for exponent,base,power in [(p,a,exact_a),(q,b,exact_b)]:
            for k in range(oracle.width(base,exponent)+1):
                assert oracle.digit(base,exponent,k)==(power>>(16*k))&MASK
                cases+=1
        scale=min(ae,be);left=exact_a<<(ae-scale);right=exact_b<<(be-scale)
        expected=(left>right)-(left<right)
        got=oracle.compare(a,p,ae,b,q,be);assert got==expected
        digest.update(struct.pack('<QQiiQQi',a,b,ae,be,p,q,got))
        maximum_depth=max(maximum_depth,oracle.maximum_depth)
    return dict(cases=cases,power_comparisons=160,result_sha256=digest.hexdigest(),maximum_depth=maximum_depth)


def experiments():
    rows=[]
    for base in (3,(1<<53)-1):
        for exponent in (16,32,64,128,256,512,1024):
            for capacity in (0,32,128):
                oracle=Digits(capacity=capacity,budget=200000)
                index=(base.bit_length()*exponent-1)//16
                begin=time.monotonic()
                try:
                    got=oracle.digit(base,exponent,index)
                    assert got==(pow(base,exponent)>>(16*index))&MASK
                    status='EXACT_DIGIT_RETURNED'
                except WorkLimit:status='DECLINED_WORK_CAP_NO_RESULT'
                rows.append(dict(base=base,exponent=exponent,digit_index=index,cache_capacity=capacity,
                    status=status,elapsed_host_seconds=time.monotonic()-begin,**oracle.facts()))
    # A real RNE midpoint from the independent MPFR gap report, not a
    # manufactured equality. The input exponent is15/32 in reduced form.
    gap=json.loads((WORK.parent/'m0-pow-totality-review-20261023/boundary-gap.json').read_text())
    sample=next(row for row in gap['cases'] if row['line']==6259)
    x=F(float.fromhex(sample['x_hex']));y=F(float.fromhex(sample['y_hex']))
    midpoint=F(sample['nearest_54bit_boundary'])
    def dyadic(value):
        a=value.numerator;e=-(value.denominator.bit_length()-1)
        while not a&1:a>>=1;e+=1
        return a,e
    a,ae=dyadic(x);b,be=dyadic(midpoint);p,q=y.numerator,y.denominator
    left=a**p;right=b**q;se=min(ae*p,be*q);left<<=ae*p-se;right<<=be*q-se
    expected=(left>right)-(left<right)
    av,af=bulk_power(a,p);bv,bf=bulk_power(b,q)
    assert av==a**p and bv==b**q
    for capacity in (0,32,128,512):
        oracle=Digits(capacity=capacity,budget=1000000);begin=time.monotonic()
        try:assert oracle.compare(a,p,ae*p,b,q,be*q)==expected;status='EXACT_MIDPOINT_RELATION_RETURNED'
        except WorkLimit:status='DECLINED_WORK_CAP_NO_RESULT'
        rows.append(dict(kind='actual_pow_RNE_midpoint',x=sample['x_hex'],y=sample['y_hex'],cache_capacity=capacity,
            status=status,elapsed_host_seconds=time.monotonic()-begin,**oracle.facts()))
    baseline=dict(kind='same_midpoint_retained_limb_baseline',left=af,right=bf,
        total_limb_products=af['limb_products']+bf['limb_products'],
        scope='Counts the same16x16 product primitive. This is not ARM timing; existing firmware adds fixed buffer clears and loop/call overhead.')
    return rows,baseline


def main():
    small=verify_small();rows,baseline=experiments()
    record=dict(status='EXACT_DIGIT_CIRCUIT_FEASIBILITY_MEASURED_NOT_FIRMWARE',small_integer_oracle=small,
        experiments=rows,retained_limb_baseline=baseline,producer_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        algorithm='Radix2^16 grade-school column/carry invariant over a binary-exponentiation circuit. Recompute discarded child digits with a bounded LRU cache. Compare highest scaled columns first.',
        applicability='The mathematical circuit can express every positive finite binary64 pow-vs-midpoint predicate; active exponent bounds and a full fixed-width M0 implementation are separate obligations.',
        scope='Counts are host prototype limb operations, not ARM instructions or physical cycles. Declined capped experiments have no numerical result. Small oracle success does not qualify a universal firmware fallback.',
        hardware_accessed=False,candidate_changed=False,goal_complete=False)
    (WORK/'digit-circuit.json').write_text(json.dumps(record,indent=2)+'\n')
    print(json.dumps(dict(status=record['status'],small=small,
        returned=sum(r['status'].startswith('EXACT') for r in rows),declined=sum(r['status'].startswith('DECLINED') for r in rows),
        midpoint=[r for r in rows if r.get('kind')=='actual_pow_RNE_midpoint'],retained_baseline=baseline),indent=2),flush=True)


if __name__=='__main__':main()

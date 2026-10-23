"""Independent directed MPFR witness against a universal114-bit pow gap claim.

This does not change or test a new firmware. The2009 bound has a restricted
domain; it must not be used to remove V138's final undecided guard globally.
"""
import ctypes as C
from fractions import Fraction as F
import hashlib
import json
from pathlib import Path
import struct
import sys
ROOT=Path.cwd();WORK=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'tests'))
from m0_mpfr_oracle import Oracle,_Number,bits,real
oracle=Oracle();lib=oracle.lib;pointer=C.POINTER(_Number)
lib.mpfr_zero_p.argtypes=[pointer];lib.mpfr_zero_p.restype=C.c_int
lib.mpfr_add.argtypes=[pointer,pointer,pointer,C.c_int]
lib.mpfr_sub.argtypes=[pointer,pointer,pointer,C.c_int]
lib.mpfr_mul_2si.argtypes=[pointer,pointer,C.c_long,C.c_int]
assert C.sizeof(C.c_ulong)==8


def exact(number):
    if lib.mpfr_zero_p(C.byref(number)):return F(0)
    count=(number.precision+63)//64
    integer=sum(int(number.limbs[i])<<(64*i) for i in range(count))
    value=number.sign*F(integer)*F(2)**(number.exponent-64*count)
    assert float(value)==lib.mpfr_get_d(C.byref(number),0)
    return value


corpus=ROOT/'.build/m0-pow-totality-20261020/pow.wc'
rows=[];boundary_results=[]
selected_lines=set(range(5,10))|{6259,6577}|set(range(977507,977519))
for line_number,line in enumerate(corpus.read_text().splitlines(),1):
    if line_number>max(selected_lines):break
    if line_number not in selected_lines:continue
    pair=line.split('#',1)[0].strip()
    if not pair:continue
    x,y=[bits(float.fromhex(t.strip())) for t in pair.split(',')]
    numbers=[_Number() for _ in range(5)]
    a,b,lo,hi,tmp=numbers
    for n in numbers:lib.mpfr_init2(C.byref(n),512)
    try:
        lib.mpfr_set_d(C.byref(a),real(x),0);lib.mpfr_set_d(C.byref(b),real(y),0)
        lib.mpfr_pow(C.byref(lo),C.byref(a),C.byref(b),3)
        lib.mpfr_pow(C.byref(hi),C.byref(a),C.byref(b),2)
        lower,upper=exact(lo),exact(hi)
        result=oracle.reference('pow',x,y)
        center=F(real(result));previous=F(real(result-1));following=F(real(result+1))
        boundaries=[previous,(previous+center)/2,center,(center+following)/2,following]
        best=None
        for boundary in boundaries:
            if lower>boundary:gaplo,gaphi=lower-boundary,upper-boundary
            elif upper<boundary:gaplo,gaphi=boundary-upper,boundary-lower
            else:continue
            relative_lo,relative_hi=gaplo/upper,gaphi/lower
            if best is None or relative_hi<best['upper']:
                best=dict(boundary=boundary,lower=relative_lo,upper=relative_hi,
                          kind='RNE_midpoint' if boundary not in (previous,center,following) else 'binary64_value')
        assert best is not None and lower<=upper and lower>0
        # A positive lower gap certifies a non-boundary. An upper gap below
        # 2^-114 disproves the claim for the full binary64 input domain.
        witness=0<best['lower']<=best['upper']<F(1,1<<114)
        row=dict(line=line_number,source=line,x=f'{x:016X}',y=f'{y:016X}',
            x_hex=real(x).hex(),y_hex=real(y).hex(),rounded=f'{result:016X}',
            precision=512,mpfr_directed_interval=[str(lower),str(upper)],
            nearest_54bit_boundary=str(best['boundary']),
            nearest_boundary_kind=best['kind'],
            relative_gap_interval=[str(best['lower']),str(best['upper'])],
            relative_gap_upper_hex=float(best['upper']).hex(),
            positive_gap_and_below_2_to_minus114=witness)
        rows.append(row)
        if witness:boundary_results.append(row)
    finally:
        for n in numbers:lib.mpfr_clear(C.byref(n))
assert boundary_results,'Expected known cases beyond the restricted theorem domain'
midpoints=[r for r in boundary_results if r['nearest_boundary_kind']=='RNE_midpoint']
assert midpoints,'Expected at least one actual RNE midpoint witness'
record=dict(status='PASS_DIRECTED_COUNTEREXAMPLE_TO_UNRESTRICTED_114_BIT_GAP',mpfr=oracle.version,
    cases=rows,witnesses=len(boundary_results),RNE_midpoint_witnesses=len(midpoints),corpus_sha256=hashlib.sha256(corpus.read_bytes()).hexdigest(),
    producer_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    primary_sources=[dict(url='https://www.vinc17.net/research/papers/ieeetc2009-powr.pdf',scope='Theorem4.1 p9:114-bit gap only for the explicitly defined subset S; Theorem4.2 proves a boundary detector, not a general fixed-precision termination bound.'),
        dict(url='https://members.loria.fr/PZimmermann/talks/pow-arith23.pdf',scope='Slide22: hardest-to-round binary64 pow inputs are not known; final phase can reject.'),
        dict(url='https://raw.githubusercontent.com/llvm/llvm-project/main/libc/src/__support/math/pow_accurate_256.h',scope='Observed comment near pow_accurate_256 attributes a universal114-bit gap to Lauter/Lefevre. The paper does not support that broad interpretation; no claim here of a wrong LLVM result on these witnesses.')],
    conclusion='A universal114-bit separation cannot justify replacing an undecided1024-bit enclosure with a guess. These witnesses do not exceed1024 bits or show a V138 failure; totality remains an independent open obligation.',
    candidate_changed=False,hardware_accessed=False)
(WORK/'boundary-gap.json').write_text(json.dumps(record,indent=2)+'\n')
print(json.dumps(dict(status=record['status'],witnesses=len(boundary_results),RNE_midpoint_witnesses=len(midpoints),gaps=[dict(x=r['x_hex'],y=r['y_hex'],kind=r['nearest_boundary_kind'],relative_upper=r['relative_gap_upper_hex']) for r in boundary_results]),indent=2))

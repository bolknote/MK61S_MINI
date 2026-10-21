#!/usr/bin/env python3
"""Check integer range lemmas used by the owned pow boundary detector."""
import argparse
import hashlib
import json
from pathlib import Path


def root_floor(value,degree):
    lo,hi=0,1<<((value.bit_length()+degree-1)//degree)
    while lo+1<hi:
        middle=(lo+hi)//2
        if middle**degree<=value:lo=middle
        else:hi=middle
    return hi if hi**degree<=value else lo


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root',type=Path,default=Path(__file__).resolve().parents[1])
    parser.add_argument('--json',type=Path,required=True)
    args=parser.parse_args()
    source=args.source_root/'code/native_eabi_m0_pow_interval.inc'
    max_a=(1<<53)-1
    assert 3**64>max_a
    assert 3**34<(1<<54)<3**35
    assert 1074*max_a<(1<<64)
    assert ((max_a>>32)*1074)<(1<<32)
    assert 1074*54<(1<<31)
    assert root_floor(max_a,2)<(1<<27)
    assert 65535**2+2*65535==(1<<32)-1
    p=65535**2;t=p+65534;v=p+65535
    assert max(p,t,v,p+(t>>16)+(v>>16))<(1<<32)
    rows=[]
    for depth in range(6):
        degree=1<<depth;maximum=root_floor(max_a,degree)
        assert maximum**degree<=max_a<(maximum+1)**degree
        rows.append(dict(square_root_depth=depth,degree=degree,largest_integer_root=maximum))
    report=dict(status='PASS_RANGE_LEMMAS',source=str(source.resolve()),
        source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
        contract='Positive finite binary64 x!=1; finite nonzero binary64 y. The predicate recognizes x^y in the unbounded-exponent binary precision54 set and returns its RNE binary64 value.',
        argument=[
            'Write x=a*2^e with odd1<=a<2^53. In lowest terms write y=p/q, q a power of2. For a>1 and p<0, a nontrivial odd denominator prevents a dyadic result.',
            'For positive p, prime valuations imply a dyadic result exactly when q divides e and a is a perfect qth power. The independent ARM oracle tests this using a direct integer nth-root search rather than successive square-root extraction.',
            'If a>1, a perfect root has odd root>=3. Since3^64>2^53, at most five successive square roots are needed.',
            'After exact root extraction the odd output is root^p. A precision54 boundary requires this odd integer below2^54. Since3^35>2^54, p<=34; the implementation rejection threshold54 is conservative.',
            'The capped multiplier forms the complete128bit product in16bit limbs. Its accumulator maximum is2^32-1. Nonzero high limbs or limb3>=64 are exactly the condition product>=2^54.',
            'For a==1, the result is a power of2 precisely when e*p/q is integral. The significand-times-exponent product fits64bits. The clamp is used only when the integer exponent magnitude exceeds2048, safely beyond both binary64 overflow and half-minimum-subnormal.',
            'The integer exponent product after root extraction is bounded by1074*54 and fits signed32bits. Square-root candidates fit27bits and their word products fit64bits.'
        ],
        root_ranges=rows,maximum_boundary_odd_power=34,
        rounding_boundary_scope='Every binary64 exact value and RNE midpoint is in precision54, including subnormal and overflow boundaries. The predicate may also recognize other precision54 values; its returned value is rounded separately.',
        limitations=['These are checked integer inequalities plus a mathematical argument, not machine-checked verification of C++ control flow.',
            'The matching actual ARM predicate and binary64 packing still need independent execution tests.',
            'This certificate does not establish a precision bound for nonboundary pow results and does not remove the final1024bit undecided trap.'])
    args.json.parent.mkdir(parents=True,exist_ok=True)
    args.json.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(dict(status=report['status'],source_sha256=report['source_sha256'],root_ranges=rows),indent=2))


if __name__=='__main__':
    main()

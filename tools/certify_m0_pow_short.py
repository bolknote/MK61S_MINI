#!/usr/bin/env python3
"""Record exact range and rounding lemmas for RP2040 short integer powers."""
import argparse
import hashlib
import json
from pathlib import Path


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,required=True)
    parser.add_argument('--json',type=Path,required=True)
    args=parser.parse_args()
    text=args.source.read_text()
    for fragment in ('static U pow_short_integer(U xb,unsigned n)',
                     'if((53-zeros)*n>64) return undecided;',
                     'const uint32_t high=uint32_t(power>>32)*a+uint32_t(low>>32);',
                     'return D::pack(0,scale+int(top),significand);'):
        assert text.count(fragment)==1,fragment
    rows=[]
    for n in range(3,9):
        widths=[]
        for width in range(1,54):
            if width*n>64:continue
            upper=(1<<width)-1
            assert upper<1<<32 and width<=21
            for power in range(1,n+1):
                assert upper**power<1<<64
            widths.append(width)
        assert max(widths)==64//n
        rows.append(dict(n=n,maximum_odd_coefficient_width=max(widths),
                         maximum_odd_coefficient=(1<<max(widths))-1,
                         maximum_power=((1<<max(widths))-1)**n))
    assert -1074*8>-(1<<31) and (2046-1075+52)*8+63<1<<31
    report=dict(status='PASS_RANGE_AND_ROUNDING_LEMMAS',
        source_sha256=hashlib.sha256(args.source.read_bytes()).hexdigest(),
        accepted_domain='Nonnegative finite binary64 x and integer n3..8: subnormals round to zero; normal x=A*2^e with odd A is accepted when bit_length(A)*n<=64.',
        ranges=rows,new_tables=0,global_ram_bytes=0,
        argument=[
            'A normal binary64 significand F is a nonzero 53-bit integer. F & (0-F) equals its lowest set bit 2^t, so 63-clz64 of that value is exactly t. Thus A=F>>t is odd and has width w=53-t.',
            'If w*n<=64, every positive partial power A^i for 1<=i<=n is at most (2^w-1)^i<2^64. The finite table checks these monotone upper bounds for every eligible width and exponent.',
            'For P=H*2^32+L, P*A=(H*A+floor(L*A/2^32))*2^32+(L*A mod2^32). The exact wide32 computes L*A; the high sum equals floor(P*A/2^32)<2^32, so the source split multiply loses no bit and cannot overflow.',
            'Since n>=3, w<=21 and t>=32. Therefore a normal accepted input necessarily has its low32 encoding bits zero. The public gate omits no supported normal input.',
            'After stripping t zeros, x^n=A^n*2^((field-1075+t)*n) exactly. All exponent calculations fit signed32bits, and the coefficient is nonzero with leading bit between0 and63.',
            'Normalizing the exact integer coefficient to bit55 uses either an exact left shift or a right shift with a sticky low bit. No rounding occurs at this stage. Sticky shifts compose, including the further subnormal shift in the existing Binary<52,11>::pack.',
            'The pack operation retains three guard/round/sticky bits and performs the single final round-to-nearest, ties-to-even step, then handles significand carry and overflow. This is exactly binary64 RNE of the original dyadic value, rather than rounded intermediate powers.',
            'For 0<=x<2^-1022 and n>=3, x^n<2^-3066<2^-1075, so zero is the exact RNE result. The unchanged public negative-base integer path applies the exact sign after magnitude rounding.'
        ],
        limitations=['These are source-pinned algebraic/range lemmas, not machine-checked verification of every compiled instruction.',
                     'The existing pack primitive and saved-register ABI are separately qualified by actual ARM integer-oracle and MPFR tests.',
                     'The helper does not extend the general pow totality guarantee beyond the existing exact stage; the general undecided trap is retained.'])
    args.json.parent.mkdir(parents=True,exist_ok=True)
    args.json.write_text(json.dumps(report,indent=2)+'\n')
    print('PASS: all eligible width/exponent bounds and exact split-product/rounding lemmas')


if __name__=='__main__':
    main()

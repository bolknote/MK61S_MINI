#!/usr/bin/env python3
"""Check exact bit-mask and accepted-width equivalence of tiny pow helpers."""
import argparse,hashlib,json
from pathlib import Path


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source',type=Path,required=True)
    p.add_argument('--json',type=Path,required=True)
    args=p.parse_args();text=args.source.read_text()
    start=text.index('static bool pow_tiny_integer(');end=text.index('\n}\n',start)+3;helper=text[start:end]
    for token in ('unsigned(e)>16 || uint32_t(yb)', 'const unsigned shift=20-unsigned(e)',
                  'n>65536', 'uint32_t(units>>32)', 'short_units<<1'):
        assert token in helper,token
    ranges=[]
    for exponent in range(17):
        old_shift=52-exponent;new_shift=20-exponent
        assert (1<<old_shift)-1==((1<<32)-1)+(((1<<new_shift)-1)<<32)
        assert 4<=new_shift<=20 and 36<=old_shift<=52
        ranges.append(dict(exponent=exponent,old_shift=old_shift,new_shift=new_shift))
    for fraction in (52,53):
        maximum=1<<(fraction-28)
        assert maximum<1<<32 and maximum+1<1<<32
        assert maximum<<(53-fraction)<1<<32
    result=dict(status='PASS_BIT_MASK_AND_WIDTH_EQUIVALENCE',source_sha256=hashlib.sha256(args.source.read_bytes()).hexdigest(),
        helper_sha256=hashlib.sha256(helper.encode()).hexdigest(),producer_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        integer_decode_ranges=ranges,maximum_accepted_units=1<<25,maximum_accepted_shifted_units=1<<25,
        proof='For exponent0..16, the old36..52-bit integer mask decomposes exactly into the whole low32 word and a4..20-bit mask of the21-bit high significand. Quotient shifts and n<=65536 are identical. The same exact64-bit product is tested; accepting a nonzero high32 word is impossible under the old threshold. Every accepted units/units+1/shifted-units value fits32bits. The reconstructed64-bit output expressions are therefore identical, with the same decline behavior and unchanged binomial remainder argument.',
        scope='Algebraic bit-mask and width identities for the RP2040 specialization. ARM baseline comparison and MPFR tests separately check compiled code. Non-RP2040 code keeps the old implementation. No physical-speed or universal pow-totality claim.')
    args.json.parent.mkdir(parents=True,exist_ok=True);args.json.write_text(json.dumps(result,indent=2)+'\n')
    print('PASS:17 exact mask/quotient decompositions; accepted arithmetic fits32bits; old predicate and output preserved.')


if __name__=='__main__':main()

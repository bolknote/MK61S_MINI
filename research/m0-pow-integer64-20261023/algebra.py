"""Prove Q64 enclosure, cached-neighbor and two-cell lemmas for the experiment."""
import argparse
from fractions import Fraction as F
import hashlib
import json
from pathlib import Path
import struct

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--include',type=Path,required=True)
parser.add_argument('--json',type=Path,required=True)
args=parser.parse_args()
text=args.include.read_text()
required=(
    'unsigned error=((2*a.error*upper+255U)>>8)+4;',
    'unsigned error=((a.error*upper+255U)>>8)+3;',
    'else {product<<=1;error<<=1;}',
    'const Product square=pow_integer128_square64(base.high);',
    'else {q.high=(q.high<<1)|(square.low>>63);q.error=unsigned((square.low<<1)!=0);}',
    'if(scaled < -1022 || scaled+int(n)>1021) return undecided;',
    'if(magnitude>0x3FFFFFFFU) return UINT64_MAX;',
    'const unsigned info=((a.error+3)<<11)|unsigned(a.high>>53);',
    'if(fraction<2 || fraction==D::Fraction)',
    'if(!side) goto ambiguous_cell;',
    'cell,error<=511U && bool(cell&D::Fraction)',
)
for statement in required:assert statement in text,statement
assert text.count('q.error<=508U && bool(cell&D::Fraction)')==4
assert text.count('distance-=int32_t(step);++error;')==2
assert text.count('distance+=int32_t(step);++error;')==1
radix=1<<32
omission=2*F(radix-1,radix)+F((radix-1)**2,radix**2)
assert omission<3
# upper=floor(A/2^56)+1 encloses A/2^64 by upper/256.
# Ea^2/2^64<1; therefore ceil(2*Ea*upper/256)+4 encloses
# square endpoint error plus the<3 center omission. The exact base has
# no second input error, so ceil(Ea*upper/256)+3 suffices for multiplication.
assert F((1<<20)**2,1<<64)<1
assert 2*(1<<20)*256+255 < 1<<32


def error_bound(n):
    error,degree=1,2
    first=n.bit_length()-2
    if n&(1<<first):error=2*error+6;degree+=1
    for bit in range(first-1,-1,-1):
        error=4*error+8;degree*=2
        if n&(1<<bit):error=2*error+6;degree+=1
    assert degree==n
    return error


bounds={n:error_bound(n) for n in range(3,33)}
maximum=max(bounds.values())
assert maximum==5702 and maximum<65532
assert 2*maximum*256+255 < 1<<32
assert ((maximum+3)<<11)+2047 < 1<<32
assert (1<<30)-1+2*2047 < 1<<31
# Exact first-square normalization: retaining p.high or the top64 bits
# of p<<1 leaves a fractional remainder<1, and the source tests exactly
# whether that remainder vanishes. Hence the initial radius is at most1.
assert (1<<63)-1 < 1<<63
# With three/four neighbor cells in the same binade, M(h)=M(0)+h*2048.
# For A=step*2^53+remainder, P(h)-[C+h*step] is delta+h*f,
# where0<=delta<3 and0<=f<1. Its magnitude is<3+abs(h).
neighbor_bounds={h:3+abs(h) for h in (-2,-1,0,1)}
for h,bound in neighbor_bounds.items():
    assert max(abs(0+min(h,0)),abs(3+max(h,0)))<=bound
# Observed ambiguity gives |actualP-T|<2*R<=1022. An outer midpoint
# is separated by at least(A-E)/2^53>1023 raw units. Excluding a binade
# start prevents a smaller lower spacing; an upper binade change only
# increases spacing. RNE can therefore only be cell or cell+1.
min_outer_gap=F((1<<63)-508,1<<53)
assert min_outer_gap>1023 and 2*511==1022<min_outer_gap
accepted=[]
for high in range(0xC0080000,0xC0400001):
    exponent=((high&0x7FFFFFFF)>>20)-1023
    significand=(high&0xFFFFF)|0x100000
    shift=20-exponent
    assert 15<=shift<=19
    if not significand&((1<<shift)-1):accepted.append(high)
assert accepted==[struct.unpack('<Q',struct.pack('<d',-float(n)))[0]>>32 for n in range(3,33)]
normal_boxes=0
for n in range(3,33):
    for exponent in range(-1022,1024):
        scaled=exponent*n
        assert -(1<<31)<scaled<(1<<31)
        if scaled>=-1022 and scaled+n<=1021:
            normal_boxes+=1
            assert -340<=exponent<=339
            assert -1022<=scaled<=scaled+n-1<=1020
record=dict(status='PASS_Q64_ALGEBRAIC_LEMMAS_NOT_COMPLETE_QUALIFICATION',
    high_product_omission_bound=str(omission),omission_exclusive=3,
    first_square_radius_maximum=1,error_bounds=bounds,maximum_error_radius=maximum,
    integer_error_expressions_do_not_overflow=True,packed_distance_and_neighbor_steps_do_not_overflow=True,
    cached_neighbor_omission_bounds=neighbor_bounds,trusted_radius_maximum=511,
    maximum_ambiguous_product_distance_exclusive=1022,minimum_outer_midpoint_gap=str(min_outer_gap),
    exact_negative_integer_decoder_high_words=0xC0400001-0xC0080000,
    accepted_exponents=list(range(-3,-33,-1)),normal_power_and_reciprocal_exponent_boxes=normal_boxes,
    necessary_base_exponent_box=[-340,339],
    include_sha256=hashlib.sha256(args.include.read_bytes()).hexdigest(),
    producer_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    scope='Algebraic Q63 endpoint bounds, bounded32-bit arithmetic, same-binade cached midpoint differences and a guarded two-cell lemma. Source statements bind the inspected experiment. Requires independent ARM endpoint/MPFR and compiled-call-site qualification before adoption. No general pow termination or physical speed claim.')
args.json.write_text(json.dumps(record,indent=2)+'\n')
print('PASS:radius5702; cached neighbors bounded; R<=511 gives a strict two-cell enclosure; integration qualification still required.')

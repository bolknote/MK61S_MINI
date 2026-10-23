"""Exact rational endpoint bounds, retaining the existing Q62 exp certificate."""
from fractions import Fraction as F
import hashlib
import json
from pathlib import Path
import re
import sys

root=Path.cwd();work=Path(__file__).resolve().parent
parent=root/'.build/m0-pow-small-y-stable-v144-20261023'
sys.path.insert(0,str(root/'tools'))
from certify_m0_exp_fast import certificate


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


old=(parent/'source/code/native_eabi_m0.cpp').read_text()
new=(work/'source/code/native_eabi_m0.cpp').read_text()
start='MK61_M0_EXP_CORE __attribute__((optimize("Os"))) MK61_SOFT_PCS double mk61_m0_exp(double x) {'
before=old[old.index(start):old.index('  return mk61_m0_cr_exp(x);\n}\n#include "native_eabi_m0_pow_fast.inc"')]
after=new[new.index(start):new.index('#if defined(MK61_M0_RP2040_EABI) && MK61_M0_RP2040_EABI\n  const U endpoint=')]
assert before==after
table=work/'source/code/native_eabi_m0_exp_table.inc'
assert table.read_bytes()==(parent/'source/code/native_eabi_m0_exp_table.inc').read_bytes()==(root/'code/native_eabi_m0_exp_table.inc').read_bytes()
upstream=certificate()
assert upstream['status']=='PASS' and F(upstream['scaled_error'])<5
assert upstream['returned_interval_q62']==5
h=F(1,1400)
words=[int(v) for v in re.findall(r'UINT64_C\((\d+)\)',table.read_text())]
values=words[1:]
assert len(values)==512 and values[0]==1<<62
# The unchanged pre-normalization interval is within a factor exp(±h)
# of its exact segment anchor. Bound it with rational1-h and1/(1-h).
raw_lower=(F(values[0])-1)*(1-h)-5
raw_upper=(F(max(values))+1)/(1-h)+5
assert raw_lower>1<<61 and raw_upper<1<<63
# Therefore its original normalization gives2^62<=q<2^63, radius5/10.
assert 2*((1<<62)-1)<1<<63
assert 1<<61 < 1<<62 < 1<<63
assert (1<<63)+10 < 1<<64
assert (1<<62)-10 > (1<<62)-256
assert ((1<<54)-1)*(1<<8)==(1<<62)-256
assert 1024-62+8==970
assert 11<=-(-1023)-1012 and -(-1075)-1012==63
assert -(-1076)-1012==64
assert -(-1077)-1012==65
for k in range(-1075,-1022):
    shift=-k-1012
    assert 11<=shift<=63
    # (q*2^(k-62))/2^-1074 = q/2^shift.
    assert k-62+1074==-shift
    # All midpoint decisions are strict: distance>error excludes ties.
    assert (1<<(shift-1))>10
    if shift<32:
        assert 1<=shift<32 and 1<=32-shift<32
    else:
        s=shift-32
        assert 0<=s<=31
        if s:
            assert 0<=s-1<31
record=dict(status='PASS_EXACT_EXP_ENDPOINT_ROUNDING_BOUNDS',
    source_sha256=sha(work/'source/code/native_eabi_m0.cpp'),
    producer_sha256=sha(__file__),upstream=upstream,
    upstream_checker_sha256=sha(root/'tools/certify_m0_exp_fast.py'),
    exp_table_sha256=sha(table),unchanged_exp_prefix=True,
    raw_q_interval_bounds=[str(raw_lower),str(raw_upper)],
    normalized_point='2^62<=q<2^63; the existing normalization selects error5 or10.',
    uniform_subnormal_grid='RNE(exp(x)/2^-1074)=RNE(q/2^(-k-1012)), with the complete closed interval[q-error,q+error].',
    midpoint_test='Strict distance from q mod2^shift to2^(shift-1)>error. Every accepted interval lies wholly inside one RNE cell; a tie declines.',
    minimum_normal_transition='Rounding to integer2^52 is already the binary64 encoding of the minimum normal. The same uniform grid covers this boundary.',
    zero_endpoint='k<-1076 gives q+error<2^64 below the first half-min-subnormal boundary; k==-1076 requires q+error<2^63, otherwise declines.',
    overflow_endpoint='At k==1024 the overflow midpoint is Q62(2^62-256). The existing q>=2^62 with error<=10 is strictly above it; larger k also overflows.',
    implementation='Variable shifts use uint32 only, in0..31. The positive-finite exponential cannot be NaN; quiet-NaN bits safely signal decline to unchanged cr_exp.',
    scope='New endpoint packing proof assumes the unchanged, rerun exact-rational Q62 exp enclosure contract. Actual compiled integer interval checks and independently directed MPFR public-function tests are separate evidence.',
    hardware_accessed=False,production_promoted=False,general_pow_totality_proved=False,goal_complete=False)
(work/'certificate.json').write_text(json.dumps(record,indent=2)+'\n')
print('PASS: existing exp prefix/certificate retained; exact gradual-underflow, zero and overflow packing bounds.')

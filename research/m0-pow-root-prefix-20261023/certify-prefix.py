"""Bind the admitted rational domain, interval propagation and guarded rounding decisions."""

import argparse
_checkpoint_parser = argparse.ArgumentParser(description=__doc__)
_checkpoint_parser.add_argument("--work", required=True, help="Existing private work directory; see README")
_checkpoint_args = _checkpoint_parser.parse_args()
from fractions import Fraction as F
import hashlib
import json
from pathlib import Path

root=Path.cwd();work=Path(_checkpoint_args.work).resolve()
parent=root/'.build/m0-pow-final-parent-v110-20261023'
prototype=root/'.build/m0-pow-root-prefix-v120-20261023'
raw=root/'.build/m0-pow-root64-v112-20261023'
load=lambda p:json.loads(Path(p).read_text())
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
validation=load(work/'validation.json')
assert validation['status']=='PASS_GNU_SOURCE_KERNEL_AND_RESOURCE_SCOPE'
certificate=load(raw/'certificate.json')
assert certificate['assembly_sha256']==sha(work/'source/code/native_eabi_m0_pow_root64.inc')
assert certificate['generator_sha256']==sha(root/'tools/generate_m0_sqrt64_table.py')
assert F(certificate['total_point_root_error_bound'])<2
assert load(raw/'raw-endpoints.json')['status']=='PASS_RAW_FIXED_ROOT_EXACT_ENDPOINTS'
reference=(prototype/'kernels.cpp').read_text()
assert load(prototype/'gnu-equivalence.json')['cpp_sha256']==sha(prototype/'kernels.cpp')
required=(
 'unsigned error=a.error+(al?8U:(a.error?1U:0U));',
 'Root64 root={power.high,power.exponent,power.error?2U:unsigned(power.low!=0)};',
 'a.error=((3*a.error+3)>>2)+3;',
 'if(root.exponent < -1021 || root.exponent>1022 || root.error>=1024) return undecided;',
 'if(!(cell&D::Fraction) && tail+512U<=error) return undecided;',
 'if(tail+error<1024U) return cell;',
 'if(tail>1024U+error) return cell+1;',
 'radius<=511U && bool(cell&D::Fraction)',
 'const unsigned info=((a.error+3)<<11)|unsigned(a.high>>53);',
)
for statement in required:assert statement in reference,statement
# Exact first square, then the unchanged conservative128-bit square/base
# radii, with normalization allowed to double at every subsequent step.
def radius(n):
    if n<3:return 0
    error=0
    bit=n.bit_length()-2
    if n&(1<<bit):error=2*error+16
    for bit in range(bit-1,-1,-1):
        error=4*error+32
        if n&(1<<bit):error=2*error+16
    return error
power_bounds={n:radius(n) for n in range(1,33)}
assert max(power_bounds.values())==14032<1<<17
# Discarding the low64 field contributes <1 high64 unit; its error field
# contributes <2^-47. Radius2 encloses both endpoints; exact inputs can
# retain radius0 or1 according to their discarded bits.
assert 1+F(max(power_bounds.values()),1<<64)<2
root_bounds=[2]
for _ in range(7):root_bounds.append((3*root_bounds[-1]+3)//4+3)
assert max(root_bounds)==12
assert F(1,2*(1-F(1,1<<43)))<F(9,16)
# For a normalized center, E<=12 cannot reach the lower outer midpoint
# even at a binade start (distance512). Usual spacings are2048 and their
# midpoint is at1024. A strict side returns only after excluding overlap.
assert 12<512<1024
# Cached reciprocal neighbors use one<3-omission product and at most
# two steps. Their raw radius is <=17. Actual ambiguity puts the exact
# product within34 units of1; the outer midpoint gap exceeds1023 units.
cached_radius=max(root_bounds)+3+2
outer_gap=F((1<<63)-max(root_bounds),1<<53)
assert cached_radius==17 and 2*cached_radius<1023<outer_gap
assert ((max(root_bounds)+3)<<11)+2047<1<<32
assert (1<<30)-1+2*2047<1<<31
# Decoder: low32(y)==0 gives y=S*2^(ey-20), with a nonzero21-bit S.
# Removing v2(S) yields exactly the admitted reduced p/2^d domain.
for s in (1<<20,(1<<20)+1,(1<<21)-1):
    assert s and 0<=((s&-s).bit_length()-1)<=20
assert 1023*32<1<<31 and 1022*128<1<<31
# Preserve every old fine binomial-domain encoding under the broader
# coarse test. Other values fall through to the identical old checked pow.
one=0x3FF0000000000000
for x in range(one-64,one+33):assert 0<=(x>>32)-0x3FEFFFFF<=1
def function(text,signature):
    start=text.index(signature);end=text.index('{',start)+1;depth=1
    while depth:depth+=(text[end]=='{')-(text[end]=='}');end+=1
    return text[start:end]
signature='static double pow_positive_checked(double x,double y)'
assert function((parent/'source/code/native_eabi_m0_pow_fast.inc').read_text(),signature)==function(
    (work/'source/code/native_eabi_m0_pow_fast.inc').read_text(),signature)
record=dict(status='PASS_GUARDED_ROOT_PREFIX_BOUND_CERTIFICATE',build=validation['build'],
    source_sha256=validation['source_sha256'],elf_sha256=validation['elf_sha256'],
    admitted_domain='Positive normal x; exact y=+/-p/2^d, p<=32 and d<=7, bounded normal-result exponent box. Other or unresolved cases decline.',
    maximum_numerator_radius=max(power_bounds.values()),numerator_bounds=power_bounds,
    maximum_Q64_root_radius=max(root_bounds),root_radii=root_bounds,
    cached_reciprocal_radius_maximum=cached_radius,minimum_outer_midpoint_gap=str(outer_gap),
    raw_root_proof=dict(path=str((raw/'certificate.json').relative_to(root)),sha256=sha(raw/'certificate.json')),
    compiled_kernel_proof=dict(path=str((work/'validation.json').relative_to(root)),sha256=sha(work/'validation.json')),
    reference_cpp_sha256=sha(prototype/'kernels.cpp'),producer_sha256=sha(__file__),
    scope='Analytical bounds and source binding for new accepted fast decisions, combined with the unchanged128-bit kernel bounds and exact GNU-object/relocation proof. Finite ARM/MPFR tests are recorded separately. General fallback totality, cache assumptions and physical timing are not proved here.')
(work/'certificate.json').write_text(json.dumps(record,indent=2)+'\n')
print('PASS: radius14032 -> high64 radius2 -> root radius<=12; strict/cached decisions preserve rounding.')

"""Bind the changed algebra, decoder domain and interval radii to V130."""
from fractions import Fraction as F
import hashlib
import json
from pathlib import Path
import runpy
import struct
import sys

root=Path.cwd();work=Path(__file__).resolve().parent
parent=root/'.build/m0-pow-root-prefix-v122-20261023'
reference=root/'.build/m0-pow-horner-inline-v137-20261023/kernels.cpp'
cpp=reference.read_text();raw=(work/'source/code/native_eabi_m0_pow_root64.inc').read_text()
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
oldraw=(parent/'source/code/native_eabi_m0_pow_root64.inc').read_text()
marker=' // R7:R5 is exact signed residual; R1:R0 is the unrounded Q52 root.'
start=oldraw.index(marker);newstart=raw.index(marker)
assert oldraw[:start]==raw[:newstart]
assert raw[newstart:].endswith(' asrs r7,#6\n lsrs r6,#16\n muls r7,r6\n asrs r7,#19\n asrs r2,r7,#31\n adds r0,r7\n adcs r1,r2\n pop {r4-r7,pc}\n.ltorg\n.size pow_sqrt64_raw,.-pow_sqrt64_raw\n')
ns=runpy.run_path(str(root/'tools/generate_m0_sqrt64_table.py'))
packed,seed=ns['packed_coefficients'](list(ns['coefficients']()))
words=[int(v) for line in (work/'source/code/native_eabi_m0_sqrt64_table.inc').read_text().splitlines()
       if line.strip().startswith('.word') for v in line.split('.word')[1].split(',')]
assert words==[v for row in packed for v in row]
assert F(seed['root_seed_error_bound'])+F(1,1<<30)<10
assert F(seed['inverse_seed_error_bound'])+F(1,1<<30)<13
residual=2*(1<<32)*10+100
refined=F(5,8)+F(100,2048)+F(residual*13,1<<42)+F(63*((1<<31)+13),1<<42)
assert refined<1
sbound=refined*((1<<54)+refined)
assert sbound<1<<54
omitted=F((1<<38)*((1<<31)+13),1<<73)+F((sbound+(1<<38))*(1<<16),1<<73)
tail=1+omitted+F(13*sbound,1<<73)+F(refined*refined,1<<42)
point=tail+F(1,2)
assert omitted<F(1,4) and point<2<3
assert (1<<16)*(((1<<31)+13)>>16)<=1<<31

def function(text,signature):
    begin=text.index(signature);end=text.index('{',begin)+1;depth=1
    while depth:
        depth+=(text[end]=='{')-(text[end]=='}');end+=1
    return text[text.index('{',begin):end]
old=(root/'research/m0-pow-small-cross-20261023/kernels.cpp').read_text()
multiply='extern "C" void pow_integer128_multiply(PowInteger128 &a,const PowInteger128 &b)'
square='extern "C" void pow_integer128_square(PowInteger128 &a)'
assert function(old,multiply)==function(cpp,multiply)
fused_old='''    U previous=product.low;
    product.low+=cross;product.high+=U(product.low<previous);
    previous=product.low;
    product.low+=cross;product.high+=U(product.low<previous);'''
fused_new='''    const U previous=product.low;
    product.low+=cross<<1;
    product.high+=(cross>>63)+U(product.low<previous);'''
assert function(old,square).replace(fused_old,fused_new)==function(cpp,square)
assert function(cpp,square)==function(cpp,'inline static void pow_midpoint_square(PowInteger128 &a)')
assert function(old,'U pow_integer128_approx_high64(U a,U b)')==function(cpp,'U pow_integer128_approx_high64(U a,U b)')
# Addition of C twice equals addition of its low64 double plus high carry.
assert 2*((1<<64)-1)<1<<65
# The reduced odd numerator<=31 iff the21-bit normalized significand
# is a multiple of2^16. These are all16 accepted significand patterns.
admitted={p<<(20-(p.bit_length()-1)) for p in range(1,32,2)}
assert admitted==set(range(1<<20,1<<21,1<<16))
decoder_cases=0
for s in sorted(admitted):
    for ey in range(-7,6):
        n=((s>>16)&15)|16;shift=ey-4
        if not n&3:n>>=2;shift+=2
        if not n&1:n>>=1;shift+=1
        if not n&1:n>>=1;shift+=1
        value=F(s,1<<20)*F(2)**ey
        assert F(n)*F(2)**shift==value
        accepted=-7<=shift<=5 and (shift<0 or n<<shift<=32)
        assert accepted==(value.numerator<=32 and value.denominator<=128)
        decoder_cases+=1
for n in range(1,33):
    bit=0;a=n
    if a>=8:a>>=3;bit=3
    if a>=2:a>>=1;bit+=1
    if a>=2:bit+=1
    assert bit==n.bit_length()-1
for e in range(-32736,32769):assert (e-(e&1))//2==e>>1
for text in ['if(ym&65535U) return undecided;', 'a.exponent>>=1;',
             'const unsigned denominator=1U<<depth;', 'total.error>=1024',
             'radius<=511U && bool(cell&D::Fraction)']:
    assert text in cpp,text

assert function(cpp,'extern "C" void factor64_base(Root64 &a,const Root64 &base)')==function(cpp,'inline static void factor_base_inline(Root64 &a,const Root64 &base)')
assert 'if(denominator!=1 && (inverse?numerator<denominator:(numerator>3 && numerator<2*denominator)))' in cpp
assert 'for(unsigned bit=2;bit<=denominator;bit<<=1)' in cpp
assert 'if(numerator&bit) factor_base_inline(total,base);' in cpp
root_error=lambda e:(3*e+3)//4+3
maximum=positive_max=negative_max=positive_cases=negative_cases=0
for p in range(1,32,2):
    for d in range(1,8):
        denominator=1<<d
        if p>3 and p<2*denominator:
            error=0;value=F(1)
            for bit_index in range(1,d+1):
                error=root_error(error);value/=2
                if p&(1<<bit_index):error=2*error+6;value+=1
                positive_max=max(positive_max,error)
            assert value==F(p,denominator)
            positive_cases+=1
        if p<denominator:
            error=0;value=F(0);partial=48;term=F(-1,2);have=False
            for bit_index in range(d-1,-1,-1):
                if p&(1<<bit_index):
                    error=2*(error+partial+4) if have else partial
                    value+=term;have=True
                negative_max=max(negative_max,error,partial)
                if bit_index:partial=root_error(partial);term/=2
            assert have and value==F(-p,denominator)
            negative_cases+=1
maximum=max(positive_max,negative_max)
assert maximum<1<<20 and 2*(1<<20)*256+255<1<<32
assert F(1,2*(1-F(1,1<<43)))<F(9,16)
# Existing inverse-root seed proof, with the generic<3 high-product
# omission rather than depending on a narrower<2 bound.
rh=F(1,512);te=1+F(1,513);derivative=1/(2*(1-rh)**2)
qe=F(3,8)+F(1,2);ce=1+rh*rh*(1<<16)+rh;cube=F(5,16)*ce+F(1,2)
series=(1<<32)*F(35,128)*rh**4/(1-rh)
seed_error=te*derivative+qe+cube+series+F(1,2)*(1+rh)+F(1,2)
delta=seed_error/F(1<<32);inverse_error=(3*delta**2+2*delta**3)*(1<<63)+4
assert seed_error<4 and inverse_error<24
assert (4-F(1,1<<51))*(F(1,2)+F(1,1<<55))**2<1 and 256>24
assert ((1023+3)<<11)<1<<32 and (1<<30)+4094<1<<31

sys.path.insert(0,str(root/'tests'))
from native_eabi_m0_arm_self_test import Machine
elf=work/'firmware/mk61s-picocalc-pico-h.elf'
m=Machine(elf,True,stack_bytes=16384,bootrom=root/'research/rp2040-memset-2026-10-21/capture/bootrom.bin')
left=[]
for a in range(8):
    center=m.call('pow_sqrt64_raw',(1<<63)+a,0)[0]
    assert center>=1<<63
    left.append(dict(offset=a,center=hex(center)))
assert ((1<<63)+8)*(1<<63)>((1<<63)+3)**2
manifest=json.loads((work/'firmware/manifest.json').read_text())
result=dict(status='PASS_HYBRID_POW_BOUND_CERTIFICATE',build=manifest['build_id'],source_sha256=manifest['source_sha256'],
    elf_sha256=sha(elf),raw_root_total_point_error_bound=str(point),raw_root_omitted_tail_bound=str(omitted),
    raw_radius=3,raw_tail_product_fits32=True,left_normalization_cases=left,
    unchanged_Q52_Newton=True,retained128_center_and_radius_algebra_equivalent=True,
    inline_midpoint_square_body_identical=True,complete_small_numerator_significand_patterns=len(admitted),
    exact_decoder_cases=decoder_cases,bit_scan_domain=list(range(1,33)),maximum_loose_factor_radius=maximum,positive_horner_radius_maximum=positive_max,negative_factor_radius_maximum=negative_max,exact_positive_horner_exponent_cases=positive_cases,exact_negative_factor_exponent_cases=negative_cases,
    factor_root_domain_radius_limit=1<<20,direct_inverse_root_error_q63=str(inverse_error),direct_inverse_root_radius=24,
    cached_radius_limit=511,reference_cpp_sha256=sha(reference),raw_assembly_sha256=sha(work/'source/code/native_eabi_m0_pow_root64.inc'),
    producer_sha256=sha(__file__),hardware_accessed=False,root_promoted=False,
    scope='Source-bound analytical error/domain/overflow and guarded midpoint certificates for the changed fast paths, combined with unchanged retained128 arithmetic bounds. Finite ARM/MPFR, object/resource/isolation/cache checks are separate. General fallback termination and all-input physical speed remain unproved.')
(work/'certificate.json').write_text(json.dumps(result,indent=2)+'\n')
print('PASS: point root error',float(point),'<2; full128 algebra unchanged; factor radius<=',maximum,'; exact decoder domain.',flush=True)

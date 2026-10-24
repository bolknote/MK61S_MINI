"""Exact source-bound Q77 near-ln arithmetic and table certificates."""
from pathlib import Path
from fractions import Fraction as F
import ast
import hashlib
import json
import re
import struct
import sys

sys.dont_write_bytecode=True
W=Path(__file__).resolve().parent
ROOT=W.parents[1]
BASE=ROOT/'.build/m0-ln-raw-cold-entry-20261024'
sys.path.insert(0,str(ROOT/'tests'))
from check_stm32_vectors import ElfImage

sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
source=(W/'native_eabi_m0_log70.inc').read_text()
assert sha(W/'native_eabi_m0_log70.inc')=='84213d8eb6c7841b48a834cd2304eb8c0ccd6bedc150ee84fd01cf39a8a7e06b'
start=source.index('#if defined(MK61_M0_RP2040_EABI) && MK61_M0_RP2040_EABI\nstatic constexpr int8_t ln_near_q77_delta')
end=source.index('__attribute__((optimize("Os"),noinline)) static double ln_near_interval(',start)
assert source[end-7:end]=='#endif\n'
rest=source[:start]+source[end:]
dispatch='''#if defined(MK61_M0_RP2040_EABI) && MK61_M0_RP2040_EABI
    return ln_near_interval77(x,b);
#else
    return ln_near_interval(x,b);
#endif'''
assert rest.count(dispatch)==1
assert rest.replace(dispatch,'    return ln_near_interval(x,b);')==(BASE/'native_eabi_m0_log70.inc').read_text()

h=F(1,16000);scale=1<<77
product54=F(17,32)+F(1,1<<22)
old_argument=product54+F(1,128)
initial=128*old_argument
argument=F(1,2)+initial*8320*F(3,4)/(1<<24)
assert argument==F(9030828227,17179869184) and argument<F(526,1000)
assert initial*8320<1<<20
assert initial*8320*2080+(1<<23)<1<<31
assert h-F(1,16130)>argument/scale
square=1+F(1,1<<13)
cube=F(1,2)+F(1,512)+h*square
fourth=F(1,2)+(2*scale*h*h*square+square*square)/scale+(2*(scale*h*h+square)/(1<<19)+1)/(1<<39)
fifth=F(1,2)+F(1,32)+h*fourth
remainder=scale*h**6/(6*(1-h))
base=argument*h/(1-h)+F(1,2)+square/2+cube/3+fourth/4+fifth/5+remainder
full=base+argument+F(104,60)
assert base<F(3,2) and full<4
linear_u=F((1<<38),scale)+argument/scale
linear_remainder=scale*linear_u**2/(2*(1-linear_u))
linear_base=F(1,2)+linear_remainder
assert linear_base<F(751,1000) and linear_base<base
assert 'U correction=h;' in source and 'if(h>(U(1)<<38))' in source
assert scale*h+argument<1<<64
assert scale*h*h+square<1<<50
assert scale*h**3+cube<9*(1<<32)
assert scale*h**4+fourth<1<<22
assert scale*h**5+fifth<145
assert ((scale*h)/(1<<48)).__ceil__()*((scale*h**4+fourth)/(1<<6)).__ceil__()+(1<<22)<1<<31

# The one-MUL correction uses an affine denominator approximation. With
# den=8192+d, 2^24/den=2048-d/4+d^2/(4den); its integer approximation
# 4096-floor(den/4) differs by strictly less than3/4 for every used den.
for den in range(8065,8321):
    assert abs(F(4096-(den>>2))-F(1<<24,den))<F(3,4)
assert (F(131072+65537+1,1<<27))<F(1,512)
assert F(1,64)+F(1,1<<22)<F(1,32)
for hi in range(9):assert (hi*171)>>9==hi//3
for n in range(256):assert ((n+2)*205)>>10==(n+2)//5

path=ROOT/'tools/generate_m0_log_table.py'
text=path.read_text()
nodes=[n for n in ast.parse(text).body if isinstance(n,ast.FunctionDef) and n.name in ('nearest','logarithm')]
env={'Fraction':F}
exec(compile(ast.Module(body=nodes,type_ignores=[]),str(path),'exec'),env)
image=ElfImage(W/'candidate.elf')
def symbol_data(part,size):
    name=next(n for n in image.symbols if part in n and image.sizes.get(n)==size)
    a=image.symbols[name]
    section=next(s for s in image.named_sections.values() if s[3]<=a<s[3]+s[5])
    return image.bytes_at(section)[a-section[3]:a-section[3]+size]
table=symbol_data('log_near_table',4096)
corrections=symbol_data('ln_near_q77_delta',256)
reciprocals=[]
for index in range(256):
    reciprocal,old=struct.unpack_from('<QQ',table,16*index)
    c=F(8065+index,8192)
    assert reciprocal==env['nearest'](F(1<<62)/c)
    assert old==env['logarithm'](c if c>=1 else 1/c,70)
    new=env['logarithm'](c if c>=1 else 1/c,77)
    delta=struct.unpack_from('<b',corrections,index)[0]
    assert -64<=delta<=64 and new==(old<<7)+delta
    assert 0<=((old<<7)&((1<<64)-1))+delta<1<<64
    reciprocals.append(reciprocal)
array=source[source.index('static constexpr int8_t ln_near_q77_delta'):]
array=array[array.index('{')+1:array.index('};')]
assert [int(x) for x in re.findall(r'-?\d+',array)]==list(struct.unpack('<256b',corrections))

for token in ('const uint32_t correction=(magnitude*(4096U-(den>>2))+(1U<<23))>>24;',
              'h+=U(int64_t(signed_correction));',
              'residue=int32_t((uint32_t(delta)<<28)-uint32_t(h)*den);',
              'const uint32_t qh=(hi*171U)>>9;',
              'cp+=uint32_t((uint32_t(h)>>16)*(zc>>16));',
              'cp+=uint32_t((t>>16)*((uint32_t(z)>>2)&65535U));',
              'const U cube=(cp+(U(1)<<26))>>27;',
              'const uint32_t zr=uint32_t(z>>19);',
              'const uint32_t fifth=(((t>>16)*(fourth>>6))+(1U<<22))>>23;',
              'const uint32_t fifth_term=((fifth+2U)*205U)>>10;',
              'bias60=5*(-4*r3+(subtract?-even_bias:even_bias))-12*r5;',
              'int32_t(den)*(int32_t(60*distance)-bias60)+60*residue>=90*int32_t(den)',
              'int32_t(den)*(int32_t(60*distance)+bias60)-60*residue>=90*int32_t(den)',
              'U(bias-15)'):
    assert token in source,token

# Coefficient remainder signs are exact; the interval includes every
# possible r2/r3/r4/r5 combination, even unattainable correlations.
biases={5*(-4*r3+s*(6*r2+3*r4))-12*r5 for r2 in (-1,0) for r3 in (-1,0,1) for r4 in (-2,-1,0,1) for r5 in (-2,-1,0,1,2) for s in (-1,1)}
assert max(map(abs,biases))==104
checks=0
for den in range(8065,8321):
    edge=(argument*den).__ceil__()-1
    for r in (-edge,-1,0,1,edge):
        for bias in biases:
            e=F(bias,60)-F(r,den)
            assert e+base<4 and e-base>-4
            for distance in (1,2,3):
                if den*(60*distance-bias)+60*r>=90*den:assert e+base<distance
                if den*(60*distance+bias)-60*r>=90*den:assert e-base>-distance
                checks+=2
u=F(1,16384)
assert (u-u*u/2)*scale-4>(1<<62)+4
assert 4<256
out=dict(status='PASS_SOURCE_BOUND_Q77_NEAR_LN_TABLE_AND_ERROR_ENCLOSURES',
    source_sha256=sha(W/'native_eabi_m0_log70.inc'),candidate_ELF_sha256=sha(W/'candidate.elf'),
    old_product54_bound=str(product54),old_argument_bound=str(old_argument),initial_Q77_argument_bound=str(initial),
    corrected_argument_bound=str(argument),corrected_argument_bound_float=float(argument),
    internal_argument_RNE_not_required=True,linear_reciprocal_approximation_error_strictly_below='3/4',
    square_bound=str(square),cube_bound=str(cube),fourth_bound=str(fourth),fifth_bound=str(fifth),remainder_bound=str(remainder),
    cube_truncated_product_error_below='1/512',fifth_truncated_product_error_below='1/32',
    remaining_symmetric_base=str(base),remaining_symmetric_base_float=float(base),strict_cold_radius='3/2',
    linear_remaining_base=str(linear_base),linear_remaining_base_float=float(linear_base),linear_h_threshold=1<<38,
    generic_full_bound=str(full),generic_full_bound_float=float(full),strict_fast_radius=4,
    exact_error='(add ? 1:-1)*(bias60/60-residue/den) +/- base',
    coefficient_remainder_ranges=dict(r2=[-1,0],r3=[-1,0,1],r4=[-2,-1,0,1],r5=[-2,-1,0,1,2]),
    maximum_abs_bias60=104,corrected_signed_residue_strictly_below=1<<13,
    input_delta_domain=[0,1<<48],denominator_domain=[8065,8320],cube_hi_word_at_most=8,
    output_width_domain=[63,72],smallest_midpoint_half_gap=512,lower_binade_half_gap=256,
    original_existing_table_bytes_unchanged=True,new_center_correction_bytes=256,
    all256_reciprocal_Q70_Q77_rows_exact_rational=True,correction_initialization_no_carry_or_borrow_verified_all_rows=True,
    finite_integer_interval_checks=checks,exact_midpoints_decline=True,
    inherited_parent_source_unchanged_except_new_RP_near_function_and_call=True,
    source_table_generator_sha256=hashlib.sha256(text.encode()).hexdigest(),
    bare_source_units_required=True,hardware_accessed=False)
(W/'certificate.json').write_text(json.dumps(out,indent=2)+'\n')
print(json.dumps(out,indent=2))

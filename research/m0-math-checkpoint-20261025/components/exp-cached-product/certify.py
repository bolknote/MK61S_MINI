"""Exact exp enclosure and unchanged arithmetic of the cached RAM product."""
from pathlib import Path
from fractions import Fraction as F
import ast
import copy
import hashlib
import json
import struct
import sys

sys.dont_write_bytecode=True
W=Path(__file__).resolve().parent
ROOT=W.parents[1]
P=ROOT/'.build/m0-asin-scaled-bound-v164-20261023'
sys.path.insert(0,str(ROOT/'tests'))
from check_stm32_vectors import ElfImage
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
build=json.loads((W/'build.json').read_text())
source=(W/'candidate/native_eabi_m0.cpp').read_text()
assert sha(W/'candidate/native_eabi_m0.cpp')==build['source_sha256']
assert sha(W/'candidate.elf')==build['candidate_ELF_sha256']
path=ROOT/'tools/certify_m0_exp_fast.py';text=path.read_text()
function=next(n for n in ast.parse(text).body if isinstance(n,ast.FunctionDef) and n.name=='certificate')
function=copy.deepcopy(function)
function.body[-1].value=ast.Call(func=ast.Name(id='locals',ctx=ast.Load()),args=[],keywords=[])
env={'F':F,'Path':Path,'re':__import__('re'),'__file__':str(P/'source/tools/certify_m0_exp_fast.py')}
exec(compile(ast.fix_missing_locations(ast.Module(body=[function],type_ignores=[])),str(path),'exec'),env)
d=env['certificate']()
product_error=F(1,2)+F(1,1<<15)
old=d['total'];new=old-2+product_error
assert old<5 and 3<new<4
maximum_delta=d['scale']*d['h']/(1-d['h'])+d['polynomial']
assert maximum_delta<1<<54
omitted=(65535**2)*(1+2*(1<<16))
assert omitted==(1<<49)-3*(1<<32)+1 and omitted<1<<49
assert F(omitted,1<<64)<F(1,1<<15)

resident=ElfImage(P/'firmware/mk61s-picocalc-pico-h.elf')
table_image=ElfImage(W/'candidate.elf')
def body(image,name):
    address=image.symbols[name]&~1;size=image.sizes[name]
    section=next(s for s in image.named_sections.values() if s[2]&2 and s[3]<=address<s[3]+s[5])
    data=image.bytes_at(section)[address-section[3]:address-section[3]+size]
    assert size and len(data)==size
    return address,data
name='mk61_m0_pow_exp_product'
old_address,old_capsule=body(resident,name)
address,capsule=body(table_image,name)
assert address==old_address==0x20038ee4
assert len(capsule)==len(old_capsule)-14
assert len(old_capsule)==182 and len(capsule)==168
(W/'rounded-product.bin').write_bytes(capsule)
(W/'parent-rounded-product.bin').write_bytes(old_capsule)
wrapper_address,wrapper=body(resident,'mk61_m0_pow_exp_product_flash')
assert len(wrapper)==16
assert wrapper[-4:]==struct.pack('<I',old_address|1)
product_source=(W/'cached-product.S').read_text()
assert sha(W/'cached-product.S')==build['product_source_sha256']
assert product_source.count('muls ')==13
for token in ('push {r4-r7,lr}','sub sp,#20','lsrs r2,r1,#16',
    'lsrs r7,r3,#16','lsls r4,#1\n adcs r5,r6','movs r4,#0',
    'muls r2,r7\n adds r6,r2','add sp,#20','pop {r4-r7,pc}'):
    assert token in product_source,token
# All column4+ contributions are multiples of2^64; moving rounding
# before them changes no result. Column3 r5+round and the first column4
# addition cannot carry out of the word under the original63/54-bit box.
max_limb=(1<<16)-1
column2_max=3*max_limb**2
column3_max=max_limb*63+2*max_limb**2+32767*max_limb
early_rounded_r5_max=(column2_max*(1<<32)+column3_max*(1<<48)+(1<<63))>>64
assert early_rounded_r5_max<1<<18
first_column4_max=early_rounded_r5_max+max_limb*63
assert first_column4_max<1<<23
assert (20+5*4)%8==0
symbol=next(n for n in table_image.symbols if 'exp_table' in n and 'refine_' not in n and table_image.sizes.get(n)==4096)
a=table_image.symbols[symbol]
s=next(s for s in table_image.named_sections.values() if s[3]<=a<s[3]+s[5])
table=table_image.bytes_at(s)[a-s[3]:a-s[3]+4096]
values=struct.unpack('<512Q',table)
assert list(values)==d['values'] and all((1<<62)<=v<(1<<63) for v in values)

# Existing Q94 exp centres remove the unknown +/-1/2 table error.
refname=next(n for n in table_image.symbols if 'refine_exp_table' in n and table_image.sizes.get(n)==6144)
ra=table_image.symbols[refname]
rs=next(s for s in table_image.named_sections.values() if s[3]<=ra<s[3]+s[5])
refdata=table_image.bytes_at(rs)[ra-rs[3]:ra-rs[3]+6144]
deltas=[]
for i,value62 in enumerate(values):
    row=struct.unpack_from('<3I',refdata,12*i)
    value94=(row[2]<<64)|(row[1]<<32)|row[0]
    assert (2*value94-1)**512<(1<<(95*512+i))<(2*value94+1)**512
    delta32=value94-(value62<<32)
    assert -(1<<31)<delta32<1<<31
    assert row[0]-int(row[0]>>31)*(1<<32)==delta32
    deltas.append(delta32)
assert new-F(1,2)+F(1,1<<33)<F(85,32)
assert 2*new<7
assert values[0]==1<<62
assert list(values)==sorted(values)
assert F(values[1])*(1-maximum_delta/(1<<64))-product_error>(1<<62)
assert 2*(new-F(1,2))<6
assert 0x58000000==11*(1<<27)
assert (1<<63)+(1<<53)+1<(1<<64)-512
packing_checks=0
for retained in (0,1,(1<<20)-1,(1<<52)-1,1<<52,(1<<53)-1):
    for tail in range(1024):
        if tail==512:continue
        q=(retained<<10)|tail
        assert ((q+511+((q>>10)&1))>>10)==(q>>10)+int(tail>512)
        packing_checks+=1

maximum_tiny=F(1,1<<40)
tiny_remainder_sig_bound=F(1<<12)/(1-maximum_tiny)
assert tiny_remainder_sig_bound<4097
assert F(4097,1<<40)<F(1,2)
shifts=[]
for e in range(-54,-40):
    for negative in (False,True):
        shift=-e-int(negative)
        assert 40<=shift<=54 and 8<=shift-32<=22
        assert F(2)**(e+53)/(1-maximum_tiny)<4097
        shifts.append(shift)
for token in ('const U correction=mk61_m0_pow_exp_product_flash(q,below?U(0)-delta:delta);',
    'unsigned error=4;', 'const unsigned guard=error-1U;',
    'if(uint32_t(tail-(512U-guard))<=2U*guard) {',
    'if(m<=UINT64_C(0x3C90000000000000)) return 1.0;',
    'else if(e<-40)',
    'const unsigned shift=unsigned(-e)-unsigned(negative)-32U;',
    'if(tail==half && lo && lo<4097U) return D::Infinity|D::Quiet;',
    'const bool up=tail>half || (tail==half && lo);',
    'if(tail+1U==half && lo>0U-4097U) return D::Infinity|D::Quiet;',
    'U(retained+unsigned(tail>=half))'):
    assert token in source,token
out=dict(status='PASS_SOURCE_BOUND_EXP_CACHED_RAM_PRODUCT_AND_TINY_RNE',
    source_sha256=build['source_sha256'],candidate_ELF_sha256=build['candidate_ELF_sha256'],
    parent_bound=str(old),parent_bound_float=float(old),rounded_product_bound=str(product_error),
    candidate_bound=str(new),candidate_bound_float=float(new),strict_radius=4,normalized_strict_radius=6,
    original_reduction_polynomial_and_all512_table_bounds_rechecked=True,
    exp_table_sha256=hashlib.sha256(table).hexdigest(),maximum_correction_argument=str(maximum_delta),
    rounded_product_argument_domain=dict(a_bits=63,b_bits=54),
    omitted_three_limb_pairs_maximum=str(omitted),omitted_full_product_below='2^49',
    product_proof='All13 limb pairs at columns>=2 are retained; omitted integer<2^49. Half-up integer rounding adds at most1/2, so error<=1/2+2^-15 after>>64.',
    runtime_product_address=hex(address),runtime_product_bytes=len(capsule),
    runtime_product_sha256=hashlib.sha256(capsule).hexdigest(),
    parent_runtime_product_address=hex(old_address),parent_runtime_product_bytes=len(old_capsule),
    parent_runtime_product_sha256=hashlib.sha256(old_capsule).hexdigest(),
    product_source_sha256=build['product_source_sha256'],
    Flash_wrapper_address=hex(wrapper_address),Flash_wrapper_bytes=len(wrapper),
    Flash_wrapper_sha256=hashlib.sha256(wrapper).hexdigest(),Flash_wrapper_not_a_standalone_product=True,
    cached_limbs=['a3 in r2','b3 in preserved r7'],early_rounded_r5_max=early_rounded_r5_max,
    first_column4_sum_max=first_column4_max,early_rounding_commutes_with_all_upper_columns=True,
    product_stack_bytes=40,parent_product_stack_bytes=32,product_16bit_instructions=84,parent_product_16bit_instructions=91,
    tiny_magnitude_domain='2^-54<abs(x)<2^-40',tiny_input_exponents=[-54,-41],
    tiny_remainder='0<exp(x)-1-x<x^2/(2*(1-abs(x))); negative lower x^2*(1/2-abs(x)/6)>0.',
    tiny_remainder_input_significand_units=str(tiny_remainder_sig_bound),tiny_strict_integer_radius=4097,
    tiny_shift_range=[min(shifts),max(shifts)],tiny_output_grid=dict(positive='2^-52',negative='2^-53'),
    tiny_rounding_proof='Positive correction may cross only a below-midpoint cell; decline when its integer distance<4097. Negative displacement correction may cross only an above-midpoint cell, same guard. Exact midpoint chooses upward for positive x, downward displacement for negative x. Remaining margin>=4097 is strict; next midpoint is at least1/2 output unit away.',
    tiny_declines_preserve_original_exp_path=True,new_tables_or_global_RAM=False,
    refined_exp_table_sha256=hashlib.sha256(refdata).hexdigest(),all512_Q62_Q94_exp_centers_rechecked=True,
    delta32_range=[min(deltas),max(deltas)],
    table_removed_remaining_bound=str(new-F(1,2)+F(1,1<<33)),table_removed_remaining_bound_float=float(new-F(1,2)+F(1,1<<33)),
    additional_table_predicate='At distance3(normal), above needs delta32>=-11*2^27; below needs delta32<=11*2^27. Remaining bound+Q94 uncertainty<85/32.',
    normalization_only_index0_proved=True,normalized_table_center_exact=True,normalized_remaining_bound=str(2*(new-F(1,2))),
    accepted_normal_midpoints_excluded=True,exact_integer_packing_identity_checks=packing_checks,
    bare_actual_ARM_primitive_checks_required=True,hardware_accessed=False,whole_math_GO=False)
(W/'certificate.json').write_text(json.dumps(out,indent=2)+'\n')
print(json.dumps(out,indent=2))

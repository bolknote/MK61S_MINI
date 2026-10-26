"""Actual bare ARM tiny-exp, table gate/RNE pack and rounded-product proof."""
from pathlib import Path
from fractions import Fraction as F
import hashlib
import itertools
import json
import random
import struct
import sys

sys.dont_write_bytecode=True
W=Path(__file__).resolve().parent
ROOT=W.parents[1]
Q=ROOT/'.build/m0-float-fma-qualification-20261023'
sys.path.insert(0,str(Q));sys.path.insert(0,str(Q/'support'))
from native_eabi_m0_arm_self_test import Machine,SP
from check_stm32_vectors import ElfImage
from oracles import round_ratio
from unicorn import UC_HOOK_MEM_READ,UC_HOOK_MEM_WRITE

sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
build=json.loads((W/'unit-build.json').read_text());cert=json.loads((W/'certificate.json').read_text())
assert sha(W/'candidate/native_eabi_m0.cpp')==build['source_sha256']==cert['source_sha256']
assert sha(W/'unit.elf')==build['unit_ELF_sha256']
im=ElfImage(W/'unit.elf')
name=next(n for n in im.symbols if 'refine_exp_table' in n and im.sizes.get(n)==6144)
a=im.symbols[name];s=next(s for s in im.named_sections.values() if s[3]<=a<s[3]+s[5])
table=im.bytes_at(s)[a-s[3]:a-s[3]+6144]
assert hashlib.sha256(table).hexdigest()==cert['refined_exp_table_sha256']
product_section=im.bytes_at(im.named_sections['.product'])
assert hashlib.sha256(product_section).hexdigest()==cert['runtime_product_sha256']
parent_product_section=im.bytes_at(im.named_sections['.parent_product'])
assert hashlib.sha256(parent_product_section).hexdigest()==cert['parent_runtime_product_sha256']
m=Machine(W/'unit.elf',True,stack_bytes=512)
accesses=[0]
def access(*args):accesses[0]+=1
m.uc.hook_add(UC_HOOK_MEM_READ|UC_HOOK_MEM_WRITE,access,begin=0xd0000060,end=0xd000007b)
states=[struct.pack('<7I',0,0,0,0,0,0,1),struct.pack('<7I',17,3,17,3,5,2,3)]
calls=tiny_calls=pack_calls=product_calls=0
tiny_accepted=tiny_declined=pack_accepted=pack_declined=endpoints=0
digest=hashlib.sha256();costs=[];product_profile_counts={'audit_product':[],'audit_parent_product':[]}
sentinel=int(build['decline_bits'],16)
def execute(name,a,b=0,fixture=b'\0'*8):
    global calls
    values=[]
    for state_index,state in enumerate(states):
        m.uc.mem_write(0x20000000,fixture);m.uc.mem_write(0xd0000060,state)
        profile=calls%1009==0
        got,_,cost=m.call(name,a,b,count=profile)
        if profile and name in product_profile_counts:
            product_profile_counts[name].append(cost)
            assert cost==(84 if name=='audit_product' else 91),(name,cost)
        assert bytes(m.uc.mem_read(0xd0000060,28))==state
        assert bytes(m.uc.mem_read(0x20000000,8))==fixture
        digest.update(name.encode()+struct.pack('<QQQB',a,b,got,state_index)+fixture)
        if profile:costs.append(cost)
        calls+=1;values.append(got)
    assert values[0]==values[1]
    return values[0]

# All possible linear retained cells in every tiny exponent binade.
# Test exact midpoints and both sides of the conservative4097 guard.
tiny=set()
for e in range(-54,-40):
    for negative in (False,True):
        shift=-e-int(negative)
        lower=(1<<52)>>shift;upper=((1<<53)-1)>>shift
        for retained in range(lower,upper+1):
            midpoint=(retained<<shift)+(1<<(shift-1))
            for delta in (-4098,-4097,-4096,-2,-1,0,1,2,4096,4097,4098):
                sig=midpoint+delta
                if 1<<52<=sig<1<<53:
                    raw=((e+1023)<<52)+(sig-(1<<52))+(int(negative)<<63)
                    magnitude=raw&((1<<63)-1)
                    if magnitude>0x3c90000000000000 and magnitude<0x3d70000000000000:tiny.add(raw)
for raw in sorted(tiny):
    magnitude=raw&((1<<63)-1);e=(magnitude>>52)-1023
    sig=(magnitude&((1<<52)-1))|(1<<52)
    mag=F(sig,1<<(52-e));x=-mag if raw>>63 else mag
    got=execute('audit_tiny',raw);tiny_calls+=2
    if got==(0x7ff0000000000000|(1<<51)):
        tiny_declined+=1;continue
    lower=1+x+mag*mag*(F(1,2)-mag/6)
    upper=1+x+mag*mag/(2*(1-mag))
    for endpoint in (lower,upper):
        assert round_ratio(endpoint.numerator,endpoint.denominator,0,64,False)==got,(hex(raw),hex(got))
        endpoints+=1
    tiny_accepted+=1

# Every existing Q94 table row, both input signs, exact midpoint guards,
# all new distance3 threshold cases, binade carries and normal endpoints.
# Normalization is physically possible only for exact table index0;
# normalized points are even integers.
remaining=F(cert['table_removed_remaining_bound'])
plain=json.loads((W/'certificate.json').read_text())
base_im=ElfImage(W/'candidate.elf')
tn=next(n for n in base_im.symbols if 'exp_table' in n and 'refine_' not in n and base_im.sizes.get(n)==4096)
ta=base_im.symbols[tn];ts=next(s for s in base_im.named_sections.values() if s[3]<=ta<s[3]+s[5])
table62=struct.unpack('<512Q',base_im.bytes_at(ts)[ta-ts[3]:ta-ts[3]+4096])
pack_configurations=0;table_extra_admits=0
for index in range(512):
    row=struct.unpack_from('<3I',table,12*index)
    value94=(row[2]<<64)|(row[1]<<32)|row[0]
    delta32=value94-(table62[index]<<32)
    centre=-F(delta32,1<<32)
    for normalized in ((False,True) if index==0 else (False,)):
        error=6 if normalized else 4;factor=2 if normalized else 1
        lo,hi=((-remaining*factor,remaining*factor) if normalized else
            ((centre-remaining),(centre+remaining)))
        for negative in (False,True):
            n=(-index)&511 if negative else index
            fixture=struct.pack('<2I',n,(1<<31) if negative else 0)
            for tail in (0,1,504,505,506,507,508,509,510,511,512,513,514,515,516,517,518,519,520,1022,1023):
                if normalized and tail&1:continue
                distance=abs(tail-512)
                extra=not normalized and distance==3 and (delta32>=-0x58000000 if tail>512 else delta32<=0x58000000)
                accept=distance>=error or extra
                table_extra_admits+=int(extra)
                retained=(1<<52)+(0,1,1<<51,(1<<52)-1)[pack_configurations%4]
                q=(retained<<10)|tail
                k=(-1022,0,1023)[pack_configurations%3]
                config=(k&0xffffffff)|(int(normalized)<<32)
                got=execute('audit_pack',q,config,fixture);pack_calls+=2
                if not accept:
                    assert got==sentinel,(index,normalized,tail,hex(got));pack_declined+=1
                else:
                    expected=round_ratio(q,1,k-62,64,False)
                    assert got==expected,(index,normalized,tail,hex(got),hex(expected))
                    for err in (lo,hi):
                        value=F(q)-err
                        assert round_ratio(value.numerator,value.denominator,k-62,64,False)==got,(index,normalized,tail,err)
                        endpoints+=1
                    pack_accepted+=1
                pack_configurations+=1

# Scalar integer oracle for the actual existing13-MUL ARM capsule.
# The full product provides an independent error check; retained partial
# sums check every carry and the exact half-up algorithm.
pairs=set()
for a in table62:
    for b in (0,1,65535,65536,(1<<32)-1,1<<32,(1<<53)-1,1<<53,(1<<54)-1):pairs.add((a,b))
limbs=(0,1,65535)
for a0,a1,a2,b0,b1,b2 in itertools.product(limbs,repeat=6):
    for a3 in (0,1,16383,32767):
        for b3 in (0,1,31,63):
            pairs.add((a0|(a1<<16)|(a2<<32)|(a3<<48),b0|(b1<<16)|(b2<<32)|(b3<<48)))
rng=random.Random(0xE4F13A)
for _ in range(8192):pairs.add((rng.randrange(1<<63),rng.randrange(1<<54)))
product_error=F(cert['rounded_product_bound'])
for a,b in sorted(pairs):
    a0,a1=a&65535,(a>>16)&65535;b0,b1=b&65535,(b>>16)&65535
    omitted=a0*b0+((a0*b1+a1*b0)<<16)
    expected=(a*b-omitted+(1<<63))>>64
    got=execute('audit_product',a,b);product_calls+=2
    old=execute('audit_parent_product',a,b);product_calls+=2
    assert got==old,(hex(a),hex(b),got,old)
    assert got==expected,(hex(a),hex(b),got,expected)
    assert abs(F(got)-F(a*b,1<<64))<=product_error
assert calls==tiny_calls+pack_calls+product_calls and accesses[0]==0
assert tiny_accepted and tiny_declined and pack_accepted and pack_declined and table_extra_admits
out=dict(status='PASS_BARE_EXP_TINY_TABLE_PACK_PRODUCT_ARM_AND_RATIONAL_ENDPOINTS',
    source_sha256=build['source_sha256'],candidate_ELF_sha256=build['candidate_ELF_sha256'],unit_ELF_sha256=build['unit_ELF_sha256'],
    actual_ARM_calls=calls,tiny_ARM_calls=tiny_calls,tiny_distinct_inputs=len(tiny),tiny_accepted=tiny_accepted,tiny_declined=tiny_declined,
    pack_ARM_calls=pack_calls,pack_configurations=pack_configurations,pack_accepted=pack_accepted,pack_declined=pack_declined,
    new_table_gate_configurations=table_extra_admits,all512_existing_table_rows_and_both_signs=True,
    normalized_only_index0_and_even_points=True,normal_k_cases=[-1022,0,1023],
    product_ARM_calls=product_calls,product_distinct_pairs=len(pairs),product_matches_full_error_and_retained_integer_oracles=True,
    candidate_product_ARM_calls=2*len(pairs),parent_product_ARM_calls=2*len(pairs),
    new_and_old_product_bit_identical_on_all_pairs=True,profiled_product_instruction_counts=product_profile_counts,
    rational_RNE_endpoint_checks=endpoints,SIO_accesses=accesses[0],both_SIO_states_and_input_fixture_preserved=True,
    PCS_SP_bounded_writes_every_call=True,observed_stack_bytes=SP-m.stack_lowest,
    profiled_instruction_range=[min(costs),max(costs)],transcript_sha256=digest.hexdigest(),
    full_firmware_or_ROM_loaded=False,hardware_accessed=False,new_public_candidate_calls=0,
    scope='Literal helper/pack source and actual168-byte candidate RAM product against integer oracles and182-byte parent RAM body; synthetic intervals and internal operand boxes are not additional public exp inputs.')
(W/'unit-proof.json').write_text(json.dumps(out,indent=2)+'\n')
print(json.dumps(out,indent=2))

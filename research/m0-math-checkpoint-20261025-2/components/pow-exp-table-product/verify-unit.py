"""Test actual Thumb table entry: all roots, integer bounds, PCS and NZCV."""
from collections import Counter
from pathlib import Path
import json,random,sys
sys.dont_write_bytecode=True
from harness import *
from unicorn.arm_const import UC_ARM_REG_XPSR,UC_ARM_REG_R12

e=images['candidate'];m=Machine(W/'candidate.elf',True)
assert not m.rom_models and not m.rom_initializers
old=e.symbols['mk61_m0_pow_exp_product']&~1
entry=e.symbols['mk61_m0_pow_exp_table_product']&~1
wrapper=e.symbols['mk61_m0_pow_exp_table_product_flash']&~1
assert e.sizes['mk61_m0_pow_exp_product']==154 and entry==old+154
assert e.sizes['mk61_m0_pow_exp_table_product']==20
assert e.sizes['mk61_m0_pow_exp_table_product_flash']==16
parent=ElfImage(C/'candidate.elf');s=parent.named_sections['.product_ram']
assert bytes(m.uc.mem_read(old,154))==parent.bytes_at(s)[:154]
roots,certificate=table();rng=random.Random(0x61427025)
edges=list(range(8))+[(1<<32)-1,1<<32,(1<<32)+1,(1<<53)-1,1<<53,(1<<54)-1]
pairs={(a,b) for a in roots for b in edges}
pairs.update((a,rng.getrandbits(54)) for a in roots for _ in range(8))
full_edges={0,(1<<64)-1}
for k in range(65):
    full_edges.update(v for v in [(1<<k)-2,(1<<k)-1,1<<k,(1<<k)+1,(1<<k)+2] if 0<=v<1<<64)
pairs.update((1<<62,b) for b in full_edges)
pairs.update((1<<62,rng.getrandbits(64)) for _ in range(4096))
tests=[(a,b,0) for a,b in sorted(pairs)]
tests.extend((roots[i],b,flags) for i in [0,1,2,255,511]
             for b in [0,1,2,3,(1<<54)-1,(1<<64)-1] for flags in range(16))
active={};sample_trace=[];trace_enabled=False
def initialize(uc,pc,size,user):
    if pc==active.get('entry'):
        uc.reg_write(UC_ARM_REG_XPSR,0x01000000|(active['flags']<<28))
        uc.reg_write(UC_ARM_REG_R12,active['r12'])
for address in (old,entry,wrapper):
    m.uc.hook_add(UC_HOOK_CODE,initialize,begin=address,end=address)
def trace(uc,pc,size,user):
    if trace_enabled:
        assert old<=pc<old+154 or entry<=pc<entry+20 or wrapper<=pc<wrapper+16,hex(pc)
        sample_trace.append(pc)
m.uc.hook_add(UC_HOOK_CODE,trace)

costs=Counter();integer_bound_checks=dyadic_checks=fresh_calls=0
for i,(a,b,flags) in enumerate(tests):
    if i%2048==0:print('bare-product',i,'/',len(tests),flush=True)
    result={};trace_enabled=(i<64 or i>=len(tests)-480)
    for name,address in [('old',old),('gate',entry)]:
        active.update(entry=address,flags=flags,r12=rng.getrandbits(32))
        value,_,cost=m.call('mk61_m0_pow_exp_product' if name=='old' else 'mk61_m0_pow_exp_table_product',a,b,count=True)
        result[name]=(value,cost,m.uc.reg_read(UC_ARM_REG_R12));fresh_calls+=1
    x,y=result['old'],result['gate']
    assert x[0]==y[0] and x[1]==77
    assert y[1]==(10 if a==1<<62 else 79)
    if a!=1<<62:assert x[2]==y[2]
    if b<1<<54:
        assert abs((y[0]<<64)-a*b)<=((1<<63)+(1<<49))
        integer_bound_checks+=1
    if a==1<<62:
        assert y[0]==(b>>2)+bool(b&2)
        dyadic_checks+=1
    costs[y[1]]+=1

for a,b in [(roots[i],b) for i in [0,1,255,511] for b in edges]:
    active.update(entry=wrapper,flags=15,r12=0xdeadbeef);trace_enabled=True
    value,_,cost=m.call('mk61_m0_pow_exp_table_product_flash',a,b,count=True);fresh_calls+=1
    assert cost==(15 if a==1<<62 else 84)
    active.update(entry=entry,flags=0,r12=0)
    reference,_,_=m.call('mk61_m0_pow_exp_table_product',a,b,count=True);fresh_calls+=1
    assert value==reference
out=dict(status='PASS_ACTUAL_TABLE_PRODUCT_INTEGER_EQUIVALENCE_AND_PCS',candidate_ELF_sha256=sha(W/'candidate.elf'),
    table_certificate=certificate,distinct_pairs=len(pairs),test_pairs_with_flag_variants=len(tests),
    all16_incoming_NZCV_variants=True,arbitrary_initial_R12=True,
    actual_ARM_calls=fresh_calls,valid63x54_integer_error_bound_checks=integer_bound_checks,
    dyadic_full64_exact_shift_checks=dyadic_checks,gate_instruction_histogram=dict(costs),
    generic77body_byte_identical_parent=True,generic_extra_R12_fraction_identical=True,
    dyadic_R12_not_part_of_scalar_ABI=True,wrapper_cost_instructions=5,
    SP_PC_callee_saved_and_bounded_stack_writes_every_call=True,
    observed_stack_written_bytes=SP-m.stack_lowest,bare_firmware_and_ROM_not_mapped=True,
    sampled_execution_PC_count=len(sample_trace),numeric_oracle='exact host integers, not MPFR',
    hardware_accessed=False)
(W/'unit-proof.json').write_text(json.dumps(out,indent=2)+'\n')
print(json.dumps(out,indent=2))

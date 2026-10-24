"""Bare ARM core arithmetic against independent exact rational bounds."""
from pathlib import Path
from fractions import Fraction as F
from collections import Counter
import hashlib
import json
import random
import struct
import sys

sys.dont_write_bytecode=True
W=Path(__file__).resolve().parent
ROOT=W.parents[1]
sys.path.insert(0,str(ROOT/'.build/m0-float-fma-qualification-20261023/support'))
from native_eabi_m0_arm_self_test import Machine,SP
from unicorn import UC_HOOK_CODE,UC_HOOK_MEM_READ,UC_HOOK_MEM_WRITE
from unicorn.arm_const import UC_ARM_REG_SP

proof=json.loads((W/'certificate.json').read_text());b=json.loads((W/'core-unit-build.json').read_text())
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
assert sha(W/'native_eabi_m0_log70.inc')==proof['source_sha256']==b['source_sha256']
assert sha(W/'core-unit.elf')==b['unit_ELF_sha256']
assert sha(W/'product54-capsule.bin')==b['product54_capsule_sha256']
m=Machine(W/'core-unit.elf',True,stack_bytes=256)
m.uc.mem_write(0x10010000,(W/'product54-capsule.bin').read_bytes())
functions=('audit_h','audit_r','audit_third','audit_square','audit_cube','audit_fourth','audit_fifth')
ranges=[(m.elf.symbols[n]&~1,(m.elf.symbols[n]&~1)+m.elf.sizes[n]) for n in functions]+[(0x10010000,0x10010000+184)]
accesses=[0];capsule_entries=[0]
def access(*args):accesses[0]+=1
def code(uc,address,size,user):
    assert any(a<=address and address+size<=z for a,z in ranges),hex(address)
    if address==0x10010000:
        assert uc.reg_read(UC_ARM_REG_SP)%8==0
        capsule_entries[0]+=1
m.uc.hook_add(UC_HOOK_CODE,code)
m.uc.hook_add(UC_HOOK_MEM_READ|UC_HOOK_MEM_WRITE,access,begin=0xd0000060,end=0xd000007b)
states=[struct.pack('<7I',0,0,0,0,0,0,1),struct.pack('<7I',17,3,17,3,5,2,3)]
digest=hashlib.sha256();counts=Counter();costs=[]
def call(name,a,c=0):
    results=[]
    for j,state in enumerate(states):
        m.uc.mem_write(0xd0000060,state)
        got,_,cost=m.call(name,a,c,count=(sum(counts.values())%1021==0))
        assert bytes(m.uc.mem_read(0xd0000060,28))==state
        digest.update(name.encode()+struct.pack('<QQQB',a,c,got,j));results.append(got);counts[name]+=1
        if cost:costs.append(cost)
    assert results[0]==results[1]
    return results[0]

rng=random.Random(0x77A4170);argument=F(proof['corrected_argument_bound']);S=1<<77
pairs=[];hvalues={0,1,(1<<32)-1,1<<32,(1<<38)-1,1<<38,(1<<38)+1,int(F(S,16000))-1}
for den in range(8065,8321):
    for delta in (0,1,2,511,512,513,1023,1024,1025,(1<<47)-512,1<<47,(1<<47)+512,(1<<48)-1024,(1<<48)-1,1<<48,rng.randrange(1<<48)):
        h=call('audit_h',delta,den)
        r=call('audit_r',delta,den)
        if r>>63:r-=1<<64
        H=F(delta<<28,den)
        assert abs(F(h)-H)<argument,(delta,den,h,str(H))
        assert r==(delta<<28)-h*den and abs(r)<1<<13
        pairs.append((delta,den));hvalues.add(h)
for _ in range(2048):hvalues.add(rng.randrange(int(F(S,16000))))
for h in sorted(hvalues):
    z=call('audit_square',h)
    assert abs(F(z)-F(h*h,S))<F(proof['square_bound'])
    cube=call('audit_cube',h,z)
    assert abs(F(cube)-F(h*z,S))<F(1,2)+F(1,512)
    fourth=call('audit_fourth',z)
    bound=F(1,2)+(2*F(z,1<<19)+1)/(1<<39)
    assert abs(F(fourth)-F(z*z,S))<bound
    fifth=call('audit_fifth',h,fourth)
    assert abs(F(fifth)-F(h*fourth,S))<F(1,2)+F(1,32)

third_values=set()
for high in range(9):
    for low in (0,1,2,3,4,5,0xffff,0x10000,0x7fffffff,0x80000000,0xfffffffe,0xffffffff):third_values.add((high<<32)|low)
for _ in range(8192):third_values.add(rng.randrange(9<<32))
for a in sorted(third_values):
    q,r=divmod(a,3)
    assert call('audit_third',a)==q+int(r>=2)
assert accesses[0]==0 and capsule_entries[0]==4*len(pairs)
out=dict(status='PASS_EXACT_Q77_CORE_BARE_ARM_RATIONAL_BOUNDS_AND_INTEGER_THIRDS',
    source_sha256=proof['source_sha256'],candidate_ELF_sha256=b['candidate_ELF_sha256'],unit_ELF_sha256=b['unit_ELF_sha256'],
    actual_ARM_calls=sum(counts.values()),function_call_counts=dict(counts),argument_pairs=len(pairs),all256_denominators=True,
    product_configurations=len(hvalues),third_configurations=len(third_values),product54_capsule_entry_calls=capsule_entries[0],
    capsule_entry_SP8_every_call=True,executed_PC_restricted_to_exact_units_and184Bcapsule=True,
    SIO_accesses=accesses[0],both_SIO_states_preserved=True,PCS_SP_bounded_writes_every_call=True,
    corrected_argument_RNE_not_claimed=True,all_argument_bounds_and_exact_residues_pass=True,
    all_product_rational_bounds_pass=True,all_thirds_exact_integer_RNE=True,
    observed_stack_bytes=SP-m.stack_lowest,profiled_instruction_range=[min(costs),max(costs)],
    transcript_sha256=digest.hexdigest(),full_firmware_or_ROM_loaded=False,hardware_accessed=False)
(W/'core-unit-proof.json').write_text(json.dumps(out,indent=2)+'\n')
print(json.dumps(out,indent=2))

"""Exercise all sign/exponent fields through the exact ARM classifier."""
from pathlib import Path
from collections import Counter
import hashlib
import json
import struct
import sys

sys.dont_write_bytecode=True
W=Path(__file__).resolve().parent
ROOT=W.parents[1]
sys.path.insert(0,str(ROOT/'.build/m0-float-fma-qualification-20261023/support'))
from native_eabi_m0_arm_self_test import Machine,SP
from unicorn import UC_HOOK_MEM_READ,UC_HOOK_MEM_WRITE

b=json.loads((W/'entry-unit-build.json').read_text())
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
assert sha(W/'native_eabi_m0_log70.inc')==b['source_sha256']
assert sha(W/'entry-unit.elf')==b['unit_ELF_sha256']
m=Machine(W/'entry-unit.elf',True,stack_bytes=64)
accesses=[0]
def access(*args):accesses[0]+=1
m.uc.hook_add(UC_HOOK_MEM_READ|UC_HOOK_MEM_WRITE,access,begin=0xd0000060,end=0xd000007b)
states=[struct.pack('<7I',0,0,0,0,0,0,1),struct.pack('<7I',17,3,17,3,5,2,3)]
digest=hashlib.sha256();calls=0;classes=Counter();special_costs={}
for field in range(4096):
    exponent=field&2047
    # ARM classification uses only field; early returns additionally test
    # low==0 and high fraction zero. These four representatives include
    # both zero/nonzero classes, the quiet bit and the maximal payload.
    for fraction_hi in (0,1,1<<19,(1<<20)-1):
        for low in (0,1,0x80000000,0xffffffff):
            raw=(field<<52)+(fraction_hi<<32)+low
            if raw&((1<<63)-1)==0:
                expected=0xfff0000000000000;kind='zero'
            elif raw==0x7ff0000000000000:
                expected=raw;kind='positive_infinity'
            elif field<2048 and 1<=exponent<=2046:
                expected=raw^0x13579bdf2468ace0;kind='positive_normal'
            else:
                expected=raw^0xfdb97531eca86420;kind='cold_forwarding'
            for state_index,state in enumerate(states):
                m.uc.mem_write(0xd0000060,state)
                profile=kind in ('zero','positive_infinity') or calls%4093==0
                got,_,cost=m.call('mk61_m0_ln',raw,count=profile)
                assert got==expected,(hex(raw),kind,hex(got),hex(expected))
                assert bytes(m.uc.mem_read(0xd0000060,28))==state
                if kind in ('zero','positive_infinity'):
                    special_costs[f'{raw:016X}']=cost
                digest.update(struct.pack('<QQB',raw,got,state_index));calls+=1
            classes[kind]+=1
assert calls==131072 and accesses[0]==0
assert special_costs=={'0000000000000000':6,'8000000000000000':6,'7FF0000000000000':8}
out=dict(status='PASS_EXACT_NAKED_LN_IEEE_ENTRY_ALL_BIT_CLASSES_ARM',source_sha256=b['source_sha256'],unit_ELF_sha256=b['unit_ELF_sha256'],exact_fragment_sha256=b['exact_fragment_sha256'],
    raw_inputs=65536,actual_ARM_calls=calls,classes=dict(classes),all4096_sign_exponent_fields=True,
    zero_nonzero_fraction_low_quiet_payload_classes=True,all_forwarded_input_bits_preserved=True,
    early_return_instructions=special_costs,SIO_accesses=accesses[0],both_SIO_states_preserved=True,
    PCS_SP_bounded_writes_every_call=True,observed_stack_bytes=SP-m.stack_lowest,
    transcript_sha256=digest.hexdigest(),firmware_or_ROM_mapped=False,
    scope='Exact naked entry with tagged leaf targets, not public ln numerical qualification.',hardware_accessed=False)
(W/'entry-unit-proof.json').write_text(json.dumps(out,indent=2)+'\n')
print(json.dumps(out,indent=2))

#!/usr/bin/env python3
"""Check the RP2040 exact Q70 log residual and pending-divider isolation."""
import argparse
import hashlib
import json
from pathlib import Path
import random
import struct

from native_eabi_m0_arm_self_test import Machine,SP
from unicorn import UC_HOOK_MEM_READ
from unicorn.arm_const import UC_ARM_REG_PC

p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--elf',type=Path,required=True)
p.add_argument('--samples',type=int,default=100000)
p.add_argument('--json',type=Path,required=True)
a=p.parse_args();assert a.samples>=0
m=Machine(a.elf,True)
assert 'mk61_m0_log_ratio70' in m.elf.symbols
assert ((4095-1)<<20)+(1<<20)-1<1<<32
latency_checks=[0]
if 'mk61_m0_log_ratio70_slow' in m.elf.symbols:
    start=m.elf.symbols['mk61_m0_log_ratio70']&~1
    end=start+m.elf.sizes['mk61_m0_log_ratio70']
    def check_latency(uc,access,address,size,value,user):
        written=m.divisor_write_pc
        if not start<=written<end:return
        pc=uc.reg_read(UC_ARM_REG_PC)
        block=bytes(uc.mem_read(written+2,pc-written-2))
        assert len(block)%2==0
        cycles=0
        for offset in range(0,len(block),2):
            op=int.from_bytes(block[offset:offset+2],'little')
            if op==0xe7ff:cycles+=2  # Taken branch to the next instruction.
            elif op<0x4400:cycles+=1  # Independent Thumb-1 ALU instruction.
            elif op==0x6958:cycles+=1  # Earlier remainder read; conservative minimum.
            else:raise AssertionError(('Unexpected divider wait instruction',hex(op)))
        assert cycles>=8,('Early SIO result read',hex(address),cycles)
        latency_checks[0]+=1
    m.uc.hook_add(UC_HOOK_MEM_READ,check_latency,begin=0xD0000070,end=0xD0000077)
pairs=[(delta,den) for den in range(2049,4096,2)
       for delta in [0,1,(1<<41)-1,1<<41]]
for bit in range(42):
    for delta in [(1<<bit)-1,1<<bit,(1<<bit)+1]:
        if delta<=1<<41:
            pairs +=[(delta,den) for den in [2049,2051,3071,3073,4093,4095]]
rng=random.Random(0x5370)
pairs += [(rng.randrange((1<<41)+1),2049+2*rng.randrange(1024)) for _ in range(a.samples)]
digest=hashlib.sha256()
for delta,den in pairs:
    got=m.call('mk61_m0_log_ratio70',delta,den)[0]
    assert got==(delta<<29)//den,(delta,den,got,(delta<<29)//den)
    digest.update(struct.pack('<QIQ',delta,den,got))
pending=struct.pack('<7I',17,3,0,0,5,2,3)
dirty_calls=0
for delta in [0,1,(1<<41)-1,1<<41]:
    for den in [2049,2051,3071,3073,4093,4095]:
        m.uc.mem_write(0xD0000060,pending)
        assert m.call('mk61_m0_log_ratio70',delta,den)[0]==(delta<<29)//den
        assert bytes(m.uc.mem_read(0xD0000060,len(pending)))==pending
        dirty_calls+=1
m.uc.mem_write(0xD0000078,struct.pack('<I',1))
counts=[dict(delta=delta,den=den,instructions=m.call('mk61_m0_log_ratio70',delta,den,count=True)[2])
        for delta,den in [(0,2049),(1<<41,2049),(1<<41,4095)]]
report=dict(status='PASS',cases=len(pairs),dirty_sio_checks=dirty_calls,
    hardware_latency_checks=latency_checks[0],
    elf_sha256=hashlib.sha256(a.elf.read_bytes()).hexdigest(),
    domain='delta in0..2^41; all odd den in2049..4095 at four endpoints, limb boundaries and random pairs.',
    proof='Exact base2^20 long division of delta*2^29; every32-bit numerator fits, quotient limbs concatenate without truncation. Absolute Q70 error<1.',
    abi='Every call checks R4-R11,SP and bounded stack writes; dirty SIO state unchanged.',
    maximum_stack_bytes=SP-m.stack_lowest,sample_instructions=counts,
    result_sha256=digest.hexdigest())
a.json.parent.mkdir(parents=True,exist_ok=True)
a.json.write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2),flush=True)

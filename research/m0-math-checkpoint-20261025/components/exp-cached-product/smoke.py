"""Short public exp probe, exact tiny boundaries and original16 losses."""
from pathlib import Path
from collections import Counter
import hashlib
import json
import random
import struct
import sys

sys.dont_write_bytecode=True
W=Path(__file__).resolve().parent
ROOT=W.parents[1]
P=ROOT/'.build/m0-asin-scaled-bound-v164-20261023'
Q=ROOT/'.build/m0-float-fma-qualification-20261023'
sys.path.insert(0,str(Q));sys.path.insert(0,str(Q/'support'))
from native_eabi_m0_arm_self_test import Machine,SP
from check_stm32_vectors import ElfImage
from m0_mpfr_oracle import Oracle,bits
from oracles import equal

ROM=ROOT/'research/rp2040-memset-2026-10-21/capture/bootrom.bin'
ELF=P/'firmware/mk61s-picocalc-pico-h.elf'
REF=ROOT/'.build/m0-v138-execution-20261023/reference/reference.elf'
b=json.loads((W/'build.json').read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
assert sha(W/'candidate/native_eabi_m0.cpp')==b['source_sha256']
assert sha(W/'candidate.elf')==b['candidate_ELF_sha256']
machines={'resident':Machine(ELF,True,bootrom=ROM),'Qfplib':Machine(REF,True)}
for label in ('control','candidate'):
    m=Machine(ELF,True,bootrom=ROM);image=ElfImage(W/(label+'.elf'));image.load(m.uc)
    m.elf.symbols[label+'_exp']=image.symbols['mk61_m0_exp'];machines[label]=m
old=[r for r in json.loads((P/'slower-inputs.json').read_text())['rows'] if r['operation']=='exp']
jobs={int(r['x'],16):'historical16' for r in old}
def add(raw,group):
    if 0<=raw<1<<64:jobs.setdefault(raw,group)
for raw in (0,1,2,(1<<51),(1<<52)-1,1<<52,0x7fefffffffffffff,
            0x7ff0000000000000,0x7ff0000000000001,0x7ff8000000000000,0x7fffffffffffffff):
    for sign in (0,1<<63):add(raw|sign,'IEEE')
for raw in (bits(2**-54),bits(2**-53),bits(3*2**-54),bits(2**-40)):
    for sign in (0,1<<63):
        for step in range(-16,17):add((raw+step)|sign,'tiny_domain_threshold_neighbors')
for e in range(-54,-40):
    for negative in (False,True):
        shift=-e-int(negative)
        lo=(1<<52)>>shift;hi=((1<<53)-1)>>shift
        for retained in sorted({lo,lo+1,(lo+hi)//2,hi-1,hi}):
            midpoint=(retained<<shift)+(1<<(shift-1))
            for step in (-4098,-4097,-4096,-2,-1,0,1,2,4096,4097,4098):
                sig=midpoint+step
                if 1<<52<=sig<1<<53:
                    raw=((e+1023)<<52)+(sig-(1<<52))+(int(negative)<<63)
                    add(raw,'tiny_all_exponent_midpoint_and_guard_edges')
rng=random.Random(0xE4F120)
for _ in range(1024):add(bits(rng.uniform(-745.2,710)),'new_ordinary_uniform')
for _ in range(1024):
    sign=(1<<63) if rng.getrandbits(1) else 0
    add(sign+rng.randrange(bits(2**-54)+1,bits(2**-40)),'new_tiny_uniform')
for x in (-746,-745.2,-745,-744,-710,-709,0.,1.,-1.,709.,709.78,709.8,710.,1024.):
    for step in (-2,-1,0,1,2):add(bits(x)+step,'normal_endpoint_controls')
jobs={raw:group for index,(raw,group) in enumerate(jobs.items()) if group in ('historical16','IEEE') or group=='new_ordinary_uniform' and index%64==0}
states={'READY':struct.pack('<7I',0,0,0,0,0,0,1),'DIRTY':struct.pack('<7I',17,3,17,3,5,2,3)}
oracle=Oracle();rows=[]
for raw,group in jobs.items():
    if len(rows)%1024==0:print('progress',len(rows),'/',2*len(jobs),flush=True)
    expected=oracle.reference('exp',raw)
    for state_name,state in states.items():
        outputs,counts,correct={},{},{}
        for label,m in machines.items():
            m.uc.mem_write(0xd0000060,state)
            entry='mk61_m0_exp' if label=='resident' else 'qfp_dexp' if label=='Qfplib' else label+'_exp'
            got,_,cost=m.call(entry,raw,count=True)
            outputs[label]=f'{got:016X}';counts[label]=cost;correct[label]=equal(got,expected,64)
            if label!='Qfplib':assert correct[label],(label,hex(raw),hex(got),hex(expected))
            after=bytes(m.uc.mem_read(0xd0000060,28))
            if state_name=='DIRTY':assert after==state
            else:assert not(struct.unpack('<7I',after)[6]&2)
        assert outputs['candidate']==outputs['control']==outputs['resident']
        assert counts['control']==counts['resident'],(hex(raw),state_name,counts)
        rows.append(dict(x=f'{raw:016X}',group=group,SIO=state_name,expected=f'{expected:016X}',outputs=outputs,instructions=counts,correct=correct))
loss=lambda r,n:r['correct']['Qfplib'] and r['instructions'][n]>r['instructions']['Qfplib']
report=dict(status='PASS_EXP_CENTER_SHORT_SMOKE_NOT_QUALIFICATION',unique_inputs=len(jobs),public_state_cases=len(rows),
    actual_ARM_calls=4*len(rows),rows=rows,source_sha256=b['source_sha256'],candidate_ELF_sha256=b['candidate_ELF_sha256'],
    control_counts_equal_resident_every_row=True,MPFR_version=oracle.version,
    candidate_stack_bytes=SP-machines['candidate'].stack_lowest,control_stack_bytes=SP-machines['control'].stack_lowest,
    correct_Qfplib_parent_raw_losses=len({r['x'] for r in rows if loss(r,'control')}),
    correct_Qfplib_candidate_raw_losses=len({r['x'] for r in rows if loss(r,'candidate')}),
    new_correct_Qfplib_raw_losses=len({r['x'] for r in rows if loss(r,'candidate') and not loss(r,'control')}),
    hardware_accessed=False)
(W/'smoke.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps({k:v for k,v in report.items() if k!='rows'},indent=2))
for row in rows:
    if row['group']=='historical16' and row['SIO']=='READY':print(row['x'],row['instructions'])

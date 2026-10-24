from pathlib import Path
import json,struct,sys
sys.dont_write_bytecode=True
W=Path(__file__).resolve().parent;ROOT=W.parents[1];Q=ROOT/'.build/m0-float-fma-qualification-20261023';P=ROOT/'.build/m0-asin-scaled-bound-v164-20261023';E=ROOT/'.build/m0-exp-directed-product-20261024'
sys.path[:0]=[str(Q),str(Q/'support'),str(ROOT/'tests')]
from native_eabi_m0_arm_self_test import Machine,SP
from check_stm32_vectors import ElfImage
from m0_mpfr_oracle import Oracle
from oracles import equal
machines={}
for label,folder in [('parent',E),('candidate',W)]:
 m=Machine(P/'firmware/mk61s-picocalc-pico-h.elf',True,bootrom=ROOT/'research/rp2040-memset-2026-10-21/capture/bootrom.bin')
 im=ElfImage(folder/'candidate.elf');im.load(m.uc);m.elf.symbols['test_exp']=im.symbols['mk61_m0_exp'];machines[label]=m
machines['Qfplib']=Machine(ROOT/'.build/m0-v138-execution-20261023/reference/reference.elf',True)
xlist=['3EC1BD399F566C29','3E9049F06E7592B7','BE99A94473BFE892','BED1302C8F3EC2A3','3EF0000000000000','BEF123456789ABCD','3F30000000000000','BF30000000000000','3DF0000000000000','BDF0000000000000','3F2FFFFFFFFFFFFF','BF2FFFFFFFFFFFFF']
states={'READY':struct.pack('<7I',0,0,0,0,0,0,1),'DIRTY':struct.pack('<7I',17,3,17,3,5,2,3)};oracle=Oracle();rows=[]
for x in xlist:
 expected=oracle.reference('exp',int(x,16))
 for state,raw in states.items():
  row={'x':x,'SIO':state,'instructions':{},'correct':{},'outputs':{}}
  for label,m in machines.items():
   m.uc.mem_write(0xd0000060,raw);got,_,cost=m.call('qfp_dexp' if label=='Qfplib' else 'test_exp',int(x,16),count=True)
   row['instructions'][label]=cost;row['correct'][label]=equal(got,expected,64);row['outputs'][label]=f'{got:016X}'
   if label!='Qfplib':assert row['correct'][label],row
   if state=='DIRTY':assert bytes(m.uc.mem_read(0xd0000060,28))==raw
  rows.append(row);print(json.dumps(row),flush=True)
(W/'diagnostic.json').write_text(json.dumps({'status':'DIAGNOSTIC_ONLY_NOT_QUALIFICATION','unique_inputs':len(xlist),'fresh_ARM_calls':len(rows)*3,'actual_MPFR_inputs':len(xlist),'wrong':0,'observed_stack_bytes':{k:SP-m.stack_lowest for k,m in machines.items()},'rows':rows},indent=2)+'\n')

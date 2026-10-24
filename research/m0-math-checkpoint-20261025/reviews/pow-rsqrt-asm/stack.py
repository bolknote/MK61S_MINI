"""Eight focused fresh calls to isolate the changed path's stack peak."""
from pathlib import Path
import json,struct,sys
sys.dont_write_bytecode=True
R=Path('/Users/bolk/Projects/MK61S_MINI');O=Path(__file__).resolve().parent;Q=R/'.build/m0-float-fma-qualification-20261023'
sys.path[:0]=[str(Q),str(Q/'support'),str(R/'tests')]
from native_eabi_m0_arm_self_test import Machine,SP
from check_stm32_vectors import ElfImage
from unicorn import UC_HOOK_MEM_READ,UC_HOOK_MEM_WRITE
saved=json.loads((O/'public-results.json').read_text())['rows']
boundary=next(r for r in saved if r['SIO']=='READY' and r['audit'] and r['audit']['boundary_results'])
fast=next(r for r in saved if r['SIO']=='READY' and r['audit'] and (r['audit']['tail']<488 or r['audit']['tail']>536))
states={'READY':struct.pack('<7I',0,0,0,0,0,0,1),'DIRTY':struct.pack('<7I',17,3,17,3,5,2,3)}
machines={};sio=[]
for label in ['parent','candidate']:
 m=Machine(R/'.build/m0-asin-scaled-bound-v164-20261023/firmware/mk61s-picocalc-pico-h.elf',True,bootrom=R/'research/rp2040-memset-2026-10-21/capture/bootrom.bin')
 ElfImage(R/'.build/m0-exp-cached-product-20261024/candidate.elf').load(m.uc);ElfImage(R/'.build/m0-pow-square-ordinary-20261024/candidate.elf').load(m.uc)
 if label=='candidate':ElfImage(O/'rebuild/candidate.elf').load(m.uc);m.uc.hook_add(UC_HOOK_MEM_READ|UC_HOOK_MEM_WRITE,lambda *x:sio.append(x),begin=0xd0000000,end=0xd0000fff)
 machines[label]=m
rows=[]
for kind,r in [('fast',fast),('exact_boundary',boundary)]:
 a,b=int(r['x'],16),int(r['y'],16)
 for sn,state in states.items():
  for label,m in machines.items():
   m.stack_lowest=SP;m.uc.mem_write(0xd0000060,state);sio.clear();got,_,cost=m.call('_ZN12compact_math3powEdd',a,b,count=True)
   assert got==int(r['expected'],16)
   if label=='candidate':assert not sio and bytes(m.uc.mem_read(0xd0000060,28))==state
   depth=SP-m.stack_lowest
   if kind=='exact_boundary':assert depth==(196 if label=='parent' else 172)
   if kind=='fast' and label=='candidate':assert depth==64
   rows.append(dict(case=kind,x=r['x'],y=r['y'],SIO=sn,implementation=label,stack=depth,instructions=cost,output=f'{got:016X}'))
d=dict(status='PASS_ISOLATED_RSQRT_FAST_AND_EXACT_BOUNDARY_STACK',fresh_ARM_calls=8,new_MPFR_references=0,expected_bits_reused_from_own_public_MPFR=True,old_boundary_stack=196,new_boundary_stack=172,new_fast_stack=64,rows=rows,hardware=False)
(O/'stack-result.json').write_text(json.dumps(d,indent=2)+'\n');print(json.dumps(d,indent=2))

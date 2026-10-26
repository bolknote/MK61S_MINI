from pathlib import Path
import hashlib,json,struct,sys
sys.dont_write_bytecode=True
W=Path(__file__).resolve().parent;ROOT=W.parents[1];P=ROOT/'.build/m0-asin-scaled-bound-v164-20261023';C=ROOT/'.build/m0-exp-adaptive-enclosure-20261024';Q=ROOT/'.build/m0-float-fma-qualification-20261023'
sys.path[:0]=[str(Q),str(Q/'support'),str(ROOT/'tests')]
from native_eabi_m0_arm_self_test import Machine
from check_stm32_vectors import ElfImage
from m0_mpfr_oracle import Oracle
from oracles import equal
machines={}
for label in ('parent','candidate'):
 m=Machine(P/'firmware/mk61s-picocalc-pico-h.elf',True,bootrom=ROOT/'research/rp2040-memset-2026-10-21/capture/bootrom.bin');im=ElfImage((C if label=='parent' else W)/'candidate.elf');im.load(m.uc);m.elf.symbols[label+'_exp']=im.symbols['mk61_m0_exp'];machines[label]=m
machines['Qfplib']=Machine(ROOT/'.build/m0-v138-execution-20261023/reference/reference.elf',True)
states={'READY':struct.pack('<7I',0,0,0,0,0,0,1),'DIRTY':struct.pack('<7I',17,3,17,3,5,2,3)};oracle=Oracle();rows=[]
for old in json.loads((C/'old-margin-controls.json').read_text()):
 x=int(old['x'],16);expected=oracle.reference('exp',x)
 for state_name,state in states.items():
  counts={}
  for label,m in machines.items():
   m.uc.mem_write(0xd0000060,state);got,_,cost=m.call('qfp_dexp' if label=='Qfplib' else label+'_exp',x,count=True)
   assert equal(got,expected,64);counts[label]=cost
  assert counts['Qfplib']==old['Qfplib_instructions']
  rows.append(dict(x=old['x'],SIO=state_name,instructions=counts,new_loss=counts['candidate']>counts['Qfplib']))
new=[r for r in rows if r['new_loss']]
out=dict(status='TARGETED_OLD_SMALL_MARGIN_PERFORMANCE_PROBE',candidate_ELF_sha256=hashlib.sha256((W/'candidate.elf').read_bytes()).hexdigest(),fresh_ARM_calls=3*len(rows),actual_directed_MPFR_inputs=len(rows)//2,wrong=0,new_raw_losses=len({r['x'] for r in new}),rows=rows,new=new,hardware_accessed=False)
(W/'margin-probe.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps({k:v for k,v in out.items() if k not in ('rows',)},indent=2))

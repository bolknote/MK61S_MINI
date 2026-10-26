from pathlib import Path
from collections import Counter
import hashlib,json,random,struct,sys
sys.dont_write_bytecode=True
W=Path(__file__).resolve().parent;ROOT=W.parents[1]
P=ROOT/'.build/m0-asin-scaled-bound-v164-20261023';E=ROOT/'.build/m0-exp-tiny-radius-20261024';Q=ROOT/'.build/m0-float-fma-qualification-20261023'
sys.path[:0]=[str(Q),str(Q/'support'),str(ROOT/'tests')]
from native_eabi_m0_arm_self_test import Machine,SP
from check_stm32_vectors import ElfImage
from m0_mpfr_oracle import Oracle,bits
from oracles import equal
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
jobs={}
for row in json.loads((E/'qualification.json').read_text())['remaining']:jobs.setdefault(int(row['x'],16),'old669')
for row in json.loads((E/'probe.json').read_text())['rows']:jobs.setdefault(int(row['x'],16),'old_smoke')
data=(W/'tiny-inputs.bin').read_bytes();newinputs=[x for (x,) in struct.iter_unpack('<Q',data)]
for i,x in enumerate(newinputs):
 if i%127==0:jobs.setdefault(x,'new_log_cells')
rng=random.Random(0xE32AB1)
for _ in range(512):jobs.setdefault(bits(rng.uniform(-745.2,710.0)),'new_ordinary')
rom=ROOT/'research/rp2040-memset-2026-10-21/capture/bootrom.bin';machines={}
for label in ('parent','candidate'):
 m=Machine(P/'firmware/mk61s-picocalc-pico-h.elf',True,bootrom=rom)
 im=ElfImage((E if label=='parent' else W)/'candidate.elf');im.load(m.uc)
 m.elf.symbols[label+'_exp']=im.symbols['mk61_m0_exp'];machines[label]=m
machines['Qfplib']=Machine(ROOT/'.build/m0-v138-execution-20261023/reference/reference.elf',True)
states={'READY':struct.pack('<7I',0,0,0,0,0,0,1),'DIRTY':struct.pack('<7I',17,3,17,3,5,2,3)}
oracle=Oracle();rows=[];deltas=Counter();calls=0
for index,(x,group) in enumerate(jobs.items()):
 if index%512==0:print('probe',index,'/',len(jobs),flush=True)
 expected=oracle.reference('exp',x)
 for state_name,state in states.items():
  outputs={};counts={};correct={}
  for label,m in machines.items():
   if label=='parent' and group=='new_log_cells':continue
   m.uc.mem_write(0xd0000060,state)
   got,_,cost=m.call('qfp_dexp' if label=='Qfplib' else label+'_exp',x,count=True);calls+=1
   outputs[label]=f'{got:016X}';counts[label]=cost;correct[label]=equal(got,expected,64)
   if label!='Qfplib':assert correct[label],(label,hex(x),hex(got),hex(expected))
   after=bytes(m.uc.mem_read(0xd0000060,28))
   if state_name=='DIRTY':assert after==state
   else:assert not(struct.unpack('<7I',after)[6]&2)
  if 'parent' in outputs:
   assert outputs['parent']==outputs['candidate'];deltas[counts['candidate']-counts['parent']]+=1
  rows.append(dict(x=f'{x:016X}',group=group,SIO=state_name,expected=f'{expected:016X}',outputs=outputs,instructions=counts,correct=correct))
loss=lambda r,n:r['correct']['Qfplib'] and n in r['instructions'] and r['instructions'][n]>r['instructions']['Qfplib']
remaining=[r for r in rows if loss(r,'candidate')]
new=[r for r in remaining if 'parent' in r['instructions'] and not loss(r,'parent')]
out=dict(status='SHORT_PROBE_NOT_QUALIFICATION',candidate_ELF_sha256=sha(W/'candidate.elf'),unique_inputs=len(jobs),fresh_ARM_calls=calls,oracle_evaluations=len(jobs),wrong=0,parent_measured_raw_losses=len({r['x'] for r in rows if loss(r,'parent')}),candidate_raw_losses=len({r['x'] for r in remaining}),new_measured_parent_raw_losses=len({r['x'] for r in new}),parent_cost_deltas=dict(sorted(deltas.items())),candidate_stack_bytes=SP-machines['candidate'].stack_lowest,rows=rows,remaining=remaining,new=new,hardware_accessed=False)
(W/'probe.json').write_text(json.dumps(out,indent=2)+'\n')
print(json.dumps({k:v for k,v in out.items() if k not in ('rows','remaining','new','parent_cost_deltas')},indent=2))
for x in ('3D90000000000000','BD90000000000000','BC90000000000001'):
 for row in rows:
  if row['x']==x and row['SIO']=='READY':print(x,row['instructions'])

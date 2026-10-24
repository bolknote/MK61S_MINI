from pathlib import Path
from collections import Counter
import hashlib,json,random,struct,sys
sys.dont_write_bytecode=True
W=Path(__file__).resolve().parent;ROOT=W.parents[1]
P=ROOT/'.build/m0-asin-scaled-bound-v164-20261023'
B=ROOT/'.build/m0-exp-cached-product-20261024'
Q=ROOT/'.build/m0-float-fma-qualification-20261023'
sys.path[:0]=[str(Q),str(Q/'support'),str(ROOT/'tests')]
from native_eabi_m0_arm_self_test import Machine,SP
from check_stm32_vectors import ElfImage
from m0_mpfr_oracle import Oracle,bits
from oracles import equal
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
old=json.loads((B/'qualification.json').read_text());jobs={}
def add(x,g):jobs.setdefault(x,g)
for row in old['remaining_slower_correct_Qfplib']:add(int(row['x'],16),'old395')
for x in (0,1,(1<<52)-1,1<<52,0x7fefffffffffffff,0x7ff0000000000000,0x7ff0000000000001,0x7ff8000000000000):
 for sign in (0,1<<63):add(sign|x,'IEEE')
for x in (2**-54,2**-53,3*2**-54,2**-40,2**-39,2**-38):
 for delta in range(-16,17):
  for sign in (0,1<<63):add(sign|(bits(x)+delta),'tiny_domain_endpoints')
rng=random.Random(0xE4F2C0)
for _ in range(512):add(bits(rng.uniform(-745.2,710.0)),'new_ordinary')
for _ in range(512):add((rng.getrandbits(1)<<63)|rng.randrange(0x3c90000000000001,bits(2**-38)),'new_tiny')
rom=ROOT/'research/rp2040-memset-2026-10-21/capture/bootrom.bin'
machines={}
for label in ('parent','candidate'):
 m=Machine(P/'firmware/mk61s-picocalc-pico-h.elf',True,bootrom=rom)
 image=ElfImage((B if label=='parent' else W)/'candidate.elf');image.load(m.uc)
 m.elf.symbols[label+'_exp']=image.symbols['mk61_m0_exp'];machines[label]=m
machines['Qfplib']=Machine(ROOT/'.build/m0-v138-execution-20261023/reference/reference.elf',True)
states={'READY':struct.pack('<7I',0,0,0,0,0,0,1),'DIRTY':struct.pack('<7I',17,3,17,3,5,2,3)}
oracle=Oracle();rows=[];delta_counts=Counter()
for index,(x,group) in enumerate(jobs.items()):
 if index%256==0:print('probe',index,'/',len(jobs),flush=True)
 expected=oracle.reference('exp',x)
 for state_name,state in states.items():
  outputs={};counts={};correct={}
  for label,m in machines.items():
   m.uc.mem_write(0xd0000060,state)
   got,_,cost=m.call('qfp_dexp' if label=='Qfplib' else label+'_exp',x,count=True)
   outputs[label]=f'{got:016X}';counts[label]=cost;correct[label]=equal(got,expected,64)
   if label!='Qfplib':assert correct[label],(label,f'{x:016X}',f'{got:016X}',f'{expected:016X}')
   after=bytes(m.uc.mem_read(0xd0000060,28))
   if state_name=='DIRTY':assert after==state
   else:assert not(struct.unpack('<7I',after)[6]&2)
  assert outputs['candidate']==outputs['parent']
  delta_counts[counts['candidate']-counts['parent']]+=1
  rows.append(dict(x=f'{x:016X}',group=group,SIO=state_name,expected=f'{expected:016X}',outputs=outputs,instructions=counts,correct=correct))
loss=lambda r,n:r['correct']['Qfplib'] and r['instructions'][n]>r['instructions']['Qfplib']
remaining=[r for r in rows if loss(r,'candidate')]
new=[r for r in remaining if not loss(r,'parent')]
out=dict(status='SHORT_PROBE_NOT_QUALIFICATION',candidate_ELF_sha256=sha(W/'candidate.elf'),unique_inputs=len(jobs),fresh_ARM_calls=3*len(rows),oracle_evaluations=len(jobs),MPFR_version=oracle.version,wrong=0,parent_raw_losses=len({r['x'] for r in rows if loss(r,'parent')}),candidate_raw_losses=len({r['x'] for r in remaining}),new_raw_losses=len({r['x'] for r in new}),parent_cost_deltas=dict(sorted(delta_counts.items())),candidate_stack_bytes=SP-machines['candidate'].stack_lowest,rows=rows,remaining=remaining,new=new,hardware_accessed=False)
(W/'probe.json').write_text(json.dumps(out,indent=2)+'\n')
print(json.dumps({k:v for k,v in out.items() if k not in ('rows','remaining','new')},indent=2))
for x in ('BC90000000000001','4085F424184F6DC5','C041265824E2113C'):
 for r in rows:
  if r['x']==x and r['SIO']=='READY':print(x,r['instructions'])

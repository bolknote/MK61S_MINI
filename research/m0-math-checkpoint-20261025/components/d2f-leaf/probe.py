"""Fresh standalone public ABI probe, exact integer/MPFR, parent and Qfplib."""
from pathlib import Path
from collections import Counter
import gzip,hashlib,json,random,struct,sys
sys.dont_write_bytecode=True
W=Path(__file__).resolve().parent;ROOT=W.parents[1];Q=ROOT/'.build/m0-float-fma-qualification-20261023';P=ROOT/'.build/m0-asin-scaled-bound-v164-20261023'
sys.path[:0]=[str(Q),str(Q/'support'),str(ROOT/'tests')]
from native_eabi_m0_arm_self_test import Machine,SP
from oracles import integer_cast,equal,DirectMPFR
from unicorn import UC_HOOK_MEM_READ,UC_HOOK_MEM_WRITE
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
build=json.loads((W/'build.json').read_text());assert sha(W/'candidate.elf')==build['candidate_ELF_sha256']
rom=ROOT/'research/rp2040-memset-2026-10-21/capture/bootrom.bin'
machines={'parent':Machine(P/'firmware/mk61s-picocalc-pico-h.elf',True,bootrom=rom),'candidate':Machine(W/'candidate.elf',True),'Qfplib':Machine(ROOT/'.build/m0-v138-execution-20261023/reference/reference.elf',True)}
accesses=[];machines['candidate'].uc.hook_add(UC_HOOK_MEM_READ|UC_HOOK_MEM_WRITE,lambda uc,access,address,size,value,user:accesses.append((access,address,size)),begin=0xd0000000,end=0xd0000fff)
jobs={}
def add(x,group):jobs.setdefault(x,group)
for r in json.loads((Q/'float.json').read_text())['operations']['d2f']['instruction_sample']:add(int(r['arguments'][0],16),'old_sample')
for exponent in (0,1,2,872,873,874,895,896,897,898,1023,1024,1150,1151,1152,2046,2047):
 for fraction in (0,1,(1<<29)-1,1<<29,(1<<29)+1,(1<<51),(1<<52)-(1<<29)-1,(1<<52)-(1<<29),(1<<52)-(1<<29)+1,(1<<52)-1):
  for sign in (0,1<<63):add(sign|(exponent<<52)|fraction,'IEEE_transition_controls')
for exponent in (897,1023,1024,1150):
 for head in (0,1,2,3,4,5,6,7,(1<<23)-1):
  for delta in (-1,0,1):
   fraction=(head<<29)+(1<<28)+delta
   if fraction<(1<<52):
    for sign in (0,1<<63):add(sign|(exponent<<52)|fraction,'normal_actual_half_cells')
rng=random.Random(0xD2F2EAF)
for _ in range(1024):add(rng.getrandbits(64),'uniform_raw')
states={'READY':struct.pack('<7I',0,0,0,0,0,0,1),'DIRTY':struct.pack('<7I',17,3,17,3,5,2,3)}
oracle=DirectMPFR();rows=[];deltas=Counter()
for index,(x,group) in enumerate(jobs.items()):
 if index%1024==0:print('progress',index,'/',len(jobs),flush=True)
 expected=integer_cast(x,64,32);mpfr=oracle.float('d2f',x);assert equal(expected,mpfr,32)
 for state_name,state in states.items():
  outputs={};counts={};correct={}
  for label,m in machines.items():
   m.uc.mem_write(0xd0000060,state)
   got,_,cost=m.call('qfp_double2float' if label=='Qfplib' else '__aeabi_d2f',x,count=True);got&=0xffffffff
   outputs[label]=f'{got:08X}';counts[label]=cost;correct[label]=equal(got,expected,32)
   if label!='Qfplib':assert correct[label],(label,f'{x:016X}',f'{got:08X}',f'{expected:08X}')
   assert bytes(m.uc.mem_read(0xd0000060,28))==state
  assert outputs['candidate']==outputs['parent']
  deltas[counts['candidate']-counts['parent']]+=1
  rows.append({'x':f'{x:016X}','group':group,'SIO':state_name,'expected':f'{expected:08X}','outputs':outputs,'instructions':counts,'correct':correct})
assert not accesses
loss=lambda r,label:r['correct']['Qfplib'] and r['instructions'][label]>r['instructions']['Qfplib']
remaining=[r for r in rows if loss(r,'candidate')];new=[r for r in remaining if not loss(r,'parent')]
out={'status':'D2F_PUBLIC_LEAF_SHORT_PROBE','candidate_ELF_sha256':sha(W/'candidate.elf'),'unique_inputs':len(jobs),'fresh_ARM_calls':3*len(rows),'fresh_MPFR_references':len(jobs),'MPFR_version':oracle.version,'wrong':0,'raw_bits_identical_parent_including_NaNs':True,'parent_raw_losses':len({r['x'] for r in rows if loss(r,'parent')}),'candidate_raw_losses':len({r['x'] for r in remaining}),'new_raw_losses':len({r['x'] for r in new}),'delta_counts':dict(sorted(deltas.items())),'candidate_stack_bytes':SP-machines['candidate'].stack_lowest,'candidate_SIO_accesses':len(accesses),'standalone_actual_leaf_no_firmware_ROM_mocks':True,'old_sample_parent_remaining':len({r['x'] for r in rows if r['group']=='old_sample' and loss(r,'parent')}),'old_sample_candidate_remaining':len({r['x'] for r in rows if r['group']=='old_sample' and loss(r,'candidate')}),'rows':rows,'remaining':remaining,'new':new,'hardware_accessed':False}
(W/'probe.json').write_text(json.dumps(out,indent=2)+'\n')
print(json.dumps({k:v for k,v in out.items() if k not in ('rows','remaining','new','delta_counts')},indent=2))
for r in new[:10]:print('NEW',r['x'],r['instructions'])

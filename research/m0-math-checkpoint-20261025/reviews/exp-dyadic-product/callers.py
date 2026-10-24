"""Independent original other-callers qualification of the shared product delta."""
from pathlib import Path
from collections import Counter
import json,struct,sys
sys.dont_write_bytecode=True
R=Path('/Users/bolk/Projects/MK61S_MINI');O=Path(__file__).resolve().parent;P=R/'.build/m0-asin-scaled-bound-v164-20261023';Q=R/'.build/m0-float-fma-qualification-20261023'
sys.path[:0]=[str(Q/'support'),str(R/'tests')]
from native_eabi_m0_arm_self_test import Machine
from check_stm32_vectors import ElfImage
from m0_mpfr_oracle import Oracle
from unicorn import UC_HOOK_CODE
from unicorn.arm_const import UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,UC_ARM_REG_R3
rom=R/'research/rp2040-memset-2026-10-21/capture/bootrom.bin';address=0x20038ee4
images=[R/'.build/m0-exp-cached-product-20261024/candidate.elf',R/'.build/m0-pow-square-ordinary-20261024/candidate.elf',R/'.build/m0-pow-rsqrt-asm-20261024/candidate.elf']
newim=ElfImage(O/'rebuild/candidate.elf');newslot=newim.bytes_at(newim.named_sections['.product_ram']);oldim=ElfImage(O/'rebuild/control.elf');oldslot=oldim.bytes_at(oldim.named_sections['.product_ram']);cache=ElfImage(images[0]);cachedslot=cache.bytes_at(cache.named_sections['.product_ram']);machines={};traces={}
for label in ['parent','candidate']:
 m=Machine(P/'firmware/mk61s-picocalc-pico-h.elf',True,bootrom=rom)
 for path in images:
  im=ElfImage(path);im.load(m.uc);m.elf.symbols.update({n:a for n,a in im.symbols.items() if n.startswith('mk61_m0_pow_')})
 assert bytes(m.uc.mem_read(address,168))==cachedslot
 m.uc.mem_write(address,oldslot)
 if label=='candidate':m.uc.mem_write(address,newslot)
 assert not m.rom_models;machines[label]=m;traces[label]=[]
 def hook(uc,pc,size,user,label=label):
  r=[uc.reg_read(r) for r in [UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,UC_ARM_REG_R3]];a=r[0]|r[1]<<32;b=r[2]|r[3]<<32;assert a<1<<63 and b<1<<54;traces[label].append((a,b))
 m.uc.hook_add(UC_HOOK_CODE,hook,begin=address,end=address)
machines['Qfplib']=Machine(R/'.build/m0-v138-execution-20261023/reference/reference.elf',True)
def equal(x,y):return bool(x&0x7fffffffffffffff>0x7ff0000000000000 and x&(1<<51)) if y&0x7fffffffffffffff>0x7ff0000000000000 else x==y
jobs=[r for r in json.loads((P/'slower-inputs.json').read_text())['rows'] if r['operation'] in ['pow','sin','cos']];assert len(jobs)==189
states={'READY':struct.pack('<7I',0,0,0,0,0,0,1),'DIRTY':struct.pack('<7I',17,3,17,3,5,2,3)};oracle=Oracle();rows=[]
for i,job in enumerate(jobs):
 if i%32==0:print('own caller',i,'/',len(jobs),flush=True)
 op=job['operation'];x=int(job['x'],16);y=int(job['y'],16) if job.get('y') else 0;expected=oracle.reference(op,x,y) if op=='pow' else oracle.reference(op,x)
 reference=('qfp_composed_pow_exact' if job['stream']=='composed_exact_exponents' else 'qfp_composed_pow_integer' if job['stream'].startswith('composed_negative_') else 'qfp_composed_pow') if op=='pow' else 'qfp_d'+op
 for state_name,state in states.items():
  outputs={};costs={};args={}
  for label,m in machines.items():
   m.uc.mem_write(0xd0000060,state)
   if label!='Qfplib':traces[label].clear()
   got,_,cost=m.call(reference if label=='Qfplib' else '_ZN12compact_math3'+op+('Edd' if op=='pow' else 'Ed'),x,y,count=True);outputs[label]=f'{got:016X}';costs[label]=cost
   if label!='Qfplib':assert equal(got,expected);args[label]=list(traces[label])
   after=bytes(m.uc.mem_read(0xd0000060,28));assert after==state if state_name=='DIRTY' else not(struct.unpack('<7I',after)[6]&2)
  assert outputs['parent']==outputs['candidate'] and args['parent']==args['candidate'] and costs['candidate']==costs['parent']-2*len(args['parent'])
  rows.append(dict(operation=op,x=job['x'],y=job.get('y'),stream=job['stream'],SIO=state_name,expected=f'{expected:016X}',outputs=outputs,instructions=costs,product_arguments=[[f'{a:016X}',f'{b:016X}'] for a,b in args['candidate']],product_calls=len(args['candidate']),Qfplib_correct=equal(int(outputs['Qfplib'],16),expected)))
summary={}
for op in ['pow','sin','cos']:
 rr=[r for r in rows if r['operation']==op];loss=lambda r,l:r['Qfplib_correct'] and r['instructions'][l]>r['instructions']['Qfplib']
 summary[op]=dict(inputs=len(rr)//2,parent_remaining=len({(r['x'],r['y']) for r in rr if loss(r,'parent')}),candidate_remaining=len({(r['x'],r['y']) for r in rr if loss(r,'candidate')}),product_calls=sum(r['product_calls'] for r in rr),state_cost_improvements=sum(r['instructions']['candidate']<r['instructions']['parent'] for r in rr));assert summary[op]['candidate_remaining']<=summary[op]['parent_remaining']
assert [summary[op]['candidate_remaining'] for op in ['pow','sin','cos']]==[48,22,14]
new_equal=[r for r in rows if r['SIO']=='READY' and r['operation']=='pow' and r['Qfplib_correct'] and r['instructions']['parent']>r['instructions']['Qfplib']==r['instructions']['candidate']]
assert len(new_equal)==3
(O/'new-original-pow-ties.json').write_text(json.dumps(new_equal,indent=2)+'\n')
(O/'caller-results.json').write_text(json.dumps(rows,indent=2)+'\n')
out=dict(status='PASS_OWN_DYADIC_OTHER_CALLERS_THREE_ORIGINAL_POW_TIES',inputs=189,own_fresh_ARM=1134,own_directed_MPFR_inputs=189,sNaN_shortcuts=0,summary=summary,new_original_pow_equal=3,all_arguments_and_raw_outputs_identical=True,all_costs_parent_minus2_per_actual_product_call=True,all_product_arguments_in_accepted63x54_domain=True,both_SIO_states_and_ABI_checked=True,not_full_expanded_pow_requalification=True,hardware=False,canonical=False)
(O/'callers.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out,indent=2))

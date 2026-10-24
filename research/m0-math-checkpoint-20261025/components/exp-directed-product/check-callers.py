"""Product-only delta on the latest pow and unchanged sin/cos original jobs."""
from pathlib import Path
import hashlib,json,struct,sys
sys.dont_write_bytecode=True
W=Path(__file__).resolve().parent;ROOT=W.parents[1];P=ROOT/'.build/m0-asin-scaled-bound-v164-20261023';B=ROOT/'.build/m0-exp-cached-product-20261024';S=ROOT/'.build/m0-pow-square-ordinary-20261024';R=ROOT/'.build/m0-pow-rsqrt-asm-20261024';Q=ROOT/'.build/m0-float-fma-qualification-20261023';D=ROOT/'.build/m0-exp-dyadic-product-20261024'
sys.path[:0]=[str(Q),str(Q/'support'),str(ROOT/'tests')]
from native_eabi_m0_arm_self_test import Machine,SP
from check_stm32_vectors import ElfImage
from m0_mpfr_oracle import Oracle
from oracles import equal
from unicorn import UC_HOOK_CODE
from unicorn.arm_const import UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,UC_ARM_REG_R3
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
im=ElfImage(W/'candidate.elf');slot=im.named_sections['.product_ram'];address=slot[3];new=im.bytes_at(slot)
oldimage=ElfImage(D/'candidate.elf');old=oldimage.bytes_at(oldimage.named_sections['.product_ram'])
def machine(op,candidate):
 m=Machine(P/'firmware/mk61s-picocalc-pico-h.elf',True,bootrom=ROOT/'research/rp2040-memset-2026-10-21/capture/bootrom.bin')
 ElfImage(B/'candidate.elf').load(m.uc)
 if op=='pow':
  ElfImage(S/'candidate.elf').load(m.uc);ri=ElfImage(R/'candidate.elf');ri.load(m.uc);m.elf.symbols.update({n:a for n,a in ri.symbols.items() if n.startswith('mk61_m0_pow_')})
 base=ElfImage(B/'candidate.elf');assert bytes(m.uc.mem_read(address,168))==base.bytes_at(base.named_sections['.product_ram'])
 m.uc.mem_write(address,new if candidate else old)
 return m
machines={op:{'parent':machine(op,False),'candidate':machine(op,True),'Qfplib':Machine(ROOT/'.build/m0-v138-execution-20261023/reference/reference.elf',True)} for op in ('pow','sin','cos')}
traces={}
for op,group in machines.items():
 for label,m in group.items():
  if label=='Qfplib':continue
  traces[op,label]=[]
  def hook(uc,pc,size,user,op=op,label=label):
   a=uc.reg_read(UC_ARM_REG_R0)|(uc.reg_read(UC_ARM_REG_R1)<<32);b=uc.reg_read(UC_ARM_REG_R2)|(uc.reg_read(UC_ARM_REG_R3)<<32)
   assert a<1<<63 and b<1<<54
   traces[op,label].append((a,b))
  m.uc.hook_add(UC_HOOK_CODE,hook,begin=address,end=address)
jobs=[r for r in json.loads((P/'slower-inputs.json').read_text())['rows'] if r['operation'] in ('pow','sin','cos')]
assert len(jobs)==189
states={'READY':struct.pack('<7I',0,0,0,0,0,0,1),'DIRTY':struct.pack('<7I',17,3,17,3,5,2,3)};oracle=Oracle();rows=[];shortcuts=0
for index,job in enumerate(jobs):
 if index%32==0:print('caller',index,'/',len(jobs),flush=True)
 op=job['operation'];x=int(job['x'],16);y=int(job['y'],16) if job.get('y') else 0
 expected=oracle.reference(op,x,y) if op=='pow' else oracle.reference(op,x)
 shortcuts+=any((v&0x7fffffffffffffff)>0x7ff0000000000000 and not(v&(1<<51)) for v in ((x,y) if op=='pow' else (x,)))
 reference=('qfp_composed_pow_exact' if job['stream']=='composed_exact_exponents' else 'qfp_composed_pow_integer' if job['stream'].startswith('composed_negative_') else 'qfp_composed_pow') if op=='pow' else 'qfp_d'+op
 for state_name,state in states.items():
  outputs={};counts={};correct={};arguments={}
  for label,m in machines[op].items():
   if label!='Qfplib':traces[op,label].clear()
   m.uc.mem_write(0xd0000060,state)
   got,_,cost=m.call(reference if label=='Qfplib' else '_ZN12compact_math3'+op+('Edd' if op=='pow' else 'Ed'),x,y,count=True)
   outputs[label]=f'{got:016X}';counts[label]=cost;correct[label]=equal(got,expected,64)
   if label!='Qfplib':assert correct[label];arguments[label]=list(traces[op,label])
   after=bytes(m.uc.mem_read(0xd0000060,28))
   if state_name=='DIRTY':assert after==state
   else:assert not(struct.unpack('<7I',after)[6]&2)
  assert outputs['parent']==outputs['candidate'] and arguments['parent']==arguments['candidate']
  assert counts['candidate']==counts['parent']-2*len(arguments['parent'])
  rows.append(dict(operation=op,x=job['x'],y=job.get('y'),stream=job['stream'],SIO=state_name,expected=f'{expected:016X}',outputs=outputs,instructions=counts,correct=correct,product_calls=len(arguments['parent']),reference_symbol=reference))
summary={}
for op in ('pow','sin','cos'):
 rr=[r for r in rows if r['operation']==op]
 loss=lambda r,n:r['correct']['Qfplib'] and r['instructions'][n]>r['instructions']['Qfplib']
 summary[op]=dict(jobs=len(rr)//2,parent_slower_raw=len({(r['x'],r['y']) for r in rr if loss(r,'parent')}),candidate_slower_raw=len({(r['x'],r['y']) for r in rr if loss(r,'candidate')}),new_raw_losses=len({(r['x'],r['y']) for r in rr if loss(r,'candidate') and not loss(r,'parent')}),state_cases_faster=sum(r['instructions']['candidate']<r['instructions']['parent'] for r in rr),product_calls=sum(r['product_calls'] for r in rr))
assert summary['pow']['parent_slower_raw']==48 and summary['sin']['parent_slower_raw']==22 and summary['cos']['parent_slower_raw']==14
assert all(v['new_raw_losses']==0 for v in summary.values())
out=dict(status='PASS_PRODUCT_ONLY_DELTA_LATEST_POW_AND_RESIDENT_SIN_COS_ORIGINAL189',candidate_ELF_sha256=sha(W/'candidate.elf'),fresh_ARM_calls=3*len(rows),oracle_evaluations=len(jobs),actual_directed_MPFR_inputs=len(jobs)-shortcuts,sNaN_shortcuts=shortcuts,MPFR_version=oracle.version,wrong=0,all_public_return_bits_and_product_arguments_identical=True,all_cost_deltas_minus2_per_actual_product_call=True,summary=summary,observed_stacks={op:{n:SP-m.stack_lowest for n,m in group.items() if n!='Qfplib'} for op,group in machines.items()},whole_operation_qualification_not_claimed=True,hardware_accessed=False,rows=rows)
(W/'caller-proof.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps({k:v for k,v in out.items() if k!='rows'},indent=2))

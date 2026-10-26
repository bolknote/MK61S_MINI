"""Product-only overlay on all pinned original pow/sin/cos losses.
No new input corpus; no public exp overlay loaded for this check.
"""
from pathlib import Path
from collections import Counter
import hashlib,json,struct,sys
sys.dont_write_bytecode=True
W=Path(__file__).resolve().parent;ROOT=W.parents[1]
P=ROOT/'.build/m0-asin-scaled-bound-v164-20261023';Q=ROOT/'.build/m0-float-fma-qualification-20261023'
sys.path.insert(0,str(Q));sys.path.insert(0,str(Q/'support'))
from native_eabi_m0_arm_self_test import Machine,SP
from check_stm32_vectors import ElfImage
from m0_mpfr_oracle import Oracle
from oracles import equal
from unicorn import UC_HOOK_CODE
from unicorn.arm_const import UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,UC_ARM_REG_R3
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
base=P/'firmware/mk61s-picocalc-pico-h.elf';rom=ROOT/'research/rp2040-memset-2026-10-21/capture/bootrom.bin'
ref=ROOT/'.build/m0-v138-execution-20261023/reference/reference.elf'
b=json.loads((W/'build.json').read_text());im=ElfImage(W/'candidate.elf');s=im.named_sections['.product_ram'];capsule=im.bytes_at(s)
assert sha(W/'candidate.elf')==b['candidate_ELF_sha256']
machines={'parent':Machine(base,True,bootrom=rom),'candidate':Machine(base,True,bootrom=rom),'Qfplib':Machine(ref,True)}
machines['candidate'].uc.mem_write(s[3],capsule)
jobs=[r for r in json.loads((P/'slower-inputs.json').read_text())['rows'] if r['operation'] in ('pow','sin','cos')]
assert len(jobs)==189
traces={};max_a=max_b=0
for label in ('parent','candidate'):
 traces[label]=[]
 def entry(uc,address,size,user,label=label):
  global max_a,max_b
  a=uc.reg_read(UC_ARM_REG_R0)|(uc.reg_read(UC_ARM_REG_R1)<<32)
  b=uc.reg_read(UC_ARM_REG_R2)|(uc.reg_read(UC_ARM_REG_R3)<<32)
  assert a<1<<63 and b<1<<54,(label,hex(a),hex(b))
  traces[label].append((a,b));max_a=max(max_a,a);max_b=max(max_b,b)
 machines[label].uc.hook_add(UC_HOOK_CODE,entry,begin=s[3],end=s[3])
oracle=Oracle();states={'READY':struct.pack('<7I',0,0,0,0,0,0,1),'DIRTY':struct.pack('<7I',17,3,17,3,5,2,3)}
rows=[];summary={}
for job in jobs:
 op=job['operation'];a=int(job['x'],16);b=int(job['y'],16) if job.get('y') else 0
 if op=='pow':
  reference_name=('qfp_composed_pow_exact' if job['stream']=='composed_exact_exponents' else
   'qfp_composed_pow_integer' if job['stream'].startswith('composed_negative_') else 'qfp_composed_pow')
 else:reference_name='qfp_d'+op
 expected=oracle.reference(op,a,b) if op=='pow' else oracle.reference(op,a)
 for state_name,state in states.items():
  outputs={};counts={};correct={};trace={}
  for label,m in machines.items():
   if label in traces:traces[label].clear()
   m.uc.mem_write(0xd0000060,state)
   name=reference_name if label=='Qfplib' else '_ZN12compact_math3'+op+('Edd' if op=='pow' else 'Ed')
   got,_,cost=m.call(name,a,b,count=True)
   outputs[label]=f'{got:016X}';counts[label]=cost;correct[label]=equal(got,expected,64)
   after=bytes(m.uc.mem_read(0xd0000060,28))
   if state_name=='DIRTY':assert after==state
   else:assert not(struct.unpack('<7I',after)[6]&2)
   if label in traces:trace[label]=list(traces[label]);assert correct[label]
  assert outputs['candidate']==outputs['parent']
  assert trace['candidate']==trace['parent']
  assert counts['candidate']==counts['parent']-7*len(trace['parent'])
  if state_name=='READY':
   assert counts['parent']==job['own_instructions'],(op,job['stream'],job['x'],counts,job['own_instructions'])
   assert counts['Qfplib']==job['qfplib_instructions'],(op,job['stream'],job['x'],counts,job['qfplib_instructions'])
  rows.append(dict(operation=op,x=job['x'],y=job.get('y'),stream=job['stream'],SIO=state_name,
   expected=f'{expected:016X}',outputs=outputs,instructions=counts,correct=correct,product_calls=len(trace['parent']),
   Qfplib_symbol=reference_name))
for op in ('pow','sin','cos'):
 rr=[r for r in rows if r['operation']==op]
 loss=lambda r,n:r['correct']['Qfplib'] and r['instructions'][n]>r['instructions']['Qfplib']
 summary[op]=dict(unique_inputs=len(rr)//2,state_cases=len(rr),
  parent_slower_raw=len({(r['x'],r['y']) for r in rr if loss(r,'parent')}),
  candidate_slower_raw=len({(r['x'],r['y']) for r in rr if loss(r,'candidate')}),
  new_slower_raw=len({(r['x'],r['y']) for r in rr if loss(r,'candidate') and not loss(r,'parent')}),
  state_cases_improved=sum(r['instructions']['candidate']<r['instructions']['parent'] for r in rr),
  total_product_calls=sum(r['product_calls'] for r in rr))
out=dict(status='PASS_PRODUCT_ONLY_ORIGINAL_POW_SIN_COS_CALLER_CHECK_NOT_FULL_OPERATION_QUALIFICATION',
 candidate_product_sha256=hashlib.sha256(capsule).hexdigest(),candidate_ELF_sha256=sha(W/'candidate.elf'),
 original_input_file_sha256=sha(P/'slower-inputs.json'),unique_inputs=len(jobs),state_cases=len(rows),
 actual_fresh_public_ARM_calls=3*len(rows),actual_fresh_MPFR_reference_calls=len(jobs),MPFR_version=oracle.version,
 maximum_product_a=hex(max_a),maximum_product_b=hex(max_b),domain_checked_every_product_entry=True,
 product_call_traces_identical=True,instruction_delta_minus7_per_product_call=True,
 original_READY_own_and_reference_instruction_counts_reproduced=True,
 every_candidate_returned_bit_identical_parent=True,PCS_SP_SIO_and_bounded_writes_every_call=True,
 observed_stacks={k:SP-m.stack_lowest for k,m in machines.items() if k!='Qfplib'},
 summary=summary,rows=rows,hardware_accessed=False,public_exp_overlay_loaded=False,
 whole_pow_sin_cos_qualification=False,whole_math_GO=False)
(W/'existing-callers.json').write_text(json.dumps(out,indent=2)+'\n')
print(json.dumps({k:v for k,v in out.items() if k!='rows'},indent=2))

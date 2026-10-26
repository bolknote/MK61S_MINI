"""Public pow probe for shorter exact-exponent dispatch, both SIO states."""
from pathlib import Path
from collections import Counter
import hashlib,json,random,struct,sys
sys.dont_write_bytecode=True
W=Path(__file__).resolve().parent;ROOT=W.parents[1]
P=ROOT/'.build/m0-asin-scaled-bound-v164-20261023';B=ROOT/'.build/m0-exp-cached-product-20261024';Q=ROOT/'.build/m0-float-fma-qualification-20261023'
sys.path.insert(0,str(Q));sys.path.insert(0,str(Q/'support'))
from native_eabi_m0_arm_self_test import Machine,SP
from check_stm32_vectors import ElfImage
from m0_mpfr_oracle import Oracle,bits
from oracles import equal
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
b=json.loads((W/'build.json').read_text());bb=json.loads((B/'build.json').read_text())
assert sha(W/'candidate.elf')==b['images']['candidate']['ELF_sha256']
assert sha(B/'candidate.elf')==bb['candidate_ELF_sha256']
base=P/'firmware/mk61s-picocalc-pico-h.elf';rom=ROOT/'research/rp2040-memset-2026-10-21/capture/bootrom.bin';ref=ROOT/'.build/m0-v138-execution-20261023/reference/reference.elf'
machines={}
for label in ('parent','control','candidate'):
 m=Machine(base,True,bootrom=rom);ElfImage(B/'candidate.elf').load(m.uc)
 if label!='parent':ElfImage(W/(label+'.elf')).load(m.uc)
 machines[label]=m
machines['Qfplib']=Machine(ref,True)
jobs={}
def add(x,y,group,reference=None,comparable=None):
 if reference is None:
  xm=x&((1<<63)-1)
  if x>>63:reference='qfp_composed_pow_integer';valid=xm>0 and xm<0x7ff0000000000000 and y in (0,1<<63,bits(1.),bits(-1.),bits(2.))
  else:reference='qfp_composed_pow_integer' if y in (0,1<<63) else 'qfp_composed_pow_exact';valid=xm>0 and xm<0x7ff0000000000000
  if comparable is None:comparable=valid
 jobs.setdefault((x,y),dict(group=group,reference=reference,reference_comparable=bool(comparable)))
original=[r for r in json.loads((P/'slower-inputs.json').read_text())['rows'] if r['operation']=='pow']
for r in original:
 reference='qfp_composed_pow_exact' if r['stream']=='composed_exact_exponents' else 'qfp_composed_pow_integer' if r['stream'].startswith('composed_negative_') else 'qfp_composed_pow'
 add(int(r['x'],16),int(r['y'],16),'historical153',reference,True)
edges=[0,1,2,(1<<51),(1<<52)-1,1<<52,bits(.5),bits(1.),bits(2.),0x7fefffffffffffff,0x7ff0000000000000,
 0x7ff0000000000001,0x7ff00000ffffffff,0x7ff0000100000000,0x7ff7ffffffffffff,0x7ff8000000000000,0x7ff8000000000001,0x7fffffffffffffff]
ys=[0,1<<63,bits(1.),bits(-1.),bits(2.),bits(.5),bits(-.5)]
for raw in edges:
 for sign in (0,1<<63):
  for y in ys:add(raw|sign,y,'IEEE_special_exponent_controls')
for exponent in (1,2,483,484,485,486,511,512,1022,1023,1024,1534,1535,1536,2045,2046):
 for fraction in (0,1,1<<51,(1<<52)-1):
  for sign in (0,1<<63):
   for y in ys:add(sign|(exponent<<52)|fraction,y,'square_binade_endpoint_controls')
rng=random.Random(0xE4AC720)
for _ in range(256):
 x=rng.getrandbits(64)
 for y in ys:add(x,y,'uniform_special_exponents')
# General nonzero-low words retain the exact original dispatch prefix.
for x,y in [(bits(1.3),bits(.123)),(bits(2.7),bits(-.777)),(bits(.7),bits(3.25)),(bits(-1.25),bits(7.))]:add(x,y,'ordinary_controls')
for row in json.loads((ROOT/'.build/m0-pow-square-exact-20261024/qualification.json').read_text())['new_slower_correct_Qfplib']:
 add(int(row['x'],16),int(row['y'],16),'prior_three_new_loss_controls',row['reference'],True)
states={'READY':struct.pack('<7I',0,0,0,0,0,0,1),'DIRTY':struct.pack('<7I',17,3,17,3,5,2,3)}
oracle=Oracle();rows=[]
for (x,y),job in jobs.items():
 if len(rows)%2048==0:print('progress',len(rows),'/',2*len(jobs),flush=True)
 expected=oracle.reference('pow',x,y)
 for state_name,state in states.items():
  outputs={};counts={};correct={}
  for label,m in machines.items():
   m.uc.mem_write(0xd0000060,state)
   try:got,_,cost=m.call(job['reference'] if label=='Qfplib' else '_ZN12compact_math3powEdd',x,y,count=True)
   except Exception as exc:
    from unicorn.arm_const import UC_ARM_REG_PC,UC_ARM_REG_LR
    raise AssertionError((label,hex(x),hex(y),job,state_name,'PC',hex(m.uc.reg_read(UC_ARM_REG_PC)),'LR',hex(m.uc.reg_read(UC_ARM_REG_LR)))) from exc
   outputs[label]=f'{got:016X}';counts[label]=cost;correct[label]=equal(got,expected,64)
   if label!='Qfplib':assert correct[label],(label,hex(x),hex(y),hex(got),hex(expected))
   after=bytes(m.uc.mem_read(0xd0000060,28))
   if state_name=='DIRTY':assert after==state
   else:assert not(struct.unpack('<7I',after)[6]&2)
  assert outputs['candidate']==outputs['control']==outputs['parent']
  assert counts['control']==counts['parent']
  rows.append(dict(x=f'{x:016X}',y=f'{y:016X}',SIO=state_name,expected=f'{expected:016X}',**job,outputs=outputs,instructions=counts,correct=correct))
loss=lambda r,label:r['correct']['Qfplib'] and r['instructions'][label]>r['instructions']['Qfplib']
oldrows=[r for r in rows if r['group']=='historical153']
new=[r for r in rows if loss(r,'candidate') and not loss(r,'parent')]
remaining=[r for r in rows if loss(r,'candidate')]
deltas=Counter(r['instructions']['candidate']-r['instructions']['parent'] for r in rows)
out=dict(status='POW_EXACT_ENTRY_SHORT_PROBE',candidate_source_sha256=b['images']['candidate']['source_sha256'],candidate_ELF_sha256=b['images']['candidate']['ELF_sha256'],
 unique_inputs=len(jobs),public_state_cases=len(rows),actual_fresh_ARM_calls=4*len(rows),fresh_MPFR_calls=len(jobs),MPFR_version=oracle.version,
 candidate_wrong=0,control_counts_equal_parent=True,all_candidate_returned_bits_equal_parent=True,
 speed_comparison_uses_all_numerically_correct_reference_rows_without_domain_filter=True,
 old153_parent_remaining=len({(r['x'],r['y']) for r in oldrows if loss(r,'parent')}),
 old153_candidate_remaining=len({(r['x'],r['y']) for r in oldrows if loss(r,'candidate')}),
 all_parent_raw_losses=len({(r['x'],r['y']) for r in rows if loss(r,'parent')}),
 all_candidate_raw_losses=len({(r['x'],r['y']) for r in remaining}),new_candidate_raw_losses=len({(r['x'],r['y']) for r in new}),
 delta_counts=dict(deltas),observed_stacks={n:SP-m.stack_lowest for n,m in machines.items() if n!='Qfplib'},
 rows=rows,remaining_slower_correct_Qfplib=remaining,new_slower_correct_Qfplib=new,
 PCS_SP_SIO_bounded_writes_every_call=True,hardware_accessed=False)
(W/'probe.json').write_text(json.dumps(out,indent=2)+'\n')
print(json.dumps({k:v for k,v in out.items() if k not in ('rows','remaining_slower_correct_Qfplib','new_slower_correct_Qfplib')},indent=2))
for r in new[:20]:print('NEW',r['x'],r['y'],r['SIO'],r['instructions'])

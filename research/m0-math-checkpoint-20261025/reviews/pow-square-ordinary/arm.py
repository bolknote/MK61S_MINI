"""Independent bounded public pow and exact bare-square ARM checks."""
from pathlib import Path
from collections import Counter
import hashlib,json,math,struct,sys
sys.dont_write_bytecode=True
from proof import R,P,V,O,sha,read,square_oracle
T=R/'.build/m0-pow-square-exact-20261024';B=R/'.build/m0-exp-cached-product-20261024';Q=R/'.build/m0-float-fma-qualification-20261023'
sys.path[:0]=[str(Q),str(Q/'support'),str(R/'tests')]
from native_eabi_m0_arm_self_test import Machine,SP
from m0_mpfr_oracle import Oracle,bits
from check_stm32_vectors import ElfImage
from unicorn import UC_HOOK_CODE,UC_HOOK_MEM_READ,UC_HOOK_MEM_WRITE
from unicorn.arm_const import UC_ARM_REG_R3,UC_ARM_REG_R4,UC_ARM_REG_R5,UC_ARM_REG_R6,UC_ARM_REG_R7,UC_ARM_REG_R12
def equal(a,b):
 if (b&0x7fffffffffffffff)>0x7ff0000000000000:return bool((a&0x7fffffffffffffff)>0x7ff0000000000000 and a&(1<<51))
 return a==b
binding=read(O/'binding.json');assert binding['status'].startswith('PASS_')
saved=read(P/'qualification.json');previous=read(T/'qualification.json');rows=saved['rows'];oldrows=previous['rows']
assert len(rows)==len(oldrows)==127590
assert len({(r['x'],r['y']) for r in rows})==63795
old_trial_losses=previous['new_slower_correct_Qfplib'];assert len(old_trial_losses)==3
for a,b in zip(rows,oldrows):
 assert (a['x'],a['y'],a['SIO'],a['reference'],a['group'],a['reference_comparable'],a['expected'])==(b['x'],b['y'],b['SIO'],b['reference'],b['group'],b['reference_comparable'],b['expected'])
 for label in ['parent','control','Qfplib']:
  assert a['instructions'][label]==b['instructions'][label] and a['outputs'][label]==b['outputs'][label] and a['correct'][label]==b['correct'][label]
 assert a['instructions']['previous_trial']==b['instructions']['candidate'] and a['outputs']['previous_trial']==b['outputs']['candidate']
 assert a['outputs']['candidate']==a['outputs']['parent'] and equal(int(a['outputs']['candidate'],16),int(a['expected'],16))
 assert a['correct']['Qfplib']==equal(int(a['outputs']['Qfplib'],16),int(a['expected'],16))
 if int(a['y'],16)&0xffffffff:assert a['instructions']['candidate']==a['instructions']['parent']
del previous,oldrows
def loss(r,n):return r['correct']['Qfplib'] and r['instructions'][n]>r['instructions']['Qfplib']
idx={(r['x'],r['y'],r['SIO']):r for r in rows}
raw_losses={n:len({(r['x'],r['y']) for r in rows if loss(r,n)}) for n in ['parent','candidate']}
assert raw_losses==dict(parent=27414,candidate=8078)
assert not any(loss(r,'candidate') and not loss(r,'parent') for r in rows)
hist=Counter(r['instructions']['candidate']-r['instructions']['parent'] for r in rows if r['instructions']['candidate']>r['instructions']['parent'])
assert sum(hist.values())==63976 and max(hist)==59
ret=read(P/'retained-parent-regressions.json');rr=ret.get('rows',ret.get('regressions'))
assert rr is not None and len(rr)==63976
assert {(r['x'],r['y'],r['SIO']) for r in rr}=={(r['x'],r['y'],r['SIO']) for r in rows if r['instructions']['candidate']>r['instructions']['parent']}
wrong_reference=sum(not r['correct']['Qfplib'] for r in rows)
nominal_false_but_correct=sum(r['correct']['Qfplib'] and not r['reference_comparable'] for r in rows)
jobs={}
def add(r,group):jobs.setdefault((int(r['x'],16),int(r['y'],16)),dict(group=group,reference=r['reference']))
for r in rows:
 if r['SIO']=='READY' and r['group']=='historical153':add(r,'all_historical153')
assert len(jobs)==153
for r in old_trial_losses:add(r,'all_three_old_trial_new_losses')
cost_types=set();nonzero=0
for r in rows:
 if r['SIO']!='READY':continue
 d=r['instructions']['candidate']-r['instructions']['parent']
 if d>0 and d not in cost_types:add(r,'each_retained_regression_cost_type');cost_types.add(d)
 if int(r['y'],16)&0xffffffff and nonzero<8:add(r,'nonzero_low32_dispatch_invariant');nonzero+=1
assert cost_types==set(hist)
# Exact IEEE classes and cold root fallbacks. Use the established reference
# route per pair, keeping every result whether that route is correct or not.
focus=read(P/'focused-final.json')['rows']
edge_x={0,1,(1<<52)-1,bits(1.),bits(-1.),0x7ff0000000000000,0xfff0000000000000,0x7ff0000000000001,0xfff0000000000001,0x7ff0000100000000,0xfff0000100000000,0x7ff8000000000042,0xfff8000000000000,0x7fffffffffffffff}
for r in focus:
 if r['SIO']=='READY' and int(r['x'],16) in edge_x:add(r,'IEEE_zero_sign_NaN_sNaN_payload_and_cold_roots')
# Additional numeric neighbours of the input-square underflow/overflow
# partitions and exact106-bit cross-carry corners, absent from selection.
for ex in [484,485,486,511,512,1534,1535]:
 for frac in [0,(1<<52)-1]:
  for sign in [0,1<<63]:
   a=sign|(ex<<52)|frac;jobs.setdefault((a,bits(2.)),dict(group='fresh_square_grid_partition_controls',reference='qfp_composed_pow_exact' if not sign else 'qfp_composed_pow_integer'))
ROM=R/'research/rp2040-memset-2026-10-21/capture/bootrom.bin';BASE=V/'firmware/mk61s-picocalc-pico-h.elf';REF=R/'.build/m0-v138-execution-20261023/reference/reference.elf'
machines={};traces={n:Counter() for n in ['parent','control','candidate']}
for label in ['parent','control','candidate']:
 m=Machine(BASE,True,bootrom=ROM);ElfImage(B/'candidate.elf').load(m.uc)
 if label!='parent':ElfImage(P/(label+'.elf')).load(m.uc)
 machines[label]=m
 addresses=dict(m.elf.symbols)
 if label!='parent':addresses.update(ElfImage(P/(label+'.elf')).symbols)
 for name in ['mk61_m0_pow_dispatch','mk61_m0_pow_dispatch_ordinary','mk61_m0_pow_square_exact','pow_rsqrt','mk61_m0_sqrt']:
  if name not in addresses:continue
  a=addresses[name]&~1
  def hook(uc,a,s,u,label=label,name=name):traces[label][name]+=1
  m.uc.hook_add(UC_HOOK_CODE,hook,begin=a,end=a)
machines['Qfplib']=Machine(REF,True)
states={'READY':struct.pack('<7I',0,0,0,0,0,0,1),'DIRTY':struct.pack('<7I',17,3,17,3,5,2,3)}
oracle=Oracle();public=[]
for ji,((a,b),job) in enumerate(jobs.items()):
 if ji%128==0:print('public',ji,'/',len(jobs),flush=True)
 expected=oracle.reference('pow',a,b)
 for sn,state in states.items():
  outputs={};counts={};correct={};trace={}
  for label,m in machines.items():
   before=dict(traces.get(label,{}));m.uc.mem_write(0xd0000060,state)
   got,_,cost=m.call(job['reference'] if label=='Qfplib' else '_ZN12compact_math3powEdd',a,b,count=True)
   outputs[label]=f'{got:016X}';counts[label]=cost;correct[label]=equal(got,expected)
   if label!='Qfplib':assert correct[label],(label,hex(a),hex(b),hex(got),hex(expected))
   if label=='candidate':
    if b==bits(2.):assert got==square_oracle(a)
    if (b&0x7fffffffffffffff)==0:
     snan=(a&0x7fffffffffffffff)>0x7ff0000000000000 and not a&(1<<51)
     assert got==(a|(1<<51) if snan else bits(1.))
   after=bytes(m.uc.mem_read(0xd0000060,28))
   if sn=='DIRTY':assert after==state
   else:assert not struct.unpack('<7I',after)[6]&2
   if label in traces:trace[label]={n:traces[label][n]-before.get(n,0) for n in traces[label]}
  assert outputs['candidate']==outputs['control']==outputs['parent'] and counts['control']==counts['parent']
  if b&0xffffffff:assert counts['candidate']==counts['parent'] and trace['candidate'].get('mk61_m0_pow_dispatch',0)>0
  previous=idx.get((f'{a:016X}',f'{b:016X}',sn))
  if previous:
   for label in machines:assert outputs[label]==previous['outputs'][label] and counts[label]==previous['instructions'][label],(hex(a),hex(b),sn,label,counts,previous['instructions'])
  public.append(dict(x=f'{a:016X}',y=f'{b:016X}',SIO=sn,group=job['group'],reference=job['reference'],expected=f'{expected:016X}',outputs=outputs,instructions=counts,correct=correct,trace=trace))
historical=[r for r in public if r['group']=='all_historical153']
assert len(historical)==306
losses={n:len({(r['x'],r['y']) for r in historical if loss(r,n)}) for n in ['parent','candidate']}
assert losses==dict(parent=149,candidate=82)
fixed=[r for r in historical if r['SIO']=='READY' and r['correct']['Qfplib'] and r['instructions']['candidate']<r['instructions']['Qfplib']<r['instructions']['parent']]
assert len(fixed)==67
assert Counter(r['y'] for r in fixed)==Counter({'0000000000000000':19,'4000000000000000':48})
for r in public:
 if r['group']=='all_three_old_trial_new_losses':assert not loss(r,'candidate') and r['instructions']['candidate']<=r['instructions']['parent']
(O/'public-results.json').write_text(json.dumps(dict(status='PASS_FOCUSED_PUBLIC_POW',unique_inputs=len(jobs),MPFR=oracle.version,fresh_ARM_calls=8*len(jobs),fresh_MPFR_calls=len(jobs),historical149_to82=losses,new67_strict_fixes=True,three_trial_new_losses_closed=True,rows=public),indent=2)+'\n')
# Own unit was built from the intended include, not from a copied wrapper.
unit=Machine(O/'unit.elf',True,stack_bytes=128);ue=ElfImage(O/'unit.elf');current=[0];audits=[];sio=[0]
unit.uc.hook_add(UC_HOOK_MEM_READ|UC_HOOK_MEM_WRITE,lambda *a:sio.__setitem__(0,sio[0]+1),begin=0xd0000060,end=0xd000007b)
start=ue.symbols['mk61_m0_pow_square_exact']&~1;stop=start+328
def pc(uc,a,s,u):assert start<=a<a+s<=stop,hex(a)
unit.uc.hook_add(UC_HOOK_CODE,pc)
def audit(uc,a,s,u):
 raw=current[0];e=(raw>>52)&2047;sig=(raw&((1<<52)-1))|(1<<52);p=sig*sig;n=p.bit_length()-105;E=2*e-1023+n
 actual=uc.reg_read(UC_ARM_REG_R12)|(uc.reg_read(UC_ARM_REG_R5)<<32)|(uc.reg_read(UC_ARM_REG_R6)<<64)|(uc.reg_read(UC_ARM_REG_R7)<<96)
 shift=52+n if E>0 else 1076-2*e;bias=(E-1)<<20 if E>0 else 0
 assert actual==p and uc.reg_read(UC_ARM_REG_R4)==shift and uc.reg_read(UC_ARM_REG_R3)==bias
 audits.append(dict(shift=shift,bias=bias,product=f'{p:X}'))
unit.uc.hook_add(UC_HOOK_CODE,audit,begin=binding['product_audit_address'],end=binding['product_audit_address'])
inputs=set();midpoint_centre=math.isqrt(1<<105)+1
fracs=[0,1,65535,65536,0xffffffff,(1<<52)-1,midpoint_centre-(1<<52)-1,midpoint_centre-(1<<52),midpoint_centre-(1<<52)+1]
for e in [0,1,484,*range(485,513),1023,1534,1535,2046,2047]:
 for f in fracs:
  for sign in [0,1<<63]:inputs.add(sign|(e<<52)|f)
head=math.isqrt(1<<53)+1
if not head&1:head+=1
halftie_heads={head,head+2,head+14,(1<<27)-1,(1<<27)-3}
for odd in halftie_heads:
 for off in [-1,0,1]:
  sig=(odd<<26)+off
  for e in [512,1023,1534]:
   for sign in [0,1<<63]:inputs.add(sign|(e<<52)|(sig-(1<<52)))
bare=[];shifts=Counter();ties=0;cross_carries=0
for raw in sorted(inputs):
 expected=square_oracle(raw);e=(raw>>52)&2047;sig=(raw&((1<<52)-1))|(1<<52)
 if 485<=e<1535:
  p=sig*sig;n=p.bit_length()-105;E=2*e-1023+n;s=52+n if E>0 else 1076-2*e
  ties+=int(p&((1<<s)-1)==1<<(s-1));L=sig&0xffffffff;H=sig>>32
  cross_carries+=int((L>>16)*(H&65535)+(L&65535)*(H>>16)>=1<<32)
 for sn,state in states.items():
  current[0]=raw;audits.clear();unit.uc.mem_write(0xd0000060,state);got,_,cost=unit.call('mk61_m0_pow_square_exact',raw,count=True)
  assert got==expected and bytes(unit.uc.mem_read(0xd0000060,28))==state
  assert len(audits)==int(485<=e<1535)
  if audits:shifts[audits[0]['shift']]+=1
  bare.append(dict(x=f'{raw:016X}',SIO=sn,output=f'{got:016X}',instructions=cost,audit=list(audits)))
assert set(shifts)=={52,53,*range(54,107,2)} and ties>0 and cross_carries>0 and sio[0]==0
(O/'bare-results.json').write_text(json.dumps(dict(status='PASS_OWN_BARE_SQUARE_ARM',unique_inputs=len(inputs),actual_ARM_calls=len(bare),actual_exact_normal_half_inputs=ties,cross_middle_carry_inputs=cross_carries,shift_counts=dict(shifts),full_product_shift_bias_exact_every_finite_call=True,PCS_SP_boundedwrites=True,SIO_accesses=0,observed_stack_bytes=SP-unit.stack_lowest,no_firmware_ROM_or_mock_loaded=True,PC_limited_to_own_actual328byte_module=True,rows=bare),indent=2)+'\n')
out=dict(status='PASS_INDEPENDENT_BOUNDED_POW_ARM_MPFR',public_unique_inputs=len(jobs),public_ARM_calls=8*len(jobs),public_MPFR_references=len(jobs),MPFR=oracle.version,all153_historical_replayed_bothstates=True,parent_original_remaining=149,candidate_original_remaining=82,independent_new_strict_fixes=67,zero19_square48=True,three_old_trial_new_losses_closed=True,nonzero_low32_counts_equal_parent=True,public_results_exact_parent_bits=True,all_127590_metadata_baseline_rows_inherited_not_fresh=True,expanded_raw_loss_counts=raw_losses,reference_wrong_state_rows_retained=wrong_reference,nominal_domain_false_but_numerically_correct_included=nominal_false_but_correct,comparison_uses_correct_reference_only_without_domain_filter=True,retained_parent_regression_states=63976,retained_cost_histogram=dict(sorted(hist.items())),all_retained_cost_types_freshly_sampled=sorted(cost_types),public_stack={n:SP-m.stack_lowest for n,m in machines.items() if n!='Qfplib'},author_full2236_stack_retained_not_reswept=True,public_trace={n:dict(v) for n,v in traces.items()},bare_ARM_calls=len(bare),bare_unique_inputs=len(inputs),bare_actual_half_cells=ties,bare_cross_carry_inputs=cross_carries,bare_shifts=list(sorted(shifts)),bare_stack_bytes=SP-unit.stack_lowest,bare_SIO_accesses=sio[0],own_total_ARM_calls=8*len(jobs)+len(bare),own_MPFR_calls=len(jobs),inherited572776_unit_calls_not_added=True,zero_candidate_errors=True,counts_are_synthetic_instructions_not_physical_cycles=True,hardware=False,canonical=False)
(O/'arm-result.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out,indent=2))

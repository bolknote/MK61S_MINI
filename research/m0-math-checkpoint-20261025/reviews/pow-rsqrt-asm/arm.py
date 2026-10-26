"""Own bounded ARM/MPFR, exact161-bit comparator and quotient checks."""
from collections import Counter
from pathlib import Path
import hashlib,json,struct,sys
sys.dont_write_bytecode=True
from proof import R,P,S,V,O,seeds,reciprocal,model,prove_point,exact_RNE_cell,sha,read
B=R/'.build/m0-exp-cached-product-20261024';Q=R/'.build/m0-float-fma-qualification-20261023'
sys.path[:0]=[str(Q),str(Q/'support'),str(R/'tests')]
from native_eabi_m0_arm_self_test import Machine,SP
from check_stm32_vectors import ElfImage
from m0_mpfr_oracle import Oracle,bits
from unicorn import UC_HOOK_CODE,UC_HOOK_MEM_READ,UC_HOOK_MEM_WRITE
from unicorn.arm_const import UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,UC_ARM_REG_SP
def equal(a,b):
 return bool((a&0x7fffffffffffffff)>0x7ff0000000000000 and a&(1<<51)) if (b&0x7fffffffffffffff)>0x7ff0000000000000 else a==b
binding=read(O/'binding.json');assert binding['status'].startswith('PASS_')
full=read(P/'qualification.json');prior=read(S/'qualification.json')
for a,b in zip(full['rows'],prior['rows']):
 assert (a['x'],a['y'],a['SIO'],a['reference'],a['expected'])==(b['x'],b['y'],b['SIO'],b['reference'],b['expected'])
 assert a['outputs']['parent']==a['outputs']['candidate']==b['outputs']['candidate']
 assert a['instructions']['parent']==b['instructions']['candidate']
 for n in ['control','Qfplib']:
  assert a['outputs'][n]==b['outputs'][n] and a['instructions'][n]==b['instructions'][n] and a['correct'][n]==b['correct'][n]
 normal=0<int(a['x'],16)>>52<2047 and a['y']=='BFE0000000000000'
 assert a['instructions']['candidate']<=a['instructions']['parent']
 if not normal:assert a['instructions']['candidate']==b['instructions']['candidate']
del prior
target=read(P/'targeted.json');probe=read(P/'probe.json');variants={};core={};pairs=set();parentloss=set();candidate_loss=set()
def loss(r,n):return r['correct']['Qfplib'] and r['instructions'][n]>r['instructions']['Qfplib']
for data in [full,target,probe]:
 for r in data['rows']:
  key=(r['x'],r['y'],r['SIO']);pairs.add(key[:2]);v=(r['outputs']['candidate'],r['instructions']['candidate'],r['outputs']['parent'],r['instructions']['parent'],r['expected'])
  if key in core:assert core[key]==v
  core[key]=v;reference=r.get('reference','qfp_composed_pow_exact');vk=key+(reference,)
  value=v+(r['outputs']['Qfplib'],r['instructions']['Qfplib'],r['correct']['Qfplib'])
  if vk in variants:assert variants[vk]==value
  variants[vk]=value
  assert r['correct']['Qfplib']==equal(int(r['outputs']['Qfplib'],16),int(r['expected'],16))
  assert equal(int(r['outputs']['candidate'],16),int(r['expected'],16))
  assert r['instructions']['candidate']<=r['instructions']['parent']
  if loss(r,'parent'):parentloss.add(key[:2])
  if loss(r,'candidate'):candidate_loss.add(key[:2]);assert loss(r,'parent')
assert (len(pairs),len(core),len(variants),len(parentloss),len(candidate_loss))==(111912,223824,223976,42790,7904)
oldloss={(r['x'],r['y']) for r in full['rows'] if loss(r,'candidate')};newloss={(r['x'],r['y']) for r in target['rows'] if loss(r,'candidate')}
assert len(oldloss)==5912 and len(newloss)==1992 and not oldloss&newloss
idx={(r['x'],r['y'],r['SIO']):r for r in full['rows']};ti={(r['x'],r['y'],r['SIO']):r for r in target['rows']}
jobs={}
def add(a,b,group,reference='qfp_composed_pow_exact'):jobs.setdefault((a,b),dict(group=group,reference=reference))
for r in full['rows']:
 if r['SIO']=='READY' and r['group']=='historical153':add(int(r['x'],16),int(r['y'],16),'all_historical153',r['reference'])
assert len(jobs)==153
need={(p,t) for p in [0,1] for t in [0,496,*range(497,515),515,1023]};factors=set()
for r in target['rows']:
 if r['SIO']!='READY':continue
 a=int(r['x'],16);m=model(a);key=(m['p'],m['q']&1023);fh=(m['factor']>>32)-0x80000000
 if key in need:add(a,bits(-.5),'all18_unsafe_tails_and_fast_guard_neighbours_both_parities');need.remove(key)
 if fh not in factors:add(a,bits(-.5),'all_factor_high_branches');factors.add(fh)
 if not need and factors=={-2,-1,0,1}:break
assert not need and factors=={-2,-1,0,1}
for p in [0,1]:
 for i in [0,129,255]:
  for low in [0,(1<<43)-1,1<<43,(1<<43)+1,(1<<44)-1]:add(((1023+p)<<52)|(i<<44)|low,bits(-.5),'fresh_coordinate_corners')
for field in [1,2,1022,1023,1024,2045,2046]:
 for frac in [0,(1<<52)-1]:add((field<<52)|frac,bits(-.5),'fresh_normal_exponent_extremes')
add(0x5B27CF4AC334ECB8,bits(-.5),'old_hard_case')
cold={0,1<<63,1,(1<<63)|1,(1<<52)-1,(1<<63)|((1<<52)-1),0x7ff0000000000000,0xfff0000000000000,0x7ff0000000000001,0xfff0000000000001,0x7ff8000000000001,0xfff8000000000001}
for r in probe['rows']:
 if r['SIO']=='READY' and int(r['x'],16) in cold:add(int(r['x'],16),int(r['y'],16),'unchanged_IEEE_cold_dispatch',r.get('reference','qfp_composed_pow_exact'))
ROM=R/'research/rp2040-memset-2026-10-21/capture/bootrom.bin';BASE=V/'firmware/mk61s-picocalc-pico-h.elf';REF=R/'.build/m0-v138-execution-20261023/reference/reference.elf'
machines={}
for label in ['parent','control','candidate']:
 m=Machine(BASE,True,bootrom=ROM);ElfImage(B/'candidate.elf').load(m.uc);ElfImage(S/'candidate.elf').load(m.uc)
 if label!='parent':e=ElfImage(O/'rebuild'/(label+'.elf'));e.load(m.uc);m.elf.symbols.update(e.symbols)
 machines[label]=m
machines['Qfplib']=Machine(REF,True)
mc=machines['candidate'];pe=ElfImage(O/'rebuild/candidate.elf');state_now={};points=[];comparisons=[];pending=[];sio=[];quotients=[]
mc.uc.hook_add(UC_HOOK_MEM_READ|UC_HOOK_MEM_WRITE,lambda uc,a,b,s,v,u:sio.append((a,b,s)),begin=0xd0000000,end=0xd0000fff)
def point_hook(uc,a,s,u):
 vv=state_now['model'];assert vv is not None
 q=uc.reg_read(UC_ARM_REG_R0)|(uc.reg_read(UC_ARM_REG_R1)<<32);sp=uc.reg_read(UC_ARM_REG_SP)
 assert q==vv['q'] and struct.unpack('<I',uc.mem_read(sp+24,4))[0]==vv['seed'] and struct.unpack('<I',uc.mem_read(sp+28,4))[0]==vv['factor']>>32
 points.append(q)
mc.uc.hook_add(UC_HOOK_CODE,point_hook,begin=pe.symbols['mk61_m0_pow_rsqrt_point']&~1,end=pe.symbols['mk61_m0_pow_rsqrt_point']&~1)
def quotient_hook(uc,a,s,u):
 vv=state_now['model'];assert uc.reg_read(UC_ARM_REG_R0)==vv['t'];quotients.append(vv['t'])
mc.uc.hook_add(UC_HOOK_CODE,quotient_hook,begin=binding['inline_quotient_end'],end=binding['inline_quotient_end'])
boundary_addr=pe.symbols['mk61_m0_pow_rsqrt_boundary']&~1
def boundary_entry(uc,a,s,u):
 if state_now['model'] is None:return
 vv=state_now['model'];sp=uc.reg_read(UC_ARM_REG_SP);m=uc.reg_read(UC_ARM_REG_R0)|(uc.reg_read(UC_ARM_REG_R1)<<32);p=uc.reg_read(UC_ARM_REG_R2);lower=struct.unpack('<Q',uc.mem_read(sp,8))[0]
 assert sp%8==0 and m==vv['m'] and p==vv['p']
 mid=(((lower&((1<<52)-1))|(1<<52))<<1)+1;ex=(lower>>52)-1023;bit=158-p-2*ex
 assert bit==160-p;value=m*mid*mid;expected=(value>(1<<bit))-(value<(1<<bit));pending.append(expected)
mc.uc.hook_add(UC_HOOK_CODE,boundary_entry,begin=boundary_addr,end=boundary_addr)
def boundary_return(uc,a,s,u):
 assert len(pending)==1
 got=uc.reg_read(UC_ARM_REG_R0);got=got-(1<<32) if got>>31 else got;assert got==pending.pop();comparisons.append(got)
helper=pe.symbols['mk61_m0_pow_rsqrt_fast']&~1
mc.uc.hook_add(UC_HOOK_CODE,boundary_return,begin=helper+690,end=helper+690)
states={'READY':struct.pack('<7I',0,0,0,0,0,0,1),'DIRTY':struct.pack('<7I',17,3,17,3,5,2,3)}
oracle=Oracle();outrows=[];factor_seen=set();boundary_counts=Counter();normal_count=0;cellchecks=0
for ji,((a,b),job) in enumerate(jobs.items()):
 if ji%128==0:print('public',ji,'/',len(jobs),flush=True)
 normal=0<a>>52<2047 and b==bits(-.5);vv=model(a) if normal else None
 if vv:prove_point(vv);factor_seen.add((vv['factor']>>32)-0x80000000)
 expected=oracle.reference('pow',a,b)
 for sn,state in states.items():
  outputs={};counts={};correct={};audit=None
  for label,m in machines.items():
   points.clear();comparisons.clear();quotients.clear();pending.clear();sio.clear();state_now['model']=vv
   m.uc.mem_write(0xd0000060,state);got,_,cost=m.call(job['reference'] if label=='Qfplib' else '_ZN12compact_math3powEdd',a,b,count=True)
   outputs[label]=f'{got:016X}';counts[label]=cost;correct[label]=equal(got,expected)
   if label!='Qfplib':assert correct[label],(label,hex(a),hex(b),hex(got),hex(expected))
   after=bytes(m.uc.mem_read(0xd0000060,28))
   if label=='candidate' and normal:
    assert points==[vv['q']] and not sio and after==state and not pending
    calls=int(497<=(vv['q']&1023)<=514);assert len(comparisons)==calls
    assert len(quotients)==int(vv['N']!=0)
    exact_RNE_cell(a,got);cellchecks+=1;normal_count+=1;boundary_counts[str(calls)]+=1
    audit=dict(q=f'{vv["q"]:016X}',tail=vv['q']&1023,factor_high=f'{vv["factor"]>>32:08X}',boundary_results=list(comparisons),SIO_accesses=len(sio))
   elif sn=='DIRTY':assert after==state
   else:assert not struct.unpack('<7I',after)[6]&2
  assert outputs['parent']==outputs['control']==outputs['candidate'] and counts['parent']==counts['control'] and counts['candidate']<=counts['parent']
  if not normal:assert counts['candidate']==counts['parent']
  old=idx.get((f'{a:016X}',f'{b:016X}',sn)) or ti.get((f'{a:016X}',f'{b:016X}',sn))
  if old:
   for n in ['parent','candidate']:
    assert outputs[n]==old['outputs'][n] and counts[n]==old['instructions'][n]
   if job['reference']==old.get('reference','qfp_composed_pow_exact'):assert outputs['Qfplib']==old['outputs']['Qfplib'] and counts['Qfplib']==old['instructions']['Qfplib']
  outrows.append(dict(x=f'{a:016X}',y=f'{b:016X}',SIO=sn,group=job['group'],reference=job['reference'],expected=f'{expected:016X}',outputs=outputs,instructions=counts,correct=correct,audit=audit))
assert factor_seen=={-2,-1,0,1} and boundary_counts['0'] and boundary_counts['1']
original=[r for r in outrows if r['group']=='all_historical153'];assert len(original)==306
assert len({r['x'] for r in original if loss(r,'parent')})==82 and len({r['x'] for r in original if loss(r,'candidate')})==51
fixed=[r for r in original if r['SIO']=='READY' and r['correct']['Qfplib'] and r['instructions']['candidate']<r['instructions']['Qfplib']<r['instructions']['parent']]
assert len(fixed)==31 and all(r['y']=='BFE0000000000000' for r in fixed)
(O/'public-results.json').write_text(json.dumps(dict(status='PASS_OWN_FOCUSED_PUBLIC_RSQRT',unique_pairs=len(jobs),ARM_calls=8*len(jobs),MPFR=oracle.version,MPFR_references=len(jobs),rows=outrows),indent=2)+'\n')
# Five adversarial numerators for every pinned seed, rather than replaying
# the old149484-unit corpus. Cover0/1/2 correction counts explicitly.
unit=Machine(O/'rebuild/unit.elf',True,stack_bytes=128);usio=[]
unit.uc.hook_add(UC_HOOK_MEM_READ|UC_HOOK_MEM_WRITE,lambda *x:usio.append(x),begin=0xd0000000,end=0xd0000fff)
ue=ElfImage(O/'rebuild/unit.elf');sec=ue.named_sections['.quotient'];lo,hi=sec[3],sec[3]+sec[5]
def pc(uc,a,s,u):assert lo<=a<a+s<=hi
unit.uc.hook_add(UC_HOOK_CODE,pc);under=Counter();ur=[]
for j,seed in enumerate(seeds):
 p,i=divmod(j,256);d=513+2*i
 for N in [0,d-1,d,(1<<32)-1,(1<<32)-1-d]:
  exp=N//d;delta=exp-((N*reciprocal[j])>>32);under[delta]+=1
  for sn,state in states.items():
   unit.uc.mem_write(0xd0000060,state);got,_,cost=unit.call('mk61_m0_pow_center_quotient',N|(d<<32),seed|(p<<32),count=True)
   assert got&0xffffffff==exp and bytes(unit.uc.mem_read(0xd0000060,28))==state and not usio
   ur.append(dict(seed_index=j,N=N,denominator=d,SIO=sn,initial_underestimate=delta,quotient=got&0xffffffff,instructions=cost))
assert set(under)=={0,1,2}
(O/'quotient-results.json').write_text(json.dumps(dict(status='PASS_OWN_ALL512_SEED_QUOTIENT_CONTROLS',ARM_calls=len(ur),numerator_seed_pairs=len(ur)//2,correction_classes=dict(under),SIO_accesses=0,PCS_SP_boundedwrites=True,stack_bytes=SP-unit.stack_lowest,no_firmware_ROM_or_mock=True,PC_limited_to_actual_quotient_module=True,rows=ur),indent=2)+'\n')
d=dict(status='PASS_INDEPENDENT_RSQRT_ARM_MPFR_METADATA_AND_EXACT_BOUNDARY',own_public_pairs=len(jobs),own_public_ARM_calls=8*len(jobs),own_MPFR_references=len(jobs),own_quotient_ARM_calls=len(ur),own_total_ARM_calls=8*len(jobs)+len(ur),MPFR=oracle.version,all153_original_pairs_bothstates=True,original31_new_strict_fixes=True,parent_pow_remaining=82,candidate_pow_remaining=51,all18_unsafe_tails_and_outer_guard_edges_both_parities=True,all_factor_high_deltas_freshly_executed=sorted(factor_seen),live_point_seed_factor_and_inline_quotient_match_independent_model=True,live_exact_boundary_arguments_and_return_sign_match_161bit_integer_oracle=True,boundary_call_counts=dict(boundary_counts),independent_exact_rational_RNE_cell_checks=cellchecks,targeted_normal_state_calls=normal_count,normal_candidate_SIO_accesses=0,normal_full28byte_SIO_preserved=True,own_public_stack={n:SP-m.stack_lowest for n,m in machines.items() if n!='Qfplib'},own_quotient_stack=SP-unit.stack_lowest,all512_seed_quotient_and_corrections012_tested=True,zero_candidate_errors=True,metadata_full127590_baseline_rows_inherited_not_fresh=True,legacy_control_label_in_full_corpus='Preserved older pre-square control; own fresh control is the current accepted parent replica. Parent/candidate/Qfplib counts checked against current rows; legacy control provenance checked against prior rows, never relabeled as current fresh control.',expanded_dedup_union=dict(pairs=111912,states=223824,reference_variants=223976,parent_deficits=42790,candidate_deficits=7904,old_corpus_remaining5912=True,new_targeted_remaining1992_disjoint=True,no_new_losses=True,no_parent_cost_increases=True),inherited_unit_calls149484_not_added=True,all_author_or_inherited_calls_excluded_from_own_totals=True,counts_are_instructions_not_device_cycles=True,hardware=False,canonical=False)
(O/'arm-result.json').write_text(json.dumps(d,indent=2)+'\n');print(json.dumps(d,indent=2))

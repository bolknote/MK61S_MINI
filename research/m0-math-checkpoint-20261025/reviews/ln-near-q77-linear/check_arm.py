"""Focused frozen-Q77 ARM/MPFR controls; synthetic instruction counts only."""
from pathlib import Path
from fractions import Fraction as F
import json,hashlib,struct,sys
sys.dont_write_bytecode=True
ROOT=Path('/Users/bolk/Projects/MK61S_MINI');P=ROOT/'.build/m0-ln-near-q77-linear-20261024';O=Path(__file__).resolve().parent;V=ROOT/'.build/m0-asin-scaled-bound-v164-20261023';Q=ROOT/'.build/m0-float-fma-qualification-20261023'
sys.path[:0]=[str(Q),str(Q/'support'),str(ROOT/'tests')]
from native_eabi_m0_arm_self_test import Machine,SP
from check_stm32_vectors import ElfImage
from m0_mpfr_oracle import Oracle,bits
from oracles import equal,round_ratio
from unicorn import UC_HOOK_CODE,UC_HOOK_MEM_READ,UC_HOOK_MEM_WRITE
from unicorn.arm_const import UC_ARM_REG_SP
H=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
def read(p):return json.loads(Path(p).read_text())
math=read(O/'math-binding.json');assert H(P/'candidate.elf')==math['ELF']['sha256']
ROM=ROOT/'research/rp2040-memset-2026-10-21/capture/bootrom.bin';resident=V/'firmware/mk61s-picocalc-pico-h.elf';machines={}
for label,name in [('candidate','candidate.elf'),('parent','control.elf')]:
 m=Machine(resident,True,bootrom=ROM);e=ElfImage(P/name);e.load(m.uc);m.elf.symbols['review_ln']=e.symbols['mk61_m0_ln'];machines[label]=m
machines['Qfplib']=Machine(ROOT/'.build/m0-v138-execution-20261023/reference/reference.elf',True)
candidate_elf=ElfImage(P/'candidate.elf');seen={}
for name in candidate_elf.symbols:
 if any(t in name for t in ['ln_near_interval77','ln_near_one','ln_refine']):
  address=candidate_elf.symbols[name]&~1
  def entered(uc,a,s,u,name=name):seen[name]=seen.get(name,0)+1
  machines['candidate'].uc.hook_add(UC_HOOK_CODE,entered,begin=address,end=address)
jobs={}
def add(raw,group):jobs.setdefault(raw,group)
for row in read(V/'slower-inputs.json')['rows']:
 if row['operation']=='ln':add(int(row['x'],16),'historical_ln10')
remaining=read(P/'remaining-slower.json')['rows']
for row in remaining:add(int(row['x'],16),'remaining_general4')
trial=read(ROOT/'.build/m0-ln-near-q77-products-20261024/qualification.json');old_new_losses=[r for r in trial['remaining_slower_correct_Qfplib'] if r['SIO']=='READY' and r['instructions']['candidate']>r['instructions']['Qfplib']>=r['instructions']['parent']];assert len(old_new_losses)==28
for row in old_new_losses:add(int(row['x'],16),'all28_rejected_trial_new_losses')
regressions=read(P/'regressions.json');assert regressions['state_rows']==len(regressions['rows'])==47110
for row in regressions['rows'][:8]:add(int(row['x'],16),'retained_parent_regression_witness')
for x in [0x3FF01E2A43FC46C8,0x3FEFF7FFFFFFFFFC]:
 for d in [-1,0,1]:add(x+d,'hardpoint_neighbors')
ONE=0x3ff0000000000000
for negative,n in [(False,1),(False,63),(False,128),(True,1),(True,63),(True,127)]:
 center=ONE+(-n*(1<<40) if negative else n*(1<<39));grid=512 if negative else 1024;den=8192+(-n if negative else n)
 for d in [-1,0,1]:add(center+d,'table_center_neighbors')
 for side in [-1,1]:
  for d in [-1,0,1]:add(center+side*((den*1024)//grid)+d,'linear_threshold_neighbors')
 for side in [-1,1]:add(center+side*((1<<48)//grid),'near_cell_halfway')
for x in [0x3FEF808000000001,0x3FF0400000000000,ONE]:
 for d in [-1,0,1]:add(x+d,'outer_domain_or_one_neighbors')
for raw in [0,1,0x8000000000000000,0x8000000000000001,0x3fe0000000000000,0x4000000000000000,0x7ff0000000000000,0xfff0000000000000,0x7ff0000000000001,0xfff8000000000001]:add(raw,'entry_sanity_not_parent_qualification')
states={'READY':struct.pack('<7I',0,0,0,0,0,0,1),'DIRTY':struct.pack('<7I',17,3,17,3,5,2,3)};oracle=Oracle();rows=[]
for raw,group in jobs.items():
 expected=oracle.reference('ln',raw)
 for state_name,state in states.items():
  outputs={};costs={};correct={}
  for label,m in machines.items():
   m.uc.mem_write(0xd0000060,state);got,_,cost=m.call('qfp_dln' if label=='Qfplib' else 'review_ln',raw,count=True);outputs[label]=f'{got:016X}';costs[label]=cost;correct[label]=equal(got,expected,64)
   if label!='Qfplib':assert correct[label],(label,hex(raw),hex(got),hex(expected))
   after=bytes(m.uc.mem_read(0xd0000060,28))
   if state_name=='DIRTY':assert after==state
   else:assert not(struct.unpack('<7I',after)[6]&2)
  assert outputs['candidate']==outputs['parent']
  rows.append(dict(x=f'{raw:016X}',group=group,SIO=state_name,expected=f'{expected:016X}',outputs=outputs,instructions=costs,correct=correct))
(O/'public-interim.json').write_text(json.dumps(dict(status='PASS_FOCUSED_PUBLIC_SAMPLE_ONLY',unique_inputs=len(jobs),state_rows=len(rows),public_calls=3*len(rows),MPFR_version=oracle.version,rows=rows),indent=2)+'\n')
# Exact-source bare pack function at a few midpoint/binade controls.
pack_cpp=(P/'pack-unit.cpp').read_text();public=(P/'native_eabi_m0_log70.inc').read_text()
def function(s,name):
 a=s.index(name+'(');a=s.index('{',a);depth=1;i=a+1
 while depth:
  depth+=(s[i]=='{')-(s[i]=='}');i+=1
 return s[a:i]
assert function(pack_cpp,'ln_near_round_pack77')==function(public,'ln_near_round_pack77')
pm=Machine(P/'pack-unit.elf',True,stack_bytes=128);build=read(P/'pack-unit-build.json');base=F(math['symmetric_base']);arg=F(math['corrected_argument_error']);pack_rows=[];pc_ranges=[(pm.elf.symbols[n]&~1,pm.elf.sizes[n]) for n in ['audit_near_pack77','_ZL5clz32m']];sio=[0]
def observe_sio(*a):sio[0]+=1
def observe_pc(uc,a,s,u):assert any(start<=a<a+s<=start+size for start,size in pc_ranges),hex(a)
pm.uc.hook_add(UC_HOOK_CODE,observe_pc);pm.uc.hook_add(UC_HOOK_MEM_READ|UC_HOOK_MEM_WRITE,observe_sio,begin=0xd0000060,end=0xd000007b)
configurations=[]
for i in range(24):
 den=[8065,8191,8193,8320][i%4];width=[63,64,71,72][(i//2)%4];distance=[0,1,2,3,4,5][i%6];side=[-1,1][i&1];add=bool(i&2);center=(i%8==7);bias=0 if center else [-104,0,104][i%3];residue=0 if center else (((arg*den).__ceil__()-1)*[-1,1][i&1]);shift=width-53;half=1<<(shift-1);retained=(1<<52)+(i%3);tail=half+side*distance;q=(retained<<shift)+tail
 configurations.append((den,bias,residue,add,center,q,width,bool(i&1)))
for width in [63,64,71,72]:
 for sign in [False,True]:configurations.append((8065,0,0,True,False,1<<(width-1),width,sign))
for den,bias,residue,add,center,q,width,sign in configurations:
 shift=width-53;half=1<<(shift-1);tail=q&((1<<shift)-1);distance=abs(tail-half);safe=distance>=4
 if not safe and distance:safe=center or (den*(60*distance-bias)+60*residue>=90*den if (tail>half)==add else den*(60*distance+bias)-60*residue>=90*den)
 expected=round_ratio(q,1,-77,64,sign) if safe else int(build['decline_bits'],16)
 if safe:
  e=F(bias,60)-F(residue,den);lo,hi=(-F(1,2),F(1,2)) if center else ((e-base,e+base) if add else (-e-base,-e+base))
  for error in [lo,hi]:
   exact=F(q)-error;assert round_ratio(exact.numerator,exact.denominator,-77,64,sign)==expected
 high,low=q>>64,q&((1<<64)-1);meta=(bias+128)|(int(add)<<8)|(int(center)<<9)|(int(sign)<<10)|(high<<11)|((den-8065)<<19);config=meta|((residue&0xffffffff)<<32)
 for sn,state in states.items():
  pm.uc.mem_write(0xd0000060,state);got,_,cost=pm.call('audit_near_pack77',low,config,count=True);assert got==expected and bytes(pm.uc.mem_read(0xd0000060,28))==state
  pack_rows.append(dict(width=width,distance=distance,den=den,bias=bias,residue=residue,add=add,center=center,sign=sign,SIO=sn,safe=safe,output=f'{got:016X}',instructions=cost))
assert sio[0]==0
# Small core argument/residual checks include all linear-threshold sides and
# end denominators, with only the184byte actual frozen product54 capsule.
cm=Machine(P/'core-unit.elf',True,stack_bytes=256);capsule=(P/'product54-capsule.bin').read_bytes();cm.uc.mem_write(0x10010000,capsule)
assert len(capsule)==184
resident_elf=ElfImage(resident);pa=resident_elf.symbols['mk61_m0_log_product54']&~1;ps=resident_elf.sizes['mk61_m0_log_product54'];section=next(s for s in resident_elf.named_sections.values() if s[3]<=pa and pa+ps<=s[3]+s[5]);assert capsule==resident_elf.bytes_at(section)[pa-section[3]:pa-section[3]+ps]
assert function((P/'core-unit.cpp').read_text(),'ln_near_argument77')==function(public,'ln_near_argument77')
core_rows=[];core_sio=[0];entry=[0];cm.uc.hook_add(UC_HOOK_MEM_READ|UC_HOOK_MEM_WRITE,lambda *a:core_sio.__setitem__(0,core_sio[0]+1),begin=0xd0000060,end=0xd000007b)
def capsule_entry(uc,a,s,u):assert uc.reg_read(UC_ARM_REG_SP)%8==0;entry[0]+=1
cm.uc.hook_add(UC_HOOK_CODE,capsule_entry,begin=0x10010000,end=0x10010000)
for den in [8065,8191,8192,8193,8320]:
 for delta in [1,den*1024-1,den*1024,den*1024+1,(1<<48)-1,1<<48]:
  for sn,state in states.items():
   values=[]
   for fn in ['audit_h','audit_r']:
    cm.uc.mem_write(0xd0000060,state);v,_,_=cm.call(fn,delta,den);assert bytes(cm.uc.mem_read(0xd0000060,28))==state;values.append(v)
   h,res=values;res=res-(1<<64) if res>>63 else res;assert abs(F(h)-F(delta<<28,den))<arg and res==(delta<<28)-h*den and abs(res)<8192
   core_rows.append(dict(den=den,delta=delta,SIO=sn,h=h,residue=res))
assert core_sio[0]==0 and entry[0]==2*len(core_rows)
# The four remaining general controls remain slower in both source states.
remaining_x={r['x'] for r in remaining};sampled_remaining=[r for r in rows if r['x']in remaining_x];assert len(sampled_remaining)==8 and all(r['correct']['Qfplib'] and r['instructions']['candidate']>r['instructions']['Qfplib'] for r in sampled_remaining)
historical=[r for r in rows if r['group']=='historical_ln10'];assert len(historical)==20 and all(r['correct']['Qfplib'] and r['instructions']['candidate']<=r['instructions']['Qfplib'] for r in historical)
trial_rows=[r for r in rows if r['x']in {v['x'] for v in old_new_losses}];assert len(trial_rows)==56 and all(r['correct']['Qfplib'] and r['instructions']['candidate']<=r['instructions']['Qfplib'] for r in trial_rows)
result=dict(status='PASS_FOCUSED_Q77_ARM_MPFR_ONLY_PARENT_SCOPE_STILL_OPEN',MPFR_version=oracle.version,unique_public_inputs=len(jobs),public_state_rows=len(rows),public_ARM_calls=3*len(rows),public_machine_calls={k:m.calls for k,m in machines.items()},public_stack_observed={k:SP-m.stack_lowest for k,m in machines.items()},public_new_near_and_refine_entry_counts=seen,raw_NaN_policy_same_parent=True,PCS_SP_boundedwrites_and_SIO_checked_every_call=True,public_rows=rows,bare_pack_configurations=len(configurations),bare_pack_ARM_calls=len(pack_rows),bare_pack_rows=pack_rows,bare_pack_SIO_accesses=sio[0],bare_pack_stack_observed=SP-pm.stack_lowest,bare_core_pairs=30,bare_core_state_rows=len(core_rows),bare_core_ARM_calls=2*len(core_rows),bare_core_rows=core_rows,bare_core_SIO_accesses=core_sio[0],bare_core_capsule_entry_SP8_checked=True,bare_core_stack_observed=SP-cm.stack_lowest,retained_parent_regressions=47110,rejected_trial_new_raw_losses_retained_and_sampled=28,remaining_general_state_rows=sampled_remaining,historical_ln10_all_correct_and_no_slower_in_targeted_sample=True,parent_chain_independently_accepted=False,global507_reviewed_count_unchanged=298,physical_cycles=False,hardware_accessed=False)
(O/'focused-arm.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({k:v for k,v in result.items() if k not in ['public_rows','bare_pack_rows','bare_core_rows','remaining_general_state_rows']},indent=2))

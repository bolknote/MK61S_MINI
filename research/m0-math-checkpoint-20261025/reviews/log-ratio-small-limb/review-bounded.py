"""Independent bounded exact-integer/ARM/MPFR review; private component only."""
from pathlib import Path
from collections import Counter
import hashlib,json,struct,sys,time
ROOT=Path('/Users/bolk/Projects/MK61S_MINI');W=ROOT/'.build/m0-log-ratio-small-limb-20261024';OUT=Path(__file__).resolve().parent
P=ROOT/'.build/m0-asin-scaled-bound-v164-20261023';SUP=ROOT/'.build/m0-float-fma-qualification-20261023/support'
sys.path[:0]=[str(SUP),str(ROOT/'tests')]
from native_eabi_m0_arm_self_test import Machine,SP
from check_stm32_vectors import ElfImage
from m0_mpfr_oracle import Oracle
from unicorn import UC_HOOK_MEM_READ,UC_HOOK_MEM_WRITE,UC_HOOK_CODE
from unicorn.arm_const import UC_ARM_REG_SP
M32=(1<<32)-1;M64=(1<<64)-1
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
assert sha(W/'native_eabi_m0_log70_center.inc')=='af83817a78b261621a638c5cc3436bfd63ef57371d999766dfad2a50733dcef7'
assert sha(W/'candidate.elf')=='c0000b4a468cdb80228fab332978f276a21cf5e229fa1abe7622a287ef396297'
for n in ('candidate-full.o','candidate-ratio.o','candidate.elf'):assert (OUT/'rebuild'/n).read_bytes()==(W/n).read_bytes(),n
# Check all physical reciprocal rows, not an independently recreated floating table.
elf=ElfImage(W/'candidate.elf');resident=ElfImage(P/'firmware/mk61s-picocalc-pico-h.elf')
def body(image,name):
 a=image.symbols[name]&~1;size=image.sizes[name];sec=next(s for s in image.named_sections.values() if s[3]<=a and a+size<=s[3]+s[5]);return a,image.bytes_at(sec)[a-sec[3]:a-sec[3]+size]
table=next(n for n in elf.symbols if 'log10_table' in n);_,tablebytes=body(elf,table)
R=[]
for i in range(1024):
 row=struct.unpack_from('<4I',tablebytes,i*16);v=(row[1]<<32)|(row[0]&~63);assert v==((1<<75)//(2049+2*i))&~63;R.append(v)
# A distinct unbounded-integer specification. No source limb-product sequence is mirrored.
def spec(delta,den):
 lo=delta&M32;ell=lo if lo<1<<31 else lo-(1<<32);factor=(delta-ell)>>32
 rr=R[(den-2049)//2];base=(factor*rr)//(1<<14);low=(abs(ell)*(rr>>32))//(1<<14)
 seed=base-low-2 if ell<0 else base+low
 exact,remainder=divmod(delta<<29,den);r=(delta<<29)-seed*den
 assert 0<=delta<=1<<41 and 0<=factor<=512 and -64<=ell<=64
 assert seed>=0 and 0<=r<5*den and 0<=exact-seed<=4
 return seed,exact,exact-seed,r
jobs=set()
for i in range(1024):
 for f in (0,1,255,256,511,512):
  for e in (-64,-1,0,1,64):
   d=(f<<32)+e
   if 0<=d<=1<<41:jobs.add((d,2049+2*i))
for f in range(513):
 for e in range(-64,65):
  d=(f<<32)+e
  if 0<=d<=1<<41:jobs.add((d,3493))
hist=Counter();worst=None;stream=hashlib.sha256()
for d,den in sorted(jobs):
 seed,exact,c,r=spec(d,den);hist[c]+=1;stream.update(struct.pack('<QIQQ',d,den,seed,exact))
 if worst is None or r*worst[3]>worst[2]*den:worst=(d,c,r,den)
assert hist[4]>0
# The uint32 modular predicate is exactly [0,64] U [2^32-64,2^32-1].
for low in [*range(0,130),*range((1<<32)-130,1<<32),0x7fffffff,0x80000000]:
 ell=low if low<1<<31 else low-(1<<32)
 assert (((low+64)&M32)<=128)==(-64<=ell<=64)
for q in (0,1,7,8,(1<<32)-1,1<<32,1<<59,M64):
 for c in range(8):
  for negative in (False,True):assert ((q-c if negative else q+c)&M64)==((q+(-c if negative else c))&M64)
# Only actual helper and exact184B product capsule are executed by the bare machine.
cap_addr,cap=body(resident,'mk61_m0_log_product46');assert len(cap)==184 and hashlib.sha256(cap).hexdigest()=='75729579767fb4b3269141b6c62b1ae4fad49ed8817158b0e7d4bedcc717ecc8'
(OUT/'product46-capsule.bin').write_bytes(cap)
bare=Machine(W/'candidate.elf',True,stack_bytes=128);bare.uc.mem_write(cap_addr,cap);bare.elf.symbols['product_capsule']=resident.symbols['mk61_m0_log_product46']
helper_addr,helper=body(elf,'mk61_m0_log_ratio70_slow');assert len(helper)==444
stats={'sio_accesses':0,'capsule_entries':0,'pcs8_capsule_entries':0};helper_ranges=[(helper_addr,helper_addr+len(helper)),(cap_addr,cap_addr+len(cap))]
def sio(*a):stats['sio_accesses']+=1
def entered(uc,address,size,unused):
 if address==cap_addr:
  stats['capsule_entries']+=1;assert uc.reg_read(UC_ARM_REG_SP)%8==0;stats['pcs8_capsule_entries']+=1
 assert any(a<=address<z for a,z in helper_ranges),(hex(address),'unexpected helper dependency')
bare.uc.hook_add(UC_HOOK_MEM_READ|UC_HOOK_MEM_WRITE,sio,begin=0xd0000060,end=0xd000007b);bare.uc.hook_add(UC_HOOK_CODE,entered)
states={'READY':struct.pack('<7I',0,0,0,0,0,0,1),'DIRTY':struct.pack('<7I',17,3,17,3,5,2,3)}
arm=set()
for den in (2049,2051,3071,3493,4093,4095):
 for f in (0,1,512):
  for e in (-65,-64,-1,0,1,64,65):
   d=(f<<32)+e
   if 0<=d<=1<<41:arm.add((d,den))
 for f in (255,256,511):
  for e in (-64,64):arm.add(((f<<32)+e,den))
 for d in (0x123456789,1<<40,(1<<41)-66):arm.add((d,den))
arm.add((worst[0],worst[3]));armrows=[];signed_generic=Counter()
for d,den in sorted(arm):
 expected=(d<<29)//den;selected=(((d&M32)+64)&M32)<=128
 for state_name,state in states.items():
  bare.uc.mem_write(0xd0000060,state);seed=bare.call('product_capsule',d,R[(den-2049)//2])[0]
  if not selected:signed_generic['negative' if seed>expected else 'positive_or_zero']+=1
  before=stats['capsule_entries'];actual=bare.call('mk61_m0_log_ratio70_slow',d,den)[0]
  assert actual==expected and bytes(bare.uc.mem_read(0xd0000060,28))==state
  assert (stats['capsule_entries']==before)==selected
  armrows.append(dict(delta=f'{d:011X}',den=den,SIO=state_name,small_family=selected,expected=f'{expected:016X}',actual=f'{actual:016X}'))
assert stats['sio_accesses']==0 and SP-bare.stack_lowest<=76 and signed_generic['negative'] and signed_generic['positive_or_zero']
# Public actual code plus exact ROM. Bounds chosen independently; unchanged large corpus is not rerun.
ROM=ROOT/'research/rp2040-memset-2026-10-21/capture/bootrom.bin';REF=ROOT/'.build/m0-v138-execution-20261023/reference/reference.elf';trial=W/'trials/hoisted-guard-one-new-speed-deficit/candidate.elf'
ms={'Qfplib':Machine(REF,True,stack_bytes=768)}
for label,path in [('parent',W/'control.elf'),('candidate',W/'candidate.elf'),('trial',trial)]:
 m=Machine(P/'firmware/mk61s-picocalc-pico-h.elf',True,stack_bytes=768,bootrom=ROM);e=ElfImage(path);e.load(m.uc);m.elf.symbols[label+'_ln']=e.symbols['mk61_m0_ln'];ms[label]=m
inputs={0,1<<63,1,2,0x000fffffffffffff,0x0010000000000000,0x3fefffffffffffff,0x3ff0000000000000,0x3ff0000000000001,0x4000000000000000,0x400ffe7effffffbf,0x7fefffffffffffff,0x7ff0000000000000,0xfff0000000000000,0x7ff0000000000001,0xfff0000000000001,0x7ff8000012345678,0xfff8000012345678}
for i in (0,341,511,1023):
 center=0x4000000000000000+(i<<42)+(1<<41)
 for f,ell in ((1,-65),(1,-64),(256,64),(512,-64)):
  d=(f<<32)+ell
  for side in (-1,1):
   raw=center+side*d
   if 0<=((raw&((1<<52)-1))-(i<<42))<1<<42:inputs.add(raw)
for x in (0x3fef808000000001,0x3ff0400000000000):inputs.update((x-1,x,x+1))
o=Oracle();public=[];nan=lambda a:(a&0x7fffffffffffffff)>0x7ff0000000000000
for x in sorted(inputs):
 want=o.reference('ln',x)
 for state_name,state in states.items():
  outputs={};costs={}
  for label,m in ms.items():
   m.uc.mem_write(0xd0000060,state);name='qfp_dln' if label=='Qfplib' else label+'_ln';y,_,cost=m.call(name,x,count=True);outputs[label]=f'{y:016X}';costs[label]=cost
   if label!='Qfplib':assert (nan(y) if nan(want) else y==want),(label,hex(x),hex(y),hex(want))
   after=bytes(m.uc.mem_read(0xd0000060,28))
   if state_name=='DIRTY':assert after==state
   else:assert not (struct.unpack('<7I',after)[6]&2)
  assert outputs['candidate']==outputs['parent']==outputs['trial']
  public.append(dict(x=f'{x:016X}',SIO=state_name,expected=f'{want:016X}',outputs=outputs,instructions=costs))
ln2=next(r for r in public if r['x']=='4000000000000000' and r['SIO']=='DIRTY');edge=next(r for r in public if r['x']=='400FFE7EFFFFFFBF' and r['SIO']=='DIRTY')
assert ln2['instructions']['parent']==610 and ln2['instructions']['candidate']==613 and ln2['instructions']['Qfplib']==711
assert edge['instructions']['trial']==715 and edge['instructions']['candidate']==712 and edge['instructions']['Qfplib']==713
assert SP-ms['candidate'].stack_lowest<=640
out=dict(status='PASS_BOUNDED_PRIVATE_SMALL_LIMB_INTEGER_ARM_MPFR_REVIEW',source_sha256=sha(W/'native_eabi_m0_log70_center.inc'),ELF_sha256=sha(W/'candidate.elf'),whole_private_CPP_ASM_ELF_independent_rebuild_byteexact=True,host_integer_pairs=len(jobs),host_integer_not_ARM=True,host_floor_correction_histogram=dict(hist),host_max_residue_case=dict(delta=worst[0],correction=worst[1],remainder=worst[2],den=worst[3]),host_transcript_SHA256=stream.hexdigest(),bare_helper_pairs=len(arm),bare_helper_state_cases=len(armrows),actual_bare_ARM_calls=4*len(arm),bare_stack_observed=SP-bare.stack_lowest,bare_SIO_accesses=stats['sio_accesses'],capsule_stack8_entries=stats['pcs8_capsule_entries'],generic_signed_correction_examples=dict(signed_generic),helper_rows=armrows,public_unique_inputs=len(inputs),public_state_cases=len(public),actual_public_ARM_calls=4*len(public),MPFR=o.version,public_candidate_stack_observed=SP-ms['candidate'].stack_lowest,public_rows=public,raw_NaN_candidate_equals_parent=True,ln2_explicit_DIRTY_regression=ln2,withdrawn_trial_minus65_speed_loss_fixed=edge,all_saved_PCS_SP_and_bounded_write_assertions_pass=True,ROM_SHA256=sha(ROM),reference_ELF_SHA256=sha(REF),product_capsule_SHA256=hashlib.sha256(cap).hexdigest(),physical_cycles=False,hardware_accessed=False,canonical_or_Git_or_frozen_changed=False)
(OUT/'bounded-results.json').write_text(json.dumps(out,indent=2)+'\n')
print(json.dumps({k:v for k,v in out.items() if k not in ('helper_rows','public_rows')},indent=2))

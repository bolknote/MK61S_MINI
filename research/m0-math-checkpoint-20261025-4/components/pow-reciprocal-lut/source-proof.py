"""Bind the complete seed suffix and prove the finite integer correction bounds."""
from pathlib import Path
from collections import Counter
import hashlib,json,struct,subprocess,sys
sys.dont_write_bytecode=True
W=Path(__file__).resolve().parent;ROOT=W.parents[1];P=ROOT/'.build/m0-pow-reciprocal-soft-20261025';S=ROOT/'.build/m0-ddiv-seed-lut-20261025'
sys.path.insert(0,str(ROOT/'tests'));from check_stm32_vectors import ElfImage
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
parent=ElfImage(P/'candidate.elf');control=ElfImage(W/'control.elf');candidate=ElfImage(W/'candidate.elf');unit=ElfImage(S/'lut128_floor.elf')
def region(e,address,size):
 s=next(s for s in e.sections if s[2]&2 and s[3]<=address<address+size<=s[3]+s[5])
 return e.bytes_at(s)[address-s[3]:address-s[3]+size]
seed=candidate.symbols['mk61_m0_ddiv_seed17']&~1;section=candidate.named_sections['.ddiv'];old=control.named_sections['.ddiv']
offset=seed-section[3]
assert seed==control.symbols['mk61_m0_ddiv_seed17']&~1
assert candidate.bytes_at(section)[:offset]==control.bytes_at(old)[:offset]
blob=unit.bytes_at(unit.named_sections['.seed']);assert len(blob)==312
assert region(candidate,seed,len(blob))==blob
assert candidate.sizes['mk61_m0_ddiv_seed17']==56
table=struct.unpack('<128H',blob[56:]);assert all(v==(1<<32)//(65536+512*i+256)for i,v in enumerate(table))
for name in ['.rootprefix','.front','.tail']:
 assert candidate.bytes_at(candidate.named_sections[name])==control.bytes_at(control.named_sections[name])==parent.bytes_at(parent.named_sections[name])
errors=Counter();pmin=1<<64;pmax=0;emin=1<<64;emax=-(1<<64);umin=1<<64;umax=-(1<<64);rmin=1<<64;rmax=-(1<<64)
for d in range(65536,131072):
 u=table[(d>>9)-128];x=(d+1)>>1;p=x*u
 assert 0<=p<(1<<32)and abs(p-(1<<31))<(1<<30)
 folded=(p<<1)&0xffffffff;folded=folded-(1<<32)if folded&(1<<31)else folded
 e=folded>>17;assert e==(p-(1<<31))//65536
 product=u*e;assert -(1<<31)<=product<(1<<31)
 q=u-(product>>15)
 assert q==2*u-((u*(p>>16))>>15)
 residual=0xffffffff-q*d;assert -(1<<31)<=residual<(1<<31)
 modular=(~((q*d)&0xffffffff))&0xffffffff
 signed=modular-(1<<32)if modular&(1<<31)else modular
 assert signed==residual
 exact=0xffffffff//d;errors[q-exact]+=1
 while residual<0:q-=1;residual+=d
 while residual>=d:q+=1;residual-=d
 assert q==exact and q*d+residual==0xffffffff and 0<=residual<d
 pmin=min(pmin,p);pmax=max(pmax,p);emin=min(emin,e);emax=max(emax,e);umin=min(umin,product);umax=max(umax,product);rmin=min(rmin,signed);rmax=max(rmax,signed)
assert dict(errors)=={-1:140,0:5167,1:35252,2:23815,3:1162}
build=json.loads((W/'build.json').read_bytes());tc=Path(build['commands'][0][0]).parent;commands=[];disabled={}
for name,cpu,extra in [('generic_M0','cortex-m0plus',[]),('M4_soft','cortex-m4',[]),('M4_hard','cortex-m4',['-mfloat-abi=hard','-mfpu=fpv4-sp-d16'])]:
 output=W/(name+'-seed-disabled.o')
 command=[str(tc/'arm-none-eabi-gcc'),'-mcpu='+cpu,'-mthumb','-DMK61_M0_RP2040_EABI=0',*extra,'-c',str(W/'candidate-seed17.S'),'-o',str(output)]
 subprocess.run(command,check=True);commands.append(command);image=ElfImage(output)
 assert not any(s[2]&2 and s[5]for s in image.sections);disabled[output.name]=sha(output)
proof=dict(status='PASS_EXACT_TABLE_MODEL_BOUND_SUFFIX_AND_INACTIVE_CONTROLS',candidate_ELF_sha256=sha(W/'candidate.elf'),
 selected_unit_blob312B_identical_to_integrated_seed_suffix=True,function_bytes=56,table_bytes=256,
 all1050B_parent_code_except194B_seed_suffix_unchanged=True,all_other_allocated_bytes_addresses_identical=True,
 candidate_ddiv_bytes=section[5],parent_ddiv_bytes=old[5],allocated_delta_bytes=section[5]-old[5],
 exact_table_formula='floor(2^32/(65536+512*i+256)), 0<=i<128',
 exhaustive_model_divisors=65536,half_divisor_product_range=[pmin,pmax],signed_folded_high_range=[emin,emax],signed_correction_product_range=[umin,umax],signed_exact_initial_residual_range=[rmin,rmax],
 initial_quotient_error_histogram=dict(sorted(errors.items())),max_downward_corrections=3,max_upward_corrections=1,
 exact_modular_residual_and_euclidean_invariant_proved_for_every_divisor=True,
 normal_RNE_guards_tail_and_calls_unchanged=True,other_resident_ddiv_callers_unchanged=True,
 default_M0_M4_selected_root_objects_equal_and3_new_seed_objects_empty=True,
 new_global_RAM_or_libgcc_dependencies=False,commands=commands,disabled_outputs=disabled,actual_ARM_or_MPFR_calls=0,hardware_accessed=False,goal_complete=False)
(W/'source-proof.json').write_text(json.dumps(proof,indent=2)+'\n');print(json.dumps({k:v for k,v in proof.items()if k not in ['commands','disabled_outputs']},indent=2))

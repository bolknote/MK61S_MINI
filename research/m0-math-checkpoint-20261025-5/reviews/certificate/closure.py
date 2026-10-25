"""Fresh caller/live-context/resource closure; saved data only, no execution."""
import hashlib,json,struct,sys
from pathlib import Path
sys.dont_write_bytecode=True
R=Path('/Users/bolk/Projects/MK61S_MINI');O=Path(__file__).resolve().parent;W=R/'.build/m0-pow-reciprocal-certificate-20261025'
sys.path.insert(0,str(R/'tests'));from check_stm32_vectors import ElfImage
def ref(p):
 p=Path(p);b=p.read_bytes();return dict(path=str(p),bytes=len(b),sha256=hashlib.sha256(b).hexdigest())
def mem(e,a,n):
 s=next(s for s in e.sections if s[1]!=8 and s[3]<=a and a+n<=s[3]+s[5]);return e.bytes_at(s)[a-s[3]:a-s[3]+n]
tot=dict(after=0,zeros=0,pre_cert=0,certificates=0,full=0,classified=0,restored=0,inline=0,nested=0,calls=0,pops=0,returns=0,latency=0,pack=0,down=0)
for name in ['scalar-arm-mpfr.json','public-arm-mpfr.json']:
 j=json.loads((O/name).read_text())
 for row in j['rows']:
  c,n=row['captures']['control'],row['captures']['candidate']
  for key in ['calls','first','after','zeros','pre_cert','down','pack','seeds']:assert c[key]==n[key]
  for k,src in [('after','after'),('zeros','zeros'),('pre_cert','pre_cert'),('certificates','certificates'),('inline','inline'),('calls','calls'),('pops','pops'),('returns','returns'),('latency','latency9'),('pack','pack'),('down','down')]:tot[k]+=len(n[src])
  tot['classified']+=n['classified'];tot['restored']+=n['restored'];tot['full']+=sum(v['actual_full']for v in n['certificates'])
  if name.startswith('public'):tot['nested']+=sum(v['entry_SP']!=0x2003fff0 for v in n['inline'])
  for v in n['inline']:assert v['inline_SP']==v['entry_SP']-20
assert tot==dict(after=332,zeros=324,pre_cert=324,certificates=324,full=134,classified=324,restored=134,inline=164,nested=8,calls=384,pops=384,returns=16,latency=164,pack=332,down=324)
u,s,p=[json.loads((O/n).read_text())for n in ['unit-arm.json','scalar-arm-mpfr.json','public-arm-mpfr.json']]
assert u['actual_ARM_calls']+s['actual_ARM_calls']+p['actual_ARM_calls']==5592
assert s['directed_MPFR_inputs']+p['directed_MPFR_inputs']==61 and s['sNaN_shortcuts']+p['sNaN_shortcuts']==6
assert s['observed_parent_cost_increases']=={'8':64,'7':64}and not s['new_correctQfp_deficits']
assert [v['candidate']-v['parent']for v in p['both_already_losing_correctQfp_further_slowed_witnesses']]==[8,8]
e=ElfImage(O/'rebuild/candidate.elf');section=e.named_sections['.ddiv'];assert section[3]==0x101e1000 and section[5]==1108 and section[3]+section[5]<0x10200000
assert not any(t[2]&2 and t[2]&1 and t[5]for t in e.sections)
visibility={}
for sec in e.sections:
 if sec[1]!=2:continue
 names=e.bytes_at(e.sections[sec[6]])
 for n,v,z,info,other,index in struct.iter_unpack('<IIIBBH',e.bytes_at(sec)):
  name=e.string(names,n)
  if name in ['mk61_m0_reciprocal1','mk61_m0_reciprocal1_sw_from_guard']:visibility[name]=other&3
assert len(visibility)==2 and set(visibility.values())=={2}
pc=0x1014f114;h1,h2=struct.unpack('<HH',mem(e,pc,4));assert h1&0xf800==0xf000 and h2&0xd000==0xd000
S=(h1>>10)&1;I1=1^((h2>>13)&1)^S;I2=1^((h2>>11)&1)^S
imm=(S<<24)|(I1<<23)|(I2<<22)|((h1&1023)<<12)|((h2&2047)<<1);target=pc+4+(imm-(1<<25)if S else imm)
assert target==(e.symbols['mk61_m0_reciprocal1']&~1)==0x101e105e
assert mem(e,pc-10,10).hex()=='002742187b41ac493846'
ldr=struct.unpack('<H',mem(e,pc-4,2))[0];literal=((pc-4+4)&~3)+4*(ldr&255);assert struct.unpack('<I',mem(e,literal,4))[0]==0x3ff00000
source=(W/'candidate/native_eabi_m0_pow_root_prefix.inc').read_text();sequence='\tmovs\tr7, #0\n\tadds\tr2, r0, r1\n\tadcs\tr3, r7\n\tldr\tr1, .Lpow_horner_CPI10_7\n\tmov\tr0, r7\n\tbl\tmk61_m0_reciprocal1\n'
assert source.count(sequence)==source.count('\tbl\tmk61_m0_reciprocal1')==1
paths=[R/'.build/m0-asin-scaled-bound-v164-20261023/firmware/mk61s-picocalc-pico-h.elf']+[R/'.build'/n/'candidate.elf'for n in ['m0-exp-cached-product-20261024','m0-pow-square-ordinary-20261024','m0-pow-rsqrt-asm-20261024','m0-pow-exp-table-product-20261025','m0-pow-square128-r2-20261025','m0-pow-boundary128-20261025']]
for path in paths:
 im=ElfImage(path);assert not any(t[2]&2 and t[5]and max(section[3],t[3])<min(section[3]+section[5],t[3]+t[5])for t in im.sections)
table=ElfImage(R/'.build/m0-pow-exp-table-product-20261025/candidate.elf');entry=table.symbols['mk61_m0_pow_exp_table_product']&~1;old=ElfImage(R/'.build/m0-exp-directed-product-20261024/candidate.elf');os=old.named_sections['.product_ram'];assert min(entry+20,os[3]+os[5])-max(entry,os[3])==14
unit=R/'.build/m0-ddiv-remainder-certificate-r2-20261025';oldunit=R/'.build/m0-ddiv-remainder-certificate-20261025'
for name in ['candidate.S','control.S','remainder-certificate.inc','candidate.o','control.o','candidate.elf','control.elf']:assert(unit/name).read_bytes()==(oldunit/name).read_bytes()
driver=(unit/'verify-unit.py').read_text();old_driver=(oldunit/'verify-unit.py').read_text()
assert driver.replace("   assert m.uc.reg_read(UC_ARM_REG_R1)==active['r1']\n",'')==old_driver
parentroot=ref(R/'.build/m0-pow-reciprocal-inline-root-acceptance-20261025-001/RECEIPT.json');assert parentroot['bytes']==19203 and parentroot['sha256']=='7da9d4245d12468f80252912fa7e83002bf25392b1524b33ce6f7f98a567d43d'
assert not list(O.glob('RUNTIME-FAILURE-*.json'))
out=dict(status='PASS_FRESH_CALLER_PRIVATE_LIVE_CONTEXT_AND_FINITE_SCOPE_CLOSURE',counts=tot,
 own_qualified_ARM_calls5592=True,own_MPFR61_plus6sNaN=True,unit1952cases3904calls=True,scalar184flagjobs49denominators1472calls=True,public18pairs216calls=True,
 parentROOT_later_additive=parentroot,child_seal_pending_stamps_not_rewritten=True,
 actual_linked_sole_root_BL=dict(pc=hex(pc),target=hex(target),return_PC=hex(pc+4),positive_one_literal=hex(literal),no_intermediate_source_label_between_loads_and_call=True),
 missing_exact_product_limbs_and_flags_dead_before_RNE_freshly_qualified=True,known_zero_shift_proven_from_positive_one_only=True,
 all8_fast_full_up_down_cross_classes_actually_checked=True,all16NZCV_bare_boundaries_and_private_classes=True,
 own_bounded_scalar_plus7_64_plus8_64_kept=True,remaining149vs146_and_two_public_plus8_regressions_reproduced=True,
 original20B_frame_raw_operands_R6guard_R12_inline_ownSP_checked=True,READY9ALU_and_all7DIRTY_words_preserved=True,
 private_hidden_entries=visibility,allocation1108_free_Flash_below2MiB_no_new_RAM=True,no_overlap_refs=[ref(p)for p in paths],
 unit_r2_same_sources_binaries_only_R1_driver_assert_added=True,unit_wrapper_not_public_speed_or_stack_evidence=True,
 old168overlay14B_hazard_persists=True,near_one_separate_sibling_not_loaded=True,
 own_HOST_preflights4_zero_ARM_MPFR_preserved=True,own_numerical_failed_partial_discarded_calls=0,
 reviewed507422_not_author438=True,integration_shared_R12_hardware_cycles_not_qualified=True,ARM_calls=0,MPFR_inputs=0,device_IO=0)
with(O/'closure.json').open('x')as f:json.dump(out,f,indent=2);f.write('\n')
print(json.dumps(ref(O/'closure.json')),flush=True)

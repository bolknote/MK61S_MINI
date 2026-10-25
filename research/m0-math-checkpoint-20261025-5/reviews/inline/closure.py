"""Saved production-context, slowdown and free-layout evidence closure."""
import hashlib,json,struct,sys
from pathlib import Path
sys.dont_write_bytecode=True
R=Path('/Users/bolk/Projects/MK61S_MINI');O=Path(__file__).resolve().parent
sys.path.insert(0,str(R/'tests'));from check_stm32_vectors import ElfImage
def ref(p):
 p=Path(p);b=p.read_bytes();return dict(path=str(p),bytes=len(b),sha256=hashlib.sha256(b).hexdigest())
after=inline=latency=calls=returns=nested=0
for n in ['scalar-arm-mpfr.json','public-arm-mpfr.json']:
 v=json.loads((O/n).read_text())
 for r in v['rows']:
  co,ca=r['captures']['control'],r['captures']['candidate'];assert co['first']==ca['first']and co['after']==ca['after']and co['seeds']==ca['seeds']
  assert len(ca['calls'])==len(ca['pops']);calls+=len(ca['calls']);after+=len(ca['after']);latency+=len(ca['latency9'])
  for x in ca['inline']:
   assert x['inline_SP']==x['entry_SP']-20 and x['live'][-1]==x['inline_SP']and x['quotient']==0xffffffff//x['D'];inline+=1
   if n.startswith('public'):
    assert x['entry_SP']!=0x2003fff0;nested+=1
  if n.startswith('public'):assert len(ca['returns'])==len(ca['calls']);returns+=len(ca['returns'])
assert [after,inline,latency,calls,returns,nested]==[304,150,150,846,4,2]
sc=json.loads((O/'scalar-arm-mpfr.json').read_text());assert sc['new_correct_Qfp_deficits_in_bounded_set']==[]and sc['observed_parent_cost_increases']=={'11':128,'8':64,'2':26}
im=ElfImage(O/'rebuild/candidate.elf');s=im.named_sections['.ddiv'];assert s[3]==0x101e1000 and s[5]==1072 and s[3]+s[5]<0x10200000
assert 'mk61_m0_ddiv_seed17'not in im.symbols and not any(t[2]&2 and t[2]&1 and t[5]for t in im.sections)
visibility={}
for section in im.sections:
 if section[1]!=2:continue
 names=im.bytes_at(im.sections[section[6]])
 for n,v,z,info,other,index in struct.iter_unpack('<IIIBBH',im.bytes_at(section)):
  name=im.string(names,n)
  if name in ['mk61_m0_reciprocal1','mk61_m0_reciprocal1_sw_from_guard']:visibility[name]=other&3
assert len(visibility)==2 and set(visibility.values())=={2}
paths=[R/'.build/m0-asin-scaled-bound-v164-20261023/firmware/mk61s-picocalc-pico-h.elf']+[R/'.build'/n/'candidate.elf'for n in ['m0-exp-cached-product-20261024','m0-pow-square-ordinary-20261024','m0-pow-rsqrt-asm-20261024','m0-pow-exp-table-product-20261025','m0-pow-square128-r2-20261025','m0-pow-boundary128-20261025']]
for p in paths:
 e=ElfImage(p);assert not any(t[2]&2 and t[5]and max(s[3],t[3])<min(s[3]+s[5],t[3]+t[5])for t in e.sections)
table=ElfImage(R/'.build/m0-pow-exp-table-product-20261025/candidate.elf');entry=table.symbols['mk61_m0_pow_exp_table_product']&~1;old=ElfImage(R/'.build/m0-exp-directed-product-20261024/candidate.elf');os=old.named_sections['.product_ram'];assert min(entry+20,os[3]+os[5])-max(entry,os[3])==14
out=dict(status='PASS_FRESH_PRODUCTION_INLINE_CONTEXT_AND_LAYOUT_WITH_ALL_SLOWDOWNS_RETAINED',
 actual_production_inline_live_register_frame20_matches=150,nested_public_inline_checks_with_entrySP_not_outerSP=2,
 full_after_second_R0_R7_R12_SP_NZCV_frame28_checks=304,actual_READY9ALU_issue_read_checks=150,
 actual_positive_one_entry_return_POP_checks=846,actual_public_root_returns=4,
 old_seedBL8alignment_and_new_register_only_entrySPminus20_distinguished=True,
 own_scalar_parent_increases_kept=dict(plus11=128,plus8=64,plus2=26),new_correct_Qfp_deficits_in_bounded_set=0,
 no_universal_parent_or_Qfp_speed_claim=True,no_wrapper_stack_speed_production_claim=True,
 hidden_private_entries=visibility,old_standalone312_not_allocated=True,
 current1072bytes_free_Flash_below2MiB_no_new_writable_RAM=True,no_overlap_checks=[ref(p)for p in paths],
 loader_starts_from_boundary_no_old_private_trailing_code=True,old168overlay14B_table_hazard_persists=True,
 own_failed_preflights_partial_or_discarded_calls=0,integration_shared_R12_hardware_cycles_not_qualified=True,ARM_calls=0,MPFR_inputs=0,device_IO=0)
with (O/'closure.json').open('x')as f:json.dump(out,f,indent=2);f.write('\n')
print(json.dumps(ref(O/'closure.json')),flush=True)

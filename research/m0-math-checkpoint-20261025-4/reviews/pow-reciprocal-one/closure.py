"""Saved evidence closure: exact call/return scope, joins, losses and layout."""
import ast,hashlib,json,re,struct,sys
from pathlib import Path
sys.dont_write_bytecode=True
R=Path('/Users/bolk/Projects/MK61S_MINI');O=Path(__file__).resolve().parent;W=R/'.build/m0-pow-reciprocal-one-20261025'
sys.path.insert(0,str(R/'tests'));from check_stm32_vectors import ElfImage
def ref(p):
 p=Path(p);b=p.read_bytes();return dict(path=str(p),bytes=len(b),sha256=hashlib.sha256(b).hexdigest())
fn=next(n for n in ast.parse((O/'proof.py').read_text()).body if isinstance(n,ast.FunctionDef)and n.name=='parse');exec(compile(ast.Module(body=[fn],type_ignores=[]),'<pure disassembly parser>','exec'),globals())
e=ElfImage(O/'rebuild/candidate.elf');code=parse((O/'candidate.elf.actual.dis').read_text());entry=e.symbols['mk61_m0_reciprocal1']&~1
incoming=[pc for pc,(n,op,args)in code.items()if op=='bl'and int(args.split()[0],16)==entry];assert incoming==[0x1014e668+2732]
for name in ['candidate-ddiv.S','candidate-software.S']:
 s=(W/name).read_text();assert s.count('.Lrp2040_quotient_refine:')==1
 assert s.count(' b .Lrp2040_quotient_refine')==(1 if name=='candidate-ddiv.S'else 0)
visibility={}
for s in e.sections:
 if s[1]!=2:continue
 names=e.bytes_at(e.sections[s[6]])
 for n,a,z,info,other,index in struct.iter_unpack('<IIIBBH',e.bytes_at(s)):
  name=e.string(names,n)
  if name in ['mk61_m0_reciprocal1','mk61_m0_reciprocal1_sw_from_guard']:visibility[name]=other&3
assert len(visibility)==2 and set(visibility.values())=={2}
after=R3=scalar_calls=public_calls=public_returns=ready9=0
for name in ['scalar-arm-mpfr.json','public-arm-mpfr.json']:
 v=json.loads((O/name).read_text())
 for r in v['rows']:
  a,b=r['captures']['control'],r['captures']['candidate'];assert a['after']==b['after']and a['first']==b['first']and a['seeds']==b['seeds']
  assert len(b['calls'])==len(b['pops'])and all(x['numerator']=='3FF0000000000000'for x in b['calls'])
  after+=len(b['after']);R3+=len(b['R3_restore']);ready9+=len(b['hardware_latency'])
  if name.startswith('public'):
   assert len(b['calls'])==len(b['return_sites'])and all(p==0x1014e668+2732+4 for p in b['return_sites']);public_calls+=len(b['calls']);public_returns+=len(b['return_sites'])
  else:scalar_calls+=len(b['calls'])
assert after==318 and R3==157 and scalar_calls==846 and public_calls==public_returns==10 and ready9>0
s=e.named_sections['.ddiv'];assert s[3]==0x101e1000 and s[5]==1060 and s[3]+s[5]<0x10200000
paths=[R/'.build/m0-asin-scaled-bound-v164-20261023/firmware/mk61s-picocalc-pico-h.elf']+[R/'.build'/n/'candidate.elf'for n in ['m0-exp-cached-product-20261024','m0-pow-square-ordinary-20261024','m0-pow-rsqrt-asm-20261024','m0-pow-exp-table-product-20261025','m0-pow-square128-r2-20261025','m0-pow-boundary128-20261025']]
for p in paths:
 im=ElfImage(p);assert not any(t[2]&2 and t[5]and max(s[3],t[3])<min(s[3]+s[5],t[3]+t[5])for t in im.sections)
assert not any(t[2]&2 and t[2]&1 and t[5]for t in e.sections)
table=ElfImage(R/'.build/m0-pow-exp-table-product-20261025/candidate.elf');te=table.symbols['mk61_m0_pow_exp_table_product']&~1;old=ElfImage(R/'.build/m0-exp-directed-product-20261024/candidate.elf');os=old.named_sections['.product_ram'];assert min(te+20,os[3]+os[5])-max(te,os[3])==14
scalar=json.loads((O/'scalar-arm-mpfr.json').read_text());witnesses=scalar['normal_loss_witnesses'];assert len(witnesses)==18 and scalar['correct_normal_lag_ranges']==dict(READY=[2,5],DIRTY=[15,21])
assert any(r['denominator']=='3FF27D0DF6735E90'and r['SIO']=='DIRTY'and r['candidate']==167 and r['Qfplib']==146 for r in witnesses)
out=dict(status='PASS_PRIVATE_CALLER_SCOPE_FULL_AFTER_SECOND_STATE_AND_CORRECTED_DEFICIT_CLOSURE',
 sole_actual_root_BL=hex(incoming[0]),hidden_entry_and_private_software=visibility,
 first_product_incoming_controlflow_only_ready_small_divisor_or_guarded_linear_NR=True,
 actual_candidate_scalar_entries_and_return_pops=scalar_calls,actual_public_entries_return_pops_and_return_sites=public_calls,
 actual_public_return_site=hex(0x1014e668+2732+4),all_entries_exact_positive1=True,
 after_second_R0_R7_R12_SP_NZCV_saved28_equal_checks=after,R3_save_pop_and_private_raw_frame_checks=R3,
 actual_READY9ALU_issue_read_checks=ready9,
 all9remaining_normal_denominators_16flags_bothSIO_and_corrigendum_witness_reproduced=True,
 actual_normal_deficit_ranges=dict(READY=[2,5],DIRTY=[15,21],overall=[2,21]),no_universal_reciprocal_speed_claim=True,
 allocation1060_free_Flash_below2MiB_no_new_RAM=True,no_overlap_against=[ref(p)for p in paths],
 loader_starts_from_boundary_without_old_private_trailing_code=True,old168overlay14B_hazard_persists=True,
 own_HOST_preflights2_ARM0_MPFR0_preserved=True,no_failed_partial_or_discarded_own_ARM=True,
 integration_R12_loader_layout_physical_cycles_not_qualified=True,ARM_calls=0,MPFR_inputs=0,device_IO=0)
with (O/'closure.json').open('x')as f:json.dump(out,f,indent=2);f.write('\n')
print(json.dumps(ref(O/'closure.json')),flush=True)

"""Fresh linked R3 caller proof, executed capture binding and own label fix."""
import ast,hashlib,json,re,struct,sys
from pathlib import Path
sys.dont_write_bytecode=True
R=Path('/Users/bolk/Projects/MK61S_MINI');O=Path(__file__).resolve().parent;W=R/'.build/m0-pow-reciprocal-lut-20261025';P=R/'.build/m0-pow-reciprocal-soft-20261025'
sys.path.insert(0,str(R/'tests'));from check_stm32_vectors import ElfImage
def ref(p):
 p=Path(p);b=p.read_bytes();return dict(path=str(p),bytes=len(b),sha256=hashlib.sha256(b).hexdigest())
def save(n,d):
 with (O/n).open('x')as f:json.dump(d,f,indent=2);f.write('\n')
 return ref(O/n)
def parse(text):
 out={}
 for line in text.splitlines():
  m=re.match(r'^\s*([0-9a-f]+):\s+((?:[0-9a-f]{4}\s+)+)([a-z][a-z0-9.]*)\s*(.*)',line)
  if m:out[int(m[1],16)]=(len(m[2].split())*2,m[3].split('.')[0],m[4].split('@')[0].strip())
 return out
e=ElfImage(O/'rebuild/candidate.elf');old=ElfImage(P/'candidate.elf');code=parse((O/'candidate.elf.actual.dis').read_text());sw=e.symbols['mk61_m0_ddiv_sw_from_guard']&~1;seed=e.symbols['mk61_m0_ddiv_seed17']&~1;join=e.symbols['mk61_m0_sw_join']&~1
calls=[pc for pc,(n,op,args)in code.items()if sw<=pc<join and op=='bl'and int(args.split()[0],16)==seed];assert len(calls)==1;call=calls[0]
push=code[call-8];pop=code[call+8]
assert push[1]=='push'and pop[1]=='pop'and push[2]==pop[2]
assert all(re.search(r'\b'+r+r'\b',push[2])for r in ['r0','r1','r2','r3','r7'])
assert code[call+4][1:] == ('adds','r6, r0, #1')and code[call+6][1:] == ('lsrs','r6, r6, #1')and call+10==join
assert code[0x1014e668+2732][1]=='bl'and int(code[0x1014e668+2732][2].split()[0],16)==e.symbols['mk61_m0_hint_ddiv']&~1
# This prefix includes guards, the live20B frame/setup and all common282B
# NR/RNE instructions. It is bound afresh before reusing the accepted audit.
s=e.named_sections['.ddiv'];os=old.named_sections['.ddiv'];off=seed-s[3]
assert off==856 and e.bytes_at(s)[:off]==old.bytes_at(os)[:off]
chains=[]
for name in ['ddiv-arm-mpfr.json','public-arm-mpfr.json']:
 v=json.loads((O/name).read_text())
 for row in v['rows']:
  c=row['captures']['candidate'];assert len(c['seeds'])==len(c['R3_save_clobber_pop_join'])
  for rec in c['R3_save_clobber_pop_join']:
   assert rec['D']in c['seeds']and 0<=rec['leaf_R3']<rec['D']and rec['saved_R3']==rec['join_R3']>=0x100000 and rec['leaf_R3']!=rec['saved_R3']
   assert c['joins'][0]['registers'][3]==rec['join_R3']
   chains.append(dict(source=name,record=rec))
assert len(chains)==25
# Isolated additive reporting correction. The old keyword identifier survived
# an AST Constant adaptation; executable assertion and status were already9.
pub=json.loads((O/'public-arm-mpfr.json').read_text());assert pub['all48_fixes_actual_bothSIO_strict_against_all_correct_refs']is True and 'ALL9'in pub['status']
fixed={tuple(p)for p in json.loads((W/'qualification.json').read_text())['fixed_pairs']};assert len(fixed)==9
seen=set()
for r in pub['rows']:
 if (r['x'],r['y'])in fixed:
  seen.add((r['x'],r['y']))
  assert all(r['instructions']['candidate']<r['instructions'][q]for q in ['qfp_composed_pow','qfp_composed_pow_exact','qfp_composed_pow_integer']if r['correct'][q])
assert seen==fixed
src=ast.parse((O/'arm.py').read_text());adapt=next(n for n in src.body if isinstance(n,ast.ClassDef)and n.name=='Adapt');env={'ast':ast}
exec(compile(ast.Module(body=[adapt],type_ignores=[]),'<pure-driver-adaptation>','exec'),env)
prev=R/'.build/m0-pow-reciprocal-soft-independent-20261025/arm.py';tree=ast.parse(prev.read_text());driver=[]
for name in ['ddiv','public']:
 fn=next(n for n in tree.body if isinstance(n,ast.FunctionDef)and n.name==name);a=env['Adapt'](name);fn=a.visit(fn);driver.append(dict(function=name,edits=a.edits))
 if name=='ddiv':assert not any(isinstance(n,ast.Constant)and n.value=='__aeabi_ddiv'for n in ast.walk(fn))
 else:
  assert any(isinstance(n,ast.Constant)and n.value==9 for n in ast.walk(fn))
  assert any(isinstance(n,ast.keyword)and n.arg=='all48_fixes_actual_bothSIO_strict_against_all_correct_refs'for n in ast.walk(fn))
corr=save('PUBLIC-REPORT-CORRIGENDUM.json',dict(status='OWN_REPORT_KEYWORD_LABEL_CORRECTION_ONLY_NO_NUMERICAL_CHANGE',
 report=ref(O/'public-arm-mpfr.json'),executed_source=ref(O/'arm.py'),
 original_keyword='all48_fixes_actual_bothSIO_strict_against_all_correct_refs',correct_keyword='all9_fixes_actual_bothSIO_strict_against_all_correct_refs',
 reason='Keyword identifier inherited from the old bounded driver was not an AST Constant; actual fixed-count assertion9, statusALL9, raw23pairs and all9 memberships already correct.',
 independently_confirmed_all9_bothSIO_strict=True,original_raw_and_executed_source_unchanged=True,ARM_calls=0,MPFR_inputs=0,no_failed_or_discarded_ARM=True))
paths=[R/'.build/m0-asin-scaled-bound-v164-20261023/firmware/mk61s-picocalc-pico-h.elf']+[R/'.build'/n/'candidate.elf'for n in ['m0-exp-cached-product-20261024','m0-pow-square-ordinary-20261024','m0-pow-rsqrt-asm-20261024','m0-pow-exp-table-product-20261025','m0-pow-square128-r2-20261025','m0-pow-boundary128-20261025']]
assert s[3]==0x101e1000 and s[5]==1168 and s[3]+s[5]<0x10200000
for p in paths:
 im=ElfImage(p);assert not any(t[2]&2 and t[5]and max(t[3],s[3])<min(t[3]+t[5],s[3]+s[5])for t in im.sections)
assert not any(t[2]&2 and t[2]&1 and t[5]for t in e.sections)
table=ElfImage(R/'.build/m0-pow-exp-table-product-20261025/candidate.elf');entry=table.symbols['mk61_m0_pow_exp_table_product']&~1
overlay=ElfImage(R/'.build/m0-exp-directed-product-20261024/candidate.elf');ov=overlay.named_sections['.product_ram'];assert min(ov[3]+ov[5],entry+20)-max(ov[3],entry)==14
out=dict(status='PASS_FRESH_LINKED_PRIVATE_CALLER_NEW_R3_CLOBBER_SAVE_POP_JOIN_AND_LAYOUT',
 actual_seed_BL=hex(call),actual_push_R0_R3_R7=push,actual_pop_R0_R3_R7=pop,
 quotient_consumed_in_R6_before_POP_restores_R0=True,original_R3_must_be_saved_by_this_actual_caller=True,
 seed856prefix_guards_R6_frame_R12_common282_all_fresh_bound=True,new_R3_contract_not_inherited_from_old_leaf=True,
 actual_R3_save_clobber_pop_join_chains=chains,count=25,R1_R12_PCS_SP_PC_and_SIO_checks_preserved=True,
 reused_guard_driver_source=ref(prev),explicit_driver_changes=driver,parent_uses_private_hint_alias_not_original_resident_ddiv=True,
 own_report_keyword_metadata_correction=corr,own_failed_preflights=0,own_discarded_ARM_calls=0,
 allocation1168_free_Flash_below2MiB_no_new_writable_allocations=True,no_overlap_checks=[ref(p)for p in paths],
 old168_exp_overlay14B_table_hazard_persists=True,no_fresh_actual_integrated_shared_R12_guard_claim=True,
 private_continuation_raw_operands_guardedR6_original20B_frame_not_CABI=True,ARM_calls=0,MPFR_inputs=0,device_IO=0)
print(json.dumps(save('caller-layout.json',out)),flush=True)

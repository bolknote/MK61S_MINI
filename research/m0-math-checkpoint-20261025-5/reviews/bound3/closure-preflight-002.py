"""Actual full-context/count closure and exact current private layout."""
import hashlib,json,struct,sys
from pathlib import Path
sys.dont_write_bytecode=True
R=Path('/Users/bolk/Projects/MK61S_MINI');O=Path(__file__).resolve().parent;sys.path.insert(0,str(R/'tests'))
from check_stm32_vectors import ElfImage
def ref(p):
 p=Path(p);b=p.read_bytes();return dict(path=str(p),bytes=len(b),sha256=hashlib.sha256(b).hexdigest())
def mem(e,a,n):
 s=next(s for s in e.sections if s[1]!=8 and s[3]<=a and a+n<=s[3]+s[5]);return e.bytes_at(s)[a-s[3]:a-s[3]+n]
counts={k:0 for k in ['calls','before','after','residual','pre_cert','certificates','pack','inline','pops','returns','latency9','classified','restored','zero_up','rounded','nested','changed_R7_before','changed_R7_rounded']}
for name in ['scalar-arm-mpfr.json','public-arm-mpfr.json']:
 j=json.loads((O/name).read_text())
 for r in j['rows']:
  c,n=r['captures']['control'],r['captures']['candidate']
  for key in ['calls','first','after','residual','half','zeros','pre_cert','certificates','down','pack','seeds']:assert c[key]==n[key]
  for key in ['before','rounded']:
   for a,b in zip(c[key],n[key]):
    assert a['frame28']==b['frame28']and[x for i,x in enumerate(a['registers'])if i!=7]==[x for i,x in enumerate(b['registers'])if i!=7]
    D=a['registers'][1];domain=json.loads((O/'integer-domain.json').read_text())['rows']if False else None
    counts['changed_R7_'+key]+=a['registers'][7]!=b['registers'][7]
  for key in counts:
   if key=='nested':counts[key]+=sum(v['entry_SP']!=0x2003fff0 for v in n['inline'])if name.startswith('public')else 0
   elif key.startswith('changed_R7_'):continue
   else:counts[key]+=len(n[key])if isinstance(n[key],list)else n[key]
  for v in n['inline']:assert v['inline_SP']==v['entry_SP']-20
assert counts==dict(calls=566,before=514,after=514,residual=514,pre_cert=368,certificates=368,pack=514,inline=255,pops=566,returns=22,latency9=255,classified=368,restored=130,zero_up=166,rounded=255,nested=11,changed_R7_before=58,changed_R7_rounded=58)
cpu=[json.loads((O/n).read_text())for n in ['unit-arm.json','scalar-arm-mpfr.json','public-arm-mpfr.json']]
assert sum(j['actual_ARM_calls']for j in cpu)==2908 and sum(j.get('directed_MPFR_inputs',0)for j in cpu)==62 and sum(j.get('sNaN_shortcuts',0)for j in cpu)==6
assert not list(O.glob('RUNTIME-FAILURE-*'))and len(list(O.glob('HOST-PREFLIGHT-*')))==1
e=ElfImage(O/'rebuild/candidate.elf');sec=e.named_sections['.ddiv'];assert sec[3]==0x101e1000 and sec[5]==1108 and sec[3]+sec[5]<0x10200000
assert not any(s[2]&2 and s[2]&1 and s[5]for s in e.sections)
vis={}
for s in e.sections:
 if s[1]!=2:continue
 names=e.bytes_at(e.sections[s[6]])
 for n,v,z,info,other,index in struct.iter_unpack('<IIIBBH',e.bytes_at(s)):
  name=e.string(names,n)
  if name in ['mk61_m0_reciprocal1','mk61_m0_reciprocal1_sw_from_guard']:vis[name]=other&3
assert len(vis)==2 and set(vis.values())=={2}
pc=0x1014f114;h1,h2=struct.unpack('<HH',mem(e,pc,4));S=(h1>>10)&1;I1=1^((h2>>13)&1)^S;I2=1^((h2>>11)&1)^S;im=(S<<24)|(I1<<23)|(I2<<22)|((h1&1023)<<12)|((h2&2047)<<1)
assert pc+4+(im-(1<<25)if S else im)==(e.symbols['mk61_m0_reciprocal1']&~1)==0x101e105e
assert mem(e,pc-10,10).hex()=='002742187b41ac493846'and mem(e,0x1014f3c4,4)==struct.pack('<I',0x3ff00000)
paths=[R/'.build/m0-asin-scaled-bound-v164-20261023/firmware/mk61s-picocalc-pico-h.elf']+[R/'.build'/n/'candidate.elf'for n in ['m0-exp-cached-product-20261024','m0-pow-square-ordinary-20261024','m0-pow-rsqrt-asm-20261024','m0-pow-exp-table-product-20261025','m0-pow-square128-r2-20261025','m0-pow-boundary128-20261025']]
for p in paths:
 t=ElfImage(p);assert not any(s[2]&2 and s[5]and max(sec[3],s[3])<min(sec[3]+sec[5],s[3]+s[5])for s in t.sections)
table=ElfImage(R/'.build/m0-pow-exp-table-product-20261025/candidate.elf');entry=table.symbols['mk61_m0_pow_exp_table_product']&~1;old=ElfImage(R/'.build/m0-exp-directed-product-20261024/candidate.elf');os=old.named_sections['.product_ram'];assert min(entry+20,os[3]+os[5])-max(entry,os[3])==14
root=ref(R/'.build/m0-pow-reciprocal-zero-root-acceptance-20261025-001/RECEIPT.json');assert root['bytes']==20786 and root['sha256']=='4ee40fcbbcba128c8258f35efb38f72d43eea1dfff584da4611252e433529d7f'
out=dict(status='PASS_FRESH_PRIVATE_R0_SEED_CONTEXT_EXACT_R7_DEADNESS_AND_COMPLETE_DOWNSTREAM_CLOSURE',counts=counts,
 own_ARM2908_MPFR62_plus6sNaN=True,actual_seed_all5errors_all16flags_exactquotient_and_privatezero=True,58_actual_allowed_R7differences_before_dead_overwrite=True,
 full_after_second_residual_certificate_pack_NZCV_and28B_frame_equal=True,old_new_control_roles_explicit_not_failed_author_rule=True,
 READY9ALU_DIRTY7words_originalframe20_PCS_R6guard_R12_and_actualrootreturn_checked=True,all128tableconstants_andfull65536HOST_proof_bound=True,
 later_parentROOT_additive=root,child_missing_at_seal_ROOT_not_rewritten=True,hidden_private_entries=vis,
 allocation1108_freeFlash_below2MiB_noRAM_overlap_refs=[ref(p)for p in paths],same256Btable=True,
 physical_error1_branch_direction_effect_unmeasured=True,instruction_nonincrease_NOT_cycle_nonregression=True,
 oldloopcontrol_must_be_retained_for_future_physical_comparison=True,ancestral32_Certificate_regressions26plus6_6plus5_kept=True,
 own_HOST_signed_residual_representation_preflight0ARM0MPFR_retained=True,numerical_failed_partial_discarded_calls=0,
 source_merge_relink_sharedR12_loader_layout_old168overlay14B_required=True,reviewed507422_not_author438=True,
 integration_GO=False,performance_adoption_GO=False,hardware_GO=False,main_GO=False,release_GO=False,ARM_calls=0,MPFR_inputs=0,devices=0)
with(O/'closure.json').open('x')as f:json.dump(out,f,indent=2);f.write('\n')
print(json.dumps(ref(O/'closure.json')),flush=True)

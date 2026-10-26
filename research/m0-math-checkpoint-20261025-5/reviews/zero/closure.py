"""Saved fresh context/resource closure, no new numeric execution."""
import hashlib,json,struct,sys
from pathlib import Path
sys.dont_write_bytecode=True
R=Path('/Users/bolk/Projects/MK61S_MINI');O=Path(__file__).resolve().parent;sys.path.insert(0,str(R/'tests'))
from check_stm32_vectors import ElfImage
def ref(p):
 p=Path(p);b=p.read_bytes();return dict(path=str(p),bytes=len(b),sha256=hashlib.sha256(b).hexdigest())
def mem(e,a,n):
 s=next(s for s in e.sections if s[1]!=8 and s[3]<=a and a+n<=s[3]+s[5]);return e.bytes_at(s)[a-s[3]:a-s[3]+n]
tot={k:0 for k in ['calls','before','after','residual','half','zeros','pre_cert','certificates','down','pack','inline','pops','returns','latency9','classified','restored','zero_up','nested']}
for name in ['scalar-arm-mpfr.json','public-arm-mpfr.json']:
 j=json.loads((O/name).read_text())
 for r in j['rows']:
  c,n=r['captures']['control'],r['captures']['candidate']
  for k in ['before','residual','pre_cert','certificates','half','zeros','calls','down','seeds']:assert c[k]==n[k]
  for a,b in zip(c['after'],n['after']):
   b=json.loads(json.dumps(b));b['registers'][0],b['registers'][4]=b['registers'][4],b['registers'][0];assert a==b
  for a,b in zip(c['pack'],n['pack']):assert a['frame28']==b['frame28']and[x for i,x in enumerate(a['registers'])if i not in {3,6}]==[x for i,x in enumerate(b['registers'])if i not in {3,6}]
  for k in tot:
   if k=='nested':tot[k]+=sum(v['entry_SP']!=0x2003fff0 for v in n['inline'])if name.startswith('public')else 0
   else:tot[k]+=len(n[k])if isinstance(n[k],list)else n[k]
  for v in n['inline']:assert v['inline_SP']==v['entry_SP']-20
assert tot==dict(calls=460,before=408,after=408,residual=408,half=408,zeros=382,pre_cert=382,certificates=382,down=382,pack=408,inline=202,pops=460,returns=16,latency9=202,classified=382,restored=134,zero_up=202,nested=8)
us=[json.loads((O/n).read_text())for n in ['unit-arm.json','unit-decisive-arm.json','scalar-arm-mpfr.json','public-arm-mpfr.json']]
assert sum(v['actual_ARM_calls']for v in us)==6024 and sum(v.get('directed_MPFR_inputs',0)for v in us)==69 and sum(v.get('sNaN_shortcuts',0)for v in us)==6
assert not list(O.glob('RUNTIME-FAILURE-*'))and len(list(O.glob('HOST-PREFLIGHT-*')))==1
e=ElfImage(O/'rebuild/candidate.elf');sec=e.named_sections['.ddiv'];assert sec[3]==0x101e1000 and sec[5]==1100 and sec[3]+sec[5]<0x10200000
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
out=dict(status='PASS_FRESH_KNOWN_ZERO_PRIVATE_CALLER_FULL_RESIDUAL_PACK_AND_RESOURCE_CLOSURE',counts=tot,own_ARM6024_MPFR69_plus6sNaN=True,
 exact_permutation_full_product_state_and_full_after_residual_checked=True,generic_arbitraryR6_actual_decisive_target128checks=True,
 fresh_complete_residual_pre_cert_and_projected_pack_NZCV_frame_join_not_unchanged186suffix=True,
 positive_ADC_known_zero202_and134fullbase_restores_checked=True,private_zero_vs_generic_R6_preservation_separate=True,
 fresh_sole_positive_one_BL_return_PCS_original20B_frame_R6guard_R12_checked=True,hidden_private_entries=vis,
 allocation1100_free_Flash_no_new_RAM_or_overlap=True,no_overlap_refs=[ref(p)for p in paths],
 both_new_expanded_remaining_losses_and_old_loss_now_equal_checked=True,ancestral32regressions26plus6_6plus5vsInline_and2already_losing_kept=True,
 numerical_failed_partial_discarded_calls=0,one_own_HOST_syntax_preflight0ARM0MPFR_preserved=True,
 source_merge_actual_R12_loader_layout_old168overlay14B_required=True,near_one_separate_sibling=True,reviewed507422_not_author438=True,
 integration_GO=False,performance_adoption_GO=False,hardware_GO=False,main_GO=False,release_GO=False,ARM_calls=0,MPFR_inputs=0,devices=0)
with(O/'closure.json').open('x')as f:json.dump(out,f,indent=2);f.write('\n')
print(json.dumps(ref(O/'closure.json')),flush=True)

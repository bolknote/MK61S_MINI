"""Read-only sealed source/body binding and saved performance accounting."""
from pathlib import Path
from collections import Counter
import hashlib,json,struct,sys
ROOT=Path('/Users/bolk/Projects/MK61S_MINI');W=ROOT/'.build/m0-log-ratio-small-limb-20261024';OUT=Path(__file__).resolve().parent;BASE=ROOT/'.build/m0-ln-endpoint-predicate-20261024'
sys.path.insert(0,str(ROOT/'tests'));from check_stm32_vectors import ElfImage
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
def allocated(im):return {n:('NOBITS',s[5]) if s[1]==8 else ('BYTES',im.bytes_at(s)) for n,s in im.named_sections.items() if s[2]&2}
a,b=ElfImage(W/'control-full.o'),ElfImage(W/'candidate-full.o');aa,bb=allocated(a),allocated(b);assert aa.keys()==bb.keys();changed=[n for n in aa if aa[n]!=bb[n]];assert changed==['.m0_pow_extension']
old,new=aa[changed[0]][1],bb[changed[0]][1];assert len(new)-len(old)==212 and old[:848]==new[:848] and old[1080:]==new[1292:]
contexts={}
for name in ('generic_M0','M4_soft','M4_hard'):
 x,y=ElfImage(W/(name+'-control.o')),ElfImage(W/(name+'-candidate.o'));assert allocated(x)==allocated(y);contexts[name]='allocated code/data/BSS size identical (not whole-platform firmware)'
x,y=ElfImage(W/'control.elf'),ElfImage(W/'candidate.elf');assert x.bytes_at(x.named_sections['.rodata'])==y.bytes_at(y.named_sections['.rodata'])
sizes=[sum(s[5] for s in im.named_sections.values() if s[2]&2) for im in (x,y)];assert sizes[1]-sizes[0]==216
src=(W/'native_eabi_m0_log70_center.inc').read_text();parent=(BASE/'native_eabi_m0_log70_center.inc').read_text();start=src.index('  if(uint32_t(uint32_t(delta)+64U)<=128U) {');endpoint=src.index('  // At either dyadic half-segment endpoint',start);family=src.index('  // For a small signed low limb,',endpoint);tail=src.index('  const U q=mk61_m0_log_product46(delta,reciprocal);',family)
reconstructed=(src[:start]+src[endpoint:family]+src[tail:]).replace('return q+(uint32_t(r>=den)+uint32_t(r>=2*den));','return q+uint32_t(r>=den)+uint32_t(r>=2*den);').replace('  const int32_t signed_correction=negative?-int32_t(correction):int32_t(correction);\n  return q+U(int64_t(signed_correction));','  return negative?q-correction:q+correction;');assert reconstructed==parent
for n in ['native_eabi_m0.cpp','native_eabi_m0_log70.inc','native_eabi_m0_log10.inc','native_eabi_m0_log70_ratio.inc','native_eabi_m0_log_subnormal.inc','ratio.S']:assert (W/n).read_bytes()==(BASE/n).read_bytes(),n
near=[]
for n in x.symbols:
 if 'ln_near' in n and n in y.symbols and x.sizes.get(n,0):near.append(dict(symbol=n,parent=hex(x.symbols[n]),candidate=hex(y.symbols[n]),bytes=x.sizes[n]))
assert near and any(p['parent']!=p['candidate'] for p in near)
for n in ('candidate-full.o','candidate-ratio.o','candidate.elf'):assert (OUT/'rebuild'/n).read_bytes()==(W/n).read_bytes()
# Independent arithmetic reconstruction of saved eligibility/counts; not an MPFR or ARM rerun.
q=json.loads((W/'qualification.json').read_bytes());oldq=json.loads((BASE/'qualification.json').read_bytes());prior={(r['x'],r['SIO']):r for r in oldq['rows']};seen=set();state_rows={s:[] for s in ('READY','DIRTY')};parent_loss=set();child_loss=set();new_loss=[];reg=Counter()
def numeric_same(a,b):return a==b or ((a&0x7fffffffffffffff)>0x7ff0000000000000 and (b&0x7fffffffffffffff)>0x7ff0000000000000)
for row in q['rows']:
 k=row['x'],row['SIO'];assert k not in seen;seen.add(k);state_rows[k[1]].append(row)
 expected=int(row['expected'],16)
 for name,value in row['outputs'].items():assert row['correct'][name]==numeric_same(int(value,16),expected)
 assert row['outputs']['candidate']==row['outputs']['parent']==row['outputs']['resident']
 if k in prior:assert row['instructions']['parent']==prior[k]['instructions']['candidate'] and row['outputs']['parent']==prior[k]['outputs']['candidate']
 if row['correct']['Qfplib']:
  pi,ci,qi=(row['instructions'][n] for n in ('parent','candidate','Qfplib'))
  if pi>qi:parent_loss.add(row['x'])
  if ci>qi:child_loss.add(row['x'])
  if ci>qi>=pi:new_loss.append(k)
 if row['instructions']['candidate']>row['instructions']['parent']:reg[row['instructions']['candidate']-row['instructions']['parent']]+=1
assert set(prior)<=seen and len(prior)==66172 and len(seen)==68876
assert len(parent_loss)==223 and len(child_loss)==68 and len(parent_loss-child_loss)==155 and not new_loss
assert reg==Counter({3:2682,4:4097})
groups={}
for s,rows in state_rows.items():
 assert len(rows)==34438
 change=Counter('faster' if r['instructions']['candidate']<r['instructions']['parent'] else 'slower' if r['instructions']['candidate']>r['instructions']['parent'] else 'equal' for r in rows)
 groups[s]=dict(change)
assert groups=={'READY':{'equal':34438},'DIRTY':{'slower':6779,'equal':22863,'faster':4796}}
result=dict(status='PASS_SOURCE_BINDING_ISOLATION_AND_SAVED_PERFORMANCE_ACCOUNTING',source_SHA256=sha(W/'native_eabi_m0_log70_center.inc'),ELF_SHA256=sha(W/'candidate.elf'),rebuild_hashes={n:sha(OUT/'rebuild'/n) for n in ('candidate-full.o','candidate-ratio.o','candidate.elf')},only_object_allocated_section_changed=changed,object_code_growth=212,allocated_linked_sizes=sizes,linked_growth=216,no_global_RAM_or_new_table=True,contexts=contexts,parent_source_reconstructed_exactly=True,all_other_local_sources_and_ratio_ASM_byteexact=True,near_functions_linked_addresses_relocated=near,old_linked_byte_identity_not_claimed=True,retained_parent_state_rows=len(prior),all_saved_parent_counts_outputs_equal=True,numeric_Qfp_eligibility_recomputed=True,raw_NaN_candidate_parent_bits_equal=True,expanded_parent_raw_losses=len(parent_loss),expanded_child_raw_losses=len(child_loss),raw_losses_fixed=len(parent_loss-child_loss),new_correct_Qfp_raw_losses=0,saved_regression_histogram=dict(reg),groups=groups,physical_cycles=False,whole_ln_speed_GO=False,hardware_accessed=False,numerical_or_large_corpus_replay=False)
(OUT/'binding-performance.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))

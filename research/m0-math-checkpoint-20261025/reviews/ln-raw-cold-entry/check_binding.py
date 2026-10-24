"""Narrow immutable IEEE-entry source/object/ELF and saved cost binding."""
from pathlib import Path
from collections import Counter
import difflib,hashlib,json,re,subprocess,sys
sys.dont_write_bytecode=True
R=Path('/Users/bolk/Projects/MK61S_MINI');P=R/'.build/m0-ln-raw-cold-entry-20261024';PAR=R/'.build/m0-ln-main-raw-split-family-20261024';O=Path(__file__).resolve().parent
H=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
def read(p):return json.loads(Path(p).read_text())
def pin(p):return dict(path=str(p),sha256=H(p))
assert H(P/'HANDOFF.md')=='64b6eae621246192a11e3e2d5e9a8dffd330688a39cca4fd04c669248bc7c3c9'
assert H(P/'result.json')=='202be6bb558e24d314ab7dd43da6b2690fdf331bbf271b1ec40a36364710e184'
r=read(P/'result.json')
for n,h in r['files'].items():assert H(P/n)==h,n
inputs=read(P/'input-pins.json')['files']
for n,h in inputs.items():assert H(R/n)==h,n
parent_review=R/'.build/m0-ln-main-raw-split-family-independent-20261024/FINAL-REVIEW.json'
assert H(parent_review)=='54dc555c2c702619ec174354e6209da4629e1436f5799d4028c2e9d8baaf5150'
assert r['parent_result_sha256']==H(PAR/'result.json') and (P/'control.elf').read_bytes()==(PAR/'candidate.elf').read_bytes()
source=(P/'native_eabi_m0_log70.inc').read_text();parent=(PAR/'native_eabi_m0_log70.inc').read_text()
entry='__attribute__((optimize("Os"))) MK61_SOFT_PCS double mk61_m0_ln(double x) {'
replacement_start='#if defined(MK61_M0_RP2040_EABI) && MK61_M0_RP2040_EABI\n// Avoid a C++ frame'
assert source[:source.index(replacement_start)]==parent[:parent.index(entry)]
tail='  if(b>=ln_near_lower && b<=UINT64_C(0x3FF0400000000000))'
assert source[source.index(tail):]==parent[parent.index(tail):]
old_header='''__attribute__((optimize("Os"))) MK61_SOFT_PCS double mk61_m0_ln(double x) {
  const U b=bits(x);
  if(b<UINT64_C(0x0010000000000000) || b>=D::Infinity) {
#if defined(MK61_M0_RP2040_EABI) && MK61_M0_RP2040_EABI
    return mk61_m0_ln_special(x);
#else
    return mk61_m0_cr_ln(x);
#endif
  }
'''
assert parent[parent.index(entry):parent.index(tail)]==old_header
generic='''#else
__attribute__((optimize("Os"))) MK61_SOFT_PCS double mk61_m0_ln(double x) {
  const U b=bits(x);
  if(b<UINT64_C(0x0010000000000000) || b>=D::Infinity)
    return mk61_m0_cr_ln(x);
#endif
'''
assert source[source.index(replacement_start):source.index(tail)].endswith(generic)
def function(s,name):
 a=s.index(name+'(');a=s.index('{',a);d=1;i=a+1
 while d:d+=(s[i]=='{')-(s[i]=='}');i+=1
 return s[a:i]
assert function(source,'ln_main_raw')==function(parent,'ln_main_raw')
assert function(source,'mk61_m0_ln')==function((P/'entry-unit.cpp').read_text(),'mk61_m0_ln')
for n in ['native_eabi_m0.cpp','native_eabi_m0_log70_center.inc','native_eabi_m0_log70_ratio.inc','native_eabi_m0_log_subnormal.inc','native_eabi_m0_log10.inc','ratio.S']:assert (P/n).read_bytes()==(PAR/n).read_bytes(),n
# Classification is independent of arbitrary low/fraction bits, except the
# exact zero and positive-infinity predicates. Exhaust the4096 field values.
for field in range(4096):assert ((((field+1)>>11)==0) and field!=0)==(1<=field<=2046)
sys.path.insert(0,str(R/'tests'));from check_stm32_vectors import ElfImage
def alloc(e):return {n:('NOBITS',s[5]) if s[1]==8 else ('BYTES',e.bytes_at(s)) for n,s in e.named_sections.items() if s[2]&2}
aa,bb=alloc(ElfImage(P/'control-full.o')),alloc(ElfImage(P/'candidate-full.o'))
changed={n:[len(aa.get(n,('BYTES',b''))[1]),len(bb.get(n,('BYTES',b''))[1])] for n in aa.keys()|bb.keys() if aa.get(n)!=bb.get(n)}
assert set(changed)=={'.text.mk61_m0_ln','.text.mk61_m0_ln_positive','.text.ln_main_raw'}
assert sum(v[1]-v[0] for v in changed.values())==16 and changed['.text.ln_main_raw']==[1356,1360]
candidate=ElfImage(P/'candidate.elf');control=ElfImage(P/'control.elf');resident=ElfImage(R/'.build/m0-asin-scaled-bound-v164-20261023/firmware/mk61s-picocalc-pico-h.elf')
assert candidate.bytes_at(candidate.named_sections['.rodata'])==control.bytes_at(control.named_sections['.rodata'])
assert (P/'candidate-ratio.o').read_bytes()==(P/'control-ratio.o').read_bytes()
bindings=read(P/'candidate-build.json')['resident_bindings']
for n,a in bindings.items():assert resident.symbols[n if n not in ['memcpy','memset'] else '__wrap_'+n]==a,n
contexts={}
for n in ['generic_M0','M4_soft','M4_hard']:
 assert (P/(n+'-control.o')).read_bytes()==(P/(n+'-candidate.o')).read_bytes()==(PAR/(n+'-candidate.o')).read_bytes()
 contexts[n]=sum(s[5] for s in ElfImage(P/(n+'-candidate.o')).named_sections.values() if s[2]&2)
# Regenerate disassembly from actual objects. Check source sign-mask change,
# complete instruction stream, relocations, literal words AND internal CFG /
# literal-load targets under the explicit old->new instruction mapping.
objdump=Path(read(P/'candidate-build.json')['commands'][0][0]).parent/'arm-none-eabi-objdump'
def parse(path):
 text=subprocess.check_output([str(objdump),'-dr','-z','-j','.text.ln_main_raw',str(path)],text=True);items=[];words=[]
 for line in text.splitlines():
  m=re.match(r'\s*([0-9a-f]+):\s+[0-9a-f ]+\t([a-z][a-z0-9.]*)\s*(.*)',line)
  w=re.match(r'\s*([0-9a-f]+):.*\.word\s+0x([0-9a-f]+)',line)
  if w:words.append((int(w[1],16),w[2]))
  if not m:continue
  address,op,full=m.groups();operand=full.split('@')[0].strip();target=re.search(r'\b([0-9a-f]+) <ln_main_raw\+0x[0-9a-f]+>',full)
  if op.startswith(('b','ldr')):
   operand=re.sub(r'\b[0-9a-f]+ <[^>]+>','<target>',operand)
   if '[pc,' in operand:operand=re.sub(r'#\d+','#offset',operand)
  items.append(dict(address=int(address,16),text=op+' '+operand,target=int(target[1],16) if target else None))
 return items,words,re.findall(r'\b(R_ARM_\w+)\s+(\S+)',text)
old,ow,orr=parse(P/'control-full.o');new,nw,nrr=parse(P/'candidate-full.o');assert [v for _,v in ow]==[v for _,v in nw] and orr==nrr
mapping={x:y for (x,_),(y,_) in zip(ow,nw)};pairs=[];changes=[]
for kind,i,j,k,l in difflib.SequenceMatcher(a=[e['text'] for e in old],b=[e['text'] for e in new],autojunk=False).get_opcodes():
 if kind!='equal':changes.append(dict(kind=kind,parent=[e['text'] for e in old[i:j]],candidate=[e['text'] for e in new[k:l]]))
 if kind=='equal':
  for x,y in zip(old[i:j],new[k:l]):mapping[x['address']]=y['address'];pairs.append((x,y))
 elif kind=='replace':mapping[old[i]['address']]=new[k]['address']
assert changes==[dict(kind='replace',parent=['lsrs r3, r3, #20'],candidate=['lsls r3, r3, #1','lsrs r3, r3, #21']),dict(kind='insert',parent=[],candidate=['nop '])]
target_checks=0
for x,y in pairs:
 if x['target'] is not None:assert y['target']==mapping[x['target']];target_checks+=1
 else:assert y['target'] is None
# Whole private bodies/ELF rebuilt, no selective exclusion.
(O/'rebuild').mkdir(exist_ok=True);commands=[];rebuilt={}
for manifest,names in [('candidate-build.json',['candidate-full.o','candidate-ratio.o','candidate.elf']),('entry-unit-build.json',['entry-unit.o','entry-unit.elf'])]:
 substitutions={str(P/n):str(O/'rebuild'/n) for n in names}
 for command in read(P/manifest)['commands']:
  argv=[substitutions.get(a,a) for a in command];p=subprocess.run(argv,capture_output=True);assert p.returncode==0,p.stderr.decode();commands.append(argv)
 for n in names:assert (P/n).read_bytes()==(O/'rebuild'/n).read_bytes(),n;rebuilt[n]=H(O/'rebuild'/n)
# Recount saved finite corpus. This is not new public ARM execution.
q=read(P/'qualification.json');prior={(e['x'],e['SIO']):e for e in read(PAR/'qualification.json')['rows']};seen=set();hist=Counter();groups={s:Counter() for s in ['READY','DIRTY']};ploss=set();closs=set();newloss=[]
def eq(a,b):return a==b or (a&0x7fffffffffffffff)>0x7ff0000000000000 and (b&0x7fffffffffffffff)>0x7ff0000000000000
for row in q['rows']:
 key=row['x'],row['SIO'];assert key not in seen;seen.add(key)
 for n,v in row['outputs'].items():assert row['correct'][n]==eq(int(v,16),int(row['expected'],16))
 assert row['outputs']['candidate']==row['outputs']['parent']==row['outputs']['resident']
 if key in prior:assert row['instructions']['parent']==prior[key]['instructions']['candidate'] and row['outputs']['parent']==prior[key]['outputs']['candidate']
 pi,ci,qi=(row['instructions'][n] for n in ['parent','candidate','Qfplib']);groups[key[1]]['equal' if ci==pi else 'slower' if ci>pi else 'faster']+=1
 if ci>pi:hist[ci-pi]+=1
 if row['correct']['Qfplib']:
  if pi>qi:ploss.add(row['x'])
  if ci>qi:closs.add(row['x'])
  if ci>qi>=pi:newloss.append(key)
assert len(seen)==97998 and len(prior)==97536 and set(prior)<=seen
assert hist==Counter({1:19562,4:1026,5:8344,6:2022}) and len(ploss)==49 and len(closs)==46 and not newloss
assert ploss-closs=={'0000000000000000','8000000000000000','7FF0000000000000'}
out=dict(status='PASS_SOURCE_CLASSIFIER_AND_COMPLETE_PRIVATE_BINDING',target={n:pin(P/n) for n in ['HANDOFF.md','result.json','native_eabi_m0_log70.inc','candidate.elf']},accepted_parent_review=pin(parent_review),sealed_artifacts=len(r['files']),input_pins=len(inputs),actual_control_ELF_exact_accepted_parent=True,all_numeric_source_and_bounds_unchanged=True,source_naked_fragment_equals_bare_unit=True,source_classification_all4096_fields=True,other_allocated_sections_tables_BSS_deps_equal=True,changed_allocated_sections=changed,code_growth_bytes=16,raw_object_sign_mask_changes=changes,internal_CFG_and_literal_target_checks=target_checks,raw_literal_values_and_relocation_types_targets_equal=True,mask_equivalent_on_all_positive_normals=True,contexts_allocated_bytes=contexts,M4_controls_excluded_translation_units_not_platform_qualification=True,actual_resident_bindings=len(bindings),whole_CPP_ASM_ELF_and_unit_rebuild_byteexact=True,rebuild_hashes=rebuilt,rebuild_commands=commands,saved_performance=dict(rows=97998,parent_rows_retained=97536,groups={k:dict(v) for k,v in groups.items()},parent_regression_histogram=dict(hist),old_raw_losses=49,new_raw_losses=46,exact_IEEE_fixed=sorted(ploss-closs),new_correct_Qfp_deficits=0),hardware_accessed=False,later_children_not_accepted=True)
(O/'binding.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps({k:v for k,v in out.items() if k not in ['rebuild_commands']},indent=2))

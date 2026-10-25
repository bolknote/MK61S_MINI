"""Frozen private1/x sources/ELFs and own redirected full rebuilds."""
import ast,difflib,hashlib,json,struct,subprocess,sys
from pathlib import Path
sys.dont_write_bytecode=True
R=Path('/Users/bolk/Projects/MK61S_MINI');O=Path(__file__).resolve().parent;W=R/'.build/m0-pow-reciprocal-one-20261025';P=R/'.build/m0-pow-reciprocal-lut-20261025'
sys.path.insert(0,str(R/'tests'));from check_stm32_vectors import ElfImage
def ref(p):
 p=Path(p);b=p.read_bytes();return dict(path=str(p),bytes=len(b),sha256=hashlib.sha256(b).hexdigest())
def pin(p,h):v=ref(p);assert v['sha256']==h,v;return v
def save(n,d):
 with (O/n).open('x')as f:json.dump(d,f,indent=2);f.write('\n')
 return ref(O/n)
def mem(e,a,n):
 s=next(s for s in e.sections if s[1]!=8 and s[3]<=a and a+n<=s[3]+s[5]);return e.bytes_at(s)[a-s[3]:a-s[3]+n]
def alloc(e):return {n:(s[1],s[2],s[3],s[5],None if s[1]==8 else e.bytes_at(s))for n,s in e.named_sections.items()if s[2]&2 and s[5]}
refs=dict(FROZEN=pin(W/'FROZEN.json','3341f37fa8b5a5177af792be2417b1365c5b6595f66280151e5ed6f72d8c5469'),
 result=pin(W/'result.json','7989f332e186e1be2860f6048dc4e418d34c97e3cc668d82dcfa6ee6360f9e75'),
 HANDOFF=pin(W/'HANDOFF.md','f07ad6e465e704a8468cee74df5ef21712e7a47846bd56d8bda6ad9c4c25df70'),
 ELF=pin(W/'candidate.elf','90dbb82bf4a67fc0b81f3b1c73f19a6f251fb56b34d1867d587b37c2a445b3fd'),
 parent_FROZEN=pin(P/'FROZEN.json','7384323f37dae2fb8a7cf350a64165392181e20276e83551ccf9ef320d811ffc'),
 parent_independent=pin(R/'.build/m0-pow-reciprocal-lut-independent-20261025/FINAL-REVIEW.json','c1911a7d57fbdbea1ec6a2f595e99a1685d2592db18f48b3fcfb4b97997bfdde'),
 parent_ROOT_later=pin(R/'.build/m0-pow-reciprocal-lut-root-acceptance-20261025-001/RECEIPT.json','19a0b7fc1f415cd90fcf3ec20e523939c79ec8518c988774547c2cc991cdb198'),
 corrigendum=pin(R/'.build/m0-pow-reciprocal-one-report-corrigendum-20261025.json','cf6766bfefe1b7ecd5051476e697c969fba1318ef933c0a9eafba4e57680194a'),
 superseded_v1=pin(R/'.build/m0-pow-reciprocal-one-v1-20261025/FROZEN.json','425589c409e50a6151e629d6edd9b3acb82501e3d6fde094afba2f8a3a71c18d'))
local=[];external=[]
for meta,base,items in [(W/'FROZEN.json',W,local),(W/'source-lineage-pins.json',R,external)]:
 for n,d in json.loads(meta.read_text())['files'].items():
  assert not n.startswith('/')and'..'not in Path(n).parts and'.git'not in Path(n).parts
  v=ref(base/n);assert [v['bytes'],v['sha256']]==[d['bytes'],d['sha256']],v;items.append(v)
assert len(local)==80 and len(external)==2142
assert 'lut'not in json.loads((W/'result.json').read_text())['ROOT_receipts_present_at_seal']
parent=(P/'candidate/native_eabi_m0_pow_root_prefix.inc').read_text();candidate=(W/'candidate/native_eabi_m0_pow_root_prefix.inc').read_text()
assert (W/'control/native_eabi_m0_pow_root_prefix.inc').read_text()==parent
assert parent.count('\tbl\tmk61_m0_hint_ddiv\n')==1 and candidate==parent.replace('\tbl\tmk61_m0_hint_ddiv\n','\tbl\tmk61_m0_reciprocal1\n')
for label in ['control','candidate']:
 assert (W/label/'native_eabi_m0_rp2040.S').read_bytes()==(P/'candidate/native_eabi_m0_rp2040.S').read_bytes()
 assert (W/(label+'.ld')).read_bytes()==(P/'candidate.ld').read_bytes()
 assert (W/(label+'-seed17.S')).read_bytes()==(P/'candidate-seed17.S').read_bytes()
assert (W/'LICENSE.TXT').read_bytes()==(P/'LICENSE.TXT').read_bytes()
patch=''
for newname,parentname,kind in [('candidate-ddiv.S','candidate-ddiv.S','hardware'),('candidate-software.S','software.S','software')]:
 patch+=''.join(difflib.unified_diff((P/parentname).read_text().splitlines(True),(W/newname).read_text().splitlines(True),fromfile='parent/'+kind+'.S',tofile='candidate/'+kind+'.S'))
assert patch==(W/'reciprocal1.patch').read_text()
# Control adds measurement labels only, without modifying code or semantics.
for fname,pname,tag in [('control-ddiv.S','candidate-ddiv.S','mk61_m0_hint'),('software.S','software.S','mk61_m0_sw')]:
 src=(W/fname).read_text()
 for marker in ['first_product','after_second_product']:src=src.replace('.global '+tag+'_'+marker+'\n'+tag+'_'+marker+':\n','')
 assert src==(P/pname).read_text()
parentelf=ElfImage(P/'candidate.elf');images={n:ElfImage(W/(n+'.elf'))for n in ['control','candidate']}
assert alloc(images['control'])==alloc(parentelf)
assert alloc(images['candidate']).keys()==alloc(parentelf).keys()and [n for n in alloc(parentelf)if alloc(parentelf)[n]!=alloc(images['candidate'])[n]]==['.ddiv']
assert images['candidate'].symbols['mk61_m0_reciprocal1']==parentelf.symbols['mk61_m0_hint_ddiv']
tails=[]
for label,e in images.items():
 for tag,fn in([('mk61_m0_hint','mk61_m0_hint_ddiv'),('mk61_m0_sw','mk61_m0_ddiv_sw_from_guard')]if label=='control'else[('mk61_m0_reciprocal1','mk61_m0_reciprocal1'),('mk61_m0_reciprocal1_sw','mk61_m0_reciprocal1_sw_from_guard')]):
  start=e.symbols[tag+'_after_second_product']&~1;end=(e.symbols[fn]&~1)+e.sizes[fn];tails.append(mem(e,start,end-start))
 assert mem(e,e.symbols['mk61_m0_ddiv_seed17']&~1,312)==mem(parentelf,parentelf.symbols['mk61_m0_ddiv_seed17']&~1,312)
assert all(t==tails[0]for t in tails)and len(tails[0])==186
assert images['candidate'].named_sections['.ddiv'][5]==1060 and parentelf.named_sections['.ddiv'][5]==1168
s=(R/'.build/m0-exp-cached-product-independent-20261024/bind_rebuild.py').read_text();fn=next(n for n in ast.parse(s).body if isinstance(n,ast.FunctionDef)and n.name=='relocs')
exec(compile(ast.Module(body=[fn],type_ignores=[]),'<accepted-semantic-relocs>','exec'),globals())
for context in ['RP','generic_M0','M4_soft','M4_hard']:
 p=ElfImage(P/(context+'-candidate.o'));c=ElfImage(W/(context+'-control.o'));n=ElfImage(W/(context+'-candidate.o'))
 assert alloc(c)==alloc(n)==alloc(p)
 changes=[]
 for sec in alloc(p):
  aa,bb=relocs(p).get(sec,[]),relocs(n).get(sec,[]);assert len(aa)==len(bb)
  changes.extend((sec,a,b)for a,b in zip(aa,bb)if a!=b)
 if context=='RP':
  assert len(changes)==1 and changes[0][0]=='.m0_pow_root_prefix'and changes[0][1]==(2732,10,'mk61_m0_hint_ddiv')and changes[0][2]==(2732,10,'mk61_m0_reciprocal1')
 else:
  assert not changes
  for name in ['candidate-ddiv','candidate-software']:assert not alloc(ElfImage(W/(context+'-'+name+'-disabled.o')))
build=json.loads((W/'build.json').read_text());d=O/'rebuild';d.mkdir()
names=['RP-control.o','RP-candidate.o','control-ddiv.o','candidate-ddiv.o','software.o','candidate-software.o','control-seed17.o','candidate-seed17.o','control.elf','candidate.elf'];mapping={str(W/n):str(d/n)for n in names};commands=[];outputs=[]
for name in names:
 argv=next(c for c in build['commands']if Path(c[c.index('-o')+1]).name==name);cmd=[mapping.get(x,x)for x in argv]
 assert not any(x in cmd for x in ['-MD','-MMD','-MF','-save-temps'])
 if '-g'in cmd:cmd+=['-fdebug-prefix-map='+str(O)+'='+str(W)]
 p=subprocess.run(cmd,cwd=O,capture_output=True);(d/(name+'.stdout')).write_bytes(p.stdout);(d/(name+'.stderr')).write_bytes(p.stderr)
 assert p.returncode==0,p.stderr.decode();assert (d/name).read_bytes()==(W/name).read_bytes(),name
 commands.append(dict(argv=cmd,returncode=p.returncode));outputs.append(ref(d/name))
tc=Path(build['commands'][0][0]).parent
for name in ['control.elf','candidate.elf']:(O/(name+'.actual.dis')).write_bytes(subprocess.check_output([str(tc/'arm-none-eabi-objdump'),'-d',str(d/name)]))
out=dict(status='PASS_PRIVATE_NUMERATOR_ONE_SOURCE_BINARY_AND_TEN_BYTEEXACT_REBUILDS',refs=refs,
 local=local,external=external,local_count80=True,external_count2142=True,
 later_parent_ROOT_additive_child_seal_unchanged=True,control_metadata_labels_only_allocated_equal_parent=True,
 sole_root_BL_semantic_target_rename_same_actual_address_and_instruction_bytes=True,other_resident_ddiv_callers_unchanged=True,
 exact_patch_bound=True,all4_common_suffix186_byte_exact=True,common_suffix_SHA256=hashlib.sha256(tails[0]).hexdigest(),
 seed312_unchanged=True,no_new_table_values_RAM_libgcc=True,allocation1168to1060_delta_minus108=True,
 default_M0_M4_selected_controls_unchanged_six_disabled_empty=True,
 own_ten_rebuilds_byte_exact=outputs,commands=commands,all_outputs_own_directory_original_commands_not_inplace=True,
 exact_guard_firstproduct_deadsoftware_proof_and_new_private_caller_required=True,
 superseded_v1_and_failed_trace_retained_excluded=True,ARM_calls=0,MPFR_inputs=0,device_IO=0,Git=0,canonical=0,network=0,integration_GO=False)
print(json.dumps(save('binding.json',out)),flush=True)

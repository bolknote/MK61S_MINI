"""Frozen inline/overflow supplier, shared macro identity, own full rebuilds."""
import ast,difflib,hashlib,json,struct,subprocess,sys
from pathlib import Path
sys.dont_write_bytecode=True
R=Path('/Users/bolk/Projects/MK61S_MINI');O=Path(__file__).resolve().parent;W=R/'.build/m0-pow-reciprocal-inline-20261025';P=R/'.build/m0-pow-reciprocal-one-20261025'
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
refs=dict(FROZEN=pin(W/'FROZEN.json','0be351d573878a48f13f5d41edd2812a23ab269556b929db9aa8324e6a0bf219'),
 result=pin(W/'result.json','db3bb21b3d9c59fff2849b042f313e591dcd545f679f64eb6965aa60e7ac6384'),
 HANDOFF=pin(W/'HANDOFF.md','6d8859182fc77735e315b7a02a631d97638dbf51c75bed2d90a189a88aff911c'),
 ELF=pin(W/'candidate.elf','c1287a067ecfbe363d34b8e4afd1b8526b6214250bf1e7cdf3e6b833d502e8aa'),
 parent_FROZEN=pin(P/'FROZEN.json','3341f37fa8b5a5177af792be2417b1365c5b6595f66280151e5ed6f72d8c5469'),
 parent_independent=pin(R/'.build/m0-pow-reciprocal-one-independent-20261025/FINAL-REVIEW.json','f9945c0cf8c6e38dcfdce1239f0a47ee2a6d20a11e4cd01a13e15d8665f8d1b7'),
 parent_ROOT_later=pin(R/'.build/m0-pow-reciprocal-one-root-acceptance-20261025-001/RECEIPT.json','78a3c26a8954dcbf8dd8d54719825989dbf6beca103cc93d80b9795a14c9290f'))
local=[];external=[]
for meta,base,items in [(W/'FROZEN.json',W,local),(W/'source-lineage-pins.json',R,external)]:
 for n,d in json.loads(meta.read_text())['files'].items():
  assert not n.startswith('/')and'..'not in Path(n).parts and'.git'not in Path(n).parts
  v=ref(base/n);assert [v['bytes'],v['sha256']]==[d['bytes'],d['sha256']],v;items.append(v)
assert len(local)==94 and len(external)==2281
assert 'one'not in json.loads((W/'result.json').read_text())['ROOT_receipts_present_at_seal']
for label in ['control','candidate']:
 for n in ['native_eabi_m0_rp2040.S','native_eabi_m0_pow_root_prefix.inc']:assert(W/label/n).read_bytes()==(P/'candidate'/n).read_bytes()
 assert (W/(label+'-seed17.S')).read_bytes()==(P/'candidate-seed17.S').read_bytes()
assert (W/'control-ddiv.S').read_bytes()==(P/'candidate-ddiv.S').read_bytes()and(W/'software.S').read_bytes()==(P/'candidate-software.S').read_bytes()
assert (W/'control.ld').read_bytes()==(P/'control.ld').read_bytes()
assert (W/'candidate.ld').read_text()==(P/'candidate.ld').read_text().replace(' KEEP(*(.m0_ddiv_seed17))','')
patch=''
for n,pn,kind in [('candidate-ddiv.S','candidate-ddiv.S','hardware'),('candidate-software.S','candidate-software.S','software')]:
 patch+=''.join(difflib.unified_diff((P/pn).read_text().splitlines(True),(W/n).read_text().splitlines(True),fromfile='parent/'+kind+'.S',tofile='candidate/'+kind+'.S'))
assert patch==(W/'inline-and-overflow.patch').read_text()
macro=(W/'inline-seed.inc').read_text();unit=(W/'unit.S').read_text();sw=(W/'candidate-software.S').read_text()
for source in [unit,sw]:assert source.count(' reciprocal_seed_inline')==1 and'#include "inline-seed.inc"'in source and'#include "inline-seed-table.inc"'in source
assert 'push'not in macro and'pop'not in macro and'bl 'not in macro and'bx 'not in macro
assert 'bl mk61_m0_ddiv_seed17'not in sw and'push {r0-r3,r7}'not in sw
old=ElfImage(P/'candidate.elf');images={n:ElfImage(W/(n+'.elf'))for n in ['control','candidate']}
assert alloc(images['control'])==alloc(old)
assert alloc(old).keys()==alloc(images['candidate']).keys()and[n for n in alloc(old)if alloc(old)[n]!=alloc(images['candidate'])[n]]==['.rootprefix','.ddiv']
off=2732
for n in ['.rootprefix','.front','.tail']:
 a=old.bytes_at(old.named_sections[n]);b=images['candidate'].bytes_at(images['candidate'].named_sections[n])
 if n=='.rootprefix':assert a[:off]==b[:off]and a[off+4:]==b[off+4:]
 else:assert a==b
tails=[]
for label,e in images.items():
 for tag,fn in [('mk61_m0_reciprocal1','mk61_m0_reciprocal1'),('mk61_m0_reciprocal1_sw','mk61_m0_reciprocal1_sw_from_guard')]:
  a=e.symbols[tag+'_after_second_product']&~1;b=(e.symbols[fn]&~1)+e.sizes[fn];tails.append(mem(e,a,b-a))
assert len(tails[0])==186 and all(x==tails[0]for x in tails)
table=old.bytes_at(old.named_sections['.ddiv'])[-256:];assert images['candidate'].bytes_at(images['candidate'].named_sections['.ddiv'])[-256:]==table
assert 'mk61_m0_ddiv_seed17'not in images['candidate'].symbols and images['candidate'].named_sections['.ddiv'][5]==1072
assert all(x==(1<<32)//(65536+512*i+256)for i,x in enumerate(struct.unpack('<128H',table)))
s=(R/'.build/m0-exp-cached-product-independent-20261024/bind_rebuild.py').read_text();fn=next(n for n in ast.parse(s).body if isinstance(n,ast.FunctionDef)and n.name=='relocs');exec(compile(ast.Module(body=[fn],type_ignores=[]),'<accepted-relocs>','exec'),globals())
for context in ['RP','generic_M0','M4_soft','M4_hard']:
 p=ElfImage(P/(context+'-candidate.o'))
 for label in ['control','candidate']:
  n=ElfImage(W/(context+'-'+label+'.o'));assert alloc(p)==alloc(n)
  for sec in alloc(p):assert relocs(p).get(sec)==relocs(n).get(sec)
 if context!='RP':
  for name in ['candidate-ddiv','candidate-software']:assert not alloc(ElfImage(W/(context+'-'+name+'-disabled.o')))
build=json.loads((W/'build.json').read_text());ub=json.loads((W/'unit-build.json').read_text());d=O/'rebuild';d.mkdir()
names=['RP-control.o','RP-candidate.o','control-ddiv.o','candidate-ddiv.o','software.o','candidate-software.o','control-seed17.o','candidate-seed17.o','control.elf','candidate.elf','unit.o','unit.elf'];mapping={str(W/n):str(d/n)for n in names};commands=[];outputs=[]
for name in names:
 argv=next(c for c in build['commands']+ub['commands']if Path(c[c.index('-o')+1]).name==name);cmd=[mapping.get(x,x)for x in argv]
 assert not any(x in cmd for x in ['-MD','-MMD','-MF','-save-temps'])
 if '-g'in cmd:cmd+=['-fdebug-prefix-map='+str(O)+'='+str(W)]
 p=subprocess.run(cmd,cwd=O,capture_output=True);(d/(name+'.stdout')).write_bytes(p.stdout);(d/(name+'.stderr')).write_bytes(p.stderr)
 assert p.returncode==0,p.stderr.decode();assert (d/name).read_bytes()==(W/name).read_bytes(),name
 commands.append(dict(argv=cmd,returncode=p.returncode));outputs.append(ref(d/name))
tc=Path(build['commands'][0][0]).parent
for n in ['control.elf','candidate.elf','unit.elf']:(O/(n+'.actual.dis')).write_bytes(subprocess.check_output([str(tc/'arm-none-eabi-objdump'),'-d',str(d/n)]))
out=dict(status='PASS_INLINE_SHARED_SOURCE_TABLE_SUFFIX_BINDING_AND_TWELVE_BYTEEXACT_REBUILDS',refs=refs,local=local,external=external,
 local94_external2281=True,later_parent_ROOT_additive_child_seal_unchanged=True,root_source_call_unchanged_only_BL_relinked_for_moved_entry=True,
 all_other_allocated_resident_bytes_addresses_calls_unchanged=True,exact_patch_bound=True,
 production_and_unit_same_inline_macro_and_table_sources=True,no_inline_BL_stackwrites_or_C_ABI=True,
 unchanged256B_integer_table_and4common186B_suffixes=True,old312_standalone_seed_not_allocated_in_candidate=True,
 default_M0_M4_selected_contexts_and6_disabled_unchanged=True,allocation1060to1072_delta12=True,no_new_table_values_RAM_libgcc=True,
 own12_rebuilds_byte_exact=outputs,commands=commands,own_outputs_only_original_commands_not_inplace=True,
 author_preflights_preserved= [ref(W/n)for n in ['PREFLIGHT-001.json','PREFLIGHT-002.json']],
 ARM_calls=0,MPFR_inputs=0,device_IO=0,Git=0,canonical=0,network=0,integration_GO=False)
print(json.dumps(save('binding.json',out)),flush=True)

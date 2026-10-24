"""Independent immutable/source/ABI/cutoff binding and own-output rebuilds."""
from pathlib import Path
import ast,difflib,hashlib,json,shlex,struct,subprocess,sys
sys.dont_write_bytecode=True
R=Path('/Users/bolk/Projects/MK61S_MINI');P=R/'.build/m0-exp-tiny-log-midpoint-20261024';O=Path(__file__).resolve().parent
E=R/'.build/m0-exp-tiny-radius-20261024';V=R/'.build/m0-asin-scaled-bound-v164-20261023'
sys.path.insert(0,str(R/'tests'))
from check_stm32_vectors import ElfImage
def read(p):return json.loads(Path(p).read_text())
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def ref(p):return dict(path=str(p),bytes=Path(p).stat().st_size,sha256=sha(p))
assert sha(P/'FROZEN.json')=='5dfdd55a763a5b0b8eafee876d1b348ec917632a10e1d31b3975dc4fe72f9f1f'
assert sha(P/'result.json')=='42cdd6d6be73fd2fe2527fba9bc56a1a6e8cf5013848fc1671a92cae4f9536d1'
assert sha(P/'HANDOFF.md')=='37bd4ebd24d88d712566a0024b7c6c8194ca8fe3f7d3fb227cac071b508c51e6'
parent=R/'.build/m0-exp-tiny-radius-independent-20261024/FINAL-REVIEW.json'
assert sha(parent)=='ac32571a4dd0a31d806f94b6c9c85222ed34278d218115c726d4cb0c11ca4a9d'
verified=[]
for n,base,count in [('FROZEN.json',P,88),('source-lineage-pins.json',R,621)]:
 files=read(P/n)['files'];assert len(files)==count
 for name,d in files.items():
  f=base/name;assert sha(f)==d['sha256'] and f.stat().st_size==d['bytes'];verified.append(ref(f))
j=read(parent);pins=[ref(parent),j['accepted_parent'],*j['target'].values(),*j['refs'].values()];assert len(pins)==38
for pin in pins:assert ref(Path(pin['path']))==pin
seal=read(P/'parent-review-at-seal.json');assert seal['independent_review_available_at_seal'] and seal['sha256']==sha(parent) and seal['receipt_and_direct_refs_verified']==38
for f,names in [(R/'.build/m0-pow-square-ordinary-independent-20261024/bind.py',['allocated','body']),(R/'.build/m0-exp-cached-product-independent-20261024/bind_rebuild.py',['relocs']),(R/'.build/m0-exp-tiny-radius-independent-20261024/binding.py',['loads'])]:
 tree=ast.parse(f.read_text());ns=[x for x in tree.body if isinstance(x,ast.FunctionDef) and x.name in names];assert len(ns)==len(names)
 exec(compile(ast.Module(body=ns,type_ignores=[]),str(O/'binding.py'),'exec'),globals())
def rel(e):return {n:v for n,v in relocs(e).items() if n in allocated(e)}
src=(P/'candidate/native_eabi_m0.cpp').read_text();old=(P/'control/native_eabi_m0.cpp').read_text()
assert (P/'control/native_eabi_m0.cpp').read_bytes()==(E/'candidate/native_eabi_m0.cpp').read_bytes()
for label in ['control','candidate']:
 for f in (E/'candidate').iterdir():
  if f.suffix in ['.S','.inc']:assert (P/label/f.name).read_bytes()==f.read_bytes()
patch=''.join(difflib.unified_diff(old.splitlines(True),src.splitlines(True),fromfile='a/code/native_eabi_m0.cpp',tofile='b/code/native_eabi_m0.cpp'))
assert patch==(P/'qualified-tiny-to-log-midpoint.patch').read_text()
assert sha(P/'candidate/native_eabi_m0.cpp')=='1cc8f86cf948efbc152b7bf7f1f15046b0be2d0d5f9e07552305b514fc92a899'
c0,c1=ElfImage(P/'RP-control.o'),ElfImage(P/'RP-candidate.o');a,b=allocated(c0),allocated(c1);base=ElfImage(E/'RP-candidate.o')
assert a==allocated(base) and rel(c0)==rel(base)
changed={n:(len(a.get(n,b'')),len(b.get(n,b''))) for n in a.keys()|b.keys() if a.get(n)!=b.get(n)}
assert changed=={'.m0_exp_core':(5012,5012),'.m0_exp_tiny':(196,472)}
differences=[(i,x,y) for i,(x,y) in enumerate(zip(a['.m0_exp_core'],b['.m0_exp_core'])) if x!=y]
assert differences==[(3916,38,32)] and rel(c0)['.m0_exp_core']==rel(c1)['.m0_exp_core']
for n in a.keys()|b.keys():
 if n not in changed:assert rel(c0).get(n,[])==rel(c1).get(n,[])
assert not rel(c1).get('.m0_exp_tiny')
contexts={}
for ctx in ['generic_M0','M4_soft','M4_hard']:
 x,y=ElfImage(P/(ctx+'-control.o')),ElfImage(P/(ctx+'-candidate.o'))
 assert allocated(x)==allocated(y) and rel(x)==rel(y);contexts[ctx]=sum(map(len,allocated(x).values()))
for label in ['control','candidate']:
 x,y=ElfImage(P/('ASM-'+label+'.o')),ElfImage(E/'ASM-candidate.o')
 assert allocated(x)==allocated(y) and rel(x)==rel(y)
 assert len(body(x,'__aeabi_d2f'))==256 and len(body(x,'__aeabi_f2d'))==172
candidate,control,accepted=ElfImage(P/'candidate.elf'),ElfImage(P/'control.elf'),ElfImage(E/'candidate.elf')
assert allocated(control)==allocated(accepted)
assert candidate.symbols['mk61_m0_exp']==candidate.symbols['_ZN12compact_math3expEd'] and candidate.sizes['mk61_m0_exp']==1276
helper=body(candidate,'exp_tiny_rne');assert len(helper)==472 and helper==body(c1,'exp_tiny_rne') and candidate.symbols['exp_tiny_rne']==0x101a0001
segments=loads(P/'candidate.elf');parent_segments=loads(E/'candidate.elf')
assert [(r['address'],r['bytes']) for r in segments]==[(0x101a0000,16288),(0x20038ee4,168)]
assert segments[0]['bytes']-parent_segments[0]['bytes']==280
assert (P/'bindings.ld').read_bytes()==(E/'bindings.ld').read_bytes()
assert candidate.bytes_at(candidate.named_sections['.product_ram'])==accepted.bytes_at(accepted.named_sections['.product_ram'])
build=read(P/'build.json');reb=read(P/'rebuild-proof.json');cc=Path(build['commands'][0][0]).parent
assert subprocess.check_output([str(cc/'arm-none-eabi-nm'),'-u',str(P/'RP-control.o')],text=True)==subprocess.check_output([str(cc/'arm-none-eabi-nm'),'-u',str(P/'RP-candidate.o')],text=True)
for n in ['candidate.elf','control.elf']:assert not subprocess.check_output([str(cc/'arm-none-eabi-nm'),'-u',str(P/n)],text=True).strip()
db=read(V/'build/compile_commands.json')
for ext,tag in [('cpp','RP'),('S','ASM')]:
 entry=next(d for d in db if d['file'].endswith('/code/native_eabi_m0.'+ext));flags=shlex.split(entry['command'])
 for label in ['control','candidate']:
  cmds=build['commands'] if ext=='cpp' else [r['command'] for r in reb['records']]
  c=next(c for c in cmds if Path(c[c.index('-o')+1]).name==tag+'-'+label+'.o')
  expect=list(flags);expect[expect.index(entry['file'])]=str(P/label/('native_eabi_m0.'+ext));expect[expect.index('-o')+1]=c[c.index('-o')+1];assert c==expect
commands=[r['command'] for r in reb['records'][:2]]+build['commands'];assert len(commands)==12
out=O/'rebuild';out.mkdir(exist_ok=True);mapping={c[c.index('-o')+1]:str(out/Path(c[c.index('-o')+1]).name) for c in commands};records=[]
for c in commands:
 cmd=[mapping.get(x,str(out/Path(x).name) if x in {str(P/'RP-control.o'),str(P/'RP-candidate.o')} else x) for x in c]
 assert not any(x in ['-MD','-MMD','-MF'] for x in cmd)
 run=subprocess.run(cmd,cwd=P,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT);assert run.returncode==0,run.stdout
 original=P/Path(c[c.index('-o')+1]).name;fresh=out/original.name;assert sha(original)==sha(fresh)
 if original.suffix=='.o' and original.with_suffix('.su').exists():assert original.with_suffix('.su').read_bytes()==fresh.with_suffix('.su').read_bytes()
 records.append(dict(original=ref(original),rebuilt=ref(fresh),command=cmd,returncode=0))
wstart=src.index('__attribute__((always_inline)) inline U wide32(');wend=src.index('\n}',wstart)+2
start=src.index('__attribute__((always_inline)) inline uint32_t exp_tiny_log_floor(');end=src.index('\n#endif',start)
(O/'helper.cpp').write_text('#include "native_eabi_m0.hpp"\nusing U=uint64_t;\n'+src[wstart:wend]+'\nextern "C" {\n'+src[start:end]+'\nU independent_retention_anchor(U a){return exp_tiny_rne(a);}\n}\n')
cmd=list(next(c for c in build['commands'] if Path(c[c.index('-o')+1]).name=='RP-candidate.o'))
cmd[cmd.index(str(P/'candidate/native_eabi_m0.cpp'))]=str(O/'helper.cpp');cmd[cmd.index('-o')+1]=str(O/'helper.o')
run=subprocess.run(cmd,cwd=P,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT);assert run.returncode==0,run.stdout
(O/'unit.ld').write_text('PHDRS { code PT_LOAD FLAGS(5); }\nSECTIONS { .tiny 0x10190000 : { KEEP(*(.m0_exp_tiny)) } :code /DISCARD/ : { *(.text*) *(.ARM*) *(.comment) *(.note*) } }\n')
link=[str(cc/'arm-none-eabi-ld'),'--gc-sections','-T',str(O/'unit.ld'),str(O/'helper.o'),'-o',str(O/'unit.elf')]
run=subprocess.run(link,cwd=P,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT);assert run.returncode==0,run.stdout
unit=ElfImage(O/'unit.elf');assert body(unit,'exp_tiny_rne')==helper==body(ElfImage(O/'helper.o'),'exp_tiny_rne')
assert {n:v for n,v in allocated(unit).items() if v}=={'.tiny':helper}
assert not subprocess.check_output([str(cc/'arm-none-eabi-nm'),'-u',str(O/'unit.elf')],text=True).strip()
for n,im in [('candidate',out/'candidate.elf'),('unit',O/'unit.elf')]:
 (O/(n+'.dis')).write_text(subprocess.check_output([str(cc/'arm-none-eabi-objdump'),'-dr',str(im)],text=True))
(O/'reference.dis').write_text(subprocess.check_output([str(cc/'arm-none-eabi-objdump'),'-d','--disassemble=qfp_dexp',str(R/'.build/m0-v138-execution-20261023/reference/reference.elf')],text=True))
stacks={}
for label in ['control','candidate']:
 for token in ['double mk61_m0_exp(double)','m0_eabi::U exp_tiny_rne(m0_eabi::U)']:
  r=[line.split('\t')[1:] for line in (out/('RP-'+label+'.su')).read_text().splitlines() if token in line]
  assert len(r)==1 and r[0][1]=='static';stacks[label+':'+token]=int(r[0][0])
assert stacks=={'control:double mk61_m0_exp(double)':96,'candidate:double mk61_m0_exp(double)':96,'control:m0_eabi::U exp_tiny_rne(m0_eabi::U)':20,'candidate:m0_eabi::U exp_tiny_rne(m0_eabi::U)':56}
d=dict(status='PASS_INDEPENDENT_LOG_MIDPOINT_SOURCE_AND_BINARY_CLOSURE',accepted_parent=ref(parent),accepted_parent_receipt_plus_refs38=True,parent_GO_available_at_seal=True,frozen_artifacts=88,lineage_pins=621,verified=verified,exact_source_patch=True,CPP_control_exact_accepted_radius=True,CPP_changed_sections=changed,core_single_byte_change=differences,core_all_semantic_relocations_equal=True,all_other_CPP_bytes_relocations_equal=True,all_RP_ASM_bytes_relocations_equal_parent=True,d2f256_f2d172_preserved=True,generic_M0_M4_selected_CPP_allocated_bytes_equal=contexts,generic_M0_M4_ASM_inherited_from_byte_identical_sources=True,whole_M4_not_built=True,public_entry_bytes1276_direct_alias=True,no_artificial_interposition=True,source_object_whole_ELF_isolated_helper472_byte_exact=True,helper_external_calls_ROM_relocations_or_libgcc=0,selected_CPP_delta276=True,private_Flash_delta280_including_alignment=True,load_segments=segments,unchanged_bindings_and_product_RAM168=True,complete_own_byte_exact_rebuilds=12,records=records,isolated_helper_commands=[cmd,link],static_stack_bytes=stacks,whole_firmware_size_GC_not_measured=True,hardware=False,canonical=False)
(O/'binding.json').write_text(json.dumps(d,indent=2)+'\n');print(json.dumps({k:v for k,v in d.items() if k not in ['verified','records','isolated_helper_commands']},indent=2))

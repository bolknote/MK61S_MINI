"""Independent source/lineage/rebuild/public-ABI and isolated helper binding."""
from pathlib import Path
import ast,difflib,hashlib,json,shlex,struct,subprocess,sys
sys.dont_write_bytecode=True
R=Path('/Users/bolk/Projects/MK61S_MINI');P=R/'.build/m0-exp-tiny-radius-20261024';O=Path(__file__).resolve().parent
V=R/'.build/m0-asin-scaled-bound-v164-20261023';F=R/'.build/m0-f2d-leaf-20261024';S=R/'.build/m0-pow-rsqrt-asm-20261024';B=R/'.build/m0-exp-cached-product-20261024'
sys.path.insert(0,str(R/'tests'))
from check_stm32_vectors import ElfImage
def read(p):return json.loads(Path(p).read_text())
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def ref(p):return dict(path=str(p),bytes=Path(p).stat().st_size,sha256=sha(p))
assert sha(P/'FROZEN.json')=='6e3c05ec0e45d04cfd5978fc03048e296ff220582a1eb718352cbc70bfddd999'
assert sha(P/'result.json')=='0e824e71cb01c3487487ee66a92a2d42994b47a4b0bf105fedaf7bc6ea1ac09f'
assert sha(P/'HANDOFF.md')=='c17b44cab6b2f612436e428120cbb7586d5f244e898817ce0b63fc842fdb849f'
parent=R/'.build/m0-f2d-leaf-independent-20261024/FINAL-REVIEW.json'
assert sha(parent)=='7561feddf77fd13a7760b930414e68f997898526abaed866c909d39a7efcaeb2'
verified=[]
for name,base,count in [('FROZEN.json',P,80),('source-lineage-pins.json',R,513)]:
 files=read(P/name)['files'];assert len(files)==count
 for n,d in files.items():
  p=base/n;assert sha(p)==d['sha256'] and p.stat().st_size==d['bytes'],str(p)
  verified.append(ref(p))
receipt=read(parent);assert receipt['status']=='GO_PRIVATE_RP_F2D_LEAF_COMPONENT_ONLY' and not receipt['blockers']
pins=[ref(parent),receipt['accepted_parent'],*receipt['target'].values(),*receipt['refs'].values()];assert len(pins)==28
for d in pins:assert ref(Path(d['path']))==d
assert read(P/'accepted-f2d-parent.json')['sha256']==sha(parent)
for file,names in [(R/'.build/m0-pow-square-ordinary-independent-20261024/bind.py',['allocated','body']),(R/'.build/m0-exp-cached-product-independent-20261024/bind_rebuild.py',['relocs'])]:
 tree=ast.parse(file.read_text());fns=[x for x in tree.body if isinstance(x,ast.FunctionDef) and x.name in names]
 assert len(fns)==len(names);exec(compile(ast.Module(body=fns,type_ignores=[]),str(O/'binding.py'),'exec'),globals())
def rel(e):return {n:v for n,v in relocs(e).items() if n in allocated(e)}
assert (P/'control/native_eabi_m0.cpp').read_bytes()==(S/'candidate/native_eabi_m0.cpp').read_bytes()
for label in ['control','candidate']:
 for n in (F/'candidate').iterdir():
  if n.suffix in ('.S','.inc'):assert (P/label/n.name).read_bytes()==n.read_bytes()
assert (P/'candidate/native_eabi_m0.S').read_bytes()==(P/'control/native_eabi_m0.S').read_bytes()
src=(P/'candidate/native_eabi_m0.cpp').read_text();old=(P/'control/native_eabi_m0.cpp').read_text()
patch=''.join(difflib.unified_diff(old.splitlines(True),src.splitlines(True),fromfile='a/code/native_eabi_m0.cpp',tofile='b/code/native_eabi_m0.cpp'))
assert patch==(P/'qualified-f2d-to-exp-tiny.patch').read_text()
assert sha(P/'candidate/native_eabi_m0.cpp')=='d31f2f4d0b90c21618b5e58c49e6699a813f32cbef60b456155dc8de7145ffe9'
c0,c1=ElfImage(P/'RP-control.o'),ElfImage(P/'RP-candidate.o');a,b=allocated(c0),allocated(c1)
assert a==allocated(ElfImage(S/'RP-candidate-cpp.o')) and rel(c0)==rel(ElfImage(S/'RP-candidate-cpp.o'))
changed={n:(len(a.get(n,b'')),len(b.get(n,b''))) for n in a.keys()|b.keys() if a.get(n)!=b.get(n)}
assert changed=={'.m0_exp_core':(5144,5012),'.m0_exp_tiny':(0,196)}
for n in a.keys()|b.keys():
 if n not in changed:assert rel(c0).get(n,[])==rel(c1).get(n,[])
assert not rel(c1).get('.m0_exp_tiny')
contexts={}
for ctx in ['generic_M0','M4_soft','M4_hard']:
 x,y=ElfImage(P/(ctx+'-control.o')),ElfImage(P/(ctx+'-candidate.o'))
 assert allocated(x)==allocated(y) and rel(x)==rel(y)
 contexts[ctx]=dict(CPP_allocated_bytes_semantic_relocations_equal=True,allocated_bytes=sum(map(len,allocated(x).values())))
for label in ['control','candidate']:
 asm=ElfImage(P/('ASM-'+label+'.o'));base=ElfImage(F/'RP-candidate.o')
 assert allocated(asm)==allocated(base) and rel(asm)==rel(base)
 assert body(asm,'__aeabi_f2d')==body(base,'__aeabi_f2d') and len(body(asm,'__aeabi_f2d'))==172
 assert body(asm,'__aeabi_d2f')==body(base,'__aeabi_d2f') and len(body(asm,'__aeabi_d2f'))==256
candidate,control,accepted=ElfImage(P/'candidate.elf'),ElfImage(P/'control.elf'),ElfImage(B/'candidate.elf')
assert allocated(control)==allocated(accepted)
helper='exp_tiny_rne';helper_body=body(candidate,helper)
assert len(helper_body)==196 and helper_body==body(c1,helper)
assert candidate.symbols[helper]==0x101a0001
assert candidate.symbols['mk61_m0_exp']==candidate.symbols['_ZN12compact_math3expEd'] and candidate.sizes['mk61_m0_exp']==1276
assert control.symbols['mk61_m0_exp']==accepted.symbols['mk61_m0_exp']
resident=ElfImage(V/'firmware/mk61s-picocalc-pico-h.elf')
bindings=[]
for line in (P/'bindings.ld').read_text().splitlines():
 if ' = 0x' not in line or not line.endswith(';') or line.lstrip().startswith('.'):continue
 n,v=line[:-1].split(' = ');v=int(v,16)
 assert candidate.symbols[n]==v
 assert v==(accepted.symbols[n] if n in accepted.symbols else resident.symbols[n])
 bindings.append((n,v))
assert candidate.symbols['mk61_m0_pow_exp_product_flash']==accepted.symbols['mk61_m0_pow_exp_product_flash']==resident.symbols['mk61_m0_pow_exp_product_flash']
assert len(body(resident,'mk61_m0_pow_exp_product_flash'))==16
assert candidate.bytes_at(candidate.named_sections['.product_ram'])==accepted.bytes_at(accepted.named_sections['.product_ram']) and candidate.named_sections['.product_ram'][5]==168
def loads(path):
 raw=Path(path).read_bytes();off=struct.unpack_from('<I',raw,28)[0];size,num=struct.unpack_from('<HH',raw,42);out=[]
 for i in range(num):
  t,f,v,p,fs,ms,flags,align=struct.unpack_from('<8I',raw,off+i*size)
  if t==1:
   assert p==v and fs==ms and flags==5
   assert (0x101a0000<=v and v+fs<=0x10200000) or(v==0x20038ee4 and fs==168)
   out.append(dict(address=v,bytes=fs,file_offset=f))
 assert len(out)==2;return out
segments=loads(P/'candidate.elf');assert [(s['address'],s['bytes']) for s in segments]==[(0x101a0000,16008),(0x20038ee4,168)]
build=read(P/'build.json');reb=read(P/'rebuild-proof.json');cc=Path(build['commands'][0][0]).parent
for n in ['candidate.elf','control.elf']:assert not subprocess.check_output([str(cc/'arm-none-eabi-nm'),'-u',str(P/n)],text=True).strip()
assert subprocess.check_output([str(cc/'arm-none-eabi-nm'),'-u',str(P/'RP-control.o')],text=True)==subprocess.check_output([str(cc/'arm-none-eabi-nm'),'-u',str(P/'RP-candidate.o')],text=True)
db=read(V/'build/compile_commands.json')
for ext,tag in [('cpp','RP'),('S','ASM')]:
 entry=next(d for d in db if d['file'].endswith('/code/native_eabi_m0.'+ext));flags=shlex.split(entry['command'])
 for label in ['control','candidate']:
  cmds=build['commands'] if ext=='cpp' else [x['command'] for x in reb['records']]
  c=next(c for c in cmds if Path(c[c.index('-o')+1]).name==tag+'-'+label+'.o')
  expect=list(flags);expect[expect.index(entry['file'])]=str(P/label/('native_eabi_m0.'+ext));expect[expect.index('-o')+1]=c[c.index('-o')+1];assert c==expect
commands=[x['command'] for x in reb['records'][:2]]+build['commands'];assert len(commands)==12
out=O/'rebuild';out.mkdir(exist_ok=True);mapping={c[c.index('-o')+1]:str(out/Path(c[c.index('-o')+1]).name) for c in commands}
# The recorded ASM commands write the author's rebuild directory; its object
# inputs and all normal build outputs are remapped into this review only.
records=[]
for c in commands:
 cmd=[mapping.get(x,str(out/Path(x).name) if x in {str(P/'RP-control.o'),str(P/'RP-candidate.o')} else x) for x in c]
 assert not any(x in ['-MD','-MMD','-MF'] for x in cmd)
 run=subprocess.run(cmd,cwd=P,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT);assert run.returncode==0,run.stdout
 original=P/Path(c[c.index('-o')+1]).name;fresh=out/original.name;assert sha(fresh)==sha(original),(original,sha(fresh),sha(original))
 if original.suffix=='.o' and original.with_suffix('.su').exists():assert fresh.with_suffix('.su').read_bytes()==original.with_suffix('.su').read_bytes()
 records.append(dict(original=ref(original),rebuilt=ref(fresh),command=cmd,returncode=0))
# Compile exact helper source separately, using the exact RP CPP flags and
# a discarded retention anchor. Every tested helper byte must match full CPP.
start=src.index('__attribute__((noinline,noipa,section(".m0_exp_tiny")))');end=src.index('\n#endif',start)
helper_src=src[start:end]
(O/'helper.cpp').write_text('#include "native_eabi_m0.hpp"\nusing U=uint64_t;\nextern "C" {\n'+helper_src+'\nU independent_retention_anchor(U a) { return exp_tiny_rne(a); }\n}\n')
base=list(next(c for c in build['commands'] if Path(c[c.index('-o')+1]).name=='RP-candidate.o'))
base[base.index(str(P/'candidate/native_eabi_m0.cpp'))]=str(O/'helper.cpp');base[base.index('-o')+1]=str(O/'helper.o')
run=subprocess.run(base,cwd=P,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT);assert run.returncode==0,run.stdout
(O/'unit.ld').write_text('PHDRS { code PT_LOAD FLAGS(5); }\nSECTIONS { .tiny 0x10190000 : { KEEP(*(.m0_exp_tiny)) } :code /DISCARD/ : { *(.text*) *(.ARM*) *(.comment) *(.note*) } }\n')
link=[str(cc/'arm-none-eabi-ld'),'--gc-sections','-T',str(O/'unit.ld'),str(O/'helper.o'),'-o',str(O/'unit.elf')]
run=subprocess.run(link,cwd=P,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT);assert run.returncode==0,run.stdout
unit=ElfImage(O/'unit.elf');assert body(unit,helper)==helper_body and body(ElfImage(O/'helper.o'),helper)==helper_body
assert {n:v for n,v in allocated(unit).items() if v}=={'.tiny':helper_body}
assert not subprocess.check_output([str(cc/'arm-none-eabi-nm'),'-u',str(O/'unit.elf')],text=True).strip()
for n,im in [('candidate',out/'candidate.elf'),('unit',O/'unit.elf')]:
 (O/(n+'.dis')).write_text(subprocess.check_output([str(cc/'arm-none-eabi-objdump'),'-dr',str(im)],text=True))
(O/'reference.dis').write_text(subprocess.check_output([str(cc/'arm-none-eabi-objdump'),'-d','--disassemble=qfp_dexp',str(R/'.build/m0-v138-execution-20261023/reference/reference.elf')],text=True))
static={}
for label in ['control','candidate']:
 lines=(out/('RP-'+label+'.su')).read_text().splitlines()
 for token in ['double mk61_m0_exp(double)','m0_eabi::U exp_tiny_rne(m0_eabi::U)']:
  rows=[line.split('\t')[1:] for line in lines if token in line]
  if rows:assert len(rows)==1 and rows[0][1]=='static';static[label+':'+token]=int(rows[0][0])
assert static=={'control:double mk61_m0_exp(double)':88,'candidate:double mk61_m0_exp(double)':96,'candidate:m0_eabi::U exp_tiny_rne(m0_eabi::U)':20}
d=dict(status='PASS_INDEPENDENT_EXP_TINY_FULL_SOURCE_BINDING_AND_REBUILDS',accepted_parent=ref(parent),accepted_f2d_receipt_plus_direct_refs=28,frozen_artifacts=80,lineage_pins=513,verified=verified,composite_lineage='accepted rsqrt CPP plus accepted f2d/d2f ASM; not an integrated firmware',CPP_control_exact_accepted_rsqrt=True,source_patch_exact=True,CPP_changed_sections=changed,selected_CPP_delta_bytes=64,all_other_CPP_bytes_semantic_relocations_equal=True,all_RP_ASM_bytes_relocations_equal_accepted_f2d=True,d2f256_f2d172_preserved=True,contexts=contexts,ASM_generic_M0_M4_inherited_from_identical_accepted_sources=True,whole_M4_not_built=True,public_exp_alias_direct_no_added_interposition=True,public_exp_address=candidate.symbols['mk61_m0_exp'],helper_address=candidate.symbols[helper],helper_bytes=196,helper_source_object_ELF_unit_byte_exact=True,helper_no_external_calls_or_relocations=True,load_segments=segments,all_dependency_bindings_equal_accepted_or_resident=bindings,product_RAM168_and_wrapper_exact=True,rebuilds=12,records=records,isolated_helper_commands=[base,link],static_stack_bytes=static,whole_firmware_size_or_GC_not_claimed=True,hardware=False,canonical=False)
(O/'binding.json').write_text(json.dumps(d,indent=2)+'\n');print(json.dumps({k:v for k,v in d.items() if k not in ['verified','records','all_dependency_bindings_equal_accepted_or_resident','isolated_helper_commands']},indent=2))

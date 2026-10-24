"""Independent read-only source/pin/object/ABI binding and own-output rebuilds."""
from pathlib import Path
import ast,difflib,hashlib,json,shlex,struct,subprocess,sys
sys.dont_write_bytecode=True
R=Path('/Users/bolk/Projects/MK61S_MINI');P=R/'.build/m0-d2f-leaf-20261024';O=Path(__file__).resolve().parent
V=R/'.build/m0-asin-scaled-bound-v164-20261023';S=R/'.build/m0-pow-rsqrt-asm-20261024'
sys.path.insert(0,str(R/'tests'))
from check_stm32_vectors import ElfImage
def read(p):return json.loads(Path(p).read_text())
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def ref(p):return dict(path=str(p),bytes=Path(p).stat().st_size,sha256=sha(p))
assert sha(P/'FROZEN.json')=='87c989edfe183f894ad87a833aed18f7b47172366c6362cf2276c3023a6375cb'
assert sha(P/'result.json')=='b7399f8fb66ed5c3f040aae88d0004b12f813d55f2333aac14e012ce52aeaa81'
parent=R/'.build/m0-pow-rsqrt-asm-independent-20261024/FINAL-REVIEW.json'
assert sha(parent)=='90181e2ed18e8d312fc301ccfde8e93d1c63eced161883dee49fd9840ca86928'
verified=[]
for name,base,count in [('FROZEN.json',P,60),('source-lineage-pins.json',R,362)]:
 files=read(P/name)['files'];assert len(files)==count
 for n,d in files.items():
  p=base/n;assert sha(p)==d['sha256'] and p.stat().st_size==d['bytes'],str(p)
  verified.append(ref(p))
receipt=read(parent)
parent_refs=receipt['refs']
if isinstance(parent_refs,dict):parent_refs=list(parent_refs.values())
parent_refs=list(parent_refs)+list(receipt['target'].values())+[receipt['accepted_parent']]
for d in parent_refs:
 p=Path(d['path']);assert sha(p)==d['sha256'] and p.stat().st_size==d['bytes']
# Import only pure ELF parsing functions, never earlier report top-level code.
for file,names in [(R/'.build/m0-pow-square-ordinary-independent-20261024/bind.py',['allocated','body']),(R/'.build/m0-exp-cached-product-independent-20261024/bind_rebuild.py',['relocs'])]:
 tree=ast.parse(file.read_text());fns=[x for x in tree.body if isinstance(x,ast.FunctionDef) and x.name in names]
 assert len(fns)==len(names);exec(compile(ast.Module(body=fns,type_ignores=[]),str(O/'binding.py'),'exec'),globals())
def rel(e):return {n:v for n,v in relocs(e).items() if n in allocated(e)}
assert (P/'candidate/native_eabi_m0.S').read_bytes()==(P/'control/native_eabi_m0.S').read_bytes()==(S/'candidate/native_eabi_m0.S').read_bytes()
for n in ['native_eabi_m0_pow_rsqrt.inc','native_eabi_m0_pow_ordinary.inc','native_eabi_m0_pow_square.inc','native_eabi_m0_pow_exp_product.inc']:
 assert (P/'candidate'/n).read_bytes()==(P/'control'/n).read_bytes()==(S/'candidate'/n).read_bytes()
assert (P/'control/native_eabi_m0_convert.inc').read_bytes()==(V/'source/code/native_eabi_m0_convert.inc').read_bytes()
assert (P/'d2f.S').read_bytes()==(P/'candidate/native_eabi_m0_d2f.inc').read_bytes()
n='native_eabi_m0_convert.inc'
patch=''.join(difflib.unified_diff((P/'control'/n).read_text().splitlines(True),(P/'candidate'/n).read_text().splitlines(True),fromfile='a/code/'+n,tofile='b/code/'+n))
n='native_eabi_m0_d2f.inc'
patch+=''.join(difflib.unified_diff([], (P/'candidate'/n).read_text().splitlines(True),fromfile='/dev/null',tofile='b/code/'+n))
assert patch==(P/'accepted-rsqrt-to-d2f.patch').read_text()
a0,a1=ElfImage(P/'RP-control.o'),ElfImage(P/'RP-candidate.o');aa,bb=allocated(a0),allocated(a1)
parent_object=ElfImage(S/'RP-candidate-asm.o')
assert aa==allocated(parent_object) and rel(a0)==rel(parent_object)
resident=ElfImage(V/'firmware/mk61s-picocalc-pico-h.elf')
parent_body=bytearray(body(a0,'__aeabi_d2f'));resident_body=bytearray(body(resident,'__aeabi_d2f'))
assert rel(a0)['.text.__aeabi_d2f']==[(52,10,'mk61_m0_d2f_slow')]
h1,h2=struct.unpack_from('<HH',resident_body,52);s=(h1>>10)&1;j1=(h2>>13)&1;j2=(h2>>11)&1
imm=(s<<24)|((1^(j1^s))<<23)|((1^(j2^s))<<22)|((h1&1023)<<12)|((h2&2047)<<1)
if s:imm-=1<<25
assert (resident.symbols['__aeabi_d2f']&~1)+52+4+imm==(resident.symbols['mk61_m0_d2f_slow']&~1)
parent_body[52:56]=resident_body[52:56]=b'\0'*4
assert parent_body==resident_body
changed={n for n in aa.keys()|bb.keys() if aa.get(n)!=bb.get(n)}
assert changed=={'.text.__aeabi_d2f'} and len(aa['.text.__aeabi_d2f'])==68 and len(bb['.text.__aeabi_d2f'])==256
assert all(rel(a0).get(n,[])==rel(a1).get(n,[]) for n in aa.keys()|bb.keys() if n not in changed)
assert not rel(a1).get('.text.__aeabi_d2f')
contexts={}
for ctx in ['generic_M0','M4_soft','M4_hard']:
 x,y=ElfImage(P/(ctx+'-control.o')),ElfImage(P/(ctx+'-candidate.o'))
 assert allocated(x)==allocated(y) and rel(x)==rel(y)
 contexts[ctx]=dict(allocated_bytes=sum(map(len,allocated(x).values())),bytes_and_semantic_relocations_equal=True)
leaf,whole=ElfImage(P/'candidate.elf'),ElfImage(P/'whole-source.elf')
code=body(leaf,'__aeabi_d2f')
assert len(code)==256 and code==body(whole,'__aeabi_d2f')==body(a1,'__aeabi_d2f')
assert {n:b for n,b in allocated(leaf).items() if b}=={'.d2f':code}
assert {n:b for n,b in allocated(whole).items() if b}=={'.d2f':code}
assert leaf.symbols['__aeabi_d2f']==whole.symbols['__aeabi_d2f']==0x10163001
assert not any('veneer' in n.lower() for n in leaf.symbols)
build=read(P/'build.json');iso=read(P/'isolation.json');cc=Path(build['commands'][0][0]).parent
for image in ['candidate.elf','whole-source.elf','d2f.o']:
 assert not subprocess.check_output([str(cc/'arm-none-eabi-nm'),'-u',str(P/image)],text=True).strip()
# Exact frozen SDK flags and intended include precedence; no synthetic fast ABI.
db=read(V/'build/compile_commands.json');entry=next(d for d in db if d['file'].endswith('/code/native_eabi_m0.S'));flags=shlex.split(entry['command'])
for label in ['control','candidate']:
 cmd=next(c for c in iso['commands'] if Path(c[c.index('-o')+1]).name=='RP-'+label+'.o')
 expect=list(flags);expect[expect.index(entry['file'])]=str(P/label/'native_eabi_m0.S');expect[expect.index('-o')+1]=str(P/('RP-'+label+'.o'))
 assert cmd==expect
commands=build['commands']+iso['commands'];assert len(commands)==11
out=O/'rebuild';out.mkdir(exist_ok=True);outputs={c[c.index('-o')+1] for c in commands};records=[]
for c in commands:
 cmd=[str(out/Path(x).name) if x in outputs else x for x in c]
 assert not any(x in ['-MD','-MMD','-MF'] for x in cmd)
 p=subprocess.run(cmd,cwd=P,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT);assert p.returncode==0,p.stdout
 original=Path(c[c.index('-o')+1]);rebuilt=out/original.name;assert sha(rebuilt)==sha(original),(original,sha(rebuilt),sha(original))
 records.append(dict(original=ref(original),rebuilt=ref(rebuilt),command=cmd,returncode=0))
dis=subprocess.check_output([str(cc/'arm-none-eabi-objdump'),'-d',str(out/'candidate.elf')],text=True)
(O/'candidate.dis').write_text(dis)
qdis=subprocess.check_output([str(cc/'arm-none-eabi-objdump'),'-d','--disassemble=qfp_double2float',str(R/'.build/m0-v138-execution-20261023/reference/reference.elf')],text=True)
(O/'reference.dis').write_text(qdis)
d=dict(status='PASS_INDEPENDENT_RP_D2F_SOURCE_PINS_REBUILD_ABI',accepted_parent=ref(parent),parent_direct_refs_reverified=len(parent_refs),frozen_artifacts=60,lineage_pins=362,verified=verified,source_patch_exact=True,CPP_unchanged_in_accepted_parent=True,accepted_parent_RP_object_equal_current_control=True,resident_parent_entry_exact_except_resolved_BL=True,resident_parent_BL_targets_actual_old_narrow_function=True,only_changed_allocated_section='.text.__aeabi_d2f',old_bytes=68,new_bytes=256,selected_ASM_delta188=True,no_new_RAM_tables_external_or_libgcc=True,all_other_RP_bytes_semantic_relocations_equal=True,contexts=contexts,whole_M4_build_not_claimed=True,direct_public_ABI_entry='10163001',no_interposition_veneer=True,standalone_full_source_object_ELF_body_exact=True,whole_firmware_size_or_old_CPP_GC_not_measured=True,rebuilds=11,records=records,hardware=False,canonical=False)
(O/'binding.json').write_text(json.dumps(d,indent=2)+'\n')
print(json.dumps({k:v for k,v in d.items() if k not in ['verified','records']},indent=2))

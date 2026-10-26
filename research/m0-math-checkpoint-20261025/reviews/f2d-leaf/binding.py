"""Independent f2d immutable/source/parent/ABI binding and own rebuilds."""
from pathlib import Path
import ast,difflib,hashlib,json,shlex,struct,subprocess,sys
sys.dont_write_bytecode=True
R=Path('/Users/bolk/Projects/MK61S_MINI');P=R/'.build/m0-f2d-leaf-20261024';O=Path(__file__).resolve().parent
V=R/'.build/m0-asin-scaled-bound-v164-20261023';D=R/'.build/m0-d2f-leaf-20261024'
sys.path.insert(0,str(R/'tests'))
from check_stm32_vectors import ElfImage
def read(p):return json.loads(Path(p).read_text())
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def ref(p):return dict(path=str(p),bytes=Path(p).stat().st_size,sha256=sha(p))
assert sha(P/'FROZEN.json')=='931cce0b812981236a8fcadaf6cabf074ee473463092c90a8555764e4e288164'
assert sha(P/'result.json')=='1dc77e5fe5152b60df8ff5de59ad1bf4aeca5d0b5ad5ac6c85b9ffe47a41650e'
parent=R/'.build/m0-d2f-leaf-independent-20261024/FINAL-REVIEW.json'
assert sha(parent)=='500e2c5b1253e1ad73b94572b13fbddf34f5e4bf09cfce6f8ee97164d37a0aa4'
verified=[]
for name,base,count in [('FROZEN.json',P,61),('source-lineage-pins.json',R,424)]:
 files=read(P/name)['files'];assert len(files)==count
 for n,d in files.items():
  p=base/n;assert sha(p)==d['sha256'] and p.stat().st_size==d['bytes'],str(p)
  verified.append(ref(p))
assert read(P/'parent-review-at-seal.json')=={'independent_review_available_at_seal':False}
assert read(P/'result.json')['parent_review_at_seal']==read(P/'parent-review-at-seal.json')
receipt=read(parent);assert receipt['status']=='GO_PRIVATE_RP_D2F_LEAF_COMPONENT_ONLY' and not receipt['blockers']
parent_refs=list(receipt['refs'].values())+list(receipt['target'].values())+[receipt['accepted_parent'],ref(parent)]
assert len(parent_refs)==27
for d in parent_refs:
 p=Path(d['path']);assert sha(p)==d['sha256'] and p.stat().st_size==d['bytes']
postseal=R/'.build/m0-f2d-leaf-postseal-20261024.json';post=read(postseal)
assert post['d2f_receipt_sha256']==sha(parent) and post['d2f_direct_refs_verified']==26
assert post['f2d_corrected_oracle_accounting']['actual_directed_MPFR_input_conversions']==124373
assert post['f2d_corrected_oracle_accounting']['NaN_category_shortcuts_without_MPFR']==8586
# Pure parser imports only: no earlier review top-level code executes.
for file,names in [(R/'.build/m0-pow-square-ordinary-independent-20261024/bind.py',['allocated','body']),(R/'.build/m0-exp-cached-product-independent-20261024/bind_rebuild.py',['relocs'])]:
 tree=ast.parse(file.read_text());fns=[x for x in tree.body if isinstance(x,ast.FunctionDef) and x.name in names]
 assert len(fns)==len(names);exec(compile(ast.Module(body=fns,type_ignores=[]),str(O/'binding.py'),'exec'),globals())
def rel(e):return {n:v for n,v in relocs(e).items() if n in allocated(e)}
assert (P/'candidate/native_eabi_m0.S').read_bytes()==(P/'control/native_eabi_m0.S').read_bytes()==(D/'candidate/native_eabi_m0.S').read_bytes()
for n in ['native_eabi_m0_d2f.inc','native_eabi_m0_pow_rsqrt.inc','native_eabi_m0_pow_ordinary.inc','native_eabi_m0_pow_square.inc','native_eabi_m0_pow_exp_product.inc']:
 assert (P/'candidate'/n).read_bytes()==(P/'control'/n).read_bytes()==(D/'candidate'/n).read_bytes()
assert (P/'control/native_eabi_m0_convert.inc').read_bytes()==(D/'candidate/native_eabi_m0_convert.inc').read_bytes()
assert (P/'f2d.S').read_bytes()==(P/'candidate/native_eabi_m0_f2d.inc').read_bytes()
n='native_eabi_m0_convert.inc'
patch=''.join(difflib.unified_diff((P/'control'/n).read_text().splitlines(True),(P/'candidate'/n).read_text().splitlines(True),fromfile='a/code/'+n,tofile='b/code/'+n))
n='native_eabi_m0_f2d.inc'
patch+=''.join(difflib.unified_diff([], (P/'candidate'/n).read_text().splitlines(True),fromfile='/dev/null',tofile='b/code/'+n))
assert patch==(P/'qualified-d2f-to-f2d.patch').read_text()
a0,a1=ElfImage(P/'RP-control.o'),ElfImage(P/'RP-candidate.o');aa,bb=allocated(a0),allocated(a1)
parent_object=ElfImage(D/'RP-candidate.o')
assert aa==allocated(parent_object) and rel(a0)==rel(parent_object)
name='.m0_conversion_fixed.__aeabi_f2d';changed={n for n in aa.keys()|bb.keys() if aa.get(n)!=bb.get(n)}
assert changed=={name} and len(aa[name])==34 and len(bb[name])==172
assert all(rel(a0).get(n,[])==rel(a1).get(n,[]) for n in aa.keys()|bb.keys() if n not in changed)
assert not rel(a1).get(name)
assert aa['.text.__aeabi_d2f']==bb['.text.__aeabi_d2f']==body(ElfImage(D/'candidate.elf'),'__aeabi_d2f') and len(bb['.text.__aeabi_d2f'])==256
resident=ElfImage(V/'firmware/mk61s-picocalc-pico-h.elf')
parent_body=bytearray(body(a0,'__aeabi_f2d'));resident_body=bytearray(body(resident,'__aeabi_f2d'))
oldrel=rel(a0)[name];assert len(oldrel)==1 and oldrel[0][1:]==(10,'mk61_m0_f2d_slow')
offset=oldrel[0][0];h1,h2=struct.unpack_from('<HH',resident_body,offset);s=(h1>>10)&1;j1=(h2>>13)&1;j2=(h2>>11)&1
imm=(s<<24)|((1^(j1^s))<<23)|((1^(j2^s))<<22)|((h1&1023)<<12)|((h2&2047)<<1)
if s:imm-=1<<25
assert (resident.symbols['__aeabi_f2d']&~1)+offset+4+imm==(resident.symbols['mk61_m0_f2d_slow']&~1)
parent_body[offset:offset+4]=resident_body[offset:offset+4]=b'\0'*4
assert parent_body==resident_body
contexts={}
for ctx in ['generic_M0','M4_soft','M4_hard']:
 x,y=ElfImage(P/(ctx+'-control.o')),ElfImage(P/(ctx+'-candidate.o'))
 assert allocated(x)==allocated(y) and rel(x)==rel(y)
 contexts[ctx]=dict(allocated_bytes=sum(map(len,allocated(x).values())),bytes_and_semantic_relocations_equal=True)
leaf,whole=ElfImage(P/'candidate.elf'),ElfImage(P/'whole-source.elf');code=body(leaf,'__aeabi_f2d')
assert len(code)==172 and code==body(whole,'__aeabi_f2d')==body(a1,'__aeabi_f2d')
assert {n:b for n,b in allocated(leaf).items() if b}=={'.f2d':code}=={n:b for n,b in allocated(whole).items() if b}
assert leaf.symbols['__aeabi_f2d']==whole.symbols['__aeabi_f2d']==0x10164001
assert not any('veneer' in n.lower() for n in leaf.symbols)
build=read(P/'build.json');iso=read(P/'isolation.json');cc=Path(build['commands'][0][0]).parent
for image in ['candidate.elf','whole-source.elf','f2d.o']:
 assert not subprocess.check_output([str(cc/'arm-none-eabi-nm'),'-u',str(P/image)],text=True).strip()
db=read(V/'build/compile_commands.json');entry=next(d for d in db if d['file'].endswith('/code/native_eabi_m0.S'));flags=shlex.split(entry['command'])
for label in ['control','candidate']:
 cmd=next(c for c in iso['commands'] if Path(c[c.index('-o')+1]).name=='RP-'+label+'.o')
 expect=list(flags);expect[expect.index(entry['file'])]=str(P/label/'native_eabi_m0.S');expect[expect.index('-o')+1]=str(P/('RP-'+label+'.o'))
 assert cmd==expect
commands=build['commands']+iso['commands'];assert len(commands)==11
out=O/'rebuild';out.mkdir(exist_ok=True);outputs={c[c.index('-o')+1] for c in commands};records=[]
for c in commands:
 cmd=[str(out/Path(x).name) if x in outputs else x for x in c];assert not any(x in ['-MD','-MMD','-MF'] for x in cmd)
 p=subprocess.run(cmd,cwd=P,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT);assert p.returncode==0,p.stdout
 original=Path(c[c.index('-o')+1]);rebuilt=out/original.name;assert sha(rebuilt)==sha(original),(original,sha(rebuilt),sha(original))
 records.append(dict(original=ref(original),rebuilt=ref(rebuilt),command=cmd,returncode=0))
(O/'candidate.dis').write_text(subprocess.check_output([str(cc/'arm-none-eabi-objdump'),'-d',str(out/'candidate.elf')],text=True))
(O/'reference.dis').write_text(subprocess.check_output([str(cc/'arm-none-eabi-objdump'),'-d','--disassemble=qfp_float2double',str(R/'.build/m0-v138-execution-20261023/reference/reference.elf')],text=True))
d=dict(status='PASS_INDEPENDENT_RP_F2D_SOURCE_PINS_REBUILD_ABI',accepted_parent=ref(parent),parent_receipt_plus_direct_refs_reverified=27,parent_review_pending_at_seal_preserved=True,late_parent_GO_verified_without_rewriting_frozen=True,postseal=ref(postseal),frozen_artifacts=61,lineage_pins=424,verified=verified,source_patch_exact=True,CPP_not_changed_by_component_patch=True,accepted_parent_RP_object_equal_current_control=True,resident_parent_entry_exact_except_resolved_BL=True,resident_parent_BL_targets_real_extend=True,only_changed_allocated_section=name,old_bytes=34,new_bytes=172,selected_ASM_delta138=True,d2f256_exactly_preserved=True,no_new_RAM_tables_external_or_libgcc=True,all_other_RP_bytes_semantic_relocations_equal=True,contexts=contexts,whole_M4_build_not_claimed=True,direct_public_ABI_entry='10164001',no_interposition_veneer=True,standalone_full_source_object_ELF_body_exact=True,whole_firmware_size_or_old_CPP_GC_not_measured=True,rebuilds=11,records=records,hardware=False,canonical=False)
(O/'binding.json').write_text(json.dumps(d,indent=2)+'\n');print(json.dumps({k:v for k,v in d.items() if k not in ['verified','records']},indent=2))

"""Independent immutable/source/rebuild/relocation/actual macro binding."""
from pathlib import Path
import ast,difflib,hashlib,json,shlex,struct,subprocess,sys
sys.dont_write_bytecode=True
R=Path('/Users/bolk/Projects/MK61S_MINI');P=R/'.build/m0-pow-rsqrt-asm-20261024';S=R/'.build/m0-pow-square-ordinary-20261024';V=R/'.build/m0-asin-scaled-bound-v164-20261023';O=Path(__file__).resolve().parent
sys.path.insert(0,str(R/'tests'))
from check_stm32_vectors import ElfImage
def read(p):return json.loads(Path(p).read_text())
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def ref(p):return dict(path=str(p),bytes=Path(p).stat().st_size,sha256=sha(p))
assert sha(P/'FROZEN.json')=='21abcd41787ea53463b755b8f82138947ed9296b93831e00cfeac649b9408963'
assert sha(P/'result.json')=='0225a62c8a4da0780a1c14dcc3d9f583e976ea5671235bd5f7e2ead26e9fae36'
parent=R/'.build/m0-pow-square-ordinary-independent-20261024/FINAL-REVIEW.json'
assert sha(parent)=='4fb68e5ea8dbc4539befb483277ac2ce8e301bc23f1447c8b72de312fbbcdde1'
verified=[]
for n,base,count in [('FROZEN.json',P,107),('source-lineage-pins.json',R,230)]:
 files=read(P/n)['files'];assert len(files)==count
 for k,d in files.items():assert sha(base/k)==d['sha256'] and (base/k).stat().st_size==d['bytes'];verified.append(ref(base/k))
# Pure parsers only: no preceding review's top-level code executes.
for file,names in [(R/'.build/m0-pow-square-ordinary-independent-20261024/bind.py',['allocated','body']),(R/'.build/m0-exp-cached-product-independent-20261024/bind_rebuild.py',['relocs'])]:
 tree=ast.parse(file.read_text());fns=[x for x in tree.body if isinstance(x,ast.FunctionDef) and x.name in names]
 assert len(fns)==len(names);exec(compile(ast.Module(body=fns,type_ignores=[]),str(O/'binding.py'),'exec'),globals())
def rel(e):return {n:v for n,v in relocs(e).items() if n in allocated(e)}
for n in ['native_eabi_m0.cpp','native_eabi_m0.S','native_eabi_m0_pow_square.inc','native_eabi_m0_pow_exp_product.inc','native_eabi_m0_pow_ordinary.inc']:
 assert (P/'control'/n).read_bytes()==(S/'candidate'/n).read_bytes()
for n in ['native_eabi_m0_pow_square.inc','native_eabi_m0_pow_exp_product.inc','native_eabi_m0_pow_ordinary.inc']:
 assert (P/'candidate'/n).read_bytes()==(S/'candidate'/n).read_bytes()
patch=''
for n in ['native_eabi_m0.cpp','native_eabi_m0.S']:
 patch+=''.join(difflib.unified_diff((P/'control'/n).read_text().splitlines(True),(P/'candidate'/n).read_text().splitlines(True),fromfile='a/code/'+n,tofile='b/code/'+n))
n='native_eabi_m0_pow_rsqrt.inc'
patch+=''.join(difflib.unified_diff([], (P/'candidate'/n).read_text().splitlines(True),fromfile='/dev/null',tofile='b/code/'+n))
assert patch==(P/'accepted-pow-to-rsqrt.patch').read_text()
runtime=(P/'rsqrt.S').read_text().split('.section .m0_pow_center_quotient_unit_only')[0]+'\n#endif\n'
assert runtime.replace('.m0_pow_rsqrt_fast_only','.m0_pow_dispatch_extension')==(P/'candidate/native_eabi_m0_pow_rsqrt.inc').read_text()
c0,c1=ElfImage(P/'RP-control-cpp.o'),ElfImage(P/'RP-candidate-cpp.o')
assert allocated(c0)==allocated(c1)==allocated(ElfImage(S/'candidate-full.o')) and rel(c0)==rel(c1)
assert c1.symbols['mk61_m0_pow_rsqrt_boundary']==c1.symbols['pow_rsqrt_boundary'] and c1.sizes['mk61_m0_pow_rsqrt_boundary']==c1.sizes['pow_rsqrt_boundary']
a0,a1=ElfImage(P/'RP-control-asm.o'),ElfImage(P/'RP-candidate-asm.o');aa,bb=allocated(a0),allocated(a1)
assert aa.keys()==bb.keys() and {n for n in aa if aa[n]!=bb[n]}=={'.m0_pow_dispatch_extension'}
assert len(bb['.m0_pow_dispatch_extension'])-len(aa['.m0_pow_dispatch_extension'])==776
assert all(rel(a0)[n]==rel(a1)[n] for n in rel(a0) if n!='.m0_pow_dispatch_extension')
for context in ['generic_M0','M4_soft','M4_hard']:
 for kind in ['cpp','asm']:
  x,y=ElfImage(P/(context+'-control-'+kind+'.o')),ElfImage(P/(context+'-candidate-'+kind+'.o'))
  assert allocated(x)==allocated(y) and rel(x)==rel(y)
public,whole,old=ElfImage(P/'candidate.elf'),ElfImage(P/'whole-source.elf'),ElfImage(S/'candidate.elf')
expected=allocated(old);expected.update(allocated(public));expected={n:b for n,b in expected.items() if b}
assert {n:b for n,b in allocated(whole).items() if b}==expected
assert public.named_sections['.rsqrt'][5]==776
assert body(public,'mk61_m0_pow_rsqrt_fast')==body(whole,'mk61_m0_pow_rsqrt_fast')
ob=bytearray(body(a1,'mk61_m0_pow_rsqrt_fast'));pb=bytearray(body(public,'mk61_m0_pow_rsqrt_fast'))
offset=(a1.symbols['mk61_m0_pow_rsqrt_fast']&~1)-a1.named_sections['.m0_pow_dispatch_extension'][3]
helper_relocs=[(o-offset,t,n) for o,t,n in rel(a1)['.m0_pow_dispatch_extension'] if offset<=o<offset+776]
assert helper_relocs==[(686,10,'mk61_m0_pow_rsqrt_boundary'),(738,10,'pow_rsqrt'),(752,2,'factor_rsqrt_seeds')]
for o,t,n in helper_relocs:ob[o:o+4]=b'\0'*4;pb[o:o+4]=b'\0'*4
assert ob==pb
resident=ElfImage(V/'firmware/mk61s-picocalc-pico-h.elf')
assert body(c1,'pow_rsqrt_boundary')==body(ElfImage(S/'candidate-full.o'),'pow_rsqrt_boundary')
build=read(P/'build.json');iso=read(P/'isolation.json');cc=Path(build['commands'][0][0]).parent
for n,a in build['bindings'].items():
 target='pow_rsqrt_boundary' if n=='mk61_m0_pow_rsqrt_boundary' else n
 expected_address=(old.symbols[target] if target in ['mk61_m0_pow_square_exact','mk61_m0_pow_dispatch_ordinary'] else resident.symbols[target])
 assert a==expected_address and public.symbols[n]==a
assert body(ElfImage(P/'control.elf'),'mk61_m0_pow_fast')==body(old,'mk61_m0_pow_fast')
# Root entry bytes differ only by the literal target of the existing
# positive-normal inverse-root shortcut; all instructions are identical.
bo,bn=body(old,'mk61_m0_pow_fast'),body(public,'mk61_m0_pow_fast')
po=struct.pack('<I',resident.symbols['pow_rsqrt']);pn=struct.pack('<I',public.symbols['mk61_m0_pow_rsqrt_fast'])
assert bo.count(po)==1 and bo.replace(po,pn)==bn
unit=ElfImage(P/'unit.elf');trial=ElfImage(P/'trial-pre-alias-v3/unit.elf')
assert allocated(unit)==allocated(trial)
capsule=unit.bytes_at(unit.named_sections['.quotient']);macro=capsule[6:-2]
assert len(macro)==80
end=public.symbols['mk61_m0_pow_center_quotient_end']&~1;s=public.named_sections['.rsqrt'];off=end-s[3]-len(macro)
assert public.bytes_at(s)[off:off+80]==macro
undef=lambda p:subprocess.check_output([str(cc/'arm-none-eabi-nm'),'-u',str(p)],text=True).splitlines()
assert undef(P/'RP-control-cpp.o')==undef(P/'RP-candidate-cpp.o')
assert not undef(P/'candidate.elf') and not undef(P/'whole-source.elf') and not undef(P/'unit.elf')
db=read(V/'build/compile_commands.json')
for kind,ext in [('asm','S'),('cpp','cpp')]:
 entry=next(d for d in db if d['file'].endswith('/code/native_eabi_m0.'+ext));flags=shlex.split(entry['command'])
 for label in ['control','candidate']:
  cmd=next(c for c in iso['commands'] if Path(c[c.index('-o')+1]).name=='RP-'+label+'-'+kind+'.o')
  expect=list(flags);expect[expect.index(entry['file'])]=str(P/label/('native_eabi_m0.'+ext));expect[expect.index('-o')+1]=str(P/('RP-'+label+'-'+kind+'.o'));assert cmd==expect
selected=list(build['commands'])+[c for c in iso['commands'] if Path(c[c.index('-o')+1]).name in ['RP-candidate-cpp.o','RP-candidate-asm.o','whole-fixture-asm.o','whole-source.elf']]
assert len(selected)==10
out=O/'rebuild';out.mkdir(exist_ok=True);outputs={c[c.index('-o')+1] for c in selected};records=[]
for c in selected:
 cmd=[str(out/Path(x).name) if x in outputs else x for x in c];assert not any(x in ['-MD','-MMD','-MF'] for x in cmd)
 p=subprocess.run(cmd,cwd=P,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT);assert p.returncode==0,p.stdout
 original=Path(c[c.index('-o')+1]);rebuilt=out/original.name;assert sha(rebuilt)==sha(original)
 records.append(dict(original=ref(original),rebuilt=ref(rebuilt),command=cmd,returncode=0))
assert body(ElfImage(out/'unit.elf'),'mk61_m0_pow_center_quotient')==body(unit,'mk61_m0_pow_center_quotient')
d=dict(status='PASS_INDEPENDENT_RSQRT_PIN_SOURCE_REBUILD_AND_ACTUAL_CODE_BINDING',accepted_parent=ref(parent),frozen107=True,lineage230=True,verified=verified,source_patch_exact=True,old_CPP_allocated_relocations_equal=True,boundary_alias_storage_free=True,exact161bit_boundary_code_identical_resident=True,only_ASM_change='.m0_pow_dispatch_extension',code_delta776=True,zero_global_RAM_or_new_tables=True,all_generic_M0_M4_selected_bytes_relocations_equal=True,whole_M4_not_built=True,only_wrapper_literal_target_changes=True,whole_intended_source_private_overlay_equal_tested_union=True,quotient_macro_actual_bytes=80,unit_trial_final_runtime_macro_byte_exact=True,inline_quotient_begin=end-80,inline_quotient_end=end,rebuilds=10,records=records,hardware=False,canonical=False)
(O/'binding.json').write_text(json.dumps(d,indent=2)+'\n');print(json.dumps({k:v for k,v in d.items() if k not in ['verified','records']},indent=2))

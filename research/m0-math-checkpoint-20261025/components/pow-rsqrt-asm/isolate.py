"""Bind complete intended sources, byte-exact exclusions and actual unit macro."""
from pathlib import Path
import ast,difflib,hashlib,json,shlex,shutil,struct,subprocess,sys
sys.dont_write_bytecode=True
W=Path(__file__).resolve().parent;ROOT=W.parents[1]
P=ROOT/'.build/m0-asin-scaled-bound-v164-20261023';S=ROOT/'.build/m0-pow-square-ordinary-20261024'
sys.path.insert(0,str(ROOT/'tests'))
from check_stm32_vectors import ElfImage
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def allocated(e):return {n:e.bytes_at(s) for n,s in e.named_sections.items() if s[2]&2 and s[1]!=8 and s[5]}
tree=ast.parse((ROOT/'.build/m0-exp-cached-product-independent-20261024/bind_rebuild.py').read_text())
fn=next(x for x in tree.body if isinstance(x,ast.FunctionDef) and x.name=='relocs')
exec(compile(ast.Module(body=[fn],type_ignores=[]),str(W/'isolate.py'),'exec'),globals())
def relevant_relocs(e):return {n:r for n,r in relocs(e).items() if n in allocated(e)}
for label in ('control','candidate'):
 folder=W/label;folder.mkdir(exist_ok=True)
 for n in ('native_eabi_m0.cpp','native_eabi_m0.S','native_eabi_m0_pow_square.inc','native_eabi_m0_pow_ordinary.inc','native_eabi_m0_pow_exp_product.inc'):
  shutil.copyfile(S/'candidate'/n,folder/n)
cpp=(W/'candidate/native_eabi_m0.cpp').read_text()
anchor='    ".thumb_set mk61_m0_pow_near_one_binomial_dispatch,pow_near_one_binomial\\n");'
assert cpp.count(anchor)==1
addition='    ".thumb_set mk61_m0_pow_near_one_binomial_dispatch,pow_near_one_binomial\\n"\n    ".global mk61_m0_pow_rsqrt_boundary\\n.hidden mk61_m0_pow_rsqrt_boundary\\n"\n    ".thumb_set mk61_m0_pow_rsqrt_boundary,pow_rsqrt_boundary\\n");'
(W/'candidate/native_eabi_m0.cpp').write_text(cpp.replace(anchor,addition))
source=(W/'candidate/native_eabi_m0.S').read_text();assert source.count('ldr r2,=pow_rsqrt')==2
source=source.replace('ldr r2,=pow_rsqrt','ldr r2,=mk61_m0_pow_rsqrt_fast',1)
anchor='#include "native_eabi_m0_pow_square.inc"'
assert source.count(anchor)==1
source=source.replace(anchor,anchor+'\n#include "native_eabi_m0_pow_rsqrt.inc"')
(W/'candidate/native_eabi_m0.S').write_text(source)
runtime=(W/'rsqrt.S').read_text().split('.section .m0_pow_center_quotient_unit_only')[0]+'\n#endif\n'
intended=runtime.replace('.m0_pow_rsqrt_fast_only','.m0_pow_dispatch_extension')
(W/'candidate/native_eabi_m0_pow_rsqrt.inc').write_text(intended)
db=json.loads((P/'build/compile_commands.json').read_text());commands=[];rp={}
entries={k:next(r for r in db if r['file'].endswith('/code/native_eabi_m0.'+('S' if k=='asm' else 'cpp'))) for k in ('asm','cpp')}
flags={k:shlex.split(e['command']) for k,e in entries.items()};cc=Path(flags['asm'][0]).parent
def compile_one(label,kind,context='RP'):
 entry=entries[kind];command=list(flags[kind])
 if context!='RP':
  command=[v for v in command if v!='-DMK61_M0_RP2040_EABI=1']
  cpu='cortex-m0plus' if context=='generic_M0' else 'cortex-m4'
  command[command.index('-mcpu=cortex-m0plus')]='-mcpu='+cpu
  if context.startswith('M4'):command[command.index('-DMK61_USE_M0_EABI=1')]='-DMK61_USE_M0_EABI=0'
  if context=='M4_hard':command+=['-mfloat-abi=hard','-mfpu=fpv4-sp-d16']
 command[command.index(entry['file'])]=str(W/label/Path(entry['file']).name)
 out=W/(context+'-'+label+'-'+kind+'.o');command[command.index('-o')+1]=str(out)
 subprocess.run(command,cwd=W,check=True);commands.append(command)
 return ElfImage(out)
for kind in ('asm','cpp'):
 rp[kind]=[compile_one(label,kind) for label in ('control','candidate')]
old,new=rp['cpp'];assert allocated(old)==allocated(new)
assert relevant_relocs(old)==relevant_relocs(new)
assert new.symbols['mk61_m0_pow_rsqrt_boundary']==new.symbols['pow_rsqrt_boundary']
assert new.sizes['mk61_m0_pow_rsqrt_boundary']==new.sizes['pow_rsqrt_boundary']
assert allocated(old)==allocated(ElfImage(S/'candidate-full.o'))
old,new=rp['asm'];a,b=allocated(old),allocated(new)
assert a.keys()==b.keys() and {n for n in a if a[n]!=b[n]}=={'.m0_pow_dispatch_extension'}
assert len(b['.m0_pow_dispatch_extension'])-len(a['.m0_pow_dispatch_extension'])==776
for n,v in relevant_relocs(old).items():
 if n!='.m0_pow_dispatch_extension':assert v==relevant_relocs(new)[n]
contexts=[]
for context in ('generic_M0','M4_soft','M4_hard'):
 for kind in ('asm','cpp'):
  control,candidate=[compile_one(label,kind,context) for label in ('control','candidate')]
  assert allocated(control)==allocated(candidate) and relevant_relocs(control)==relevant_relocs(candidate)
  contexts.append({'context':context,'kind':kind,'allocated_bytes_and_relocations_identical':True,'allocated_bytes':sum(map(len,allocated(candidate).values()))})
fixture=W/'whole-fixture';fixture.mkdir(exist_ok=True)
for n in ('native_eabi_m0.S','native_eabi_m0_pow_exp_product.inc'):
 shutil.copyfile(W/'candidate'/n,fixture/n)
(fixture/'native_eabi_m0_pow_square.inc').write_text((W/'candidate/native_eabi_m0_pow_square.inc').read_text().replace('.m0_pow_dispatch_extension','.m0_pow_square_exact_only'))
(fixture/'native_eabi_m0_pow_rsqrt.inc').write_text(runtime)
command=list(flags['asm']);entry=entries['asm'];command[command.index(entry['file'])]=str(fixture/'native_eabi_m0.S');command[command.index('-o')+1]=str(W/'whole-fixture-asm.o')
subprocess.run(command,cwd=W,check=True);commands.append(command)
text=(S/'entry.ld').read_text();text='mk61_m0_pow_rsqrt_boundary = 0x10160025;\nfactor_rsqrt_seeds = 0x101615c8;\n'+text
text=text.replace('ordinary PT_LOAD FLAGS(5);','ordinary PT_LOAD FLAGS(5); rsqrt PT_LOAD FLAGS(5);')
text=text.replace(' /DISCARD/', ' .rsqrt 0x10162800 : { *(.m0_pow_rsqrt_fast_only) } :rsqrt\n /DISCARD/')
(W/'whole.ld').write_text(text)
command=[str(cc/'arm-none-eabi-ld'),'--gc-sections','-e','mk61_m0_pow_fast','-T',str(W/'whole.ld'),str(W/'whole-fixture-asm.o'),str(W/'RP-candidate-cpp.o'),'-o',str(W/'whole-source.elf')]
subprocess.run(command,cwd=W,check=True);commands.append(command)
public=ElfImage(W/'candidate.elf');parent=ElfImage(S/'candidate.elf');whole=ElfImage(W/'whole-source.elf')
expected=allocated(parent);expected.update(allocated(public))
assert allocated(whole)==expected
loads=[p for p in whole.segments if p[0]==1 and p[4]]
assert {(p[2],p[4]) for p in loads}=={(s[3],s[5]) for s in whole.named_sections.values() if s[2]&2 and s[5]}
assert all(p[2]==p[3] and p[4]==p[5] for p in loads)
unit=ElfImage(W/'unit.elf');body=unit.bytes_at(unit.named_sections['.quotient'])
# Unit has exactly three entry instructions and one return instruction.
macro=body[6:-2];end=public.symbols['mk61_m0_pow_center_quotient_end']&~1
s=public.named_sections['.rsqrt'];offset=end-s[3]-len(macro)
assert public.bytes_at(s)[offset:offset+len(macro)]==macro
old_unit=ElfImage(W/'trial-pre-alias-v3/unit.elf')
assert allocated(old_unit)==allocated(unit)
qualification=json.loads((W/'qualification.json').read_text())
assert qualification['candidate_ELF_sha256']==sha(W/'candidate.elf') and qualification['rsqrt_source_sha256']==sha(W/'rsqrt.S')
binding={'status':'PASS_FINAL_PUBLIC_EXECUTED_AND_PRE_ALIAS_QUOTIENT_UNIT_BYTES_IDENTICAL','final_public_ELF_sha256':sha(W/'candidate.elf'),'public_qualification_matches_final_exact_ELF':True,'executed_unit_ELF_sha256':sha(W/'trial-pre-alias-v3/unit.elf'),'final_unit_ELF_sha256':sha(W/'unit.elf'),'unit_allocated_equal':True,'unit_change':'storage-free CPP alias names only; actual quotient load address and bytes identical','full_qualification_sha256':sha(W/'qualification.json'),'unit_proof_sha256':sha(W/'unit-proof.json')}
(W/'executed-code-binding.json').write_text(json.dumps(binding,indent=2)+'\n')
patch=''
for n in ('native_eabi_m0.cpp','native_eabi_m0.S'):
 patch+=''.join(difflib.unified_diff((W/'control'/n).read_text().splitlines(True),(W/'candidate'/n).read_text().splitlines(True),fromfile='a/code/'+n,tofile='b/code/'+n))
n='native_eabi_m0_pow_rsqrt.inc'
patch+=''.join(difflib.unified_diff([],intended.splitlines(True),fromfile='/dev/null',tofile='b/code/'+n))
(W/'accepted-pow-to-rsqrt.patch').write_text(patch)
out={'status':'PASS_RP_RSQRT_WHOLE_SOURCE_BINDING_AND_M4_M0_EXCLUSION','whole_source_ELF_sha256':sha(W/'whole-source.elf'),'candidate_ELF_sha256':sha(W/'candidate.elf'),'CPP_sha256':sha(W/'candidate/native_eabi_m0.cpp'),'ASM_sha256':sha(W/'candidate/native_eabi_m0.S'),'include_sha256':sha(W/'candidate/native_eabi_m0_pow_rsqrt.inc'),'all_CPP_allocated_bytes_and_relocations_identical':True,'new_CPP_boundary_alias_storage_free':True,'only_ASM_section_changed':'.m0_pow_dispatch_extension','allocated_object_bytes_delta':776,'new_tables_RAM_libgcc':False,'whole_intended_source_emits_tested_allocated_bytes':True,'unit_quotient_macro_equals_inline_runtime_bytes':True,'quotient_macro_bytes':len(macro),'executed_unit_pre_alias_and_final_load_bytes_identical':True,'contexts':contexts,'whole_M4_firmware_not_built':True,'whole_repaired_platform_integration_not_done':True,'commands':commands,'hardware_accessed':False}
(W/'isolation.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps({k:v for k,v in out.items() if k!='commands'},indent=2))

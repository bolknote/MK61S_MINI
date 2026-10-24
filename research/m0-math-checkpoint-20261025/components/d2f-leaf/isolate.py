"""Only the RP conversion section changes; bind the full ASM source body."""
from pathlib import Path
import ast,difflib,hashlib,json,shlex,shutil,struct,subprocess,sys
sys.dont_write_bytecode=True
W=Path(__file__).resolve().parent;ROOT=W.parents[1]
P=ROOT/'.build/m0-asin-scaled-bound-v164-20261023';R=ROOT/'.build/m0-pow-rsqrt-asm-20261024'
sys.path.insert(0,str(ROOT/'tests'))
from check_stm32_vectors import ElfImage
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def allocated(e):return {n:e.bytes_at(s) for n,s in e.named_sections.items() if s[2]&2 and s[1]!=8 and s[5]}
tree=ast.parse((ROOT/'.build/m0-exp-cached-product-independent-20261024/bind_rebuild.py').read_text())
fn=next(x for x in tree.body if isinstance(x,ast.FunctionDef) and x.name=='relocs')
exec(compile(ast.Module(body=[fn],type_ignores=[]),str(W/'isolate.py'),'exec'),globals())
def actual_relocs(e):return {n:v for n,v in relocs(e).items() if n in allocated(e)}
assert sha(R/'FROZEN.json')=='21abcd41787ea53463b755b8f82138947ed9296b93831e00cfeac649b9408963'
for label in ('control','candidate'):
 folder=W/label;folder.mkdir(exist_ok=True)
 for source in (R/'candidate').iterdir():
  if source.suffix in ('.S','.inc'):shutil.copyfile(source,folder/source.name)
 shutil.copyfile(P/'source/code/native_eabi_m0_convert.inc',folder/'native_eabi_m0_convert.inc')
source=(W/'candidate/native_eabi_m0_convert.inc').read_text();a=source.index('function __aeabi_d2f\n');z=source.index('end __aeabi_d2f',a)+len('end __aeabi_d2f');old=source[a:z]
replacement='#if defined(MK61_M0_RP2040_EABI) && MK61_M0_RP2040_EABI\n#include "native_eabi_m0_d2f.inc"\n#else\n'+old+'\n#endif'
(W/'candidate/native_eabi_m0_convert.inc').write_text(source[:a]+replacement+source[z:])
shutil.copyfile(W/'d2f.S',W/'candidate/native_eabi_m0_d2f.inc')
entry=next(e for e in json.loads((P/'build/compile_commands.json').read_text()) if e['file'].endswith('/code/native_eabi_m0.S'))
flags=shlex.split(entry['command']);cc=Path(flags[0]).parent;commands=[];images={}
for context in ('RP','generic_M0','M4_soft','M4_hard'):
 for label in ('control','candidate'):
  command=list(flags)
  if context!='RP':command=[s for s in command if s!='-DMK61_M0_RP2040_EABI=1']
  if context.startswith('M4'):
   command[command.index('-mcpu=cortex-m0plus')]='-mcpu=cortex-m4'
   command[command.index('-DMK61_USE_M0_EABI=1')]='-DMK61_USE_M0_EABI=0'
   if context=='M4_hard':command+=['-mfloat-abi=hard','-mfpu=fpv4-sp-d16']
  command[command.index(entry['file'])]=str(W/label/'native_eabi_m0.S');out=W/(context+'-'+label+'.o');command[command.index('-o')+1]=str(out)
  subprocess.run(command,cwd=W,check=True);commands.append(command);images[(context,label)]=ElfImage(out)
contexts=[]
for context in ('generic_M0','M4_soft','M4_hard'):
 a,b=[images[(context,label)] for label in ('control','candidate')]
 assert allocated(a)==allocated(b) and actual_relocs(a)==actual_relocs(b)
 contexts.append({'context':context,'all_allocated_bytes_and_relocations_identical':True,'allocated_bytes':sum(map(len,allocated(a).values()))})
a,b=images[('RP','control')],images[('RP','candidate')];aa,bb=allocated(a),allocated(b)
assert aa==allocated(ElfImage(R/'RP-candidate-asm.o'))
assert aa.keys()==bb.keys() and {n for n in aa if aa[n]!=bb[n]}=={'.text.__aeabi_d2f'}
for n,v in actual_relocs(a).items():
 if n!='.text.__aeabi_d2f':assert v==actual_relocs(b)[n]
private=ElfImage(W/'candidate.elf');assert bb['.text.__aeabi_d2f']==private.bytes_at(private.named_sections['.d2f'])
assert not actual_relocs(b).get('.text.__aeabi_d2f')
command=[str(cc/'arm-none-eabi-ld'),'--gc-sections','-e','__aeabi_d2f','-T',str(W/'entry.ld'),str(W/'RP-candidate.o'),'-o',str(W/'whole-source.elf')]
subprocess.run(command,cwd=W,check=True);commands.append(command)
assert allocated(ElfImage(W/'whole-source.elf'))==allocated(private)
patch=''.join(difflib.unified_diff((W/'control/native_eabi_m0_convert.inc').read_text().splitlines(True),(W/'candidate/native_eabi_m0_convert.inc').read_text().splitlines(True),fromfile='a/code/native_eabi_m0_convert.inc',tofile='b/code/native_eabi_m0_convert.inc'))
patch+=''.join(difflib.unified_diff([],(W/'d2f.S').read_text().splitlines(True),fromfile='/dev/null',tofile='b/code/native_eabi_m0_d2f.inc'))
(W/'accepted-rsqrt-to-d2f.patch').write_text(patch)
out={'status':'PASS_ONLY_RP_D2F_SECTION_CHANGED_FULL_SOURCE_BOUND_GENERIC_M0_M4_EXCLUDED','candidate_ELF_sha256':sha(W/'candidate.elf'),'whole_source_ELF_sha256':sha(W/'whole-source.elf'),'full_ASM_source_unchanged_from_accepted_parent':True,'convert_include_sha256':sha(W/'candidate/native_eabi_m0_convert.inc'),'new_include_sha256':sha(W/'candidate/native_eabi_m0_d2f.inc'),'CPP_unchanged':True,'only_allocated_section_changed':'.text.__aeabi_d2f','old_body_bytes':len(aa['.text.__aeabi_d2f']),'new_body_bytes':len(bb['.text.__aeabi_d2f']),'code_delta_bytes':len(bb['.text.__aeabi_d2f'])-len(aa['.text.__aeabi_d2f']),'new_tables_global_RAM_libgcc_external_calls':False,'all_other_RP_allocated_and_relocations_identical':True,'full_source_selected_entry_emits_exact_tested_body':True,'private_entry_test_direct_no_interposition_veneer':True,'full_relinked_firmware_not_built':True,'contexts':contexts,'commands':commands,'hardware_accessed':False}
(W/'isolation.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps({k:v for k,v in out.items() if k!='commands'},indent=2))

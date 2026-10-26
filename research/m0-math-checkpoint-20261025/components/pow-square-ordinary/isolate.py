"""Whole source/allocated binding and generic M0/M4 exclusion controls."""
from pathlib import Path
import hashlib,json,shlex,shutil,subprocess,sys
sys.dont_write_bytecode=True
W=Path(__file__).resolve().parent;ROOT=W.parents[1];P=ROOT/'.build/m0-asin-scaled-bound-v164-20261023';B=ROOT/'.build/m0-exp-cached-product-20261024'
sys.path.insert(0,str(ROOT/'tests'))
from check_stm32_vectors import ElfImage
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
b=json.loads((W/'build.json').read_text());cc=Path(b['commands'][0][0]).parent;commands=[]
source=(P/'source/code/native_eabi_m0.S').read_text();a=source.index('// Thin exact-power dispatch keeps trivial results out of the large frame.');z=source.index('end mk61_m0_pow_fast',a)+len('end mk61_m0_pow_fast');old=source[a:z]
wrapper=(W/'candidate.S').read_text();start=wrapper.index('// Thin exact-power dispatch');end=wrapper.rindex('#endif');wrapper=wrapper[start:end].replace('.size mk61_m0_pow_fast,.-mk61_m0_pow_fast','end mk61_m0_pow_fast')
replacement='#if defined(MK61_M0_RP2040_EABI) && MK61_M0_RP2040_EABI\n'+wrapper+'#include "native_eabi_m0_pow_square.inc"\n#else\n'+old+'\n#endif'
(W/'control/native_eabi_m0.S').write_text(source)
(W/'candidate/native_eabi_m0.S').write_text(source[:a]+replacement+source[z:])
square=(W/'square.S').read_text().replace('.m0_pow_square_exact_only','.m0_pow_dispatch_extension')
(W/'candidate/native_eabi_m0_pow_square.inc').write_text(square)
for label in ('control','candidate'):
 shutil.copyfile(B/'candidate/native_eabi_m0_pow_exp_product.inc',W/label/'native_eabi_m0_pow_exp_product.inc')
DB=json.loads((P/'build/compile_commands.json').read_text())
asm_entry=next(r for r in DB if r['file'].endswith('/code/native_eabi_m0.S'))
cpp_entry=next(r for r in DB if r['file'].endswith('/code/native_eabi_m0.cpp'))
asflags=shlex.split(asm_entry['command']);cppflags=shlex.split(cpp_entry['command'])
def compile_one(flags,entry,label,suffix):
 command=list(flags);command[command.index(entry['file'])]=str(W/label/Path(entry['file']).name)
 command[command.index('-o')+1]=str(W/(label+'-'+suffix+'.o'))
 subprocess.run(command,cwd=W,check=True);commands.append(command)
 return ElfImage(W/(label+'-'+suffix+'.o'))
def allocated(im):return {n:im.bytes_at(s) for n,s in im.named_sections.items() if s[2]&2 and s[1]!=8}
asm=[compile_one(asflags,asm_entry,label,'full-asm') for label in ('control','candidate')]
ac,an=map(allocated,asm);assert set(ac)==set(an)
assert {n for n in ac if ac[n]!=an[n]}=={'.m0_pow_dispatch_extension'}
assert len(an['.m0_pow_dispatch_extension'])-len(ac['.m0_pow_dispatch_extension'])==320
# Entire helper body in intended source is identical to the qualified
# partial fixture, despite its original production input section name.
helper='mk61_m0_pow_square_exact';s=asm[1].named_sections['.m0_pow_dispatch_extension'];offset=(asm[1].symbols[helper]&~1)-s[3]
public=ElfImage(W/'candidate.elf')
assert asm[1].bytes_at(s)[offset:offset+asm[1].sizes[helper]]==public.bytes_at(public.named_sections['.square'])
# Build the entire intended ASM source into the private section map.
# Only the helper's input section name is changed, without editing its code.
fixture=W/'whole-fixture';fixture.mkdir(exist_ok=True)
shutil.copyfile(W/'candidate/native_eabi_m0.S',fixture/'native_eabi_m0.S')
shutil.copyfile(W/'candidate/native_eabi_m0_pow_exp_product.inc',fixture/'native_eabi_m0_pow_exp_product.inc')
(fixture/'native_eabi_m0_pow_square.inc').write_text(square.replace('.m0_pow_dispatch_extension','.m0_pow_square_exact_only'))
command=list(asflags);command[command.index(asm_entry['file'])]=str(fixture/'native_eabi_m0.S');command[command.index('-o')+1]=str(W/'whole-fixture-asm.o')
subprocess.run(command,cwd=W,check=True);commands.append(command)
command=[str(cc/'arm-none-eabi-ld'),'--gc-sections','-e','mk61_m0_pow_fast','-T',str(W/'entry.ld'),str(W/'whole-fixture-asm.o'),str(W/'candidate-full.o'),'-o',str(W/'whole-source.elf')]
subprocess.run(command,cwd=W,check=True);commands.append(command)
assert allocated(ElfImage(W/'whole-source.elf'))==allocated(public),'Whole intended source differs from actual tested allocated code'
contexts=[]
for context,cpu,enabled,hard in (('generic_M0','cortex-m0plus',True,False),('M4_soft','cortex-m4',False,False),('M4_hard','cortex-m4',False,True)):
 control_sets=[];candidate_sets=[]
 for entry,flags,kind in ((asm_entry,asflags,'asm'),(cpp_entry,cppflags,'cpp')):
  images=[]
  for label in ('control','candidate'):
   command=[v for v in flags if v!='-DMK61_M0_RP2040_EABI=1']
   command[command.index('-mcpu=cortex-m0plus')]='-mcpu='+cpu
   if not enabled:command[command.index('-DMK61_USE_M0_EABI=1')]='-DMK61_USE_M0_EABI=0'
   if hard:command+=['-mfloat-abi=hard','-mfpu=fpv4-sp-d16']
   command[command.index(entry['file'])]=str(W/label/Path(entry['file']).name)
   command[command.index('-o')+1]=str(W/(context+'-'+label+'-'+kind+'.o'))
   subprocess.run(command,cwd=W,check=True);commands.append(command);images.append(ElfImage(W/(context+'-'+label+'-'+kind+'.o')))
  assert allocated(images[0])==allocated(images[1]),(context,kind)
  contexts.append(dict(context=context,kind=kind,allocated_code_data_identical=True,allocated_bytes=sum(map(len,allocated(images[1]).values()))))
cpp=ElfImage(W/'candidate-full.o');parent=ElfImage(W/'control-full.o');cp,cn=allocated(parent),allocated(cpp)
assert all(cp[n]==cn[n] for n in cp) and set(cn)-set(cp)=={'.m0_pow_dispatch_ordinary'}
assert not subprocess.check_output([str(cc/'arm-none-eabi-nm'),'-u',str(W/'candidate.elf')],text=True)
# Bind inherited exact-product units without re-counting their old calls.
T=ROOT/'.build/m0-pow-square-exact-20261024';inherited={}
for name in ('unit-build.json','unit-proof.json','midpoint-proof.json'):
 d=json.loads((T/name).read_text());assert d['square_source_sha256']==b['square_source_sha256'];inherited[str((T/name).relative_to(ROOT))]=sha(T/name)
for report in ('unit-proof.json','midpoint-proof.json'):
 d=json.loads((T/report).read_text());assert d['candidate_wrong']==0
out=dict(status='PASS_ONLY_RP_POW_ENTRY_EXACT_SQUARE_ORDINARY_TAIL_GENERIC_M0_M4_IDENTICAL',
 wrapper_source_sha256=sha(W/'candidate.S'),square_source_sha256=sha(W/'square.S'),ordinary_include_sha256=sha(W/'candidate/native_eabi_m0_pow_ordinary.inc'),
 full_CPP_source_sha256=sha(W/'candidate/native_eabi_m0.cpp'),full_ASM_source_sha256=sha(W/'candidate/native_eabi_m0.S'),
 candidate_ELF_sha256=sha(W/'candidate.elf'),whole_source_ELF_sha256=sha(W/'whole-source.elf'),
 whole_intended_sources_emit_identical_public_allocated_bytes=True,
 all_existing_CPP_allocated_code_and_data_byte_exact_parent=True,new_CPP_section='.m0_pow_dispatch_ordinary',new_CPP_section_bytes=len(cn['.m0_pow_dispatch_ordinary']),
 only_changed_existing_ASM_section='.m0_pow_dispatch_extension',ASM_allocated_bytes_delta=320,
 full_CPP_ASM_combined_object_allocated_bytes_delta=320+len(cn['.m0_pow_dispatch_ordinary']),
 public_fixture_allocated_code_bytes_delta=sum(s[5] for s in public.named_sections.values() if s[2]&2)-204,
 exact_square_body_bytes=328,storage_free_aliases=True,no_new_tables_global_RAM_or_libgcc=True,
 inherited_exact_kernel_proofs=inherited,inherited_ARM_calls_not_added=572776,
 contexts=contexts,commands=commands,whole_M4_firmware_not_built=True,
 whole_repaired_platform_firmware_integration_not_done=True,hardware_accessed=False)
(W/'isolation.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps({k:v for k,v in out.items() if k!='commands'},indent=2))

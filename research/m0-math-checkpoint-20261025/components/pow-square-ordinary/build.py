"""Build pow entry/exact square/ordinary tail, preserving all frozen code."""
from pathlib import Path
import hashlib,json,shlex,subprocess,sys
sys.dont_write_bytecode=True
W=Path(__file__).resolve().parent;ROOT=W.parents[1]
P=ROOT/'.build/m0-asin-scaled-bound-v164-20261023';B=ROOT/'.build/m0-exp-cached-product-20261024'
sys.path.insert(0,str(ROOT/'tests'))
from check_stm32_vectors import ElfImage
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
entry=next(r for r in json.loads((P/'build/compile_commands.json').read_text()) if r['file'].endswith('/code/native_eabi_m0.cpp'))
flags=shlex.split(entry['command']);cc=Path(flags[0]).parent;commands=[]
def allocated(im):return {n:im.bytes_at(s) for n,s in im.named_sections.items() if s[2]&2 and s[1]!=8}
for label in ('control','candidate'):
 command=list(flags);command[command.index(entry['file'])]=str(W/label/'native_eabi_m0.cpp');command[command.index('-o')+1]=str(W/(label+'-full.o'))
 subprocess.run(command,cwd=W,check=True);commands.append(command)
control=ElfImage(W/'control-full.o');candidate=ElfImage(W/'candidate-full.o')
old,new=allocated(control),allocated(candidate)
assert old==allocated(ElfImage(B/'candidate-full.o'))
assert set(new)-set(old)=={'.m0_pow_dispatch_ordinary'}
assert all(old[n]==new[n] for n in old),'Existing CPP code/data must remain byte exact'
aliases={'mk61_m0_pow_negative_integer_dispatch':'pow_negative_integer','mk61_m0_pow_positive_checked_dispatch':'pow_positive_checked','mk61_m0_pow_near_one_binomial_dispatch':'pow_near_one_binomial'}
for alias,target in aliases.items():assert candidate.symbols[alias]==candidate.symbols[target],(alias,target)
command=list(flags);command[command.index(entry['file'])]=str(W/'ordinary.cpp');command[command.index('-o')+1]=str(W/'ordinary.o')
subprocess.run(command,cwd=W,check=True);commands.append(command)
ordinary_object=ElfImage(W/'ordinary.o')
assert ordinary_object.bytes_at(ordinary_object.named_sections['.m0_pow_dispatch_ordinary'])==new['.m0_pow_dispatch_ordinary'],'Full source include differs from standalone tail code'
resident=ElfImage(P/'firmware/mk61s-picocalc-pico-h.elf');name='mk61_m0_pow_fast';a=resident.symbols[name]&~1
s=next(s for s in resident.named_sections.values() if s[3]<=a<s[3]+s[5]);original=resident.bytes_at(s)[a-s[3]:a-s[3]+resident.sizes[name]]
refs=['mk61_m0_pow_dispatch','__aeabi_ddiv','__aeabi_dmul','mk61_m0_sqrt','pow_rsqrt','pow_root128_ranged']
text=''.join(n+' = '+hex(resident.symbols[n])+';\n' for n in refs)
text+=''.join(alias+' = '+hex(resident.symbols[target])+';\n' for alias,target in aliases.items())
text+='''PHDRS { entry PT_LOAD FLAGS(5); square PT_LOAD FLAGS(5); ordinary PT_LOAD FLAGS(5); }
SECTIONS {
 .pow 0x101614cc : { *(.m0_pow_dispatch_extension) } :entry
 .square 0x10161e00 : { *(.m0_pow_square_exact_only) } :square
 .ordinary 0x10162200 : { *(.m0_pow_dispatch_ordinary) *(.text*) *(.rodata*) } :ordinary
 /DISCARD/ : { *(.ARM*) *(.comment) *(.note*) }
}
'''
(W/'entry.ld').write_text(text)
meta={}
for label in ('control','candidate'):
 sources=[label]+(['square'] if label=='candidate' else [])
 for source in sources:
  command=[str(cc/'arm-none-eabi-gcc'),'-mcpu=cortex-m0plus','-mthumb','-DMK61_USE_M0_EABI=1','-DMK61_M0_RP2040_EABI=1','-c',str(W/(source+'.S')),'-o',str(W/(source+'.o'))]
  subprocess.run(command,cwd=W,check=True);commands.append(command)
 objects=[str(W/(label+'.o'))]+([str(W/'square.o'),str(W/'candidate-full.o')] if label=='candidate' else [])
 command=[str(cc/'arm-none-eabi-ld'),'--gc-sections','-e',name,'-T',str(W/'entry.ld'),*objects,'-o',str(W/(label+'.elf'))]
 subprocess.run(command,cwd=W,check=True);commands.append(command)
 im=ElfImage(W/(label+'.elf'));code=im.bytes_at(im.named_sections['.pow'])
 assert im.symbols[name]==resident.symbols[name]
 assert not subprocess.check_output([str(cc/'arm-none-eabi-nm'),'-u',str(W/(label+'.elf'))],text=True)
 assert im.sizes[name]==len(code)
 if label=='control':assert code==original
 else:assert len(code)<=len(original)
 expected=set()
 for n,s in im.named_sections.items():
  if s[2]&2 and s[5]:
   assert n in ('.pow','.square','.ordinary');expected.add((s[3],s[5]))
   if n!='.pow':assert not any(old[2]&2 and old[5] and max(old[3],s[3])<min(old[3]+old[5],s[3]+s[5]) for old in resident.named_sections.values())
 loads=[p for p in im.segments if p[0]==1 and p[4]]
 assert {(p[2],p[4]) for p in loads}==expected
 assert all(p[2]==p[3] and p[4]==p[5] for p in loads)
 with (W/(label+'.dis')).open('w') as f:subprocess.run([str(cc/'arm-none-eabi-objdump'),'-d',str(W/(label+'.elf'))],stdout=f,check=True)
 meta[label]=dict(source_sha256=sha(W/(label+'.S')),object_sha256=sha(W/(label+'.o')),ELF_sha256=sha(W/(label+'.elf')),body_sha256=hashlib.sha256(code).hexdigest(),body_bytes=len(code),
 allocated_sections={n:s[5] for n,s in im.named_sections.items() if s[2]&2 and s[5]})
old_square=ElfImage(ROOT/'.build/m0-pow-square-exact-20261024/candidate.elf')
new_square=ElfImage(W/'candidate.elf')
assert old_square.bytes_at(old_square.named_sections['.square'])==new_square.bytes_at(new_square.named_sections['.square'])
out=dict(status='BUILT_PRIVATE_POW_EXACT_SQUARE_WITH_UNCHANGED_TAIL_BODY_ORDINARY_DISPATCH',images=meta,commands=commands,
 source_alias_CPP_sha256=sha(W/'candidate/native_eabi_m0.cpp'),parent_CPP_sha256=sha(W/'control/native_eabi_m0.cpp'),
 square_source_sha256=sha(W/'square.S'),ordinary_source_sha256=sha(W/'ordinary.cpp'),ordinary_object_sha256=sha(W/'ordinary.o'),
 all_existing_CPP_allocated_bytes_identical_parent=True,new_CPP_section='.m0_pow_dispatch_ordinary',
 standalone_and_full_CPP_ordinary_emitted_bytes_identical=True,storage_free_alias_targets=aliases,
 exact_square_bytes_identical_qualified_numeric_trial=True,control_body_byte_exact_frozen=True,candidate_fits_old_body=True,
 entry_address=hex(a),hardware_accessed=False,canonical_or_Git_changes=False)
(W/'build.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps({k:v for k,v in out.items() if k!='commands'},indent=2))

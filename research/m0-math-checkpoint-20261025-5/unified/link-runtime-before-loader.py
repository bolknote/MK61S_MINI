"""Link one source-built math ELF, with actual SDK memory initialization."""
from pathlib import Path
import hashlib,json,shlex,subprocess,sys
sys.dont_write_bytecode=True
W=Path(__file__).resolve().parent;ROOT=W.parents[1];BASE=ROOT/'.build/m0-asin-scaled-bound-v164-20261023';CODE=W/'source/code'
assert not(W/'link-result.json').exists()
sys.path.insert(0,str(ROOT/'tests'));from check_stm32_vectors import ElfImage
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
runtime=json.loads((W/'runtime-composition.json').read_bytes());entries=json.loads((BASE/'build/compile_commands.json').read_bytes())
commands=[];support={}
for p in (BASE/'source/code').glob('mem*.inc'):
 q=CODE/p.name;q.write_bytes(p.read_bytes())
for suffix,name in [('/ports/picocalc/memory.c','native_math_memory.c'),('/ports/picocalc/memory_fill.S','native_math_memory_fill.S'),('/pico_bootrom/bootrom.c','native_math_bootrom.c')]:
 entry=next(e for e in entries if e['file'].endswith(suffix));src=Path(entry['file']);q=CODE/name;q.write_bytes(src.read_bytes())
 c=shlex.split(entry['command']);c[c.index(entry['file'])]=str(q);out=W/('RP-unified-'+name+'.o');c[c.index('-o')+1]=str(out)
 subprocess.run(c,cwd=W,check=True);commands.append(c);support[name]=dict(source=str(src.relative_to(ROOT)),source_sha256=sha(src),output=str(out),output_sha256=sha(out))
tc=Path(commands[0][0]).parent
# Retain the previous exact loop as a source-built timing control.
zero=ROOT/'.build/m0-pow-reciprocal-zero-20261025'
(CODE/'control-inline-seed.inc').write_bytes((zero/'inline-seed.inc').read_bytes())
control=W/'timing-control';control.mkdir(exist_ok=True)
sw=CODE/'native_eabi_m0_reciprocal1_sw.S';text=sw.read_text();needle='#include "candidate-inline-seed.inc"';assert text.count(needle)==1
q=control/sw.name;q.write_text(text.replace(needle,'#include "control-inline-seed.inc"'))
recorded=next(c for c in runtime['commands']if'-c'in c and Path(c[c.index('-c')+1]).name==sw.name)
c=list(recorded);c[c.index('-c')+1]=str(q);control_obj=W/'RP-zero-control-sw.o';c[c.index('-o')+1]=str(control_obj);c.insert(1,'-I'+str(CODE))
subprocess.run(c,cwd=W,check=True);commands.append(c)
objects=[Path(p)for p in runtime['runtime_objects']]+[Path(v['output'])for v in support.values()]
roots=set();definitions={}
for obj in map(Path,runtime['runtime_objects']):
 for line in subprocess.check_output([str(tc/'arm-none-eabi-nm'),'-g','--defined-only',str(obj)],text=True).splitlines():
  words=line.split()
  if len(words)<3:continue
  name,kind=words[-1],words[-2];definitions[name]=kind
  if name.startswith(('__aeabi_','mk61_m0_','_ZN12compact_math'))and kind.upper()in ['T','W']:roots.add(name)
roots.add('__aeabi_mem_init')
wrappers=['memcpy','memset','memmove','memcmp','__aeabi_memmove','__aeabi_memmove4','__aeabi_memmove8','__aeabi_memcpy','__aeabi_memcpy4','__aeabi_memcpy8','__aeabi_memset','__aeabi_memset4','__aeabi_memset8']
script='EXTERN('+ ' '.join(sorted(roots))+')\n'+'''MEMORY {
 FLASH(rx) : ORIGIN = 0x10010000, LENGTH = 1984K
 RAM(rwx) : ORIGIN = 0x20000000, LENGTH = 224K
 HOT(rwx) : ORIGIN = 0x20038000, LENGTH = 4K
}
PHDRS { flash PT_LOAD FLAGS(5); hot PT_LOAD FLAGS(5); ram PT_LOAD FLAGS(6); }
SECTIONS {
 .sqrt_group : { *(.m0_sqrt_special) *(.m0_sqrt64_fixed.mk61_m0_sqrt) *(.m0_sqrt64_fixed.*) } > FLASH :flash
 .pow_log_group : { *(.m0_pow_log_selector) *(.m0_pow_extension) } > FLASH :flash
 .pow_dispatch_group : { *(.m0_pow_dispatch_extension) *(.m0_pow_extension_data) *(.m0_pow_argument_extension) } > FLASH :flash
 .text : { *(.text*) *(.m0_*) *(.time_critical*) } > FLASH :flash
 .rodata : { *(.rodata*) *(.data.rel.ro*) } > FLASH :flash
 .scratch_y : ALIGN(4) { __scratch_y_start__ = .; *(.scratch_y*) . = ALIGN(4); __scratch_y_end__ = .; } > HOT AT>FLASH :hot
 __scratch_y_source__ = LOADADDR(.scratch_y);
 .data : ALIGN(4) { __data_start__ = .; *(.data*) . = ALIGN(4); __data_end__ = .; } > RAM AT>FLASH :ram
 __data_source__ = LOADADDR(.data);
 .bss (NOLOAD) : ALIGN(4) { __bss_start__ = .; *(.bss*) *(COMMON) . = ALIGN(4); __bss_end__ = .; } > RAM :ram
 __StackBottom = 0x20039000; __StackTop = 0x20041000;
 /DISCARD/ : { *(.ARM.exidx*) *(.ARM.extab*) *(.comment) *(.note*) *(.ARM.attributes) *(.preinit_array*) *(.init_array*) }
}
ASSERT(SIZEOF(.scratch_y) <= 4080, "Math scratch bank exceeds 4080 bytes")
ASSERT(__scratch_y_end__ <= __StackBottom, "Math code overlaps stack")
ASSERT(__bss_end__ <= 0x20038000, "Math data overlaps scratch bank")
'''
(W/'unified.ld').write_text(script)
results={}
for label in ['candidate','zero-control']:
 objs=[control_obj if label=='zero-control'and p.name=='RP-unified-native_eabi_m0_reciprocal1_sw.S.o'else p for p in objects]
 output=W/(label+'.elf');cmd=[str(tc/'arm-none-eabi-ld'),'--gc-sections','--fatal-warnings','-z','noexecstack','-e','mk61_m0_pow_fast','-T',str(W/'unified.ld'),*[('--wrap='+name)for name in wrappers],*map(str,objs),'-Map='+str(W/(label+'.map')),'-o',str(output)]
 subprocess.run(cmd,cwd=W,check=True);commands.append(cmd)
 assert not subprocess.check_output([str(tc/'arm-none-eabi-nm'),'-u',str(output)],text=True)
 e=ElfImage(output);sections={name:dict(address=s[3],bytes=s[5],flags=s[2],type=s[1])for name,s in e.named_sections.items()if s[2]&2 and s[5]}
 with(W/(label+'.dis')).open('w')as stream:subprocess.run([str(tc/'arm-none-eabi-objdump'),'-d',str(output)],stdout=stream,check=True)
 results[label]=dict(ELF_sha256=sha(output),sections=sections,public_function_roots=len(roots),all_undefined_symbols_resolved=True,actual_source_objects=len(objs),old_firmware_address_bindings=False,
   scratch_y_bytes=e.named_sections['.scratch_y'][5],scratch_y_address=e.named_sections['.scratch_y'][3],memory_initializer=e.symbols['__aeabi_mem_init'])
result=dict(status='SOURCE_LINKED_MATH_ELFS_NOT_RUNTIME_QUALIFIED',images=results,commands=commands,support_sources=support,roots=sorted(roots),
 zero_control_is_previous_exact_seed_loop=True,no_libgcc_or_Qfplib_object_linked=True,ROM_memset_uses_real_SDK_lookup=True,
 actual_linked_R12_guard_passed=False,loader_layout_guard_passed=False,bootable_device_firmware=False,
 actual_ARM_or_MPFR_calls=0,canonical_M4_Git_device_USB_Flash_changed=False,integration_GO=False,goal_complete=False)
(W/'link-result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({k:v for k,v in result.items()if k not in ['commands','support_sources','roots']},indent=2))

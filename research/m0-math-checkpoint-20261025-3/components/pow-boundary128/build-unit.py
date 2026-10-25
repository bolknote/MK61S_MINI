"""Bare boundary images plus exact old compare/multiply and accepted square code."""
from pathlib import Path
import hashlib,json,subprocess,sys
sys.dont_write_bytecode=True
W=Path(__file__).resolve().parent;ROOT=W.parents[1]
P=ROOT/'.build/m0-asin-scaled-bound-v164-20261023';BASE=ROOT/'.build/m0-pow-square128-r2-20261025'
sys.path.insert(0,str(ROOT/'tests'));from check_stm32_vectors import ElfImage
source=(BASE/'candidate/native_eabi_m0_pow_root_prefix.inc').read_text()
names={'multiply':'pow_integer128_multiply','compare':'_ZL15root128_compareRK13PowInteger128S1_'}
assembly='.syntax unified\n.cpu cortex-m0plus\n.thumb\n'
for section,name in names.items():
 begin=source.index('\t.type\t'+name);end=source.index('@ -- End function',begin)
 assembly+='\n.section .unit_'+section+',"ax",%progbits\n.p2align 2\n.global '+name+'\n'+source[begin:end]
(W/'unit-helpers.S').write_text(assembly)
tc=Path('/Users/bolk/Library/Arduino15/packages/STMicroelectronics/tools/xpack-arm-none-eabi-gcc/14.2.1-1.1/bin')
cmd=[str(tc/'arm-none-eabi-gcc'),'-mcpu=cortex-m0plus','-mthumb','-c',str(W/'unit-helpers.S'),'-o',str(W/'unit-helpers.o')]
subprocess.run(cmd,check=True);commands=[cmd]
script='''pow_integer128_approx_high64 = 0x1014e669;
PHDRS { mul PT_LOAD FLAGS(5); cmp PT_LOAD FLAGS(5); }
SECTIONS { .multiply 0x100f9268 : { KEEP(*(.unit_multiply)) } :mul
.compare 0x1014f720 : { KEEP(*(.unit_compare)) } :cmp
/DISCARD/ : { *(.ARM.exidx*) *(.ARM.extab*) *(.comment) *(.note*) *(.ARM.attributes) } }
'''
(W/'unit-helpers.ld').write_text(script)
cmd=[str(tc/'arm-none-eabi-ld'),'--gc-sections','-e','pow_integer128_multiply','-T',str(W/'unit-helpers.ld'),str(W/'unit-helpers.o'),'-o',str(W/'unit-helpers.elf')]
subprocess.run(cmd,check=True);commands.append(cmd)
e=ElfImage(W/'unit-helpers.elf');resident=ElfImage(P/'firmware/mk61s-picocalc-pico-h.elf')
for section,name in names.items():
 s=e.named_sections['.'+section];address=resident.symbols[name]&~1;size=resident.sizes[name]
 assert s[3]==address and s[5] in [size,size+2]
 r=next(r for r in resident.named_sections.values()if r[3]<=address and address+size<=r[3]+r[5])
 assert e.bytes_at(s)[:size]==resident.bytes_at(r)[address-r[3]:address-r[3]+size]
 assert not e.bytes_at(s)[size:] or e.bytes_at(s)[size:]==bytes.fromhex('c046')
out=dict(status='BARE_EXACT_OLD_HELPERS_BYTE_IDENTICAL_RESIDENT',commands=commands,
 ELF_sha256=hashlib.sha256((W/'unit-helpers.elf').read_bytes()).hexdigest(),
 helper_function_bytes={section:resident.sizes[name]for section,name in names.items()},
 helper_section_bytes={section:e.named_sections['.'+section][5]for section in names},
 multiply_has_two_unexecuted_GAS_alignment_bytes=True,
 frozen_square_and_helper_image=str((BASE/'unit-candidate.elf').relative_to(ROOT)),hardware_accessed=False)
(W/'unit-build.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps({k:v for k,v in out.items()if k!='commands'},indent=2))

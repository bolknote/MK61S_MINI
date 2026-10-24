"""Bind exact Q77 arithmetic fragments to a bare ARM unit and184B capsule."""
from pathlib import Path
import hashlib
import json
import struct
import subprocess
import sys

sys.dont_write_bytecode=True
W=Path(__file__).resolve().parent
ROOT=W.parents[1]
P=ROOT/'.build/m0-asin-scaled-bound-v164-20261023'
CC=Path('/Users/bolk/Library/Arduino15/packages/STMicroelectronics/tools/xpack-arm-none-eabi-gcc/14.2.1-1.1/bin')
sys.path.insert(0,str(ROOT/'tests'))
from check_stm32_vectors import ElfImage
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
header=(W/'native_eabi_m0_log70.inc').read_text();cpp=(W/'native_eabi_m0.cpp').read_text()
a=cpp.index('__attribute__((always_inline)) inline U wide32(');z=cpp.index('struct Product',a)
wide=cpp[a:z]
a=header.index('__attribute__((always_inline)) inline U ln_near_argument77(');z=header.index('__attribute__((always_inline)) inline double ln_near_round_pack77(',a)
helpers=header[a:z]
near=header[header.index('static double ln_near_interval77('):]
def fragment(start,end):return near[near.index(start):near.index(end)]
square=fragment('const uint32_t t=uint32_t(h>>32);','const uint32_t zc=')
cube=fragment('const uint32_t zc=','const U third=')
fourth=fragment('const uint32_t zr=','const uint32_t fifth=')
fifth=fragment('const uint32_t fifth=','const uint32_t fifth_term=')
image=ElfImage(W/'candidate.elf');name=next(n for n in image.symbols if 'log_near_table' in n)
a=image.symbols[name];section=next(s for s in image.named_sections.values() if s[3]<=a<s[3]+s[5]);data=image.bytes_at(section);offset=a-section[3]
recip=[struct.unpack_from('<Q',data,offset+16*i)[0] for i in range(256)]
fixture='static constexpr U reciprocals[256]={\n'+''.join(' UINT64_C('+str(v)+'),\n' for v in recip)+'};\n'
unit='#include <stdint.h>\nusing U=uint64_t;\nextern "C" U mk61_m0_log_product54(U,U);\n'+wide+helpers+fixture+'''
extern "C" U audit_h(U delta,U denominator) {
 int32_t residue;const uint32_t den=uint32_t(denominator);
 return ln_near_argument77(delta,reciprocals[den-8065],den,residue);
}
extern "C" U audit_r(U delta,U denominator) {
 int32_t residue;const uint32_t den=uint32_t(denominator);
 ln_near_argument77(delta,reciprocals[den-8065],den,residue);
 return U(int64_t(residue));
}
extern "C" U audit_third(U a) {return ln_near_third77(a);}
extern "C" U audit_square(U h) {
'''+square+'return z;\n}\nextern "C" U audit_cube(U h,U z) {\n const uint32_t t=uint32_t(h>>32);\n'+cube+'return cube;\n}\nextern "C" U audit_fourth(U z) {\n'+fourth+'return fourth;\n}\nextern "C" U audit_fifth(U h,U value) {\n const uint32_t t=uint32_t(h>>32),fourth=uint32_t(value);\n'+fifth+'return fifth;\n}\n'
(W/'core-unit.cpp').write_text(unit)
(W/'core-unit.ld').write_text('mk61_m0_log_product54 = 0x10010001;\nSECTIONS { . = 0x10000000; .text : { *(.text*) *(.rodata*) } /DISCARD/ : { *(.ARM*) *(.comment) *(.note*) } }\n')
commands=[[str(CC/'arm-none-eabi-g++'),'-mcpu=cortex-m0plus','-mthumb','-mfloat-abi=soft','-Os','-std=gnu++17','-fno-exceptions','-fno-rtti','-fno-unwind-tables','-ffunction-sections','-fno-lto','-c',str(W/'core-unit.cpp'),'-o',str(W/'core-unit.o')],
          [str(CC/'arm-none-eabi-ld'),'-T',str(W/'core-unit.ld'),str(W/'core-unit.o'),'-o',str(W/'core-unit.elf')]]
for command in commands:subprocess.run(command,check=True)
assert sha(P/'firmware/mk61s-picocalc-pico-h.elf')=='3b92d7dc30cc860c0b1f17943f1cd626f94112a98adaf165ec4f9cd300364db1'
resident=ElfImage(P/'firmware/mk61s-picocalc-pico-h.elf');address=resident.symbols['mk61_m0_log_product54']&~1;size=resident.sizes['mk61_m0_log_product54'];assert size==184
section=next(s for s in resident.named_sections.values() if s[3]<=address<s[3]+s[5]);capsule=resident.bytes_at(section)[address-section[3]:address-section[3]+size]
(W/'product54-capsule.bin').write_bytes(capsule)
out=dict(status='BUILT_EXACT_Q77_CORE_FRAGMENTS_AND_PRODUCT54_CAPSULE',source_sha256=sha(W/'native_eabi_m0_log70.inc'),candidate_ELF_sha256=sha(W/'candidate.elf'),unit_ELF_sha256=sha(W/'core-unit.elf'),
    exact_fragment_sha256={n:hashlib.sha256(v.encode()).hexdigest() for n,v in dict(wide32=wide,argument_and_third=helpers,square=square,cube=cube,fourth=fourth,fifth=fifth).items()},
    reciprocal_fixture_bytes=2048,fixture_not_a_new_runtime_table=True,product54_capsule_bytes=184,product54_capsule_sha256=sha(W/'product54-capsule.bin'),capsule_runtime_address='10010000',capsule_original_address=f'{address:08X}',commands=commands,full_firmware_or_ROM_loaded=False,hardware_accessed=False)
(W/'core-unit-build.json').write_text(json.dumps(out,indent=2)+'\n')
print(json.dumps({k:v for k,v in out.items() if k!='commands'},indent=2))

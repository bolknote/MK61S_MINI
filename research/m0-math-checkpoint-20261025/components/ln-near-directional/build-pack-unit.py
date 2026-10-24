"""Compile the exact inline packer as a two-register-pair bare ARM unit."""
from pathlib import Path
import hashlib
import json
import subprocess

W = Path(__file__).resolve().parent
CC = Path('/Users/bolk/Library/Arduino15/packages/STMicroelectronics/tools/xpack-arm-none-eabi-gcc/14.2.1-1.1/bin')
header = (W / 'native_eabi_m0_log70.inc').read_text()
cpp = (W / 'native_eabi_m0.cpp').read_text()
helper_start = cpp.index('MK61_M0_TRIG_CACHE(clz32) unsigned clz32(')
helper_end = cpp.index('// Four 16x16 products', helper_start)
helpers = cpp[helper_start:helper_end].replace('MK61_M0_TRIG_CACHE(clz32)', 'static').replace('MK61_M0_TRIG_CACHE(clz64)', 'static')
start = header.index('__attribute__((always_inline)) inline double ln_near_round_pack(')
end = header.index('\n#endif', start)
fragment = header[start:end]
unit = '''#include <stdint.h>
using U=uint64_t;
''' + helpers + '''
static double real(U x) {union {U u;double d;} q={x};return q.d;}
static U bits(double x) {union {double d;U u;} q={x};return q.u;}
static double ln_refine(double) {return real(UINT64_C(0x7FF800000000019A));}
''' + fragment + '''
extern "C" U audit_near_pack(U low,U configuration) {
 const uint32_t meta=uint32_t(configuration);
 return bits(ln_near_round_pack(low,(meta>>9)&1U,U((meta>>8)&1U)<<63,
   int32_t(meta&63U)-16,int32_t(configuration>>32),8065U+((meta>>10)&255U),
   (meta>>6)&1U,(meta>>7)&1U,0.));
}
'''
(W / 'pack-unit.cpp').write_text(unit)
(W / 'pack-unit.ld').write_text('SECTIONS { . = 0x10000000; .text : { *(.text*) *(.rodata*) } /DISCARD/ : { *(.ARM*) *(.comment) *(.note*) } }\n')
commands = [[str(CC / 'arm-none-eabi-g++'), '-mcpu=cortex-m0plus', '-mthumb', '-mfloat-abi=soft',
             '-Os', '-std=gnu++17', '-fno-exceptions', '-fno-rtti', '-fno-unwind-tables',
             '-ffunction-sections', '-fno-lto', '-c', str(W / 'pack-unit.cpp'), '-o', str(W / 'pack-unit.o')],
            [str(CC / 'arm-none-eabi-ld'), '-T', str(W / 'pack-unit.ld'), str(W / 'pack-unit.o'), '-o', str(W / 'pack-unit.elf')]]
for command in commands:
    subprocess.run(command, check=True)
out = dict(status='BUILT_EXACT_INLINE_NEAR_LN_PACK_UNIT',
           source_sha256=hashlib.sha256(header.encode()).hexdigest(),
           exact_fragment_sha256=hashlib.sha256(fragment.encode()).hexdigest(),
           unit_ELF_sha256=hashlib.sha256((W / 'pack-unit.elf').read_bytes()).hexdigest(),
           commands=commands, decline_bits='7FF800000000019A', hardware_accessed=False)
(W / 'pack-unit-build.json').write_text(json.dumps(out, indent=2) + '\n')
print(json.dumps({k:v for k,v in out.items() if k!='commands'}, indent=2))

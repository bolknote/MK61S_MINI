"""Compile exact old/new main pack source as bare two-register-pair units."""
from pathlib import Path
import hashlib
import json
import subprocess

W=Path(__file__).resolve().parent
CC=Path('/Users/bolk/Library/Arduino15/packages/STMicroelectronics/tools/xpack-arm-none-eabi-gcc/14.2.1-1.1/bin')
header=(W/'native_eabi_m0_log70.inc').read_text();cpp=(W/'native_eabi_m0.cpp').read_text()
a=cpp.index('MK61_M0_TRIG_CACHE(clz32) unsigned clz32(');z=cpp.index('// Four 16x16 products',a)
helpers=cpp[a:z].replace('MK61_M0_TRIG_CACHE(clz32)','static').replace('MK61_M0_TRIG_CACHE(clz64)','static')
def function(name):
    a=header.index('__attribute__((always_inline)) inline double '+name+'(')
    p=header.index('{',a);depth=0
    for z in range(p,len(header)):
        if header[z]=='{':depth+=1
        if header[z]=='}':
            depth-=1
            if not depth:return header[a:z+1]
    raise AssertionError(name)
exact,raw=function('ln_pack70'),function('ln_main_pack70')
unit='''#include <stdint.h>
#define MK61_M0_RP2040_EABI 1
using U=uint64_t;
enum : uint32_t {ln_main_radius=8U};
struct D {static constexpr U Fraction=(U(1)<<52)-1;};
'''+helpers+'''
static double real(U x) {union {U u;double d;} q={x};return q.d;}
static U bits(double x) {union {double d;U u;} q={x};return q.u;}
static double ln_refine(double) {return real(UINT64_C(0x7FF8000000000282));}
'''+exact+'\n'+raw+'''
extern "C" U audit_exact(U low,U config) {
 const uint32_t c=uint32_t(config),n=(c>>16)&1023U;
 return bits(ln_pack70(low,c&65535U,U((c>>26)&1U)<<63,8U+(n+1U)/2,0.));
}
extern "C" U audit_raw(U low,U config) {
 const uint32_t c=uint32_t(config),n=(c>>16)&1023U;
 return bits(ln_main_pack70(low,c&65535U,U((c>>26)&1U)<<63,(n+1U)/2,0,0.));
}
'''
(W/'pack-unit.cpp').write_text(unit)
(W/'pack-unit.ld').write_text('SECTIONS { . = 0x10000000; .text : { *(.text*) *(.rodata*) } /DISCARD/ : { *(.ARM*) *(.comment) *(.note*) } }\n')
commands=[[str(CC/'arm-none-eabi-g++'),'-mcpu=cortex-m0plus','-mthumb','-mfloat-abi=soft','-Os','-std=gnu++17','-fno-exceptions','-fno-rtti','-fno-unwind-tables','-ffunction-sections','-fno-lto','-c',str(W/'pack-unit.cpp'),'-o',str(W/'pack-unit.o')],
          [str(CC/'arm-none-eabi-ld'),'-T',str(W/'pack-unit.ld'),str(W/'pack-unit.o'),'-o',str(W/'pack-unit.elf')]]
for command in commands:subprocess.run(command,check=True)
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
out=dict(status='BUILT_EXACT_MAIN_LN_LN2_UPPER_GATE_PACK_UNITS',source_sha256=sha(W/'native_eabi_m0_log70.inc'),exact_fragment_sha256=hashlib.sha256(exact.encode()).hexdigest(),raw_fragment_sha256=hashlib.sha256(raw.encode()).hexdigest(),unit_ELF_sha256=sha(W/'pack-unit.elf'),commands=commands,decline_bits='7FF8000000000282',hardware_accessed=False)
(W/'pack-unit-build.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps({k:v for k,v in out.items() if k!='commands'},indent=2))

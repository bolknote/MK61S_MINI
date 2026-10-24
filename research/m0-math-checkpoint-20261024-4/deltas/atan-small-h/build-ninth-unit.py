"""Expose the exact inline ninth source in a standalone diagnostic wrapper."""
from pathlib import Path
import hashlib,json,subprocess
W=Path(__file__).resolve().parent
CC=Path('/Users/bolk/Library/Arduino15/packages/STMicroelectronics/tools/xpack-arm-none-eabi-gcc/14.2.1-1.1/bin')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
header=(W/'native_eabi_m0_atan_fast.inc').read_text()
begin=header.index('struct AtanTailCorrection ');end=header.index('// Pack the bounded atan domain',begin)
fragment=header[begin:end]
cpp=(W/'native_eabi_m0.cpp').read_text()
start=cpp.index('__attribute__((always_inline)) inline U wide32(')
wide=cpp[start:cpp.index('struct Product',start)]
parents=W.parents[1]/'.build/m0-asin-scaled-bound-v164-20261023/source/code'
kernels=(parents/'native_eabi_m0_kernels.inc').read_text()
start=kernels.index('__attribute__((always_inline)) inline U math62_third(')
third=kernels[start:kernels.index('__attribute__((always_inline)) inline U math62_scale32(',start)]
source='#include <stdint.h>\nusing U=uint64_t;\n'+wide+third+fragment+'''
extern "C" uint64_t check_ninth(U h,int32_t r5) {
  const AtanTailCorrection q=atan_fast_ninth(h,r5);
  return (uint64_t(uint32_t(q.remainder))<<32)|uint32_t(q.delta);
}
extern "C" uint64_t check_third(U a) {return math62_third(a);}
'''
(W/'ninth-unit.cpp').write_text(source)
(W/'ninth-unit.ld').write_text('SECTIONS { . = 0x101c0000; .text : { *(.text*) } /DISCARD/ : { *(.ARM.exidx*) *(.ARM.extab*) *(.comment) *(.ARM.attributes) } }\n')
commands=[
 [str(CC/'arm-none-eabi-g++'),'-mcpu=cortex-m0plus','-mthumb','-mfloat-abi=soft','-Os','-std=gnu++17','-fno-exceptions','-fno-rtti','-fno-unwind-tables','-ffunction-sections','-fno-lto','-c',str(W/'ninth-unit.cpp'),'-o',str(W/'ninth-unit.o')],
 [str(CC/'arm-none-eabi-ld'),'-T',str(W/'ninth-unit.ld'),str(W/'ninth-unit.o'),'-o',str(W/'ninth-unit.elf')]]
for command in commands:subprocess.run(command,check=True)
assert not subprocess.check_output([str(CC/'arm-none-eabi-nm'),'-u',str(W/'ninth-unit.o')],text=True).strip()
report=dict(status='BUILT_ISOLATED_COPY_OF_ACTUAL_INLINE_SOURCE',public_source_sha256=sha(W/'native_eabi_m0_atan_fast.inc'),
            exact_fragment_sha256=hashlib.sha256(fragment.encode()).hexdigest(),wrapper_ELF_sha256=sha(W/'ninth-unit.elf'),
            exact_third_fragment_sha256=hashlib.sha256(third.encode()).hexdigest(),exact_wide_fragment_sha256=hashlib.sha256(wide.encode()).hexdigest(),
            scope='Wrapper source contains the exact inline source fragment; its register allocation is not the public caller. Public bytes are separately bound/replayed.',
            no_undefined_symbols=True,commands=commands,hardware_accessed=False)
(W/'ninth-unit-build.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({k:v for k,v in report.items() if k!='commands'}))

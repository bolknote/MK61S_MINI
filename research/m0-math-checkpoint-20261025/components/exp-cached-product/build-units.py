"""Compile literal tiny/normal-pack source and the existing ARM product bytes."""
from pathlib import Path
import hashlib
import json
import struct
import subprocess
import sys

sys.dont_write_bytecode=True
W=Path(__file__).resolve().parent
ROOT=W.parents[1]
sys.path.insert(0,str(ROOT/'tests'))
from check_stm32_vectors import ElfImage
build=json.loads((W/'build.json').read_text())
cert=json.loads((W/'certificate.json').read_text())
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
source=(W/'candidate/native_eabi_m0.cpp').read_text()
assert sha(W/'candidate/native_eabi_m0.cpp')==build['source_sha256']==cert['source_sha256']
assert sha(W/'rounded-product.bin')==cert['runtime_product_sha256']
assert sha(W/'parent-rounded-product.bin')==cert['parent_runtime_product_sha256']
def block(start):
    a=source.index('{',start);depth=0
    for z in range(a,len(source)):
        if source[z]=='{':depth+=1
        if source[z]=='}':
            depth-=1
            if not depth:return source[start:z+1]
    raise AssertionError(start)
tiny=block(source.index('__attribute__((always_inline)) inline U exp_tiny_rne('))
entry=source.index('MK61_M0_EXP_CORE __attribute__((optimize("Os"))) MK61_SOFT_PCS double mk61_m0_exp(')
normal=block(source.index('  if(k>=-1022 && k<=1023) {',entry))
im=ElfImage(W/'candidate.elf')
n=next(n for n in im.symbols if 'refine_exp_table' in n and im.sizes.get(n)==6144)
a=im.symbols[n];s=next(s for s in im.named_sections.values() if s[3]<=a<s[3]+s[5])
table=im.bytes_at(s)[a-s[3]:a-s[3]+6144]
assert hashlib.sha256(table).hexdigest()==cert['refined_exp_table_sha256']
rows=struct.unpack('<1536I',table)
array='static constexpr uint32_t refine_exp_table[512][3]={\n'+''.join(
    ' {'+','.join(str(v)+'U' for v in rows[i:i+3])+'},\n' for i in range(0,len(rows),3))+'};\n'
unit='''#include <stdint.h>
#define MK61_M0_RP2040_EABI 1
using U=uint64_t;
struct D {static constexpr U Sign=U(1)<<63,Infinity=UINT64_C(0x7ff0000000000000),Quiet=U(1)<<51;};
static double real(U x) {union {U u;double d;} v={x};return v.d;}
static U bits(double x) {union {double d;U u;} v={x};return v.u;}
static double exp_refine(double,uint32_t) {return real(UINT64_C(0x7FF80000000005E0));}
'''+array+tiny+'''
extern "C" U audit_tiny(U a,U) {return exp_tiny_rne(a);}
__attribute__((always_inline)) static inline double pack(U q,U config) {
 const auto p=reinterpret_cast<const volatile uint32_t*>(UINT32_C(0x20000000));
 const int k=int32_t(config);const unsigned error=uint32_t(config>>32)?6U:4U;
 const uint32_t n=p[0];const U a=U(p[1])<<32;const double x=real(a);
'''+normal+'''
 return real(UINT64_C(0x7FF80000000005E0));
}
extern "C" U audit_pack(U q,U config) {return bits(pack(q,config));}
'''
(W/'unit.cpp').write_text(unit)
(W/'product-unit.S').write_text('''.syntax unified
.cpu cortex-m0plus
.thumb
.section .product,"ax",%progbits
.balign 2
.global audit_product
.type audit_product,%function
.thumb_func
audit_product:
.incbin "'''+str(W/'rounded-product.bin')+'''"
.size audit_product,.-audit_product
 .section .parent_product,"ax",%progbits
 .balign 2
 .global audit_parent_product
 .type audit_parent_product,%function
 .thumb_func
 audit_parent_product:
 .incbin "'''+str(W/'parent-rounded-product.bin')+'''"
 .size audit_parent_product,.-audit_parent_product
''')
(W/'unit.ld').write_text('SECTIONS { . = 0x10000000; .text : { *(.text*) *(.rodata*) } .product 0x10010000 : { *(.product) } .parent_product 0x10020000 : { *(.parent_product) } /DISCARD/ : { *(.ARM*) *(.comment) *(.note*) } }\n')
cc=Path(build['commands'][0][0]).parent
commands=[[str(cc/'arm-none-eabi-g++'),'-mcpu=cortex-m0plus','-mthumb','-mfloat-abi=soft','-Os','-std=gnu++17','-fno-exceptions','-fno-rtti','-fno-unwind-tables','-ffunction-sections','-fno-lto','-c',str(W/'unit.cpp'),'-o',str(W/'unit.o')],
    [str(cc/'arm-none-eabi-gcc'),'-mcpu=cortex-m0plus','-mthumb','-c',str(W/'product-unit.S'),'-o',str(W/'product-unit.o')],
    [str(cc/'arm-none-eabi-ld'),'-T',str(W/'unit.ld'),str(W/'unit.o'),str(W/'product-unit.o'),'-o',str(W/'unit.elf')]]
for command in commands:subprocess.run(command,check=True)
assert not subprocess.check_output([str(cc/'arm-none-eabi-nm'),'-u',str(W/'unit.elf')],text=True)
out=dict(status='BUILT_EXACT_EXP_TINY_PACK_AND_PRODUCT_BARE_UNITS',source_sha256=build['source_sha256'],
    candidate_ELF_sha256=build['candidate_ELF_sha256'],unit_ELF_sha256=sha(W/'unit.elf'),
    tiny_fragment_sha256=hashlib.sha256(tiny.encode()).hexdigest(),normal_pack_fragment_sha256=hashlib.sha256(normal.encode()).hexdigest(),
    copied_existing_refine_table_sha256=hashlib.sha256(table).hexdigest(),copied_existing_product_sha256=sha(W/'rounded-product.bin'),
    copied_parent_product_sha256=sha(W/'parent-rounded-product.bin'),
    commands=commands,decline_bits='7FF80000000005E0',input_fixture_bytes=8,hardware_accessed=False)
(W/'unit-build.json').write_text(json.dumps(out,indent=2)+'\n')
print(json.dumps({k:v for k,v in out.items() if k!='commands'},indent=2))

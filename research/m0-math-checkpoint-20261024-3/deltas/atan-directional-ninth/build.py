"""Compile exact public C++ sources into local atan-only execution fixtures."""
from pathlib import Path
import hashlib,json,subprocess,sys
sys.dont_write_bytecode=True
W=Path(__file__).resolve().parent;ROOT=W.parents[1]
BASE=ROOT/'.build/m0-atan-residual-geometry-20261024'
P=ROOT/'.build/m0-asin-scaled-bound-v164-20261023/source/code'
CC=Path('/Users/bolk/Library/Arduino15/packages/STMicroelectronics/tools/xpack-arm-none-eabi-gcc/14.2.1-1.1/bin')
sys.path.insert(0,str(ROOT/'tests'))
from check_stm32_vectors import ElfImage
ELF=ROOT/'.build/m0-asin-scaled-bound-v164-20261023/firmware/mk61s-picocalc-pico-h.elf'
resident=ElfImage(ELF);commands=[]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
for label,source in [('control',BASE/'native_eabi_m0.cpp'),('candidate',W/'native_eabi_m0.cpp')]:
 cmd=[str(CC/'arm-none-eabi-g++'),'-mcpu=cortex-m0plus','-mthumb','-mfloat-abi=soft','-Os','-std=gnu++17','-fno-exceptions','-fno-rtti','-fno-unwind-tables','-fno-use-cxa-atexit','-ffunction-sections','-fdata-sections','-fno-lto','-DMK61_USE_M0_EABI=1','-DMK61_M0_RP2040_EABI=1','-I',str(P),'-c',str(source),'-o',str(W/(label+'-full.o'))]
 subprocess.run(cmd,check=True);commands.append(cmd)
 undefined=[line.split()[-1] for line in subprocess.check_output([str(CC/'arm-none-eabi-nm'),'-u',str(W/(label+'-full.o'))],text=True).splitlines()]
 bindings={n:resident.symbols[n] for n in undefined if n in resident.symbols}
 script='\n'.join(n+' = '+hex(v)+';' for n,v in sorted(bindings.items()))+'\n'
 script+='''SECTIONS {
 . = 0x10185000;
 .text : { *(.text*) *(.m0*) }
 .rodata : { *(.rodata*) }
 /DISCARD/ : { *(.ARM.exidx*) *(.ARM.extab*) *(.comment) *(.ARM.attributes) *(.note*) }
}
'''
 (W/(label+'.ld')).write_text(script)
 cmd=[str(CC/'arm-none-eabi-ld'),'--gc-sections','-e','mk61_m0_atan','-T',str(W/(label+'.ld')),str(W/(label+'-full.o')),'-o',str(W/(label+'.elf'))]
 subprocess.run(cmd,check=True);commands.append(cmd)
 with (W/(label+'.dis')).open('w') as f:subprocess.run([str(CC/'arm-none-eabi-objdump'),'-dr',str(W/(label+'.elf'))],stdout=f,check=True)
 report=dict(status='BUILT_PRIVATE_ATAN_COMPONENT_NOT_FIRMWARE',label=label,source_sha256=sha(source),source_include_sha256=sha((BASE if label=='control' else W)/'native_eabi_m0_atan_fast.inc'),ELF_sha256=sha(W/(label+'.elf')),resident_ELF_sha256=sha(ELF),resident_bindings=bindings,commands=commands,hardware_accessed=False,canonical_or_frozen_changed=False,goal_complete=False)
 (W/(label+'-build.json')).write_text(json.dumps(report,indent=2)+'\n')
 if label=='control':
  assert sha(W/'control-full.o')==sha(BASE/'candidate-full.o')
  assert sha(W/'control.elf')==sha(BASE/'candidate.elf')
 print(json.dumps({k:v for k,v in report.items() if k not in ('commands','resident_bindings')}))

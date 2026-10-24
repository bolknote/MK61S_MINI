"""Build only the isolated polynomial-tail experiment, without firmware."""
from pathlib import Path
import hashlib,json,subprocess
W=Path(__file__).resolve().parent
CC=Path('/Users/bolk/Library/Arduino15/packages/STMicroelectronics/tools/xpack-arm-none-eabi-gcc/14.2.1-1.1/bin')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
(W/'poly.ld').write_text('SECTIONS { . = 0x10190000; .text : { *(.text*) } /DISCARD/ : { *(.ARM.exidx*) *(.ARM.extab*) *(.comment) *(.ARM.attributes) } }\n')
commands=[
 [str(CC/'arm-none-eabi-g++'),'-mcpu=cortex-m0plus','-mthumb','-mfloat-abi=soft','-Os','-fno-exceptions','-fno-rtti','-fno-unwind-tables','-fno-lto','-ffunction-sections','-c',str(W/'poly-correction.cpp'),'-o',str(W/'poly.o')],
 [str(CC/'arm-none-eabi-ld'),'-T',str(W/'poly.ld'),str(W/'poly.o'),'-o',str(W/'poly.elf')]]
for command in commands:subprocess.run(command,check=True)
assert not subprocess.check_output([str(CC/'arm-none-eabi-nm'),'-u',str(W/'poly.o')],text=True).strip()
with (W/'poly.dis').open('w') as f:subprocess.run([str(CC/'arm-none-eabi-objdump'),'-dr',str(W/'poly.elf')],stdout=f,check=True)
report=dict(status='BUILT_ISOLATED_POLYNOMIAL_TAIL_NOT_RUNTIME',source_sha256=sha(W/'poly-correction.cpp'),ELF_sha256=sha(W/'poly.elf'),
            no_undefined_symbols=True,commands=commands,hardware_accessed=False,goal_complete=False)
(W/'build.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({k:v for k,v in report.items() if k!='commands'}))

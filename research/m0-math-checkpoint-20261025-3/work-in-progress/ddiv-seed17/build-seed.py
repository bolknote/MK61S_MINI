from pathlib import Path
import hashlib,json,subprocess,sys
sys.dont_write_bytecode=True
W=Path(__file__).resolve().parent;tc=Path('/Users/bolk/Library/Arduino15/packages/STMicroelectronics/tools/xpack-arm-none-eabi-gcc/14.2.1-1.1/bin');commands=[]
cmd=[str(tc/'arm-none-eabi-gcc'),'-mcpu=cortex-m0plus','-mthumb','-DMK61_M0_RP2040_EABI=1','-c',str(W/'seed17.S'),'-o',str(W/'seed17.o')]
subprocess.run(cmd,check=True);commands.append(cmd)
(W/'seed17.ld').write_text('PHDRS { code PT_LOAD FLAGS(5); }\nSECTIONS { .seed 0x101e1000 : { KEEP(*(.m0_ddiv_seed17)) } :code\n /DISCARD/ : { *(.ARM.exidx*) *(.ARM.extab*) *(.comment) *(.note*) *(.ARM.attributes) } }\n')
cmd=[str(tc/'arm-none-eabi-ld'),'--gc-sections','-e','mk61_m0_ddiv_seed17','-T',str(W/'seed17.ld'),str(W/'seed17.o'),'-o',str(W/'seed17.elf')]
subprocess.run(cmd,check=True);commands.append(cmd)
out=dict(status='SEED17_UNIT_BUILT_NOT_QUALIFIED',ELF_sha256=hashlib.sha256((W/'seed17.elf').read_bytes()).hexdigest(),commands=commands,hardware_accessed=False)
(W/'seed-build.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps({k:v for k,v in out.items()if k!='commands'},indent=2))

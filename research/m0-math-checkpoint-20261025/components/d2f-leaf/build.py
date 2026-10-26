from pathlib import Path
import hashlib,json,subprocess,sys
sys.dont_write_bytecode=True
W=Path(__file__).resolve().parent;ROOT=W.parents[1]
sys.path.insert(0,str(ROOT/'tests'))
from check_stm32_vectors import ElfImage
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
cc=Path('/Users/bolk/Library/Arduino15/packages/STMicroelectronics/tools/xpack-arm-none-eabi-gcc/14.2.1-1.1/bin')
(W/'entry.ld').write_text('''PHDRS { code PT_LOAD FLAGS(5); }
SECTIONS { .d2f 0x10163000 : { *(.text.__aeabi_d2f) } :code
 /DISCARD/ : { *(.ARM*) *(.comment) *(.note*) } }
''')
commands=[[str(cc/'arm-none-eabi-gcc'),'-mcpu=cortex-m0plus','-mthumb','-DMK61_USE_M0_EABI=1','-DMK61_M0_RP2040_EABI=1','-c',str(W/'d2f.S'),'-o',str(W/'d2f.o')],
 [str(cc/'arm-none-eabi-ld'),'--gc-sections','-e','__aeabi_d2f','-T',str(W/'entry.ld'),str(W/'d2f.o'),'-o',str(W/'candidate.elf')]]
for command in commands:subprocess.run(command,cwd=W,check=True)
im=ElfImage(W/'candidate.elf');sections={n:s[5] for n,s in im.named_sections.items() if s[2]&2 and s[5]}
assert set(sections)=={'.d2f'} and im.symbols['__aeabi_d2f']==0x10163001
assert not subprocess.check_output([str(cc/'arm-none-eabi-nm'),'-u',str(W/'candidate.elf')],text=True)
loads=[p for p in im.segments if p[0]==1 and p[4]]
assert len(loads)==1 and loads[0][2]==loads[0][3]==0x10163000 and loads[0][4]==loads[0][5]==sections['.d2f']
with (W/'candidate.dis').open('w') as f:subprocess.run([str(cc/'arm-none-eabi-objdump'),'-d',str(W/'candidate.elf')],stdout=f,check=True)
out={'status':'BUILT_UNQUALIFIED_RP_D2F_LEAF','source_sha256':sha(W/'d2f.S'),'candidate_ELF_sha256':sha(W/'candidate.elf'),'sections':sections,'no_external_calls_RAM_tables_libgcc':True,'commands':commands,'hardware_accessed':False}
(W/'build.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps({k:v for k,v in out.items() if k!='commands'},indent=2))

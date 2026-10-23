"""Build only a private diagnostic dadd/dsub object; original ELF is read only."""
from pathlib import Path
import hashlib,json,subprocess,sys
sys.dont_write_bytecode=True
W=Path(__file__).resolve().parent;ROOT=W.parents[1]
P=ROOT/'.build/m0-asin-scaled-bound-v164-20261023'
CC=Path('/Users/bolk/Library/Arduino15/packages/STMicroelectronics/tools/xpack-arm-none-eabi-gcc/14.2.1-1.1/bin')
sys.path.insert(0,str(ROOT/'tests'))
from check_stm32_vectors import ElfImage
ELF=P/'firmware/mk61s-picocalc-pico-h.elf'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
assert sha(ELF)=='3b92d7dc30cc860c0b1f17943f1cd626f94112a98adaf165ec4f9cd300364db1'
e=ElfImage(ELF)
original=(P/'source/code/native_eabi_m0_rp2040.S').read_text()
prefix=original.split('mk61_m0_dadd_end:',1)[0]
start=prefix.index('.Lda_mixed_general:')
assert prefix.count('regular_func __aeabi_dadd')==1
prefix=prefix[:start]+(W/'mixed-general.S.txt').read_text()+'\n.ltorg\n'
prefix=prefix.replace('__aeabi_dadd','candidate_dadd').replace('__aeabi_dsub','candidate_dsub')
prefix=prefix.replace('.text.mk61_rp2040_arithmetic','.text.m0_add_trial')
(W/'candidate.S').write_text(prefix+'\n#endif\n')
(W/'candidate.ld').write_text('SECTIONS { . = 0x10180000; .text : { *(.text.m0_add_trial) } /DISCARD/ : { *(.ARM.attributes) } }\n')
slow=e.symbols['mk61_m0_dadd_slow']
commands=[
 [str(CC/'arm-none-eabi-gcc'),'-mcpu=cortex-m0plus','-mthumb','-mfloat-abi=soft','-DMK61_USE_M0_EABI=1','-DMK61_M0_RP2040_EABI=1','-c',str(W/'candidate.S'),'-o',str(W/'candidate.o')],
 [str(CC/'arm-none-eabi-ld'),'-T',str(W/'candidate.ld'),'--defsym',f'mk61_m0_dadd_slow={slow}',str(W/'candidate.o'),'-o',str(W/'candidate.elf')],
 [str(CC/'arm-none-eabi-objcopy'),'-O','binary',str(W/'candidate.elf'),str(W/'candidate.bin')]]
for command in commands:subprocess.run(command,check=True)
with (W/'candidate.dis').open('w') as f:subprocess.run([str(CC/'arm-none-eabi-objdump'),'-dr',str(W/'candidate.elf')],stdout=f,check=True)
report={'status':'BUILT_PRIVATE_DIAGNOSTIC_OBJECT_NOT_NEW_FIRMWARE','input_ELF_sha256':sha(ELF),'input_asm_sha256':sha(P/'source/code/native_eabi_m0_rp2040.S'),'candidate_bytes':(W/'candidate.bin').stat().st_size,'fallback_address':hex(slow),'commands':commands,'outputs':{n:sha(W/n) for n in ('candidate.S','candidate.ld','candidate.o','candidate.elf','candidate.bin','candidate.dis')},'canonical_or_frozen_files_changed':False,'USB_accessed':False,'goal_complete':False}
(W/'build.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps({'status':report['status'],'bytes':report['candidate_bytes'],'fallback':hex(slow)}))

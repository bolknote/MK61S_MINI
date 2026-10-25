from pathlib import Path
import hashlib,json,subprocess,sys
sys.dont_write_bytecode=True
W=Path(__file__).resolve().parent;ROOT=W.parents[1]
tc=Path('/Users/bolk/Library/Arduino15/packages/STMicroelectronics/tools/xpack-arm-none-eabi-gcc/14.2.1-1.1/bin')
common=['-Os','-mcpu=cortex-m0plus','-mthumb','-mfloat-abi=soft','-DMK61_M0_RP2040_EABI=1',
        '-ffreestanding','-ffunction-sections','-fdata-sections','-fno-unwind-tables','-fno-asynchronous-unwind-tables','-fno-lto']
commands=[]
for name,exe,extra in [('filter.cpp','arm-none-eabi-g++',['-std=c++17','-fno-exceptions','-fno-rtti']),('kernels.S','arm-none-eabi-gcc',[])]:
 out=W/(Path(name).stem+'.o');cmd=[str(tc/exe),*common,*extra,'-c',str(W/name),'-o',str(out)]
 subprocess.run(cmd,check=True);commands.append(cmd)
script='''EXTERN(mk61_m0_bound80_square mk61_m0_bound80_multiply mk61_m0_bound80_compare mk61_m0_bound80_wide32)
PHDRS { text PT_LOAD FLAGS(5); }
SECTIONS { .unit 0x101e0000 : {
  KEEP(*(.m0_pow_bound80_square)) KEEP(*(.m0_pow_bound80_wide32))
  KEEP(*(.m0_pow_bound80_multiply)) KEEP(*(.m0_pow_bound80_compare))
} :text
/DISCARD/ : { *(.ARM.exidx*) *(.ARM.extab*) *(.comment) *(.note*) *(.ARM.attributes) }
}
'''
(W/'unit.ld').write_text(script)
cmd=[str(tc/'arm-none-eabi-ld'),'--gc-sections','-e','mk61_m0_bound80_square','-T',str(W/'unit.ld'),str(W/'kernels.o'),str(W/'filter.o'),'-o',str(W/'unit.elf')]
subprocess.run(cmd,check=True);commands.append(cmd)
with (W/'unit.dis').open('w')as f:subprocess.run([str(tc/'arm-none-eabi-objdump'),'-d',str(W/'unit.elf')],stdout=f,check=True)
sys.path.insert(0,str(ROOT/'tests'));from check_stm32_vectors import ElfImage
e=ElfImage(W/'unit.elf')
out=dict(status='EXPERIMENTAL_BOUND80_UNIT_BUILT_NOT_QUALIFIED',ELF_sha256=hashlib.sha256((W/'unit.elf').read_bytes()).hexdigest(),
 sizes={n:s for n,s in e.sizes.items() if n.startswith('mk61_m0_bound80_')},commands=commands,hardware_accessed=False)
(W/'unit-build.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps({k:v for k,v in out.items()if k!='commands'},indent=2))

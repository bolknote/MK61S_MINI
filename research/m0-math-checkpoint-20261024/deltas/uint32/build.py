"""Private, RP2040-only uint32 conversion candidate; no production link."""
from pathlib import Path
import difflib,hashlib,json,subprocess,sys
sys.dont_write_bytecode=True
W=Path(__file__).resolve().parent;ROOT=W.parents[1]
P=ROOT/'.build/m0-asin-scaled-bound-v164-20261023/source/code'
CC=Path('/Users/bolk/Library/Arduino15/packages/STMicroelectronics/tools/xpack-arm-none-eabi-gcc/14.2.1-1.1/bin')
body=(W/'unsigned32-body.S.txt').read_text()
diagnostic='.syntax unified\n.cpu cortex-m0plus\n.thumb\n.section .text.uint32_trial,"ax",%progbits\n.global candidate_d2uiz\n.type candidate_d2uiz,%function\n.thumb_func\ncandidate_d2uiz:\n'+body+'\n.ltorg\n.size candidate_d2uiz,.-candidate_d2uiz\n'
(W/'candidate.S').write_text(diagnostic)
(W/'candidate.ld').write_text('SECTIONS { . = 0x10181000; .text : { *(.text.uint32_trial) } /DISCARD/ : { *(.ARM.attributes) } }\n')
commands=[
 [str(CC/'arm-none-eabi-gcc'),'-mcpu=cortex-m0plus','-mthumb','-mfloat-abi=soft','-c',str(W/'candidate.S'),'-o',str(W/'candidate.o')],
 [str(CC/'arm-none-eabi-ld'),'-T',str(W/'candidate.ld'),str(W/'candidate.o'),'-o',str(W/'candidate.elf')],
 [str(CC/'arm-none-eabi-objcopy'),'-O','binary',str(W/'candidate.elf'),str(W/'candidate.bin')]]
for cmd in commands:subprocess.run(cmd,check=True)
with (W/'candidate.dis').open('w') as f:subprocess.run([str(CC/'arm-none-eabi-objdump'),'-dr',str(W/'candidate.elf')],stdout=f,check=True)

inc=(P/'native_eabi_m0_convert.inc').read_text()
needle='function __aeabi_d2iz\n';assert inc.count(needle)==1
newinc=inc.replace(needle,'#if defined(MK61_M0_RP2040_EABI) && MK61_M0_RP2040_EABI\nfunction __aeabi_d2uiz\n'+body+'\n.ltorg\nend __aeabi_d2uiz\n#endif\n\n'+needle)
cpp=(P/'native_eabi_m0.cpp').read_text()
needle='MK61_SOFT_PCS uint32_t __aeabi_d2uiz(double x) {return D::unsigned32(bits(x));}'
assert cpp.count(needle)==1
newcpp=cpp.replace(needle,'#if !((defined(__arm__) || defined(__thumb__)) && defined(MK61_M0_RP2040_EABI) && MK61_M0_RP2040_EABI)\n'+needle+'\n#endif')
patch=''
for name,old,new in [('native_eabi_m0_convert.inc',inc,newinc),('native_eabi_m0.cpp',cpp,newcpp)]:
    (W/name).write_text(new)
    patch+=''.join(difflib.unified_diff(old.splitlines(True),new.splitlines(True),fromfile='V164/code/'+name,tofile='candidate/code/'+name))
(W/'native_eabi_m0.S').write_bytes((P/'native_eabi_m0.S').read_bytes())
(W/'unsigned32-only.patch').write_text(patch)
report=dict(status='BUILT_PRIVATE_RP2040_UINT32_LEAF_NOT_FIRMWARE',bytes=(W/'candidate.bin').stat().st_size,
            commands=commands,input_sources={n:hashlib.sha256((P/n).read_bytes()).hexdigest() for n in ('native_eabi_m0.cpp','native_eabi_m0_convert.inc','native_eabi_m0.S')},
            files={n:hashlib.sha256((W/n).read_bytes()).hexdigest() for n in ('candidate.S','candidate.elf','candidate.o','candidate.bin','native_eabi_m0.cpp','native_eabi_m0_convert.inc','unsigned32-only.patch')},
            source_mutated=False,canonical_mutated=False,hardware_accessed=False,goal_complete=False)
(W/'build.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps({'status':report['status'],'bytes':report['bytes']}))

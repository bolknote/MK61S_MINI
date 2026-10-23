"""Private sqrt cold partition; normal arithmetic and tables are unchanged."""
from pathlib import Path
import difflib,hashlib,json,subprocess,sys
sys.dont_write_bytecode=True
W=Path(__file__).resolve().parent;ROOT=W.parents[1]
P=ROOT/'.build/m0-asin-scaled-bound-v164-20261023/source/code'
CC=Path('/Users/bolk/Library/Arduino15/packages/STMicroelectronics/tools/xpack-arm-none-eabi-gcc/14.2.1-1.1/bin')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
old=(P/'native_eabi_m0.S').read_text()
begin=old.index(' lsrs r3,r1,#20\n adds r2,r3,#1\n lsrs r2,#11\n',old.index('function mk61_m0_sqrt, .m0_sqrt64_fixed'))
end=old.index('.Lsqrt64_normal:\n',begin)
original=old[begin:end]
generic=original.split('#else\n',1)[1].split('#endif\n',1)[0]
newguard=''' lsrs r3,r1,#20
 adds r2,r3,#1
 lsrs r2,#11
#if defined(MK61_M0_RP2040_EABI) && MK61_M0_RP2040_EABI
 bne .Lsqrt64_nonpositive_or_nonfinite
 cmp r3,#0
 bne .Lsqrt64_normal
 // Positive E0 is already known; retain the zero return and skip the
 // cold helper's repeated class test for a nonzero subnormal.
 lsls r2,r1,#1
 orrs r2,r0
 bne mk61_m0_sqrt_subnormal
 bx lr
.Lsqrt64_nonpositive_or_nonfinite:
 // Thumb ORRS and BNE preserve the carry from LSLS: C is input sign.
 lsls r2,r1,#1
 orrs r2,r0
 bne mk61_m0_sqrt_special
 bx lr
#else
 bne .Lsqrt64_slow
 cmp r3,#0
 bne .Lsqrt64_normal
.Lsqrt64_slow:
'''+generic+'''#endif
'''
new=old[:begin]+newguard+old[end:]
(W/'native_eabi_m0.S').write_text(new)
(W/'native_eabi_m0_rp2040.S').write_bytes((P/'native_eabi_m0_rp2040.S').read_bytes())
special=(P/'native_eabi_m0_sqrt_special.S.inc').read_text()
first=special.index(' cmp r3,#0\n')
last=special.index(' // The only positive nonzero inputs',first)
special_new=special[:first]+''' // Public nonzero entry supplies C=input sign. Positive inputs reaching
 // this entry have exponent2047; positive E0 enters the subnormal alias.
 bcs .Lsqrt_special_negative
'''+special[last:]
special_new=special_new.replace(' * R3=R1>>20 from the unchanged public guard, and the input is nonzero and outside\n * the positive-normal domain. A direct B preserves the caller LR/SP.',
''' * R3=R1>>20 and C=input sign from the public cold guard. This entry receives
 * negative nonzero inputs or positive exponent2047. The subnormal alias
 * receives positive E0 nonzero inputs. Direct B preserves caller LR/SP.''')
special_new=special_new.replace('.Lsqrt_special_subnormal:\n','''// Internal public-guard target; same stack/scaling/root code as the parent.
.global mk61_m0_sqrt_subnormal
.hidden mk61_m0_sqrt_subnormal
.type mk61_m0_sqrt_subnormal,%function
.thumb_func
mk61_m0_sqrt_subnormal:
.Lsqrt_special_subnormal:
''')
(W/'native_eabi_m0_sqrt_special.S.inc').write_text(special_new)
patch=''
for name,before,after in [('native_eabi_m0.S',old,new),('native_eabi_m0_sqrt_special.S.inc',special,special_new)]:
 patch+=''.join(difflib.unified_diff(before.splitlines(True),after.splitlines(True),fromfile='V164/code/'+name,tofile='candidate/code/'+name))
(W/'sqrt-cold-only.patch').write_text(patch)
commands=[]
for name,out in [('native_eabi_m0.S','main.o'),('native_eabi_m0_rp2040.S','rp.o')]:
 command=[str(CC/'arm-none-eabi-gcc'),'-mcpu=cortex-m0plus','-mthumb','-mfloat-abi=soft','-DMK61_USE_M0_EABI=1','-DMK61_M0_RP2040_EABI=1','-I',str(P),'-c',str(W/name),'-o',str(W/out)]
 subprocess.run(command,check=True);commands.append(command)
(W/'candidate.ld').write_text('''SECTIONS {
 .sqrt_special 0x1016ba20 : { *(.m0_sqrt_special) }
 .sqrt 0x1016bb00 : { *(.m0_sqrt64_fixed.mk61_m0_sqrt) }
 .conversion 0x10185000 : { *(.text.__aeabi_i2d) }
 /DISCARD/ : { *(*) }
}
''')
command=[str(CC/'arm-none-eabi-ld'),'-T',str(W/'candidate.ld'),str(W/'main.o'),str(W/'rp.o'),'-o',str(W/'candidate.elf')]
subprocess.run(command,check=True);commands.append(command)
with (W/'candidate.dis').open('w') as f:subprocess.run([str(CC/'arm-none-eabi-objdump'),'-dr',str(W/'candidate.elf')],stdout=f,check=True)
report=dict(status='BUILT_PRIVATE_SQRT_COLD_PARTITION_NO_FIRMWARE',source_files={n:sha(W/n) for n in ('native_eabi_m0.S','native_eabi_m0_sqrt_special.S.inc')},candidate_ELF_sha256=sha(W/'candidate.elf'),commands=commands,canonical_or_frozen_changed=False,hardware_accessed=False,goal_complete=False)
(W/'build.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({k:v for k,v in report.items() if k!='commands'}))

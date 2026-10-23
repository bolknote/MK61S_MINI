"""Private dadd/dsub extension to the largest finite exponent; no firmware."""
from pathlib import Path
import difflib,hashlib,json,subprocess,sys
sys.dont_write_bytecode=True
W=Path(__file__).resolve().parent;ROOT=W.parents[1]
P=ROOT/'.build/m0-asin-scaled-bound-v164-20261023'
BASE=ROOT/'.build/m0-mixed-sign-original-goal-20261023'
CC=Path('/Users/bolk/Library/Arduino15/packages/STMicroelectronics/tools/xpack-arm-none-eabi-gcc/14.2.1-1.1/bin')
sys.path.insert(0,str(ROOT/'tests'))
from check_stm32_vectors import ElfImage
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
assert sha(BASE/'result.json')=='5b1fa3434b9bd887115a2e00926ae48ec8d924d382c6926d9f06a15fdf8a83d5'
old=(BASE/'native_eabi_m0_rp2040.S').read_text()
assert old.count('ldr r7, =1990')==1
new=old.replace('ldr r7, =1990','ldr r7, =1991',1)
assert new.count('bhi .Lda_slow')==1
new=new.replace('bhi .Lda_slow','bhs .Lda_top_guard',1)
new=new.replace('// This also rejects Inf/NaN before the significands change.',
'''// The top guard separately accepts exponent2046 with normal inputs.
 // Inf/NaN are rejected before the significands change.''',1)
# A separate top same-sign path leaves ordinary addition unchanged. Its
# original packed exponent addend is always sign:(2045):0. An extra leading
# bit, before or after rounding, therefore means overflow immediately.
start=old.index(' // With equal signs there is no cancellation')
end=old.index('.Lda_mixed_sign:',start)
special=old[start:end].replace('.Lda_same_', '.Lda_top_same_')
special='.Lda_top_same_start:\n'+special
a=special.index('.Lda_top_same_shift:');b=special.index('.Lda_top_same_y:',a)
special=special[:a]+'''.Lda_top_same_shift:
 // R5=1 from the leading-bit test. R12 is sign:(2045):0.
 lsls r5,#21
 mov r1,r12
 orrs r1,r5
 movs r0,#0
 pop {r4-r7,pc}

'''+special[b:]
needle='''.Lda_top_same_pack:
 mov r2,r12'''
assert special.count(needle)==1
special=special.replace(needle,'''.Lda_top_same_pack:
 // This also detects a carry caused only by the final RNE increment.
 lsrs r5,r1,#21
 bne .Lda_top_same_shift
 mov r2,r12''',1)
assert 'add r12' not in special
macro='''.macro da_top_same_y_finish
 adds r0,r2
 adcs r1,r3
 lsrs r5,r1,#21
 bne .Lda_top_same_shift
 lsls r4,#1
 bcc .Lda_top_same_pack
 b .Lda_top_same_increment
.endm

'''
for begin,end in (('.Lda_top_same_y:\n','.Lda_top_same_x_far:\n'),('.Lda_top_same_y_far:\n',None)):
    a=special.index(begin);b=special.index(end,a) if end else len(special)
    block=special[a:b];assert block.count(' b .Lda_top_same_add\n')==1
    special=special[:a]+block.replace(' b .Lda_top_same_add\n',' da_top_same_y_finish\n',1)+special[b:]
slow='''.Lda_slow:
 sub sp, #4
 bl mk61_m0_dadd_slow
 add sp, #4
 pop {r4-r7,pc}'''
assert new.count(slow)==1
new=new.replace(slow,macro+'''.Lda_top_guard:
 // BHS retained the preceding CMP flags. Equality means exponent2046;
 // every larger unsigned value remains a fallback input.
 bne .Lda_slow
 mov r6,r1
 eors r6,r3
 bmi 1f
 b .Lda_top_same_start
1:
 b .Lda_mixed_sign
.Lda_slow:
 // Save the volatile R3 in the previously reserved alignment word.
 // A six-register pop restores the identical24-byte frame in one step.
 push {r3}
 bl mk61_m0_dadd_slow
 pop {r3-r7,pc}''',1)
needle='\n.ltorg\nmk61_m0_dadd_end:'
assert new.count(needle)==1
new=new.replace(needle,'\n.ltorg\n'+special+'\n.align 2\n'+needle,1)
(W/'native_eabi_m0_rp2040.S').write_text(new)
(W/'top-normal-only.patch').write_text(''.join(difflib.unified_diff(old.splitlines(True),new.splitlines(True),fromfile='accepted-mixed/code/native_eabi_m0_rp2040.S',tofile='candidate/code/native_eabi_m0_rp2040.S')))
prefix=new.split('mk61_m0_dadd_end:',1)[0]
prefix=prefix.replace('__aeabi_dadd','top_candidate_dadd').replace('__aeabi_dsub','top_candidate_dsub')
prefix=prefix.replace('.text.mk61_rp2040_arithmetic','.text.m0_top_trial')
(W/'candidate.S').write_text(prefix+'\n#endif\n')
(W/'candidate.ld').write_text('SECTIONS { . = 0x10182000; .text : { *(.text.m0_top_trial) } /DISCARD/ : { *(.ARM.attributes) } }\n')
slow=ElfImage(P/'firmware/mk61s-picocalc-pico-h.elf').symbols['mk61_m0_dadd_slow']
commands=[
 [str(CC/'arm-none-eabi-gcc'),'-mcpu=cortex-m0plus','-mthumb','-mfloat-abi=soft','-DMK61_USE_M0_EABI=1','-DMK61_M0_RP2040_EABI=1','-c',str(W/'candidate.S'),'-o',str(W/'candidate.o')],
 [str(CC/'arm-none-eabi-ld'),'-T',str(W/'candidate.ld'),'--defsym',f'mk61_m0_dadd_slow={slow}',str(W/'candidate.o'),'-o',str(W/'candidate.elf')],
 [str(CC/'arm-none-eabi-objcopy'),'-O','binary',str(W/'candidate.elf'),str(W/'candidate.bin')]]
for command in commands:subprocess.run(command,check=True)
with (W/'candidate.dis').open('w') as f:subprocess.run([str(CC/'arm-none-eabi-objdump'),'-dr',str(W/'candidate.elf')],stdout=f,check=True)
r=dict(status='BUILT_PRIVATE_TOP_EXPONENT_DADD_CANDIDATE_NOT_FIRMWARE',parent_source_sha256=sha(BASE/'native_eabi_m0_rp2040.S'),parent_ELF_sha256=sha(BASE/'candidate.elf'),
       candidate_bytes=(W/'candidate.bin').stat().st_size,commands=commands,source_sha256=sha(W/'native_eabi_m0_rp2040.S'),candidate_ELF_sha256=sha(W/'candidate.elf'),canonical_or_frozen_mutated=False,USB_accessed=False)
(W/'build.json').write_text(json.dumps(r,indent=2)+'\n')
print(json.dumps({k:v for k,v in r.items() if k!='commands'}))

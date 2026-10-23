"""Private low-normal/nonfinite add/sub candidate, keeping reviewed inputs immutable."""
from pathlib import Path
import difflib,hashlib,json,subprocess,sys
sys.dont_write_bytecode=True
W=Path(__file__).resolve().parent;ROOT=W.parents[1]
BASE=ROOT/'.build/m0-mixed-sign-top-normal-20261023'
P=ROOT/'.build/m0-asin-scaled-bound-v164-20261023'
CC=Path('/Users/bolk/Library/Arduino15/packages/STMicroelectronics/tools/xpack-arm-none-eabi-gcc/14.2.1-1.1/bin')
sys.path.insert(0,str(ROOT/'tests'))
from check_stm32_vectors import ElfImage
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
assert sha(BASE/'result.json')=='6e4e5b7eafeea3a11eebb499860f53d1d51fe892ce47b325ae4e48ae90f7d11d'
old=(BASE/'native_eabi_m0_rp2040.S').read_text();new=old
needle=' // With equal signs there is no cancellation'
assert needle in new
new=new.replace(needle,'.Lda_same_sign_start:\n'+needle,1)
needle=' bhi .Lda_far_return\n // Unpack unsigned magnitudes'
assert new.count(needle)==1
new=new.replace(needle,' bhi .Lda_far_return\n.Lda_mixed_unsigned_core:\n // Unpack unsigned magnitudes',1)
needle='''.Lda_top_guard:
 // BHS retained the preceding CMP flags. Equality means exponent2046;
 // every larger unsigned value remains a fallback input.
 bne .Lda_slow'''
assert new.count(needle)==1
new=new.replace(needle,'''.Lda_top_guard:
 // Equality means exponent2046; the remaining cases retain CMP's N flag.
 bne .Lda_cold_other''',1)
needle='.Lda_slow:\n'
assert new.count(needle)==1
other='''.Lda_cold_other:
 // Negative residual means normal max exponent1..54. The only positive
 // residual here is exponent2047; zero was handled by the top path.
 bpl .Lda_nonfinite_start
 b .Lda_low_start
'''+(W/'nonfinite.S.txt').read_text()+'\n'
new=new.replace(needle,other+needle,1)

a=old.index('.Lda_mixed_sign:');b=old.index('.Lda_far_return:',a)
low=old[a:b].replace('.Lda_mixed_sign:','.Lda_low_mixed_sign:').replace('.Lda_near_','.Lda_low_near_')
needle=' bhi .Lda_mixed_general\n'
assert low.count(needle)==1
low=low.replace(needle,' bls .Lda_low_near_input\n b .Lda_mixed_unsigned_core\n.Lda_low_near_input:\n',1)
a=low.index('.Lda_low_near_normalize:');b=low.index('.Lda_low_near_pack:',a)
low=low[:a]+(W/'capped-normalize.S.txt').read_text()+'\n'+low[b:]
low='''.Lda_low_start:
 mov r6,r1
 eors r6,r3
 bmi .Lda_low_mixed_sign
 b .Lda_same_sign_start
'''+low
needle='\n.align 2\n\n.ltorg\nmk61_m0_dadd_end:'
assert new.count(needle)==1
new=new.replace(needle,'\n'+low+needle,1)
(W/'native_eabi_m0_rp2040.S').write_text(new)
(W/'cold-normal-only.patch').write_text(''.join(difflib.unified_diff(old.splitlines(True),new.splitlines(True),fromfile='top-parent/code/native_eabi_m0_rp2040.S',tofile='candidate/code/native_eabi_m0_rp2040.S')))
prefix=new.split('mk61_m0_dadd_end:',1)[0]
prefix=prefix.replace('__aeabi_dadd','cold_candidate_dadd').replace('__aeabi_dsub','cold_candidate_dsub')
prefix=prefix.replace('.text.mk61_rp2040_arithmetic','.text.m0_cold_trial')
(W/'candidate.S').write_text(prefix+'\n#endif\n')
(W/'candidate.ld').write_text('SECTIONS { . = 0x10183000; .text : { *(.text.m0_cold_trial) } /DISCARD/ : { *(.ARM.attributes) } }\n')
slow=ElfImage(P/'firmware/mk61s-picocalc-pico-h.elf').symbols['mk61_m0_dadd_slow']
commands=[
 [str(CC/'arm-none-eabi-gcc'),'-mcpu=cortex-m0plus','-mthumb','-mfloat-abi=soft','-DMK61_USE_M0_EABI=1','-DMK61_M0_RP2040_EABI=1','-c',str(W/'candidate.S'),'-o',str(W/'candidate.o')],
 [str(CC/'arm-none-eabi-ld'),'-T',str(W/'candidate.ld'),'--defsym',f'mk61_m0_dadd_slow={slow}',str(W/'candidate.o'),'-o',str(W/'candidate.elf')],
 [str(CC/'arm-none-eabi-objcopy'),'-O','binary',str(W/'candidate.elf'),str(W/'candidate.bin')]]
for command in commands:subprocess.run(command,check=True)
with (W/'candidate.dis').open('w') as f:subprocess.run([str(CC/'arm-none-eabi-objdump'),'-dr',str(W/'candidate.elf')],stdout=f,check=True)
r=dict(status='BUILT_PRIVATE_LOW_NORMAL_NONFINITE_DADD_NOT_FIRMWARE',parent_source_sha256=sha(BASE/'native_eabi_m0_rp2040.S'),parent_ELF_sha256=sha(BASE/'candidate.elf'),source_sha256=sha(W/'native_eabi_m0_rp2040.S'),candidate_bytes=(W/'candidate.bin').stat().st_size,candidate_ELF_sha256=sha(W/'candidate.elf'),commands=commands,canonical_or_frozen_changed=False,USB_accessed=False,goal_complete=False)
(W/'build.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps({k:v for k,v in r.items() if k!='commands'}))

"""Complete the private add/sub bit-domain without a C++ fallback."""
from pathlib import Path
import difflib,hashlib,json,subprocess,sys
sys.dont_write_bytecode=True
W=Path(__file__).resolve().parent;ROOT=W.parents[1]
BASE=ROOT/'.build/m0-add-cold-normal-20261023'
CC=Path('/Users/bolk/Library/Arduino15/packages/STMicroelectronics/tools/xpack-arm-none-eabi-gcc/14.2.1-1.1/bin')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
assert sha(BASE/'result.json')=='70014f74e93ddf39ff37a1001a56601c85e16dcd89a22b3e0dbbce1f3f5a5bdb'
old=(BASE/'native_eabi_m0_rp2040.S').read_text();new=old
assert new.count('beq .Lda_slow')==2
new=new.replace('beq .Lda_slow','beq .Lda_zero_a_stub',1).replace('beq .Lda_slow','beq .Lda_zero_b_stub',1)
slow='''.Lda_slow:
 // Save the volatile R3 in the previously reserved alignment word.
 // A six-register pop restores the identical24-byte frame in one step.
 push {r3}
 bl mk61_m0_dadd_slow
 pop {r3-r7,pc}'''
assert new.count(slow)==1
new=new.replace(slow,'''.Lda_zero_a_stub:
 b .Lda_zero_a
.Lda_zero_b_stub:
 b .Lda_zero_b''',1)
needle='\n.align 2\n\n.ltorg\nmk61_m0_dadd_end:'
assert new.count(needle)==1
new=new.replace(needle,'\n'+(W/'zero-input.S.txt').read_text()+needle,1)
assert '.Lda_slow' not in new and 'mk61_m0_dadd_slow' not in new
(W/'native_eabi_m0_rp2040.S').write_text(new)
(W/'subnormal-input-only.patch').write_text(''.join(difflib.unified_diff(old.splitlines(True),new.splitlines(True),fromfile='cold-normal-parent/code/native_eabi_m0_rp2040.S',tofile='candidate/code/native_eabi_m0_rp2040.S')))
prefix=new.split('mk61_m0_dadd_end:',1)[0]
prefix=prefix.replace('__aeabi_dadd','sub_candidate_dadd').replace('__aeabi_dsub','sub_candidate_dsub')
prefix=prefix.replace('.text.mk61_rp2040_arithmetic','.text.m0_subnormal_trial')
(W/'candidate.S').write_text(prefix+'\n#endif\n')
(W/'candidate.ld').write_text('SECTIONS { . = 0x10184000; .text : { *(.text.m0_subnormal_trial) } /DISCARD/ : { *(.ARM.attributes) } }\n')
commands=[
 [str(CC/'arm-none-eabi-gcc'),'-mcpu=cortex-m0plus','-mthumb','-mfloat-abi=soft','-DMK61_USE_M0_EABI=1','-DMK61_M0_RP2040_EABI=1','-c',str(W/'candidate.S'),'-o',str(W/'candidate.o')],
 [str(CC/'arm-none-eabi-ld'),'-T',str(W/'candidate.ld'),str(W/'candidate.o'),'-o',str(W/'candidate.elf')],
 [str(CC/'arm-none-eabi-objcopy'),'-O','binary',str(W/'candidate.elf'),str(W/'candidate.bin')]]
for command in commands:subprocess.run(command,check=True)
with (W/'candidate.dis').open('w') as f:subprocess.run([str(CC/'arm-none-eabi-objdump'),'-dr',str(W/'candidate.elf')],stdout=f,check=True)
r=dict(status='BUILT_PRIVATE_FULL_DOMAIN_ADD_SUB_NO_CPP_FALLBACK_NOT_FIRMWARE',parent_source_sha256=sha(BASE/'native_eabi_m0_rp2040.S'),parent_ELF_sha256=sha(BASE/'candidate.elf'),source_sha256=sha(W/'native_eabi_m0_rp2040.S'),candidate_bytes=(W/'candidate.bin').stat().st_size,candidate_ELF_sha256=sha(W/'candidate.elf'),commands=commands,external_fallback_reference=False,canonical_or_frozen_changed=False,USB_accessed=False,goal_complete=False)
(W/'build.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps({k:v for k,v in r.items() if k!='commands'}))

"""Private RP2040-only signed int64 entry; baseline kernels are unchanged."""
from pathlib import Path
import difflib
import hashlib
import json
import subprocess
import sys
sys.dont_write_bytecode = True
W = Path(__file__).resolve().parent
ROOT = W.parents[1]
P = ROOT / '.build/m0-asin-scaled-bound-v164-20261023/source/code'
CC = Path('/Users/bolk/Library/Arduino15/packages/STMicroelectronics/tools/xpack-arm-none-eabi-gcc/14.2.1-1.1/bin')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
assert sha(P/'native_eabi_m0.S') == '1a9d2183fcf3ee72ef5eb523150329f884cd6a1b9f67ca266a2a44229b5d8b44'
assert sha(P/'native_eabi_m0_convert.inc') == 'd4b15b0be7f54c9a67d4d7d4b1e8b60874ff054587b6c09d0ec0cd97338a4cc3'
old = (P/'native_eabi_m0_convert.inc').read_text()
start = old.index('.global __aeabi_l2d\n')
end = old.index('.global __aeabi_ul2d\n')
new = old[:start] + (W/'signed-entry.S.txt').read_text() + old[end:]
(W/'native_eabi_m0.S').write_bytes((P/'native_eabi_m0.S').read_bytes())
(W/'native_eabi_m0_convert.inc').write_text(new)
(W/'signed64-entry-only.patch').write_text(''.join(difflib.unified_diff(
    old.splitlines(True), new.splitlines(True), fromfile='V164/code/native_eabi_m0_convert.inc',
    tofile='candidate/code/native_eabi_m0_convert.inc')))
prefix = (P/'native_eabi_m0.S').read_text().split('#include "native_eabi_m0_convert.inc"',1)[0]
conversion_prefix = new.split('#if defined(MK61_M0_RP2040_EABI) && MK61_M0_RP2040_EABI\nfunction __aeabi_f2d',1)[0]
(W/'candidate.S').write_text(prefix + conversion_prefix + '\n#endif\n')
(W/'candidate.ld').write_text('SECTIONS { . = 0x10185000; .text : { *(.text.__aeabi_i2d) } /DISCARD/ : { *(.ARM.attributes) } }\n')
commands = [
 [str(CC/'arm-none-eabi-gcc'), '-mcpu=cortex-m0plus', '-mthumb', '-mfloat-abi=soft', '-DMK61_USE_M0_EABI=1', '-DMK61_M0_RP2040_EABI=1', '-c', str(W/'candidate.S'), '-o', str(W/'candidate.o')],
 [str(CC/'arm-none-eabi-ld'), '-T', str(W/'candidate.ld'), str(W/'candidate.o'), '-o', str(W/'candidate.elf')],
 [str(CC/'arm-none-eabi-objcopy'), '-O', 'binary', str(W/'candidate.elf'), str(W/'candidate.bin')]]
for command in commands:subprocess.run(command, check=True)
with (W/'candidate.dis').open('w') as f:subprocess.run([str(CC/'arm-none-eabi-objdump'), '-dr', str(W/'candidate.elf')], stdout=f, check=True)
report = dict(status='BUILT_PRIVATE_RP2040_L2D_ENTRY_NOT_FIRMWARE',
              input_sources={n:sha(P/n) for n in ('native_eabi_m0.S','native_eabi_m0_convert.inc')},
              source_files={n:sha(W/n) for n in ('native_eabi_m0.S','native_eabi_m0_convert.inc','signed64-entry-only.patch')},
              candidate_ELF_sha256=sha(W/'candidate.elf'), candidate_bytes=(W/'candidate.bin').stat().st_size,
              commands=commands, canonical_or_frozen_changed=False, hardware_accessed=False, goal_complete=False)
(W/'build.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps({k:v for k,v in report.items() if k!='commands'}))

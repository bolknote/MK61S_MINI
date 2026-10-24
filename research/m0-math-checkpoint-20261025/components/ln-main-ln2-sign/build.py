"""Build a new ln component with the exact pinned parent as control."""
from pathlib import Path
import hashlib
import json
import shutil
import subprocess
import sys

sys.dont_write_bytecode = True
W = Path(__file__).resolve().parent
ROOT = W.parents[1]
BASE = ROOT/'.build/m0-ln-near-q77-linear-20261024'
P = ROOT/'.build/m0-asin-scaled-bound-v164-20261023'
CC = Path('/Users/bolk/Library/Arduino15/packages/STMicroelectronics/tools/xpack-arm-none-eabi-gcc/14.2.1-1.1/bin')
sys.path.insert(0,str(ROOT/'tests'))
from check_stm32_vectors import ElfImage


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


parent = json.loads((BASE/'candidate-build.json').read_text())
assert sha(BASE/'candidate.elf') == '1164948d280c23bc66601af789dbd2a4af44c0982fb8c813b35fa2b7a396052e'
for suffix in ('full.o','ratio.o','elf','ld'):
    shutil.copyfile(BASE/('candidate-'+suffix if suffix.endswith('.o') else 'candidate.'+suffix),
                    W/('control-'+suffix if suffix.endswith('.o') else 'control.'+suffix))
control = dict(parent)
control.update(label='control',control_is_unchanged_pinned_parent=True,commands=[])
(W/'control-build.json').write_text(json.dumps(control,indent=2)+'\n')
commands = [[str(CC/'arm-none-eabi-g++'),'-mcpu=cortex-m0plus','-mthumb','-mfloat-abi=soft',
    '-Os','-std=gnu++17','-fno-exceptions','-fno-rtti','-fno-unwind-tables','-fno-use-cxa-atexit',
    '-ffunction-sections','-fdata-sections','-fno-lto','-DMK61_USE_M0_EABI=1','-DMK61_M0_RP2040_EABI=1',
    '-I',str(P/'source/code'),'-c',str(W/'native_eabi_m0.cpp'),'-o',str(W/'candidate-full.o')],
    [str(CC/'arm-none-eabi-gcc'),'-mcpu=cortex-m0plus','-mthumb','-mfloat-abi=soft',
     '-DMK61_USE_M0_EABI=1','-DMK61_M0_RP2040_EABI=1','-I',str(P/'source/code'),
     '-c',str(W/'ratio.S'),'-o',str(W/'candidate-ratio.o')]]
for cmd in commands:
    subprocess.run(cmd,check=True)
assert sha(W/'candidate-ratio.o') == sha(BASE/'candidate-ratio.o')
shutil.copyfile(BASE/'candidate.ld',W/'candidate.ld')
link = [str(CC/'arm-none-eabi-ld'),'--gc-sections','-e','mk61_m0_ln','-T',str(W/'candidate.ld'),
        str(W/'candidate-full.o'),str(W/'candidate-ratio.o'),'-o',str(W/'candidate.elf')]
commands.append(link)
subprocess.run(link,check=True)
e = ElfImage(W/'candidate.elf')
ranges = [(s[3],s[3]+s[5]) for s in e.named_sections.values() if s[2]&2 and s[5]]
assert all(0x101a0000<=a<z<=0x10200000 for a,z in ranges)
assert all(not any(a<=(v&~1)<z for a,z in ranges) for v in parent['resident_bindings'].values())
with (W/'candidate.dis').open('w') as f:
    subprocess.run([str(CC/'arm-none-eabi-objdump'),'-dr',str(W/'candidate.elf')],check=True,stdout=f)
b = dict(status='BUILT_PRIVATE_MAIN_LN_LN2_DIRECTIONAL_GATE_COMPONENT',commands=commands,
    source_include_sha256=sha(W/'native_eabi_m0_log70.inc'),
    subnormal_source_sha256=sha(W/'native_eabi_m0_log_subnormal.inc'),
    full_object_sha256=sha(W/'candidate-full.o'),ELF_sha256=sha(W/'candidate.elf'),
    parent_ELF_sha256=sha(W/'control.elf'),resident_bindings=parent['resident_bindings'],
    all_bindings_outside_overlay=True,allocated_ranges=ranges,hardware_accessed=False,
    canonical_or_frozen_changed=False)
(W/'candidate-build.json').write_text(json.dumps(b,indent=2)+'\n')
print(json.dumps({k:v for k,v in b.items() if k not in ('commands','resident_bindings')},indent=2))

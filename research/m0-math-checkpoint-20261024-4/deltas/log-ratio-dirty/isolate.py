"""Check full objects, every other function/table, and generic/M4 controls."""
from pathlib import Path
import hashlib
import json
import subprocess
import struct
import sys

sys.dont_write_bytecode = True
W = Path(__file__).resolve().parent
ROOT = W.parents[1]
P = ROOT / '.build/m0-asin-scaled-bound-v164-20261023'
CC = Path('/Users/bolk/Library/Arduino15/packages/STMicroelectronics/tools/xpack-arm-none-eabi-gcc/14.2.1-1.1/bin')
sys.path.insert(0, str(ROOT/'tests'))
from check_stm32_vectors import ElfImage


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def allocated(e):
    return {n: e.bytes_at(s) for n, s in e.named_sections.items() if s[2]&2 and s[1] != 8}


old, new = ElfImage(W/'control-full.o'), ElfImage(W/'candidate-full.o')
a, b = allocated(old), allocated(new)
assert set(a) == set(b)
changed = [n for n in a if a[n] != b[n]]
assert changed == ['.m0_pow_extension'], changed
assert len(b[changed[0]])-len(a[changed[0]]) == 156


def function_bytes(image, name):
    address, size = image.symbols[name]&~1, image.sizes[name]
    section = image.named_sections['.m0_pow_extension']
    return image.bytes_at(section)[address-section[3]:address-section[3]+size]


members = []
target_index = old.sections.index(old.named_sections['.m0_pow_extension'])
for section in old.sections:
    if section[1] != 2:
        continue
    strings = old.sections[section[6]]
    names = old.data[strings[4]:strings[4]+strings[5]]
    for offset in range(section[4], section[4]+section[5], section[9]):
        n, value, size, info, other, index = struct.unpack_from('<IIIBBH', old.data, offset)
        if index == target_index and size and (info&15) == 2:
            members.append(old.string(names, n))
other_functions = [n for n in members if n != 'mk61_m0_log_ratio70_slow']
assert all(function_bytes(old, n) == function_bytes(new, n) for n in other_functions)
asm_old, asm_new = [allocated(ElfImage(W/(v+'-ratio.o'))) for v in ('control', 'candidate')]
assert set(asm_old) == set(asm_new)
assert sum(map(len, asm_new.values()))-sum(map(len, asm_old.values())) == 8
ratio_old = (P/'source/code/native_eabi_m0_log70_ratio.inc').read_text()
ratio_new = (W/'native_eabi_m0_log70_ratio.inc').read_text()
assert ratio_old.split('.Llog_ratio70_slow:')[0] == ratio_new.split('.Llog_ratio70_slow:')[0]
assert 'movs r3,r0\n orrs r3,r1\n beq .Llog_ratio70_zero' in ratio_new
assert '.Llog_ratio70_zero:\n bx lr' in ratio_new


def undefined(p):
    return sorted(subprocess.check_output([str(CC/'arm-none-eabi-nm'), '-u', str(p)], text=True).splitlines())


assert undefined(W/'control-full.o') == undefined(W/'candidate-full.o')
contexts = []
commands = []
for label, cpu, enabled, hard in [('generic_M0', 'cortex-m0plus', True, False),
                                 ('M4_soft', 'cortex-m4', False, False), ('M4_hard', 'cortex-m4', False, True)]:
    images = []
    for variant, source in [('control', P/'source/code/native_eabi_m0.cpp'), ('candidate', W/'native_eabi_m0.cpp')]:
        cmd = [str(CC/'arm-none-eabi-g++'), '-mcpu='+cpu, '-mthumb', '-mfloat-abi='+('hard' if hard else 'soft'),
               '-Os', '-std=gnu++17', '-fno-exceptions', '-fno-rtti', '-fno-unwind-tables', '-fno-use-cxa-atexit',
               '-ffunction-sections', '-fdata-sections', '-fno-lto', '-I', str(P/'source/code')]
        if enabled:
            cmd += ['-DMK61_USE_M0_EABI=1']
        if hard:
            cmd += ['-mfpu=fpv4-sp-d16']
        target = W/(label+'-'+variant+'.o')
        cmd += ['-c', str(source), '-o', str(target)]
        subprocess.run(cmd, check=True)
        commands.append(cmd)
        images.append(ElfImage(target))
    assert allocated(images[0]) == allocated(images[1]), label
    contexts.append(dict(context=label, allocated_code_and_data_identical=True,
                         allocated_bytes=sum(map(len, allocated(images[1]).values()))))
out = dict(status='PASS_ONLY_RP2040_DIRTY_LOG_RATIO_HELPER_CHANGED',
           changed_sections={n:[len(a[n]), len(b[n])] for n in changed}, allocated_object_bytes_delta=156,
           ratio_ASM_allocated_bytes_delta=8, linked_component_allocated_bytes_delta=160,
           other_functions_in_shared_section_byte_identical=other_functions,
           all_other_allocated_sections_and_tables_identical=True,
           hardware_ready_ratio_assembly_source_prefix_identical=True,
           only_ASM_delta_is_busy_zero_shortcut=True,
           undefined_dependency_sets_unchanged=True, new_tables_or_global_RAM_or_libgcc=False,
           contexts=contexts, source_sha256=sha(W/'native_eabi_m0_log70_center.inc'),
           candidate_ELF_sha256=sha(W/'candidate.elf'), full_object_sha256=sha(W/'candidate-full.o'),
           commands=commands, hardware_accessed=False, canonical_or_frozen_changed=False,
           scope='Diagnostic ln component; whole-library integration and whole M4 rebuild not performed.')
(W/'isolation.json').write_text(json.dumps(out, indent=2)+'\n')
print(json.dumps({k:v for k,v in out.items() if k != 'commands'}, indent=2))

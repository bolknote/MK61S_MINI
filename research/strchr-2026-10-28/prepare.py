#!/usr/bin/env python3
"""Prepare deterministic strchr cases and checked timing core; never access devices."""
import argparse
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / 'tests'))
from strchr_arm_self_test import pin, command


def cases():
    result, seen = [], set()
    for n in [0, 1, 2, 3, 4, 7, 8, 15, 16, 31, 32, 63, 64, 127, 128, 255, 512]:
        for align in range(4):
            for mode in ['missing', 'nul', 'first', 'middle', 'last', 'repeated', 'high', 'truncate', 'truncate_nul']:
                text = bytearray(b'\x81' * n)
                c = 0 if mode == 'nul' else 255 if mode == 'high' else 0x152 if mode == 'truncate' else 256 if mode == 'truncate_nul' else 0x52
                if n and mode not in ['missing', 'nul', 'truncate_nul']:
                    at = 0 if mode == 'first' else n - 1 if mode in ['last', 'high'] else n // 2
                    text[at] = c & 255
                    if mode == 'repeated':
                        text[-1] = c & 255
                text += b'\0'
                key = (bytes(text), c, align)
                if key in seen:
                    continue
                seen.add(key)
                expected = text.find(bytes([c & 255]))
                for bank in ['SRAM', 'Flash']:
                    result.append(dict(index=len(result), length=n, alignment=align, mode=mode,
                        operand_bank=bank, text_hex=text.hex(), text_bytes=len(text), character=c,
                        expected_offset=expected))
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--toolchain-bin', type=Path, required=True)
    p.add_argument('--output-dir', type=Path, required=True)
    a = p.parse_args()
    a.output_dir.mkdir(parents=True, exist_ok=False)
    logs, objects = [], []
    exe = a.output_dir / 'bench-self-test'
    command(['cc', '-std=c11', '-O2', '-Wall', '-Wextra', '-Werror', '-fsanitize=address,undefined',
             HERE / 'bench.c', HERE / 'bench_self_test.c', '-o', exe], logs)
    print(command([exe], logs), end='')
    for arch, cpu in [('m4', 'cortex-m4'), ('m0', 'cortex-m0plus')]:
        obj = a.output_dir / (arch + '-bench.o')
        command([a.toolchain_bin / 'arm-none-eabi-gcc', '-mcpu=' + cpu, '-mthumb', '-mfloat-abi=soft',
            '-Os', '-fno-builtin', '-fno-lto', '-Wall', '-Wextra', '-Werror', '-c', HERE / 'bench.c', '-o', obj], logs)
        dis = command([a.toolchain_bin / 'arm-none-eabi-objdump', '-d', obj], logs)
        (a.output_dir / (arch + '-bench.dis')).write_text(dis)
        assert '\tblx\t' in dis and 'cpsid' not in dis and 'cpsie' not in dis
        objects.append(dict(arch=arch, object=pin(obj), real_indirect_calls=True, IRQ_mask_instructions=False))
    matrix = cases()
    plan = dict(status='HOST_READY_NOT_A_HARDWARE_GRANT', physical_IO=0, hardware_winner=None,
        source_base='7a01beb4827c05bb2ba34fc0576f85f929b6160f', cases=matrix, case_count=len(matrix),
        rounds=7, raw_values_per_route=len(matrix) * 7,
        candidates=dict(M4=['actual_native', 'actual_SDK', 'qualified_newlib', 'byte1', 'byte4', 'word1', 'word2', 'dsp1', 'dsp2'],
                        M0=['actual_installed_newlib_to_be_bound', 'actual_SDK', 'byte1', 'byte4', 'word1', 'word2']),
        code_placements=['resident Flash', 'resident SRAM on M0+', 'standalone APP SRAM', 'shared APP real slot18 veneer'],
        runtime=dict(count=26, strchr_slot=18, API_unchanged=True,
                     emulated_table_is_not_installed_firmware=True),
        operand_layout='64-byte guards, aligned readable containing word at NUL/first match; no prefix; preserve input and guards after every group',
        timer=dict(core='bench.c, checked supplied uint32 tick function', actual_unit_frequency='UNBOUND',
            IRQ='enabled; do not mix with masked historical campaigns', repeats='1..4096 frozen per case after actual timer qualification',
            metric='whole indirect-call loop and pointer-mismatch accumulation, no empty subtraction',
            acceptance='all raw intervals 0 < ticks < 2^31; first-fault, no retries'),
        selection='hardware paired results per architecture/placement; retain short regressions and code/Flash/RAM cost; no HOST speed claims',
        target_binding='UNBOUND; actual installed identity/image/clock/power/supplier needed',
        requirements_before_hardware=['current device and source/body binding', 'qualified actual timer and actual frequency',
            'unique context flags/PATH and RUN power state', 'exact accepted carrier/APP/argv/lease and coordinator hardware grant',
            'snapshot original Flash, files, cache, typed state and qualified RTC context',
            'raw first-fault results, actual process/session/EXIT/reap/FD/lock records',
            'restore original image and state, independent close'],
        Pico_outer_supplier='existing qualified operator via coordinator; no competing helper or lease',
        bench_tests=dict(status='PASS_HOST_SYNTHETIC_TICKS_ONLY', commands=logs, ARM_objects=objects),
        source_pins=[pin(HERE / x) for x in ['bench.h', 'bench.c', 'bench_self_test.c', 'prepare.py', 'APP-CHECK.c', 'candidates.S']])
    (a.output_dir / 'PLAN.json').write_text(json.dumps(plan, indent=2) + '\n')
    print(json.dumps(dict(plan=pin(a.output_dir / 'PLAN.json'), cases=len(matrix), physical_IO=0)))


if __name__ == '__main__':
    main()

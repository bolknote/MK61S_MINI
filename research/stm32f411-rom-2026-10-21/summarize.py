#!/usr/bin/env python3
"""Summarize the saved captures; no device access or firmware changes."""
import hashlib
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / '.build/stm32f411-rom-20261021/deps'))
from capstone import Cs, CS_ARCH_ARM, CS_MODE_THUMB, CS_MODE_MCLASS


def listing(raw, base, functions):
    md = Cs(CS_ARCH_ARM, CS_MODE_THUMB | CS_MODE_MCLASS)
    lines = ['/* Annotated address ranges; labels are analytical, not vendor symbols. */']
    for name, begin, end in functions:
        instructions = list(md.disasm(raw[begin-base:end-base], begin))
        assert sum(i.size for i in instructions) == end-begin
        lines.append(f'\n/* {name}: {end-begin} bytes, [{begin:08X}, {end:08X}) */')
        lines.extend(f'{i.address:08x}: {i.bytes.hex():10s} {i.mnemonic:8s} {i.op_str}'
                     for i in instructions)
    return '\n'.join(lines) + '\n'


def main():
    rom = (HERE/'capture/rom-a.bin').read_bytes()
    assert rom == (HERE/'capture/rom-b.bin').read_bytes()
    for directory in ('capture', 'benchmark', 'benchmark-bulk'):
        report = json.loads((HERE/directory/(directory.split('-bulk')[0]+'.json')).read_text())
        assert report['status'] == 'PASS'
        assert all(report[k] for k in ('files_unchanged', 'state_unchanged', 'identity_unchanged'))

    full = json.loads((HERE/'benchmark/benchmark.json').read_text())['measurements']
    bulk = json.loads((HERE/'benchmark-bulk/benchmark.json').read_text())['measurements']
    assert full['resident_pointer'] == '08008A21'
    assert bulk['resident_pointer'] == '08008935'
    rows = [r for r in bulk['rows'] if r['bytes'] >= 16]
    assert len(rows) == 88
    assert all(r['rom_over_resident'] < 1 for r in rows)

    # Excludes alignment padding and includes the public size dispatcher.
    resident_functions = [
        ('fill_small, 1..3 bytes', 0x080088B0, 0x080088C0),
        ('fill_short_words, 4..15 bytes', 0x080088C0, 0x080088F4),
        ('fill_bulk, >=16 bytes', 0x08008934, 0x0800898C),
        ('public memset', 0x08008A20, 0x08008A38),
    ]
    code = (HERE/'benchmark/resident-code.bin').read_bytes()
    (HERE/'resident-memset.S').write_text(listing(code, 0x08008800, resident_functions))
    (HERE/'rom-helpers.S').write_text(listing(rom, 0x1FFF0000, [
        ('copy words; NOT ISO C memcpy', 0x1FFF0A4C, 0x1FFF0A6E),
        ('high nibbles to uppercase UTF-16LE hex; no terminator', 0x1FFF27C0, 0x1FFF27E8),
        ('swap low two bytes; u16 input', 0x1FFF3A60, 0x1FFF3A6A),
        ('fill: r0=dest, r1=size, r2=value; ISO C adapter required', 0x1FFF3BD4, 0x1FFF3C3A),
    ]))

    summary = {
        'scope': 'One Classic V3 UC1609, STM32F411, resident build 3AB3DD45. No F401 ROM capture.',
        'rom_sha256': hashlib.sha256(rom).hexdigest(),
        'full_replacement': {
            'decision': 'Reject as a blanket replacement: short-call regressions.',
            'slower_cases': sum(r['rom_over_resident'] > 1 for r in full['rows']),
            'total_cases': len(full['rows']),
        },
        'bulk_candidate': {
            'tested_sizes': sorted({r['bytes'] for r in rows}),
            'alignment_mod_4': [0, 1, 2, 3],
            'faster_cases': len(rows),
            'rom_cycles_over_existing_bulk_range': [min(r['rom_over_resident'] for r in rows),
                                                   max(r['rom_over_resident'] for r in rows)],
            'existing_bulk_bytes': 88,
            'measured_adapter_bytes': 16,
            'estimated_code_saving_before_version_guards_and_link_layout': 72,
            'integration_status': 'Historical ROM probe with adapter in SRAM. ROM was not selected: subsequent local-Flash qualification is recorded below.',
        },
        'resident_functions': [{'name': name, 'start': f'{begin:08X}', 'end_exclusive': f'{end:08X}',
                                'bytes': end-begin} for name, begin, end in resident_functions],
        'resident_total_bytes_excluding_padding': sum(end-begin for _, begin, end in resident_functions),
        'max_repeat_drift_cycles_per_call': max(r['control_drift_cycles'] for r in full['rows'] + bulk['rows']),
        'correctness': {'emulated_fill_cases': 4432, 'hardware_checks_per_run': 2416, 'hardware_runs': 2},
        'limitations': [
            'Warm microbenchmark with interrupts enabled; no whole-firmware workload speed claim.',
            'Candidate entrypoints and ABI inferred from this exact ROM, not a documented ST service API.',
            'A function checksum/version check and fallback may consume the estimated Flash saving.',
            'Code inventory is conservative and incomplete at indirect dispatches.',
        ],
    }
    flash_path=HERE/'flash-comparison.json'
    if flash_path.exists():
        flash=json.loads(flash_path.read_text())
        summary['flash_selection']={'priority':'speed','selected':'local_bulk_style',
            'summary':flash['summary']['style'],'data':'flash-comparison.json',
            'code':'code/memory_word_ops.h','rom_dependency':False,
            'body_bytes':82,'previous_body_bytes':88,
            'small_paths':'unchanged for sizes 0..15'}
    resident_path=HERE/'resident-comparison.json'
    if resident_path.exists():
        resident=json.loads(resident_path.read_text())
        assert resident['status']=='PASS'
        summary['resident_qualification']={k:v for k,v in resident.items() if k!='rows'}
        summary['resident_qualification']['data']='resident-comparison.json'
    (HERE/'findings.json').write_text(json.dumps(summary, indent=2)+'\n')
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    main()

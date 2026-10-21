#!/usr/bin/env python3
"""Measure actual ARM instruction counts for explicit Qfplib compositions."""
import argparse
import hashlib
import json
from pathlib import Path
import statistics

from m0_qfplib_compositions import corpus
from native_eabi_m0_arm_self_test import Machine, ordered
from check_stm32_vectors import ElfImage


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--elf', type=Path, required=True)
    p.add_argument('--per-group', type=int, default=0, help='0 checks every prepared vector.')
    p.add_argument('--operations', nargs='+', choices=('asin', 'acos', 'log10', 'pow'))
    p.add_argument('--reference-elf', type=Path, help='Load only the isolated .m0_qfplib section from this diagnostic ELF.')
    p.add_argument('--json', type=Path, required=True)
    args = p.parse_args()
    assert args.per_group >= 0
    machine = Machine(args.elf, True, stack_bytes=16384, instruction_budget=20000000)
    if args.reference_elf:
        reference = ElfImage(args.reference_elf)
        section = reference.named_sections['.m0_qfplib']
        assert section[3] == 0x10180000 and section[3]+section[5] <= 0x10200000
        machine.uc.mem_write(section[3], reference.bytes_at(section))
        for name, address in reference.symbols.items():
            if section[3] <= (address & ~1) < section[3]+section[5]:
                machine.elf.symbols[name] = address
    groups = []
    for g in corpus():
        if args.operations and g['operation'] not in args.operations:
            continue
        vectors = g['vectors']
        if 0 < args.per_group < len(vectors):
            vectors = [vectors[i * (len(vectors)-1) // (args.per_group-1)]
                       for i in range(args.per_group)] if args.per_group > 1 else vectors[:1]
        counts = {'own': [], 'qfplib': []}
        wrong = {'own': 0, 'qfplib': 0}
        worst = {'own': 0, 'qfplib': 0}
        for a, b, expected in vectors:
            for label, symbol in (('own', g['own_symbol']), ('qfplib', g['qfplib_symbol'])):
                got, _, instructions = machine.call(symbol, a, b, count=True)
                counts[label].append(instructions)
                wrong[label] += got != expected
                worst[label] = max(worst[label], abs(ordered(got)-ordered(expected)))
        means = {k: statistics.mean(v) for k, v in counts.items()}
        row = {k: v for k, v in g.items() if k != 'vectors'}
        row.update(cases=len(vectors), mean_instructions=means, wrong_rounding=wrong,
                   worst_ulp=worst, own_over_qfplib=means['own']/means['qfplib'])
        groups.append(row)
        print(g['operation'], g['stream'], means, 'wrong', wrong, flush=True)
    report = dict(status='FAIL' if any(g['wrong_rounding']['own'] for g in groups) else 'PASS',
                  performance_status='SLOW_GROUPS' if any(g['own_over_qfplib'] > 1 for g in groups) else 'PASS',
                  elf_sha256=hashlib.sha256(args.elf.read_bytes()).hexdigest(), groups=groups,
                  scope='ARM instruction counts, not physical cycle timings. Explicit Qfplib compositions and algebraic shortcuts with per-stream domains. Finite input corpus.')
    if args.reference_elf:
        report['reference_elf_sha256'] = hashlib.sha256(args.reference_elf.read_bytes()).hexdigest()
    args.json.parent.mkdir(parents=True, exist_ok=True)
    args.json.write_text(json.dumps(report, indent=2)+'\n')
    assert report['status'] == 'PASS', report['status']


if __name__ == '__main__':
    main()

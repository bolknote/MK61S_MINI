#!/usr/bin/env python3
"""Replay a frozen comparison matrix excluding pow, retaining individual results.

Raw averages and averages over correct-reference inputs are kept separately.
Neither is an RP2040 timing measurement or an all-input speed guarantee.
"""
import argparse
from collections import Counter
import gzip
import hashlib
import json
from pathlib import Path
import struct
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parent))
from native_eabi_m0_arm_self_test import Machine, SP


def pin(path):
    path = Path(path).resolve()
    data = path.read_bytes()
    return dict(path=str(path), bytes=len(data), sha256=hashlib.sha256(data).hexdigest())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--benchmark', type=Path, required=True)
    parser.add_argument('--elf', type=Path, required=True)
    parser.add_argument('--bootrom', type=Path, required=True)
    parser.add_argument('--output-dir', type=Path, required=True)
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=False)
    config_path = args.benchmark / 'benchmark.json'
    config = json.loads(config_path.read_text())
    ref_elf = args.benchmark / 'firmware/mk61s-picocalc-pico-h.elf'
    assert pin(ref_elf)['sha256'] == config['elf_sha256']
    chunks = [chunk for chunk in config['chunks'] if chunk['operation'] != 'pow']
    assert chunks and all('pow' not in c[key] for c in chunks for key in ('own_symbol', 'qfplib_symbol'))
    prepared, input_pins = [], []
    for chunk in chunks:
        path = Path(chunk['input'])
        identity = pin(path)
        assert identity['sha256'] == chunk['input_sha256']
        vectors = list(struct.iter_unpack('<3Q', path.read_bytes()[32:]))
        assert len(vectors) == chunk['cases']
        prepared.append((chunk, vectors))
        input_pins.append(identity)
    identities = dict(benchmark=pin(config_path), owned_elf=pin(args.elf), reference_elf=pin(ref_elf),
                      bootrom=pin(args.bootrom), operator=pin(__file__),
                      machine=pin(Path(__file__).with_name('native_eabi_m0_arm_self_test.py')),
                      parser=pin(Path(__file__).with_name('check_stm32_vectors.py')), inputs=input_pins,
                      chunks=len(chunks), cases=sum(c['cases'] for c in chunks),
                      excluded_operations=['pow'], instruction_cap_per_call=1000000,
                      stack_bytes=4096, wall_seconds=600)
    (args.output_dir / 'PREPARED.json').write_text(json.dumps(identities, indent=2) + '\n')
    machines = dict(own=Machine(args.elf, True, bootrom=args.bootrom),
                    reference=Machine(ref_elf, True, bootrom=args.bootrom))
    groups = {}
    completed, wrong, fatal = Counter(), [], None
    start = time.monotonic()
    try:
        with gzip.open(args.output_dir / 'records.jsonl.gz', 'xt') as output:
            for chunk, vectors in prepared:
                group = groups.setdefault(chunk['stream_index'], dict(
                    stream_index=chunk['stream_index'], operation=chunk['operation'], stream=chunk['stream'],
                    own_symbol=chunk['own_symbol'], reference_symbol=chunk['qfplib_symbol'],
                    reference_kind='composition' if chunk['qfplib_symbol'].startswith('qfp_composed_') else 'kernel_or_adapter',
                    cases=0, own_wrong=0, reference_wrong=0, raw_sums=Counter(),
                    correct_reference_cases=0, correct_reference_sums=Counter(),
                    correct_reference_comparisons=Counter()))
                width = 32 if chunk['kind'] in (6, 7, 11, 12) else 64
                mask = (1 << width) - 1
                for index, (a, b, expected) in enumerate(vectors):
                    row = dict(stream_index=chunk['stream_index'], chunk=chunk['index'], index=index,
                               a=f'{a:016X}', b=f'{b:016X}', expected=f'{expected:016X}', result_width=width)
                    values = {}
                    for role, machine in machines.items():
                        assert completed[role] < identities['cases'], 'call cap'
                        assert time.monotonic() - start <= identities['wall_seconds'], 'wall deadline'
                        machine.uc.mem_write(0xd0000060, struct.pack('<7I', 0, 0, 0, 0, 0, 0, 1))
                        symbol = chunk['own_symbol'] if role == 'own' else chunk['qfplib_symbol']
                        got, _, cost = machine.call(symbol, a, b, count=True)
                        values[role] = dict(bits=f'{got & mask:016X}', instructions=cost, correct=(got & mask) == expected)
                        completed[role] += 1
                        group['raw_sums'][role] += cost
                    row['actual'] = values
                    output.write(json.dumps(row, separators=(',', ':')) + '\n')
                    group['cases'] += 1
                    if not values['own']['correct']:
                        wrong.append(row)
                        group['own_wrong'] += 1
                    if not values['reference']['correct']:
                        group['reference_wrong'] += 1
                    else:
                        group['correct_reference_cases'] += 1
                        for role in machines:
                            group['correct_reference_sums'][role] += values[role]['instructions']
                        delta = values['own']['instructions'] - values['reference']['instructions']
                        group['correct_reference_comparisons']['slower' if delta > 0 else 'faster' if delta < 0 else 'equal'] += 1
                print(chunk['index'], chunk['operation'], chunk['stream'], 'own_wrong', group['own_wrong'], flush=True)
    except Exception as error:
        fatal = dict(type=type(error).__name__, message=str(error))
    rows = []
    for group in groups.values():
        group['raw_means'] = {role:total/group['cases'] for role,total in group['raw_sums'].items()}
        n = group['correct_reference_cases']
        group['correct_reference_means'] = {role:total/n for role,total in group['correct_reference_sums'].items()} if n else None
        group['correct_reference_mean_comparison'] = ('unavailable' if not n else
            'slower' if group['correct_reference_sums']['own'] > group['correct_reference_sums']['reference'] else
            'faster' if group['correct_reference_sums']['own'] < group['correct_reference_sums']['reference'] else 'equal')
        rows.append(group)
    result = dict(status='PASS_FINITE_NUMERICAL_REPLAY' if not wrong and fatal is None else 'FAIL',
                  identities=identities, actual_completed_calls=dict(completed), own_wrong=len(wrong), fatal=fatal,
                  groups=rows, group_comparisons=dict(Counter(r['correct_reference_mean_comparison'] for r in rows)),
                  maximum_observed_stack_bytes={role:SP-m.stack_lowest for role,m in machines.items()},
                  ROM_initializers={role:m.rom_initializers for role,m in machines.items()},
                  intrinsic_models={role:m.rom_models for role,m in machines.items()},
                  elapsed_seconds=time.monotonic()-start, physical_device_IO=0, pow_calls=0,
                  scope='Finite ARM instructions. Correct-reference averages use the identical subset on both sides; raw averages also retain wrong references. Compositions are labeled. This is not hardware timing, universal correctness or all-input speed parity.')
    assert pin(args.elf) == identities['owned_elf'] and pin(ref_elf) == identities['reference_elf']
    (args.output_dir / 'RESULT.json').write_text(json.dumps(result, indent=2) + '\n')
    (args.output_dir / 'WRONG.json').write_text(json.dumps(wrong, indent=2) + '\n')
    print(json.dumps({k:v for k,v in result.items() if k not in ('identities', 'groups', 'ROM_initializers')}), flush=True)
    if result['status'] != 'PASS_FINITE_NUMERICAL_REPLAY':
        raise SystemExit(1)


if __name__ == '__main__':
    main()

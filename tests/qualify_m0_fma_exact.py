#!/usr/bin/env python3
"""Check actual ARM FMA against an independent exact integer oracle.

No pow symbol is called. Every frozen triple executes in all three SIO states.
An MPFR cross-check checks the oracle independently before target execution.
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
from m0_fma_exact_reference import corpus, equivalent, reference, self_test


def pin(path):
    data = Path(path).read_bytes()
    return dict(path=str(Path(path).resolve()), bytes=len(data), sha256=hashlib.sha256(data).hexdigest())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--elf', type=Path, required=True)
    parser.add_argument('--bootrom', type=Path, required=True)
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--samples', type=int, default=2000)
    parser.add_argument('--wall-seconds', type=int, default=600)
    args = parser.parse_args()
    assert 0 <= args.samples <= 100000 and 0 < args.wall_seconds <= 3600
    args.output_dir.mkdir(parents=True, exist_ok=False)
    self_test()
    cases = list(corpus(args.samples))
    inputs = args.output_dir / 'inputs.jsonl.gz'
    classes = Counter()
    frozen = []
    with gzip.open(inputs, 'xt') as file:
        for index, (label, triple) in enumerate(cases):
            expected = reference(*triple)
            row = dict(id=index, construction=label, arguments=[f'{v:016X}' for v in triple],
                       expected=f'{expected:016X}')
            frozen.append(row)
            classes[label] += 1
            file.write(json.dumps(row, separators=(',', ':')) + '\n')
    # Systematically cover each construction and every special-value triple;
    # sampling here validates an independent oracle, not the firmware answer.
    from m0_mpfr_oracle import Oracle
    oracle = Oracle()
    cross_checked = 0
    for row in frozen:
        if row['construction'] == 'special_cartesian' or row['id'] % 31 == 0:
            arguments = tuple(int(v, 16) for v in row['arguments'])
            expected = int(row['expected'], 16)
            other = oracle.reference('fma', *arguments)
            assert equivalent(expected, other), ('integer oracle/MPFR mismatch', row, hex(other))
            cross_checked += 1
    identity = dict(elf=pin(args.elf), bootrom=pin(args.bootrom), inputs=pin(inputs),
                    operator=pin(__file__), integer_oracle=pin(Path(__file__).with_name('m0_fma_exact_reference.py')),
                    MPFR_oracle=pin(Path(__file__).with_name('m0_mpfr_oracle.py')),
                    ARM_machine=pin(Path(__file__).with_name('native_eabi_m0_arm_self_test.py')),
                    ELF_parser=pin(Path(__file__).with_name('check_stm32_vectors.py')),
                    triples=len(cases), math_call_cap=3 * len(cases), stack_bytes=4096,
                    instruction_cap_per_call=1000000, wall_seconds=args.wall_seconds,
                    construction_classes=dict(classes), MPFR_cross_checked=cross_checked,
                    MPFR_version=oracle.version, pow_calls=0)
    (args.output_dir / 'PREPARED.json').write_text(json.dumps(identity, indent=2) + '\n')
    print('PREPARED', len(cases), 'triples;', cross_checked, 'MPFR oracle cross-checks', flush=True)
    from native_eabi_m0_arm_self_test import Machine, SP
    machine = Machine(args.elf, True, stack_bytes=4096, instruction_budget=1000000, bootrom=args.bootrom)
    assert machine.calls == 0 and not machine.rom_initializers and not machine.rom_models
    sio_states = {
        'READY': (0, 0, 0, 0, 0, 0, 1),
        'DIRTY': (17, 3, 17, 3, 5, 2, 3),
        'PENDING': (0x80000001, 7, 0x80000001, 7, 0x11223344, 0x55667788, 2),
    }
    start = time.monotonic()
    counts, wrong, fatal = Counter(), [], None
    instruction_min, instruction_max, instruction_total = None, 0, 0
    attempted = 0
    try:
        with gzip.open(args.output_dir / 'records.jsonl.gz', 'xt') as output:
            for row in frozen:
                arguments = tuple(int(v, 16) for v in row['arguments'])
                expected = int(row['expected'], 16)
                for state, words in sio_states.items():
                    assert attempted < identity['math_call_cap'], 'target call cap'
                    assert time.monotonic() - start <= args.wall_seconds, 'wall deadline'
                    before = struct.pack('<7I', *words)
                    machine.uc.mem_write(0xd0000060, before)
                    attempted += 1
                    actual, _, instructions = machine.call('mk61_m0_fma', *arguments[:2], c=arguments[2], count=True)
                    counts[state] += 1
                    after = bytes(machine.uc.mem_read(0xd0000060, 28))
                    assert before == after, ('FMA changed SIO divider state', row, state)
                    correct = equivalent(actual, expected)
                    result = dict(row, SIO=state, actual=f'{actual:016X}', instructions=instructions, correct=correct)
                    output.write(json.dumps(result, separators=(',', ':')) + '\n')
                    instruction_min = instructions if instruction_min is None else min(instruction_min, instructions)
                    instruction_max = max(instruction_max, instructions)
                    instruction_total += instructions
                    if not correct:
                        wrong.append(result)
                if (row['id'] + 1) % 5000 == 0:
                    print('FMA', row['id'] + 1, '/', len(cases), 'triples;', sum(counts.values()), 'calls;', len(wrong), 'wrong', flush=True)
    except Exception as error:
        fatal = dict(type=type(error).__name__, message=str(error))
    result = dict(status='PASS_FINITE_FMA' if fatal is None and not wrong else 'FAIL',
                  prepared=identity, actual_completed_math_calls=dict(counts), attempted_math_calls=attempted,
                  wrong_rounding=len(wrong), fatal=fatal, instruction_extrema=[instruction_min, instruction_max],
                  total_executed_instructions=instruction_total, maximum_observed_stack_bytes=SP-machine.stack_lowest,
                  elapsed_seconds=time.monotonic()-start, ABI='R4-R11/SP, bounded writes on every call',
                  SIO='All 7 words preserved in READY, DIRTY and PENDING on every triple',
                  physical_device_IO=0, pow_calls=0, scope='Finite tests; no universal proof, hardware cycles or Qfplib FMA comparison claimed.')
    assert pin(args.elf) == identity['elf'] and pin(args.bootrom) == identity['bootrom']
    (args.output_dir / 'RESULT.json').write_text(json.dumps(result, indent=2) + '\n')
    (args.output_dir / 'WRONG.json').write_text(json.dumps(wrong, indent=2) + '\n')
    print(json.dumps({k:v for k,v in result.items() if k != 'prepared'}), flush=True)
    if result['status'] != 'PASS_FINITE_FMA':
        raise SystemExit(1)


if __name__ == '__main__':
    main()

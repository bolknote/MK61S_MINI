"""Attribute executed hard-pow instructions to linked functions, offline."""
import argparse
from bisect import bisect_right
from collections import Counter
import hashlib
import json
from pathlib import Path
import struct
import sys

root = Path.cwd()
sys.path.insert(0, str(root/'tests'))
from native_eabi_m0_arm_self_test import Machine
from unicorn import UC_HOOK_CODE

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--elf', type=Path, required=True)
parser.add_argument('--json', type=Path, required=True)
args = parser.parse_args()
bootrom = root/'research/rp2040-memset-2026-10-21/capture/bootrom.bin'
m = Machine(args.elf, True, stack_bytes=16384, instruction_budget=200000000, bootrom=bootrom)
functions = {}
for table in m.elf.sections:
    if table[1] != 2:
        continue
    strings = m.elf.bytes_at(m.elf.sections[table[6]])
    for offset in range(table[4], table[4]+table[5], table[9]):
        name, value, size, info, other, index = struct.unpack_from('<IIIBBH', m.elf.data, offset)
        if info & 15 == 2:
            label = m.elf.string(strings, name)
            address = value & ~1
            if address not in functions or len(label) < len(functions[address]):
                functions[address] = label
starts = sorted(functions)
counts = Counter()
def instruction(uc, address, size, unused):
    if address < 0x4000:
        counts['ROM'] += 1
        return
    at = bisect_right(starts, address)-1
    counts[functions[starts[at]] if at >= 0 else 'OTHER'] += 1
hook = m.uc.hook_add(UC_HOOK_CODE, instruction)
m.uc.ctl_flush_tb()
inputs = root/'research/m0-pow-checked-20261022/hard-pow-inputs.json'
original = json.loads(inputs.read_text())
qfp = json.loads((root/'.build/m0-pow-square-kernel-v98-20261022/hard-profile.json').read_text())
qfp_cases = {(c['a'], c['b']): c for g in qfp['groups'] for c in g['cases']}
groups = []
for group in original['groups']:
    total = Counter()
    cases = []
    for case in group['cases']:
        counts.clear()
        x, y, expected = (int(case[k], 16) for k in ('a', 'b', 'expected'))
        got, _, instructions = m.call('_ZN12compact_math3powEdd', x, y, count=True)
        assert got == expected
        assert sum(counts.values()) == instructions
        previous = qfp_cases[case['a'], case['b']]
        cases.append(dict(a=case['a'], b=case['b'], expected=case['expected'],
                          instructions=instructions, qfplib_instructions=previous['qfplib']['instructions'],
                          functions=dict(counts)))
        total.update(counts)
    row = dict(stream=group['stream'], cases=cases, mean_instructions=sum(c['instructions'] for c in cases)/len(cases),
               function_mean_instructions={name: count/len(cases) for name, count in total.most_common()})
    groups.append(row)
    print(group['stream'], row['mean_instructions'], list(row['function_mean_instructions'].items())[:10], flush=True)
record = dict(status='PASS_DIAGNOSTIC_ATTRIBUTION', groups=groups,
              elf_sha256=hashlib.sha256(args.elf.read_bytes()).hexdigest(),
              inputs_sha256=hashlib.sha256(inputs.read_bytes()).hexdigest(),
              producer_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              scope='Executed instructions, attributed to the nearest preceding typed function entry or ROM. Function extents and alias spelling make this a diagnostic partition, not a linker equivalence proof. Totals exactly match the independent instruction counter; results match the saved MPFR inputs. No device cycles or all-input speed claims.')
args.json.parent.mkdir(parents=True, exist_ok=True)
args.json.write_text(json.dumps(record, indent=2)+'\n')

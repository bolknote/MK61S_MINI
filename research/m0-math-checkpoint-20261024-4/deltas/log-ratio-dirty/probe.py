"""Probe public ln entry, IEEE edges and representative normal controls."""
from pathlib import Path
import hashlib
import json
import struct
import sys

sys.dont_write_bytecode = True
W = Path(__file__).resolve().parent
ROOT = W.parents[1]
P = ROOT / '.build/m0-asin-scaled-bound-v164-20261023'
Q = ROOT / '.build/m0-float-fma-qualification-20261023'
sys.path.insert(0, str(Q))
sys.path.insert(0, str(Q / 'support'))
from native_eabi_m0_arm_self_test import Machine, SP
from check_stm32_vectors import ElfImage
from m0_mpfr_oracle import Oracle, bits
from oracles import equal

ROM = ROOT / 'research/rp2040-memset-2026-10-21/capture/bootrom.bin'
ELF = P / 'firmware/mk61s-picocalc-pico-h.elf'
REF = ROOT / '.build/m0-v138-execution-20261023/reference/reference.elf'
b = json.loads((W / 'candidate-build.json').read_text())
assert hashlib.sha256((W / 'candidate.elf').read_bytes()).hexdigest() == b['ELF_sha256']
assert hashlib.sha256((W / 'native_eabi_m0_log70_center.inc').read_bytes()).hexdigest() == b['source_include_sha256']
machines = {'resident': Machine(ELF, True, bootrom=ROM), 'Qfplib': Machine(REF, True)}
for label in ('parent', 'candidate'):
    m = Machine(ELF, True, bootrom=ROM)
    image = ElfImage(W / (('control' if label == 'parent' else label) + '.elf'))
    image.load(m.uc)
    m.elf.symbols[label + '_ln'] = image.symbols['mk61_m0_ln']
    machines[label] = m
old = [r for r in json.loads((P / 'slower-inputs.json').read_text())['rows'] if r['operation'] == 'ln']
jobs = {int(r['x'], 16): 'historical' for r in old}
for x in [0, 1, 2, 3, (1 << 51), (1 << 52) - 1, 1 << 52, (1 << 52) + 1,
          0x7ff0000000000000, 0x7ff0000000000001, 0x7ff8000000000000, 0x7fffffffffffffff]:
    for sign in (0, 1 << 63):
        jobs.setdefault(x | sign, 'IEEE')
for x in [1/1024, 1/2, 0.9, 0.99, 1., 1.001, 1.01, 1.1, 2., 4., 16., 100., 1e100]:
    for sign in (1, -1):
        jobs.setdefault(bits(x*sign), 'normal_control')
states = {'READY': struct.pack('<7I', 0, 0, 0, 0, 0, 0, 1),
          'DIRTY': struct.pack('<7I', 17, 3, 17, 3, 5, 2, 3)}
o = Oracle()
rows = []
for raw, group in jobs.items():
    expected = o.reference('ln', raw)
    for state_name, state in states.items():
        outputs, counts, correct = {}, {}, {}
        for label, m in machines.items():
            m.uc.mem_write(0xd0000060, state)
            name = 'mk61_m0_ln' if label == 'resident' else 'qfp_dln' if label == 'Qfplib' else label + '_ln'
            got, _, cost = m.call(name, raw, count=True)
            outputs[label] = f'{got:016X}'
            counts[label] = cost
            correct[label] = equal(got, expected, 64)
            if label != 'Qfplib':
                assert correct[label], (label, hex(raw), hex(got), hex(expected))
            after = bytes(m.uc.mem_read(0xd0000060, 28))
            if state_name == 'DIRTY':
                assert after == state
            else:
                assert not (struct.unpack('<7I', after)[6] & 2)
        assert outputs['candidate'] == outputs['parent'] == outputs['resident']
        rows.append(dict(x=f'{raw:016X}', group=group, SIO=state_name, expected=f'{expected:016X}',
                         outputs=outputs, instructions=counts, correct=correct))
report = dict(status='PASS_PRIVATE_DIRTY_LOG_RATIO_PUBLIC_PROBE_NOT_QUALIFICATION', cases=len(rows), rows=rows,
              source_sha256=b['source_include_sha256'], candidate_ELF_sha256=b['ELF_sha256'],
              candidate_stack_bytes=SP-machines['candidate'].stack_lowest,
              parent_stack_bytes=SP-machines['parent'].stack_lowest,
              MPFR_version=o.version, hardware_accessed=False)
(W / 'probe.json').write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps({k: v for k, v in report.items() if k != 'rows'}, indent=2))
print(json.dumps([{k: r[k] for k in ('x', 'instructions')} for r in rows
                  if r['group'] == 'historical' and r['SIO'] == 'DIRTY'], indent=2))

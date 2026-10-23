"""Retain the full independent audit, freeze future vectors, run public canaries."""
import hashlib
import json
from pathlib import Path
import struct
import sys

root = Path.cwd()
work = Path(__file__).resolve().parent
sys.path.insert(0, str(root/'tests'))
from native_eabi_m0_arm_self_test import Machine, SP


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


elf = work/'firmware/mk61s-picocalc-pico-h.elf'
matrix = json.loads((work/'instruction-matrix.json').read_text())
old_matrix = json.loads((root/'.build/m0-pow-tiny-stable-v142-20261023/instruction-matrix.json').read_text())
audit = json.loads((work/'result.json').read_text())
old_audit_path = root/'.build/m0-cold-domain-audit-20261023/result.json'
old_audit = json.loads(old_audit_path.read_text())
tiny = json.loads((work/'tiny-profile.json').read_text())
assert matrix['owned_elf_sha256'] == audit['elf_sha256'] == tiny['elf_sha256'] == sha(elf)
assert matrix['groups'] == old_matrix['groups'] and matrix['chunks'] == old_matrix['chunks']
assert len(matrix['chunks']) == 119 and len(audit['groups']) == 53
changed = []
for before, after in zip(old_audit['groups'], audit['groups'], strict=True):
    assert (before['operation'], before['stream']) == (after['operation'], after['stream'])
    assert len(before['rows']) == len(after['rows']) == 128
    own_changed = False
    for b, a in zip(before['rows'], after['rows'], strict=True):
        assert {k:v for k,v in a.items() if k!='own_instructions'} == {k:v for k,v in b.items() if k!='own_instructions'}
        own_changed |= b['own_instructions'] != a['own_instructions']
    if own_changed:
        assert before['operation'] == 'pow'
        assert after['mean_instructions']['own'] < after['mean_instructions']['qfplib']
        assert before['mean_instructions']['own'] > before['mean_instructions']['qfplib']
        changed.append(dict(operation='pow', stream=after['stream'],
                            before=before['mean_instructions']['own'],
                            own=after['mean_instructions']['own'],
                            qfplib=after['mean_instructions']['qfplib'],
                            qfplib_wrong=after['qfplib_wrong']))
assert {g['stream'] for g in changed} == {
    'cutoff_adjacent_y_2p-64', 'cutoff_adjacent_y_2p-63', 'cutoff_adjacent_y_2p-62',
    'cutoff_adjacent_y_2p-60', 'cutoff_adjacent_y_2p-50',
    'huge_finite_exponents', 'near_one_variable_exponent'}

tiny_rows = [r for r in tiny['cases_data'] if r['positive_normal_base']]
assert len(tiny_rows) == 168
assert all(r['own'] == r['expected'] == r['qfplib'] for r in tiny_rows)
assert all(r['own_instructions'] < r['qfplib_instructions'] for r in tiny_rows)
groups = [dict(operation=r['operation'], stream=r['stream'], cases=r['cases'],
               mean_instructions=r['mean_instructions'],
               owned_wrong_rounding=r['owned_wrong_rounding'],
               qfplib_wrong_results=r['qfplib_wrong_results'], origin='original117')
          for r in matrix['groups']]
groups += [dict(operation=r['operation'], stream=r['stream'], cases=r['cases'],
                mean_instructions=r['mean_instructions'], owned_wrong_rounding=r['own_wrong'],
                qfplib_wrong_results=r['qfplib_wrong'], origin='independent53',
                both_correct_cases=r['both_correct_cases'],
                both_correct_mean_instructions=r['both_correct_mean_instructions'],
                both_correct_own_slower=r['both_correct_own_slower'])
           for r in audit['groups']]
groups.append(dict(operation='pow', stream='tiny_exponents_normal_bases', cases=168,
                   mean_instructions=dict(own=tiny['own_mean_instructions'], qfplib=tiny['qfplib_mean_instructions']),
                   owned_wrong_rounding=0, qfplib_wrong_results=0, origin='tiny168'))
faster = sum(r['mean_instructions']['own'] < r['mean_instructions']['qfplib'] for r in groups)
equal = sum(r['mean_instructions']['own'] == r['mean_instructions']['qfplib'] for r in groups)
slower = sum(r['mean_instructions']['own'] > r['mean_instructions']['qfplib'] for r in groups)
assert (len(groups), faster, equal, slower) == (171, 155, 2, 14)
assert sum(r['cases'] for r in groups) == 30304
report = dict(status='PASS_EXPANDED_COVERAGE_NOT_A_SPEED_PASS', owned_elf_sha256=sha(elf),
              groups=groups, group_count=len(groups), cases=sum(r['cases'] for r in groups),
              instruction_groups_faster=faster, instruction_groups_equal=equal,
              instruction_groups_slower=slower, owned_wrong_rounding=0,
              original119_chunk_records_identical_V142=True,
              original117_group_records_identical_V142=True,
              newly_improved_groups=changed,
              unchanged_independent_groups=46,
              remaining_raw_slower_groups=[r for r in groups if r['mean_instructions']['own'] > r['mean_instructions']['qfplib']],
              both_correct_subset_mean_deficits=[r for r in groups if r.get('both_correct_cases',0) and r['both_correct_mean_instructions']['own'] > r['both_correct_mean_instructions']['qfplib']],
              source_reports={n:sha(work/n) for n in ('instruction-matrix.json','result.json','tiny-profile.json')},
              old_independent_report_sha256=sha(old_audit_path), producer_sha256=sha(__file__),
              scope='All117 original groups, all53 independently selected groups and168 original normal-base tiny-y vectors. Retains raw deficits even when Qfplib gives incorrect values. ARM instructions with modeled SIO division, not physical cycles or a universal input guarantee.',
              hardware_accessed=False, approved_hardware_package_changed=False,
              general_pow_totality_proved=False, goal_complete=False)
(work/'extended-instruction-matrix.json').write_text(json.dumps(report, indent=2)+'\n')

corpus = dict(status='FROZEN_OFFLINE_FUTURE_TIMING_VECTORS_NOT_APPROVED_FOR_HARDWARE',
              source_reports=report['source_reports'], producer_sha256=sha(__file__),
              groups=[dict(operation=g['operation'], stream=g['stream'],
                           vectors=[dict(a=r['x'],b=r['y'],expected=r['expected']) for r in g['rows']])
                      for g in audit['groups']])
corpus['groups'].append(dict(operation='pow', stream='tiny_exponents_normal_bases',
                            vectors=[dict(a=r['x'],b=r['y'],expected=r['expected']) for r in tiny_rows]))
corpus['cases'] = sum(len(g['vectors']) for g in corpus['groups'])
assert corpus['cases'] == 6952
(work/'future-timing-corpus.json').write_text(json.dumps(corpus, indent=2)+'\n')

canary = root/'.build/m0-v138-execution-20261023/inputs/119.bin'
vectors = list(struct.iter_unpack('<3Q', canary.read_bytes()[32:]))
assert len(vectors) == 30
machine = Machine(elf, True, stack_bytes=16384, instruction_budget=200000000,
                  bootrom=root/'research/rp2040-memset-2026-10-21/capture/bootrom.bin')
digest = hashlib.sha256()
for x, y, expected in vectors:
    got = machine.call('_ZN12compact_math3powEdd', x, y)[0]
    assert got == expected, (hex(x), hex(y), hex(got), hex(expected))
    digest.update(struct.pack('<4Q', x, y, expected, got))
canary_report = dict(status='PASS_FROZEN_PUBLIC_POW_CANARY_ON_V144', cases=30,
                     wrong_rounding=0, result_sha256=digest.hexdigest(),
                     input_sha256=sha(canary), elf_sha256=sha(elf),
                     maximum_observed_stack_bytes=SP-machine.stack_lowest,
                     producer_sha256=sha(__file__),
                     scope='Actual public pow on the30 frozen negative-factor vectors. Expected directed MPFR bits are preserved. Emulator execution, not a physical acceptance receipt.',
                     hardware_accessed=False, production_promoted=False, goal_complete=False)
(work/'public-canary.json').write_text(json.dumps(canary_report, indent=2)+'\n')
print('PASS:171 groups155 faster/2 equal/14 slower; seven new improvements;30 public canaries. Goal remains open.', flush=True)

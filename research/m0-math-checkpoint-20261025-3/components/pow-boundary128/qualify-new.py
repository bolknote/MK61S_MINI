"""Fresh independent MPFR/public controls; keep every Qfplib output and cost."""
from collections import Counter
import json, math, random, sys, time
sys.dont_write_bytecode = True
from harness import *

assert not (HERE / 'FROZEN.json').exists()
assert not (HERE / 'new-qualification.json').exists()
jobs = {}
for row in json.loads((PARENT / 'new-qualification.json').read_bytes())['rows']:
    jobs.setdefault((int(row['x'], 16), int(row['y'], 16)), row['group'])
assert len(jobs) == 5127

machines = {name: machine(name) for name in ['parent', 'control', 'candidate', 'Qfplib']}
traces = {name: trace_boundaries(m,name) for name, m in machines.items() if name != 'Qfplib'}
references = ['qfp_composed_pow', 'qfp_composed_pow_exact', 'qfp_composed_pow_integer']
oracle = Oracle()
rows, shortcuts, actual_square_calls = [], 0, 0
start = time.monotonic()
for i, ((x, y), group) in enumerate(jobs.items()):
    if i % 64 == 0:
        print('boundary128-new', i, '/', len(jobs), 'elapsed', round(time.monotonic() - start, 1), flush=True)
    expected = oracle.reference('pow', x, y)
    shortcuts += any((v & 0x7fffffffffffffff) > 0x7ff0000000000000 and not v & (1 << 51)
                     for v in [x, y])
    for state_name, state in states.items():
        outputs, counts, correct, arguments = {}, {}, {}, {}
        for label in ['parent', 'control', 'candidate', *references]:
            m = machines[label if label in machines else 'Qfplib']
            if label not in references:
                traces[label][0].clear();traces[label][1].clear()
            m.uc.mem_write(0xd0000060, state)
            got, _, cost = m.call(label if label in references else '_ZN12compact_math3powEdd',
                                  x, y, count=True)
            outputs[label], counts[label] = f'{got:016X}', cost
            correct[label] = equal(got, expected, 64)
            state_after(m, state)
            if label not in references:
                assert correct[label], (i, label, hex(x), hex(y), hex(got), hex(expected))
                arguments[label] = dict(entries=list(traces[label][0]),operands=list(traces[label][1]))
        assert len({outputs[n] for n in ['parent', 'control', 'candidate']}) == 1
        assert counts['control'] == counts['parent']
        assert arguments['parent'] == arguments['control'] == arguments['candidate']
        delta = counts['candidate'] - counts['parent']
        assert counts['candidate'] == counts['parent'] + delta and delta <= 0
        actual_square_calls += len(arguments['candidate']['entries'])
        rows.append(dict(x=f'{x:016X}', y=f'{y:016X}', group=group, SIO=state_name,
                         expected=f'{expected:016X}', outputs=outputs, instructions=counts,
                         correct=correct, boundary_calls=arguments['candidate']['entries'], midpoint_operands=arguments['candidate']['operands']))

def loss(row, name):
    return any(row['correct'][q] and row['instructions'][name] > row['instructions'][q]
               for q in references)
old = {(r['x'], r['y']) for r in rows if loss(r, 'parent')}
new = {(r['x'], r['y']) for r in rows if loss(r, 'candidate')}
assert not new - old
result = dict(status='PASS_FRESH_MPFR_POW_CONTROLS_AFTER_EXACT_BOUNDARY128',
              candidate_ELF_sha256=sha(HERE / 'candidate.elf'), unique_pairs=len(jobs),
              state_rows=len(rows), fresh_ARM_calls=6 * len(rows),
              fresh_candidate_calls=len(rows), fresh_parent_calls=len(rows),
              fresh_layout_control_calls=len(rows), fresh_Qfplib_calls=3 * len(rows),
              oracle_evaluations=len(jobs), actual_directed_MPFR_inputs=len(jobs) - shortcuts,
              sNaN_policy_shortcuts=shortcuts, MPFR_version=oracle.version,
              all_actual_parent_control_candidate_bits_identical=True,
              all_kernel_argument_sequences_identical=True, all_midpoint_operand_bytes_identical=True, no_parent_cost_increases=True,
              candidate_wrong=0, new_raw_losses=0, parent_raw_loss_pairs=len(old),
              candidate_raw_loss_pairs=len(new), fixed_raw_pairs=len(old - new),
              actual_candidate_boundary_calls=actual_square_calls,
              wrong_Qfplib_state_variants_retained=sum(not r['correct'][q] for r in rows for q in references),
              strict_quiet_NaN_reference_classification=True, no_nominal_reference_domain_filter=True,
              pilot1836_not_added_to_qualification=True,
              cost_delta_histogram=dict(sorted(Counter(r['instructions']['candidate'] - r['instructions']['parent']
                                                       for r in rows).items())),
              observed_stacks={n: SP - m.stack_lowest for n, m in machines.items() if n != 'Qfplib'},
              elapsed_seconds=time.monotonic() - start, rows=rows, hardware_accessed=False)
(HERE / 'new-qualification.json').write_text(json.dumps(result, indent=2) + '\n')
print(json.dumps({k: v for k, v in result.items() if k != 'rows'}, indent=2))

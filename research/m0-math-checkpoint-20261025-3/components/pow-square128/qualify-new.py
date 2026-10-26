"""Fresh independent MPFR/public controls; keep every Qfplib output and cost."""
from collections import Counter
import json, math, random, sys, time
sys.dont_write_bytecode = True
from harness import *

assert not (HERE / 'FROZEN.json').exists()
assert not (HERE / 'new-qualification.json').exists()
jobs = {}
def add(x, y, group):
    jobs.setdefault((x, y), group)
for row in json.loads((BASE / 'original153.json').read_bytes())['rows']:
    add(int(row['x'], 16), int(row['y'], 16), 'original153_reexecuted_pilot_excluded')
special = [0, 1 << 63, 1, (1 << 63) | 1, 0x000fffffffffffff, 0x0010000000000000,
           bits(0.5), bits(-0.5), bits(1.), bits(-1.), bits(2.), bits(-2.),
           0x7fefffffffffffff, 0xffefffffffffffff, 0x7ff0000000000000,
           0xfff0000000000000, 0x7ff0000000000001, 0xfff0000000000001,
           0x7ff8123456789abc, 0xfff8123456789abc]
for x in special:
    for y in special:
        add(x, y, 'IEEE_cartesian')
rng = random.Random(0x614128025A)
for denominator in [2, 4, 8, 16, 32, 64, 128]:
    for exponent in [-3, -1, 0, 1, 4]:
        for _ in range(4):
            target = math.ldexp(1. + rng.random(), exponent)
            # Host pow only selects inputs. Every actual binary64 pair below
            # is independently validated with directed MPFR, never host libm.
            center = bits(target ** denominator)
            for offset in [-1, 0, 1]:
                for numerator in [1, 3, 5, 7]:
                    for sign in [-1, 1]:
                        add(center + offset, bits(sign * numerator / denominator),
                            'root_near_exact_output_cell')
for i in range(1024):
    exponent = rng.choice([1, 2, 17, 511, 1022, 1023, 1024, 1535, 2045, 2046])
    x = (exponent << 52) | rng.getrandbits(52)
    y = bits(rng.choice([-127, -63, -31, -7, -1, 1, 3, 5, 31, 63, 127]) /
             rng.choice([2, 4, 8, 16, 32, 64, 128]))
    if i % 17 == 0:
        y = (y & 0xfff0000000000000) | rng.getrandbits(52)
    add(x, y, 'full_mantissa_root_exponent_bands')
for x in range(1, 33):
    for y in [-127/128, -0.5, -1/128, 1/128, 0.5, 127/128]:
        add(x, bits(y), 'subnormal_root_inputs')

machines = {name: square_machine(name) for name in ['parent', 'control', 'candidate', 'Qfplib']}
traces = {name: square_trace(m) for name, m in machines.items() if name != 'Qfplib'}
references = ['qfp_composed_pow', 'qfp_composed_pow_exact', 'qfp_composed_pow_integer']
oracle = Oracle()
rows, shortcuts, actual_square_calls = [], 0, 0
start = time.monotonic()
for i, ((x, y), group) in enumerate(jobs.items()):
    if i % 64 == 0:
        print('square128-new', i, '/', len(jobs), 'elapsed', round(time.monotonic() - start, 1), flush=True)
    expected = oracle.reference('pow', x, y)
    shortcuts += any((v & 0x7fffffffffffffff) > 0x7ff0000000000000 and not v & (1 << 51)
                     for v in [x, y])
    for state_name, state in states.items():
        outputs, counts, correct, arguments = {}, {}, {}, {}
        for label in ['parent', 'control', 'candidate', *references]:
            m = machines[label if label in machines else 'Qfplib']
            if label not in references:
                traces[label].clear()
            m.uc.mem_write(0xd0000060, state)
            got, _, cost = m.call(label if label in references else '_ZN12compact_math3powEdd',
                                  x, y, count=True)
            outputs[label], counts[label] = f'{got:016X}', cost
            correct[label] = equal(got, expected, 64)
            state_after(m, state)
            if label not in references:
                assert correct[label], (i, label, hex(x), hex(y), hex(got), hex(expected))
                arguments[label] = list(traces[label])
        assert len({outputs[n] for n in ['parent', 'control', 'candidate']}) == 1
        assert counts['control'] == counts['parent']
        assert arguments['parent'] == arguments['control'] == arguments['candidate']
        delta = sum(c['new_cost'] - c['old_cost'] for c in arguments['candidate'])
        assert counts['candidate'] == counts['parent'] + delta and delta <= 0
        actual_square_calls += len(arguments['candidate'])
        rows.append(dict(x=f'{x:016X}', y=f'{y:016X}', group=group, SIO=state_name,
                         expected=f'{expected:016X}', outputs=outputs, instructions=counts,
                         correct=correct, square_calls=arguments['candidate']))

def loss(row, name):
    return any(row['correct'][q] and row['instructions'][name] > row['instructions'][q]
               for q in references)
old = {(r['x'], r['y']) for r in rows if loss(r, 'parent')}
new = {(r['x'], r['y']) for r in rows if loss(r, 'candidate')}
assert not new - old
result = dict(status='PASS_FRESH_INDEPENDENT_POW_CONTROLS_AFTER_SQUARE128',
              candidate_ELF_sha256=sha(HERE / 'candidate.elf'), unique_pairs=len(jobs),
              state_rows=len(rows), fresh_ARM_calls=6 * len(rows),
              fresh_candidate_calls=len(rows), fresh_parent_calls=len(rows),
              fresh_layout_control_calls=len(rows), fresh_Qfplib_calls=3 * len(rows),
              oracle_evaluations=len(jobs), actual_directed_MPFR_inputs=len(jobs) - shortcuts,
              sNaN_policy_shortcuts=shortcuts, MPFR_version=oracle.version,
              all_actual_parent_control_candidate_bits_identical=True,
              all_kernel_argument_sequences_identical=True, all_costs_match_kernel_delta=True,
              candidate_wrong=0, new_raw_losses=0, parent_raw_loss_pairs=len(old),
              candidate_raw_loss_pairs=len(new), fixed_raw_pairs=len(old - new),
              actual_candidate_kernel_calls=actual_square_calls,
              wrong_Qfplib_state_variants_retained=sum(not r['correct'][q] for r in rows for q in references),
              strict_quiet_NaN_reference_classification=True, no_nominal_reference_domain_filter=True,
              pilot918_not_added_to_qualification=True,
              cost_delta_histogram=dict(sorted(Counter(r['instructions']['candidate'] - r['instructions']['parent']
                                                       for r in rows).items())),
              observed_stacks={n: SP - m.stack_lowest for n, m in machines.items() if n != 'Qfplib'},
              elapsed_seconds=time.monotonic() - start, rows=rows, hardware_accessed=False)
(HERE / 'new-qualification.json').write_text(json.dumps(result, indent=2) + '\n')
print(json.dumps({k: v for k, v in result.items() if k != 'rows'}, indent=2))

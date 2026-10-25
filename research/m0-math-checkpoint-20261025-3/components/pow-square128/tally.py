"""Recount all saved public evidence without ARM/MPFR or reference filtering."""
from pathlib import Path
from collections import Counter
import gzip, hashlib, json, sys
sys.dont_write_bytecode = True
W = Path(__file__).resolve().parent
ROOT = W.parents[1]
BASE = ROOT / '.build/m0-pow-exp-table-product-20261025'
assert not (W / 'FROZEN.json').exists()
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
full = json.loads((W / 'qualification.json').read_bytes())
new = json.loads((W / 'new-qualification.json').read_bytes())
unit = json.loads((W / 'unit-proof.json').read_bytes())
jobs = {}
def add(row, output, cost, parent, references):
    key = row['x'], row['y'], row['SIO']
    values = dict(candidate=output, candidate_instructions=cost,
                  parent_instructions=parent, expected=row['expected'])
    saved = jobs.setdefault(key, values | dict(references={}))
    assert all(saved[k] == v for k, v in values.items()), key
    for label, ref in references.items():
        if label in saved['references']:
            assert saved['references'][label] == ref, (key, label)
        saved['references'][label] = ref
with gzip.open(W / 'qualification-records.jsonl.gz', 'rt') as stream:
    for line in stream:
        row = json.loads(line)
        assert row['candidate'] == row['parent_output']
        delta = sum(c['new_cost'] - c['old_cost'] for c in row['square_calls'])
        assert delta <= 0 and row['candidate_instructions'] == row['parent_cost'] + delta
        add(row, row['candidate'], row['candidate_instructions'], row['parent_cost'], row['references'])
assert len(jobs) == 232936
overlap = 0
for row in new['rows']:
    overlap += (row['x'], row['y'], row['SIO']) in jobs
    assert all(row['correct'][n] for n in ['parent', 'control', 'candidate'])
    refs = {name: dict(output=row['outputs'][name], instructions=row['instructions'][name],
                       correct_Qfplib=row['correct'][name])
            for name in ['qfp_composed_pow', 'qfp_composed_pow_exact', 'qfp_composed_pow_integer']}
    add(row, row['outputs']['candidate'], row['instructions']['candidate'], row['instructions']['parent'], refs)

def equal(a, b):
    a, b = int(a, 16), int(b, 16)
    return bool((a & 0x7fffffffffffffff) > 0x7ff0000000000000 and a & (1 << 51)) if (
        b & 0x7fffffffffffffff) > 0x7ff0000000000000 else a == b
old_loss, new_loss = set(), set()
comparison, deltas = Counter(), Counter()
wrong = variants = 0
remaining = []
for key, row in jobs.items():
    assert equal(row['candidate'], row['expected'])
    cost, parent = row['candidate_instructions'], row['parent_instructions']
    deltas[cost - parent] += 1
    assert cost <= parent
    for name, ref in row['references'].items():
        variants += 1
        assert ref['correct_Qfplib'] == equal(ref['output'], row['expected']), (key, name, ref)
        if not ref['correct_Qfplib']:
            wrong += 1
            continue
        qcost = ref['instructions']
        comparison['faster' if cost < qcost else 'equal' if cost == qcost else 'slower'] += 1
        if parent > qcost:
            old_loss.add(key[:2])
        if cost > qcost:
            assert parent > qcost
            new_loss.add(key[:2])
            remaining.append(dict(x=key[0], y=key[1], SIO=key[2], reference=name,
                                  parent=parent, candidate=cost, Qfplib=qcost,
                                  candidate_output=row['candidate'], Qfplib_output=ref['output']))
assert not new_loss - old_loss
original, counts = [], {name: Counter() for name in ['parent', 'candidate']}
for row in json.loads((BASE / 'original153.json').read_bytes())['rows']:
    states = []
    for state in ['READY', 'DIRTY']:
        j = jobs[row['x'], row['y'], state]
        ref = j['references'][row['reference']]
        assert ref['correct_Qfplib']
        states.append(dict(SIO=state, parent=j['parent_instructions'], candidate=j['candidate_instructions'], Qfplib=ref['instructions']))
    for name in counts:
        direction = 'slower' if any(r[name] > r['Qfplib'] for r in states) else (
            'equal' if any(r[name] == r['Qfplib'] for r in states) else 'strict')
        counts[name][direction] += 1
    original.append(dict(x=row['x'], y=row['y'], stream=row['stream'], reference=row['reference'], states=states))
assert counts['parent'] == dict(slower=35, strict=118)
assert counts['candidate'] == dict(slower=34, strict=119)
assert full['fresh_candidate_ARM_calls'] + new['fresh_ARM_calls'] + unit['actual_ARM_calls'] == 330880
summary = dict(status='PASS_SAVED_PUBLIC_UNION_ACCOUNTING_STRICT_QUIET_NAN_POLICY',
               union_unique_pairs=len({key[:2] for key in jobs}), union_states=len(jobs),
               union_reference_state_variants=variants, new_control_overlap_states=overlap,
               parent_raw_loss_pairs=len(old_loss), candidate_raw_loss_pairs=len(new_loss),
               fixed_raw_pairs=len(old_loss - new_loss), new_raw_losses=0,
               additional_measured_preexisting_loss_pairs=len(old_loss) - full['parent_raw_loss_pairs'],
               correct_Qfplib_comparison=dict(comparison), wrong_Qfplib_state_variants_retained=wrong,
               all_reference_flags_match_raw_strict_quiet_NaN_policy=True,
               candidate_wrong=0, parent_cost_delta_histogram=dict(sorted(deltas.items())),
               parent_cost_increase_states=0,
               original153={name: dict(value) for name, value in counts.items()},
               qualified_fresh_ARM_calls=330880,
               fresh_public_ARM_calls=full['fresh_candidate_ARM_calls'] + new['fresh_ARM_calls'],
               fresh_bare_ARM_calls=unit['actual_ARM_calls'],
               actual_fresh_directed_MPFR_inputs=new['actual_directed_MPFR_inputs'],
               sNaN_shortcuts=new['sNaN_policy_shortcuts'], oracle_evaluations=new['oracle_evaluations'],
               pilot918_and_route_study70_not_qualified=True,
               inherited_parent_Qfplib_old_MPFR_not_fresh=True, goal_complete=False)
(W / 'union-summary.json').write_text(json.dumps(summary, indent=2) + '\n')
(W / 'original153.json').write_text(json.dumps(dict(rows=original), indent=2) + '\n')
(W / 'remaining-expanded.json').write_text(json.dumps(dict(rows=remaining), indent=2) + '\n')
with gzip.GzipFile(filename=str(W / 'union-records.jsonl.gz'), mode='wb', mtime=0) as stream:
    for key, row in jobs.items():
        stream.write((json.dumps(dict(x=key[0], y=key[1], SIO=key[2], **row), separators=(',', ':')) + '\n').encode())
print(json.dumps(summary, indent=2))

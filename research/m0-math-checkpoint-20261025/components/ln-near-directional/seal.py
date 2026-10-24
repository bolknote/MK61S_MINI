"""Freeze the completed near-ln component, retaining expanded losses."""
from pathlib import Path
from collections import Counter
import hashlib
import json

W = Path(__file__).resolve().parent
ROOT = W.parents[1]
BASE = ROOT / '.build/m0-ln-enclosure-20261024'
assert not (W / 'result.json').exists()
def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()
def read(name):
    return json.loads((W / name).read_text())
q, iso, body, cert, unit = [read(n) for n in ['qualification.json','isolation.json','public-body-proof.json','certificate.json','pack-unit-proof.json']]
source, elf = sha(W / 'native_eabi_m0_log70.inc'), sha(W / 'candidate.elf')
assert source == 'ba084abda5a2c3d71071ae800224c552efce2652d2838735782cd16e764b090e'
assert elf == '272ecb817c396bd655cb19132f4df97c4d5d9da6046dc999a94a164de55e4425'
for d in (q, iso, body, cert):
    assert d['source_sha256'] == source and d['candidate_ELF_sha256'] == elf
assert unit['source_sha256'] == source and unit['actual_ARM_calls'] == 16896
assert q['cases'] == len(q['rows']) == 65880 and q['unique_inputs'] == 32940
assert q['actual_ARM_calls'] == 263520 and q['retained_parent_counts_checked'] == 39318
assert all(r['correct']['candidate'] and r['correct']['parent'] and
           r['outputs']['candidate'] == r['outputs']['parent'] for r in q['rows'])
assert all(g['newly_slower_correct_Qfplib'] == 0 for g in q['groups'])
assert iso['allocated_object_bytes_delta'] == 248 and all(c['allocated_code_and_data_identical'] for c in iso['contexts'])
assert body['entire_ELF_byte_exact_without_exclusions']
fixed = [r for r in q['rows'] if r['correct']['Qfplib'] and r['instructions']['parent'] > r['instructions']['Qfplib'] >= r['instructions']['candidate']]
losses = q['remaining_slower_correct_Qfplib']
old = json.loads((BASE / 'remaining-slower.json').read_text())['rows']
old_inputs = {r['x'] for r in old}
old_fixed = {r['x'] for r in fixed} & old_inputs
assert len(fixed) == 88 and len({r['x'] for r in fixed}) == 44 and len(old_fixed) == 15
assert len({r['x'] for r in losses}) == 51
regress = q['regressions_vs_parent']
change = Counter('faster' if r['instructions']['candidate'] < r['instructions']['parent'] else
                 'equal' if r['instructions']['candidate'] == r['instructions']['parent'] else 'slower' for r in q['rows'])
deltas = [r['instructions']['candidate']-r['instructions']['parent'] for r in regress]
(W / 'remaining-slower.json').write_text(json.dumps(dict(status='EXPANDED_LN_SPEED_INPUTS_OPEN',raw_inputs=51,state_rows=len(losses),rows=losses),indent=2)+'\n')
(W / 'regressions.json').write_text(json.dumps(dict(status='ALL_PARENT_REGRESSIONS_RETAINED',state_rows=len(regress),delta_range=[min(deltas),max(deltas)],rows=regress),indent=2)+'\n')
pins = dict(json.loads((BASE / 'input-pins.json').read_text())['files'])
for name,digest in pins.items():
    assert sha(ROOT / name) == digest, name
for name in ['result.json','qualification.json','candidate.elf','candidate-full.o','certificate.json','isolation.json']:
    p = BASE / name
    pins[str(p.relative_to(ROOT))] = sha(p)
pins['.build/m0-ln-near-rounding-20261024/native_eabi_m0_log70.inc'] = source
(W / 'input-pins.json').write_text(json.dumps(dict(status='READ_ONLY_INPUTS_PINNED',files=pins),indent=2)+'\n')
report = dict(status='AUTHOR_PASS_NEAR_LN_DIRECTIONAL_WITH_51_EXPANDED_SPEED_INPUTS_OPEN',
    unique_inputs=32940,public_state_cases=65880,all_cases_profiled=True,
    qualified_public_ARM_calls=263520,qualified_bare_packer_ARM_calls=16896,
    total_qualified_ARM_calls=280416,discarded_generator_error_run_not_counted=True,
    candidate_wrong=0,retained_parent_counts_checked=39318,groups=q['groups'],
    old34_raw_inputs_fixed=15,expanded_raw_deficits_fixed=44,new_correct_Qfplib_deficits=0,
    remaining_expanded_raw_inputs=51,remaining_state_rows=len(losses),
    historical_ln10_total_fixed=6,historical_ln10_remaining=4,
    vs_parent=dict(change),regression_instruction_range=[min(deltas),max(deltas)],
    candidate_public_stack=q['candidate_stack_bytes'],parent_public_stack_same_corpus=q['parent_stack_bytes'],
    allocated_code_bytes_delta=248,new_tables_global_RAM_or_libgcc=False,
    M4_generic_M0_allocated_controls_equal=True,whole_public_ELF_rebuild_byte_exact=True,
    source_sha256=source,candidate_ELF_sha256=elf,candidate_full_object_sha256=sha(W / 'candidate-full.o'),
    parent_result_sha256=sha(BASE / 'result.json'),independent_review='not_claimed',
    production_integration=False,hardware_accessed=False,physical_cycles_measured=False,goal_complete=False)
handoff = f'''# Near-ln directional remainder gate

Private RP2040 child of the frozen strict-enclosure component. Reuse the
exact polynomial division remainders and signed h residual to shrink the
one-sided error interval. All polynomial/table/helper algorithms remain.

Fresh32940 unique inputs/65880 fully profiled READY/DIRTY state cases:
263520 public ARM calls, zero own errors against fresh MPFR4.2.2.
All39318 retained parent counts reproduce. Caller SIO/PCS/SP/bounded
writes and exact raw parent NaN policy pass. The exact inline packer adds
16896 bare ARM calls and11554 Fraction RNE endpoint checks without any
firmware or ROM mapped. Qualification total280416 calls; a discarded
invalid-neighbor test-generator run is not counted.

Of the old34 raw losses,15 are removed, including one more historical
ln input:2158->604 DIRTY instructions versus correct Qfplib800. The larger
corpus has parent89READY/95DIRTY losses and candidate45READY/51DIRTY:
44 expanded raw inputs fixed, zero newly introduced correct-Qfplib losses.
51 raw/{len(losses)} state losses remain. All incorrect Qfplib answers,
remaining losses and regressions are retained. Historical ln now6/10
fixed and4 open; expanded inputs overlap and are not added to that count.

Versus parent: {dict(change)}. Regression range{min(deltas)}..{max(deltas)}
instructions. Candidate stack640 versus parent600 on this same expanded
corpus; previous568 concerned a smaller corpus. Code+248 bytes, only
ln_near_interval912->1160. No new tables/RAM/libgcc/dependencies. Generic
M0 and guarded M4 controls match; this is not a whole M4 image rebuild.
Entire public CPP/ASM/ELF producer rebuild is byte-exact. Public calls use
pinned resident helpers/support ROM; no new math ROM calls are added.

Source:{source}
ELF:{elf}
Object:{report['candidate_full_object_sha256']}

Hold this packet unchanged. Independent review, canonical integration,
physical cycles and hardware acceptance are not claimed. The full math
goal, other operations, general pow totality and integration remain OPEN.
'''
(W / 'HANDOFF.md').write_text(handoff)
report['files'] = {p.name:sha(p) for p in sorted(W.iterdir()) if p.is_file()}
(W / 'result.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps({k:v for k,v in report.items() if k!='files'},indent=2))

"""Join fresh R38 diagnostic admissions without re-executing ARM or MPFR."""
from pathlib import Path
import json, gzip, hashlib
W = Path(__file__).resolve().parent; ROOT = W.parents[1]
S = ROOT / '.build/m0-math-unified-exp-row0-midpoint-r38-20261026'
Q = ROOT / '.build/m0-math-unified-exp-row0-small-r37-qualification-20261026'
read = lambda p: json.loads(p.read_bytes())
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
assert not (W / 'admissions.json').exists()
prior = read(Q / 'joined-audit.json'); oldloss = set(prior['remaining_losing_arguments'])
targets = set(read(S / 'probe-inputs.json')['groups']); oldset, cache = set(), {}
for name in ('full', 'boundary', 'power', 'edge'):
    with gzip.open(Q / (name + '-records.jsonl.gz'), 'rt') as f:
        for line in f:
            r = json.loads(line); x = r['x']; oldset.add(x)
            if x not in targets: continue
            if name == 'edge': v = (r['outputs']['candidate'], r['instructions']['candidate'], r['outputs']['Qfplib'], r['instructions']['Qfplib'], r['correct']['Qfplib'])
            else: v = (r['candidate_output'], r['candidate_instructions'], r['inherited_Qfplib_output'], r['inherited_Qfplib_instructions'], r['inherited_Qfplib_correct'])
            key = x, r['SIO']
            assert key not in cache or cache[key] == v
            cache[key] = v
parentloss, childloss, records = set(), set(), []
overlap = 0
with gzip.open(S / 'probe-records.jsonl.gz', 'rt') as f:
    for line in f:
        r = json.loads(line); x = r['x']; key = x, r['SIO']
        v = (r['outputs']['parent'], r['instructions']['parent'], r['outputs']['Qfplib'], r['instructions']['Qfplib'], r['correct']['Qfplib'])
        if key in cache: assert cache[key] == v; overlap += 1
        if not r['correct']['Qfplib']: continue
        if r['instructions']['parent'] > r['instructions']['Qfplib']:
            parentloss.add(x)
            if x not in oldloss: records.append(r)
        if r['instructions']['candidate'] > r['instructions']['Qfplib']: childloss.add(x)
assert oldloss <= parentloss and len(parentloss) == 510 and len(childloss) == 491 and not childloss - parentloss
new = parentloss - oldloss
assert len(new) == 48 and len(oldloss - childloss) == 15 and len(new - childloss) == 4
out = dict(status='PASS_FRESH_R38_DIAGNOSTIC_ADMISSIONS_PREEXIST_IN_SELECTED_R37', source_probe_result_sha256=sha(S / 'probe-result.json'), probe_records_sha256=sha(S / 'probe-records.jsonl.gz'), current_R37_qualification_FROZEN_sha256=sha(Q / 'FROZEN.json'),
    previous_R37_qualified_losing_inputs=462, new_R37_preexisting_losing_inputs=len(new), current_R37_known_losing_inputs=len(parentloss), diagnostic_R38_losing_inputs=len(childloss), old462_fixed=len(oldloss - childloss), new48_fixed=len(new - childloss), new_correct_Qfplib_losses=0,
    prior_qualified_corpus_inputs=len(oldset), new_diagnostic_inputs=len(targets - oldset), expanded_observed_corpus_inputs=len(oldset | targets), overlap_state_rows_checked=overlap,
    new_parent_preexisting_losing_arguments=sorted(new), all_new_parent_preexisting_losing_state_rows=records, source_scope_erratum='.build/m0-exp-r38-source-scope-correction-20261026.json',
    diagnostic_ARM_calls=78021, diagnostic_MPFR_inputs=8669, not_full_qualification_pool=True, new_ARM_MPFR_calls_in_this_join=0, selected_remains_R37=True, hardware_accessed=False, integration_GO=False, goal_complete=False)
(W / 'admissions.json').write_text(json.dumps(out, indent=2) + '\n')
ledger = ROOT / '.build/m0-math-original-goal-status-20261023/status.json'; state = read(ledger)
cur = state['unified_private_runtime_candidate']
assert cur['path'].endswith('small-r37-20261026') and cur['known_current_exp_unique_inputs'] == 462
state['previous_current_measured_loss_union_before_R38_admissions'] = dict(state['current_measured_loss_union_after_full_ln_exp_replay'])
cur.update(known_current_exp_unique_inputs=510, known_current_primary_and_expanded_unique_losing_operation_arguments=3011, author_qualified_exp_losses_before_R38_diagnostic=462, additional_diagnostic_R37_preexisting_losses=48, known_exp_inputs_including_diagnostic_admissions=out['expanded_observed_corpus_inputs'])
state['current_measured_loss_union_after_full_ln_exp_replay'].update(exp=510, measured_operation_input_tuples=3011, R38_diagnostic_R37_preexisting_losses=48)
state['R38_midpoint_private_followup'] = dict(path=str(S.relative_to(ROOT)), source_FROZEN_sha256=sha(S / 'FROZEN.json'), qualification=str(W.relative_to(ROOT)), status='SOURCE_PROVED_DIAGNOSTIC_PASS_PENDING_FULL_QUALIFICATION', selected=False, admissions_report=str((W / 'admissions.json').relative_to(ROOT)), admissions_sha256=sha(W / 'admissions.json'), source_scope_erratum=out['source_scope_erratum'], current_R37_known_exp_losses=510, R38_diagnostic_losses=491, goal_complete=False)
state['current_status_field_scope'] = 'PRIVATE selection remains R37. Frozen qualification exp462 on556422 inputs remains immutable; fresh R38 diagnostic includes48 new preexisting R37 losses, current known R37 exp510/pow2501/ln0=3011. R38 diagnostic sameexpanded510->491/19fix(15old+4new)/0wrong/new, not selected/fullqualification. All global gates remain open.'
ledger.write_text(json.dumps(state, indent=2) + '\n')
print(json.dumps({k: v for k, v in out.items() if not isinstance(v, list)}, indent=2), flush=True)

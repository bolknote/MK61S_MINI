"""Merge all174 unchanged domains and retain the full slower-input inventory."""
import hashlib,json
from pathlib import Path
root=Path.cwd();work=Path(__file__).resolve().parent;parent=root/'.build/m0-sqrt-zero-tail-v163-20261023'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def read(p):return json.loads(Path(p).read_text())
matrix=read(work/'matrix-subsets.json');audit=read(work/'result.json');comparison=read(work/'case-comparison.json')
tiny=read(parent/'tiny-profile.json');special=read(parent/'special-profile.json')
validation=read(work/'validation.json');elf=work/'firmware/mk61s-picocalc-pico-h.elf'
assert matrix['owned_elf_sha256']==audit['elf_sha256']==comparison['new_elf_sha256']==validation['elf_sha256']==sha(elf)
assert comparison['status'].startswith('PASS') and validation['status'].startswith('PASS')
groups=[dict(operation=g['operation'],stream=g['stream'],cases=g['cases'],mean_instructions=g['mean_instructions'],
    owned_wrong_rounding=g['owned_wrong_rounding'],qfplib_wrong_results=g['qfplib_wrong_results'],
    both_correct_cases=g['both_correct_cases'],both_correct_mean_instructions=g['both_correct_mean_instructions'],
    both_correct_own_slower=g['both_correct_own_slower'],origin='original117',evidence='V164 actual ARM') for g in matrix['groups']]
groups += [dict(operation=g['operation'],stream=g['stream'],cases=g['cases'],mean_instructions=g['mean_instructions'],
    owned_wrong_rounding=g['own_wrong'],qfplib_wrong_results=g['qfplib_wrong'],both_correct_cases=g['both_correct_cases'],
    both_correct_mean_instructions=g['both_correct_mean_instructions'],both_correct_own_slower=g['both_correct_own_slower'],
    origin='independent53',evidence='V164 actual ARM') for g in audit['groups']]
groups.append(dict(operation='pow',stream='tiny_exponents_normal_bases',cases=168,
    mean_instructions=dict(own=tiny['own_mean_instructions'],qfplib=tiny['qfplib_mean_instructions']),
    owned_wrong_rounding=0,qfplib_wrong_results=0,both_correct_cases=168,
    both_correct_mean_instructions=dict(own=tiny['own_mean_instructions'],qfplib=tiny['qfplib_mean_instructions']),
    both_correct_own_slower=tiny['own_slower_normal_cases'],origin='tiny168',evidence='V163 inherited: unchanged linked pow bodies, data and complete scratch bytes'))
for op in ('ln','log10','sqrt'):
    rows=[r for r in special['rows'] if r['operation']==op];correct=[r for r in rows if r['qfplib_correct']]
    groups.append(dict(operation=op,stream='cold_IEEE_and_subnormal_specials',cases=len(rows),
        mean_instructions=dict(own=sum(r['after_instructions'] for r in rows)/len(rows),qfplib=sum(r['qfplib_instructions'] for r in rows)/len(rows)),
        owned_wrong_rounding=0,qfplib_wrong_results=len(rows)-len(correct),both_correct_cases=len(correct),
        both_correct_mean_instructions=dict(own=sum(r['after_instructions'] for r in correct)/len(correct),qfplib=sum(r['qfplib_instructions'] for r in correct)/len(correct)),
        both_correct_own_slower=sum(r['after_instructions']>r['qfplib_instructions'] for r in correct),origin='cold51',
        evidence='V163 inherited: unchanged linked functions and data'))
score=[sum(g['mean_instructions']['own']<g['mean_instructions']['qfplib'] if op=='faster' else
    g['mean_instructions']['own']==g['mean_instructions']['qfplib'] if op=='equal' else
    g['mean_instructions']['own']>g['mean_instructions']['qfplib'] for g in groups) for op in ('faster','equal','slower')]
assert len(groups)==174 and sum(g['cases'] for g in groups)==30355 and score==[167,2,5]
eligible=[g for g in groups if g['both_correct_cases']]
subset_deficits=[g for g in eligible if g['both_correct_mean_instructions']['own']>g['both_correct_mean_instructions']['qfplib']]
assert len(eligible)==155 and subset_deficits==[]
old_extended=read(parent/'extended-instruction-matrix.json')
assert [(g['operation'],g['stream'],g['cases']) for g in groups]==[(g['operation'],g['stream'],g['cases']) for g in old_extended['groups']]
for g in groups:
    if g['origin']=='original117':
        source=next(s for s in matrix['groups'] if (s['operation'],s['stream'])==(g['operation'],g['stream']))
    elif g['origin']=='independent53':
        source=next(s for s in audit['groups'] if (s['operation'],s['stream'])==(g['operation'],g['stream']))
    else:continue
    assert g['cases']==source['cases']

def slower_inventory(original,independent):
    rows=[]
    for chunk in original['chunks']:
        for r in chunk['both_correct_slower_rows']:
            rows.append(dict(operation=chunk['operation'],stream=chunk['stream'],x=r['x'],y=r['y'],expected=r['expected'],
                own_instructions=r['own_instructions'],qfplib_instructions=r['qfplib_instructions'],origin='original117'))
    for g in independent['groups']:
        for r in g['rows']:
            if r['qfplib_correct'] and r['own_instructions']>r['qfplib_instructions']:
                rows.append(dict(operation=g['operation'],stream=g['stream'],x=r['x'],y=r['y'],expected=r['expected'],
                    own_instructions=r['own_instructions'],qfplib_instructions=r['qfplib_instructions'],origin='independent53'))
    for r in special['rows']:
        if r['qfplib_correct'] and r['after_instructions']>r['qfplib_instructions']:
            rows.append(dict(operation=r['operation'],stream='cold_IEEE_and_subnormal_specials',x=r['x'],y='0000000000000000',
                expected=r['expected'],own_instructions=r['after_instructions'],qfplib_instructions=r['qfplib_instructions'],origin='cold51'))
    for r in tiny['cases_data']:
        if r['positive_normal_base'] and not r['qfplib_wrong'] and r['own_instructions']>r['qfplib_instructions']:
            rows.append(dict(operation='pow',stream='tiny_exponents_normal_bases',x=r['x'],y=r['y'],expected=r['expected'],
                own_instructions=r['own_instructions'],qfplib_instructions=r['qfplib_instructions'],origin='tiny168'))
    keyed={}
    for r in rows:
        key=(r['operation'],r['x'],r['y']);assert key not in keyed,key;keyed[key]=r
    return keyed
before=slower_inventory(read(parent/'matrix-subsets.json'),read(parent/'result.json'))
after=slower_inventory(matrix,audit);assert len(before)==508
resolved=[before[k] for k in sorted(set(before)-set(after))]
introduced=[after[k] for k in sorted(set(after)-set(before))]
inventory=dict(status='PASS_COMPLETE_FINITE_SLOWER_INPUT_INVENTORY',baseline='V163',candidate='V164',
    baseline_distinct_slower_inputs=len(before),candidate_distinct_slower_inputs=len(after),
    resolved_inputs=resolved,new_slower_inputs=introduced,
    rows=sorted(after.values(),key=lambda r:(r['qfplib_instructions']-r['own_instructions'],r['operation'],r['x'],r['y'])),
    semantics='Exact finite returned bits and quiet NaNs, payload/sign unspecified. Entries are actual tested inputs, not an all-input inventory.',
    source_reports={str(p.relative_to(root)):sha(p) for p in (work/'matrix-subsets.json',work/'result.json',parent/'matrix-subsets.json',parent/'result.json',parent/'special-profile.json',parent/'tiny-profile.json')},
    producer_sha256=sha(__file__),goal_complete=False)
(work/'slower-inputs.json').write_text(json.dumps(inventory,indent=2)+'\n')
report=dict(status='PASS_ALL174_RETAINED_WITH_ALL_CASE_REGRESSIONS_NOT_UNIVERSAL_SPEED',groups=groups,group_count=174,cases=30355,
    instruction_groups_faster=score[0],instruction_groups_equal=score[1],instruction_groups_slower=score[2],owned_wrong_rounding=0,
    original117_groups=dict(faster=115,equal=2,slower=0),original117_cases=23352,
    correct_reference_nonempty_groups=len(eligible),correct_reference_empty_groups=174-len(eligible),correct_reference_mean_deficits=subset_deficits,
    correct_reference_distinct_individual_slower_inputs=len(after),V163_distinct_individual_slower_inputs=508,
    resolved_individual_deficits=resolved,introduced_individual_deficits=introduced,
    changed_original_chunks=comparison['changed_original_chunks'],unchanged_original_chunks=comparison['unchanged_original_chunks'],
    changed_independent_groups=comparison['changed_independent_groups'],unchanged_independent_groups=comparison['unchanged_independent_groups'],
    groups_with_higher_mean_vs_V163=[{k:v for k,v in g.items() if k!='rows'} for g in comparison['groups_with_higher_mean']],
    raw_deficits=[g for g in groups if g['mean_instructions']['own']>g['mean_instructions']['qfplib']],
    inherited_reports={n:dict(path=str((parent/n).relative_to(root)),sha256=sha(parent/n),source_elf_sha256=read(parent/n)['elf_sha256'],
        reason='Required functions/data are byte-identical in validation.json; inherited calls are not counted as fresh V164 qualification.') for n in ('tiny-profile.json','special-profile.json','public-canary.json')},
    source_reports={n:sha(work/n) for n in ('matrix-subsets.json','result.json','validation.json','case-comparison.json','slower-inputs.json')},
    owned_elf_sha256=sha(elf),producer_sha256=sha(__file__),
    scope='Every V163 operation/stream/case domain is retained in order. All failure counts/raw means and every changed-case regression remain visible. Five raw deficits remain; all155 nonempty both-correct subset means still win/equal. Per-case deficits remain. Instruction counts, not physical cycles or universal speed proof.',
    hardware_accessed=False,production_promoted=False,general_pow_totality_proved=False,goal_complete=False)
(work/'extended-instruction-matrix.json').write_text(json.dumps(report,indent=2)+'\n')
print('PASS:174 groups167/2/5;155 correct-reference means without deficit;distinct slower inputs508->',len(after),
    ';resolved',len(resolved),';introduced',len(introduced),';higher means',len(comparison['groups_with_higher_mean']),';all retained.')

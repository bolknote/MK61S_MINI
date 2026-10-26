"""Author qualification of exact R29 code mapping and fresh full candidate."""
from pathlib import Path
from collections import Counter
import gzip,hashlib,json,sys
sys.dont_write_bytecode=True
W=Path(__file__).resolve().parent;ROOT=W.parents[1]
S=ROOT/'.build/m0-math-unified-exp-bit62-r29-20261026'
P=ROOT/'.build/m0-math-unified-exp-directed-distance-r28-qualification-20261026'
read=lambda p:json.loads(p.read_bytes())
def sha(p):
    h=hashlib.sha256()
    with p.open('rb')as f:
        for b in iter(lambda:f.read(1048576),b''):h.update(b)
    return h.hexdigest()
def verify(d):
    for n,r in read(d/'FROZEN.json')['files'].items():
        p=d/n;assert p.stat().st_size==r['bytes']and sha(p)==r['sha256'],p
assert not(W/'FROZEN.json').exists()
assert sha(S/'FROZEN.json')=='c176067a6ba6afda1ff3f158be5c8e148c6bdc8f98dfc0f63dfa86f03f262018'
assert sha(P/'FROZEN.json')=='0ba57f4e189ef444dc849d8dc42836f2a56ab8780282c36854d320317b42a70b'
for d in [S,P]:verify(d)
e=read(W/'exp-result.json');proof=read(S/'source-binding-proof.json');matrix=read(W/'matrix-comparison.json')
assert e['actual_fresh_public_R29_ARM_calls']==e['state_rows']==989922 and e['unique_inputs']==494961
assert e['candidate_wrong']==e['new_losing_inputs']==0 and not e['new_correct_Qfplib_loss_rows']and not e['all_parent_increases']
assert e['parent_losing_inputs']==e['candidate_losing_inputs']==428
assert e['actual_fresh_parent_ARM_calls']==e['actual_fresh_Qfplib_ARM_calls']==e['actual_fresh_MPFR_inputs']==0
assert proof['changed_R2_and_NZCV_dead_before_next_use_on_both_successors']and proof['both_CFGs_acyclic_normalization_visited_at_most_once']
assert proof['instruction_delta_per_normalization_visit']==-2 and proof['other_paths_instruction_delta']==0
for v in matrix['matrices'].values():assert not v['parent_increase_rows']and not v['new_correct_Qfplib_loss_rows']
rows=0;deltas=Counter();visits=Counter();parent=set();candidate=set();wrong=0
with gzip.open(W/'exp-records.jsonl.gz','rt')as f:
    for line in f:
        r=json.loads(line);rows+=1;n=r['normalization_visits'];assert n in [0,1]
        assert r['candidate_output']==r['inherited_R28_output']
        delta=r['candidate_instructions']-r['inherited_R28_instructions'];assert delta==-2*n
        deltas[delta]+=1;visits[n]+=1
        if not r['inherited_Qfplib_correct']:wrong+=1;continue
        q=r['inherited_Qfplib_instructions']
        if r['inherited_R28_instructions']>q:parent.add(r['x'])
        if r['candidate_instructions']>q:candidate.add(r['x'])
assert rows==989922 and len(parent)==len(candidate)==428 and not candidate-parent
assert dict(deltas)=={int(k):v for k,v in e['instruction_delta_histogram'].items()}
assert dict(visits)=={int(k):v for k,v in e['normalization_visit_histogram'].items()}
assert wrong==e['wrong_inherited_Qfplib_rows_retained']
primary=sum(read(W/(n+'.json'))['actual_qualified_math_ARM_calls']for n in ['original507','broad'])
assert primary==196714
result=dict(status='PASS_PRIVATE_AUTHOR_R29_EXACT_BIT62_FULL_FRESH_CANDIDATE',source_FROZEN_sha256=sha(S/'FROZEN.json'),candidate_ELF_sha256=sha(S/'candidate.elf'),parent_R28_qualification_FROZEN_sha256=sha(P/'FROZEN.json'),
 actual_fresh_full_R29_public_ARM_calls=989922,actual_fresh_primary_public_ARM_calls=primary,actual_fresh_qualified_ARM_calls=989922+primary,actual_fresh_private_primitive_ARM_calls=0,
 full_unique_inputs=494961,full_state_rows=989922,full_actual_fresh_MPFR_inputs=0,full_actual_fresh_Qfplib_ARM_calls=0,full_actual_fresh_parent_ARM_calls=0,
 inherited_full_directed_MPFR_inputs=e['inherited_actual_directed_MPFR_inputs'],inherited_full_sNaN_shortcuts=e['inherited_exact_sNaN_shortcuts'],inherited_Qfplib_state_measurements=989922,inherited_R28_state_measurements=989922,
 inherited_R28_1114954_primitive_ARM_and_2969766_full_ARM_not_fresh_R29=True,diagnostic70056_ARM_and7784_MPFR_not_pooled=True,
 source_bound_global_q_range_and_actual_CFG_R2_NZCV_mapping=True,all_outputs_exact_frozen_correct_R28=True,all_actual_normalization_q_within_global_bound=True,
 all_actual_costs_follow0_or_minus2_mapping=True,full_instruction_delta_histogram=dict(deltas),full_normalization_visit_histogram=dict(visits),all_parent_increases=0,new_correct_Qfplib_losses=0,candidate_wrong=0,
 parent_exp_losing_inputs=428,current_exp_losing_inputs=428,current_pow_losing_pairs=2501,current_ln_losing_inputs=0,known_finite_losing_operation_arguments=2929,whole_remaining_library_count=False,
 all_wrong_inherited_Qfplib_rows_retained=wrong,all_primary_nonexp_outputs_reference_and_own_costs_exact_R28=True,all_primary_parent_increases=0,
 fresh_primary_oracle_accounting={n:{k:v for k,v in read(W/(n+'.json')).items()if'Oracle'in k or'oracle'in k or'MPFR'in k}for n in ['original507','broad']},
 other18_objects_M4_default_exact=True,RP_exp_core_bytes=5208,code_delta_bytes_vs_R28=-4,new_tables_RAM_libgcc_bytes=0,linked_bank_changed_bytes=1,linked_bank_all_changes_symbolically_mapped=True,
 actual_linked_R12_17negative_realROMloader9disabled_pass=True,observed_full_stack=e['observed_stack'],not_universal_stack_bound=True,
 source_pending_snapshot_and_initial_RUNNING_superseded_by_completed_qualification=True,selected_private_author_candidate=True,
 new_independent_acceptance=False,universal_CR_totality_floatFMA_stack_cycles_integration_release_GO=False,hardware_accessed=False,integration_GO=False,goal_complete=False)
(W/'author-result.json').write_text(json.dumps(result,indent=2)+'\n')
(W/'TERMINAL.json').write_text(json.dumps(dict(status='TERMINAL_R29_PASS_SELECTED_PRIVATE_AUTHOR',all_producers_terminal=True,selected_private_source='R29',initial_RUNNING_json_superseded=True,author_result_sha256=sha(W/'author-result.json'),goal_complete=False),indent=2)+'\n')
(W/'HANDOFF.txt').write_text('PRIVATE R29 author-qualified exact bit62 normalization; whole goal remains open.\n'
 'Fresh full candidate989922ARM/494961inputs with explicit INHERITED R28 oracle/Qfp/parent; fresh primary196714ARM gives1186636qualifiedARM.\n'
 'FullMPFR/Qfp/parentfresh0; primaryoracle evidence fresh and reported separately, all inherited raw baselines pinned.\n'
 'All actual outputs exactR28, qrange checks and0/-2 pernormalization checks pass, no wrong/new/increase; exp428/pow2501/ln0FINITE2929 unchanged.\n'
 'Source exactrange proof + actual669otherinstructions mapped, R2/NZCVdead/CFG/branch/literal closed.\n'
 'Core5212->5208B;18otherobjects/M4default exact; bank1changedbyte mapped; actualR12/17/ROMloader/9disabled pass; no newtablesRAMlibgcc.\n'
 'Sourcepending and initialRUNNING snapshots superseded by completedqualification only. No independent/HW/main/adoption/integration/releaseGO.\n'
 'No canonical/Git/device/USB/Flash changes; globalCR/generalpowtotality/floatFMA/stack/cycles still open.\n')
files={str(p.relative_to(W)):dict(bytes=p.stat().st_size,sha256=sha(p))for p in sorted(W.rglob('*'))if p.is_file()and'__pycache__'not in p.parts}
(W/'FROZEN.json').write_text(json.dumps(dict(status='FROZEN_AUTHOR_QUALIFIED_R29_BIT62',source_FROZEN_sha256=sha(S/'FROZEN.json'),files=files,all_producers_terminal=True,selected_private_author_candidate=True,hardware_accessed=False,integration_GO=False,goal_complete=False),indent=2)+'\n')
verify(W)
ledger=ROOT/'.build/m0-math-original-goal-status-20261023/status.json';state=read(ledger)
assert state['unified_private_runtime_candidate']['path']=='.build/m0-math-unified-exp-directed-distance-r28-20261026'
state['previous_unified_private_runtime_candidate_before_R29']=state['unified_private_runtime_candidate']
selected=dict(state['unified_private_runtime_candidate']);selected.update(path=str(S.relative_to(ROOT)),source_FROZEN_sha256=sha(S/'FROZEN.json'),qualification_path=str(W.relative_to(ROOT)),qualification_FROZEN_sha256=sha(W/'FROZEN.json'),result_sha256=sha(W/'author-result.json'),candidate_ELF_sha256=sha(S/'candidate.elf'),
 actual_qualified_ARM_executions=1186636,actual_qualified_public_math_ARM_calls=1186636,actual_qualified_private_primitive_ARM_calls=0,full_matrix_math_ARM_calls=196714,expanded_public_ARM_calls=989922,
 full_exp_oracles_Qfp_parent_explicitly_inherited_R28=True,full_exp_actual_fresh_MPFR_Qfp_parent_calls=0,inherited_R28_primitive_calls_not_fresh=True,
 current_primary_matrix_parent_increase_rows=0,large_exp_parent_increase_rows=0,linked_hotbank_changed_bytes_vs_R28=1,linked_bank_actual_bytes_identical_current_R28=False,code_and_literal_pool_delta_bytes_vs_R28=-4,
 current_author_candidate_independently_accepted=False,independent_review_complete=False,goal_complete=False)
state['unified_private_runtime_candidate']=selected
state['R29_bit62_private_followup'].update(selected=True,full_public_qualification_pending=False,qualification_FROZEN_sha256=sha(W/'FROZEN.json'),qualification_state=read(W/'TERMINAL.json'))
state['current_measured_loss_union_after_full_ln_exp_replay'].update(source_R29_qualification_sha256=sha(W/'FROZEN.json'),exp=428,pow=2501,ln=0,measured_operation_input_tuples=2929)
for name,key in [('original507','current_source_linked_original507'),('broad','current_source_linked_original119_and_independent53')]:
    state['previous_'+key+'_before_R29']=state[key]
    state[key]=dict(state[key],result=str((W/(name+'.json')).relative_to(ROOT)),result_sha256=sha(W/(name+'.json')),source=str((W/(name+'.json')).relative_to(ROOT)),sha256=sha(W/(name+'.json')),
      scope='Fresh R29 primary matrices; all nonexp outputs/reference/own costs exact R28, exp0/-2, instructions not cycles.')
state['latest_goal_turn_classification']='progress: R29 full989922freshcandidate+196714freshprimary, explicit inherited full R28 oracles/refs, exact0/-2 code proof and all actualcosts, selectedPRIVATE author; whole goal open'
ledger.write_text(json.dumps(state,indent=2)+'\n')
with(ledger.parent/'HANDOFF.md').open('a')as f:f.write('\n\nR29 author-qualified source'+sha(S/'FROZEN.json')+'/qualification'+sha(W/'FROZEN.json')+': fresh1186636ARM (989922fullcandidate+196714primary), fullMPFR/Qfp/parentexplicitlyinheritedR28/notfresh. Alloutputs exactR28/qrange and0/-2costmapping,0wrong/new/increases; exp428/pow2501/ln0=2929FINITE unchanged. Core5212->5208/18otherobjectsM4default exact/bank1byte mapped/no newtablesRAMlibgcc; actualR12/17/ROMloader/9disabledpass. Sourcepending/initialRUNNING superseded by completedqualification only. Wholegoal/universalCR/totality/floatFMA/stack/cycles/independent/integration/releaseopen; no canonical/Git/devicechanges.\n')
print('R29 author-qualified',sha(W/'FROZEN.json'),'freshARM',1186636,'fullcostdelta',dict(deltas),'knownexp428/pow2501',flush=True)

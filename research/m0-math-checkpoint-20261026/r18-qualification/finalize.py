"""Current-R15 paired audit and finite author qualification of R18."""
from pathlib import Path
from collections import Counter
import gzip,hashlib,itertools,json,sys
sys.dont_write_bytecode=True
W=Path(__file__).resolve().parent;ROOT=W.parents[1]
S=ROOT/'.build/m0-math-unified-ln-small-partials-r18-20261025'
PS=ROOT/'.build/m0-math-unified-ln-ln2-r15-20261025'
P=ROOT/'.build/m0-math-unified-ln-ln2-r15-qualification-20261025'
read=lambda p:json.loads(p.read_text())
def sha(p):
    h=hashlib.sha256()
    with p.open('rb')as f:
        for b in iter(lambda:f.read(1048576),b''):h.update(b)
    return h.hexdigest()
def verify(directory):
    for name,d in read(directory/'FROZEN.json')['files'].items():
        p=directory/name;assert p.stat().st_size==d['bytes']and sha(p)==d['sha256'],p
assert not(W/'FROZEN.json').exists()
assert sha(S/'FROZEN.json')=='eb8d9ec8d61ad1eded286d52046d7b1d54053712d4fca4c88b288d7ddf7c5479'
for d in [S,PS,P]:verify(d)
ln=read(W/'ln-result.json');adm=read(W/'admission-result.json');proof=read(S/'source-binding-proof.json')
gate=read(S/'unit-result.json');router=read(S/'router-unit-result.json')
assert ln['candidate_wrong']==adm['candidate_wrong']==gate['candidate_wrong']==0
assert ln['unique_input_cases']==91573 and adm['input_cases']==92160
assert ln['remaining_losing_input_cases']==adm['remaining_losing_inputs']==0
assert not ln['remaining_reference_state_rows']and not adm['remaining_reference_state_rows']
assert ln['newly_losing_cases_vs_historical_component']==adm['newly_losing_inputs_vs_R15']==0
for k in ['fresh_reference_disagreements_with_old_records','old_expected_disagreements_with_fresh_gold','old_candidate_bits_different_from_current']:assert not ln[k],k
assert sha(S/'FROZEN.json')==ln['source_FROZEN_sha256']==adm['source_FROZEN_sha256']
assert sha(PS/'FROZEN.json')==adm['parent_FROZEN_sha256']
changed=Counter();increases=[];primary_losses=set();new=[];public=0
for campaign in ['original507','broad']:
    d=read(W/(campaign+'.json'));assert d['candidate_wrong']==0
    public+=d['actual_qualified_math_ARM_calls']
    with gzip.open(W/(campaign+'-records.jsonl.gz'),'rt')as af,gzip.open(P/(campaign+'-records.jsonl.gz'),'rt')as bf:
        for al,bl in itertools.zip_longest(af,bf):
            assert al is not None and bl is not None
            a,b=json.loads(al),json.loads(bl)
            for k in ['operation','x','y','SIO','expected','outputs','correct']:assert a[k]==b[k],(campaign,k)
            refs={k:v for k,v in a['instructions'].items()if k not in ['candidate','zero-control']}
            assert refs=={k:v for k,v in b['instructions'].items()if k not in ['candidate','zero-control']}
            delta=a['instructions']['candidate']-b['instructions']['candidate']
            if a['operation']!='ln':assert not delta,(campaign,a['operation'],delta)
            if delta:changed[campaign+'/'+a['operation']]+=1
            if delta>0:increases.append(dict(campaign=campaign,operation=a['operation'],x=a['x'],y=a['y'],SIO=a['SIO'],delta=delta))
            for ref,cost in refs.items():
                if not a['correct'][ref]:continue
                if a['instructions']['candidate']>cost:
                    if campaign=='broad':primary_losses.add((a['operation'],a['x'],a['y']))
                    if b['instructions']['candidate']<=cost:new.append(a)
assert not new and len(primary_losses)==35 and all(k[0]=='pow'for k in primary_losses)
with gzip.open(W/'admission-records.jsonl.gz','rt')as af,gzip.open(P/'admission-records.jsonl.gz','rt')as bf:
    rows=0;hist=Counter()
    for al,bl in itertools.zip_longest(af,bf):
        assert al is not None and bl is not None
        a,b=json.loads(al),json.loads(bl);rows+=1
        for k in ['index','exponent','cell','offset_kind','x','SIO','expected']:assert a[k]==b[k],k
        for field in ['outputs','instructions','correct']:
            assert a[field]['parent']==b[field]['candidate'],(field,a['x'])
            assert a[field]['Qfplib']==b[field]['Qfplib'],(field,a['x'])
        hist[a['instructions']['candidate']-a['instructions']['parent']]+=1
    assert rows==184320 and dict(hist)=={int(k):v for k,v in adm['parent_instruction_delta_histogram'].items()}
public+=ln['actual_qualified_ARM_calls']+adm['actual_qualified_math_ARM_calls']
private=gate['actual_qualified_gate_unit_ARM_calls']+router['actual_qualified_router_unit_ARM_calls']
assert public==1115966 and private==214464
assert proof['default_M0_M4_exact']and proof['all18_other_object_fingerprints_exact']
assert proof['CPP_code_delta_bytes_vs_R15']==proof['linked_flash_load_delta_bytes_vs_R15']==328
assert proof['linked_bank_literal_byte_identity']is False and proof['linked_bank_changed_bytes']==17
result=dict(status='PASS_PRIVATE_AUTHOR_R18_SMALL_POSITIVE_LN_ZERO_OBSERVED_QFPLIB_DEFICITS',
 source_FROZEN_sha256=sha(S/'FROZEN.json'),candidate_ELF_sha256=sha(S/'candidate.elf'),
 parent_source_FROZEN_sha256=sha(PS/'FROZEN.json'),parent_qualification_FROZEN_sha256=sha(P/'FROZEN.json'),
 source_snapshot_pending_flag_superseded_by_this_completed_qualification=True,
 actual_fresh_public_math_ARM_calls=public,actual_fresh_gate_unit_ARM_calls=113664,
 actual_fresh_router_unit_ARM_calls=100800,actual_fresh_qualified_ARM_calls=public+private,
 inherited_R12_point151536_and_R15_bias17760_calls_not_fresh=True,
 diagnostic_probe_ARM_calls_not_pooled=28566,diagnostic_probe_MPFR_inputs_not_pooled=3174,
 rejected_R16_R17_diagnostic_calls_not_pooled=True,
 campaigns=dict(ln_union=dict(inputs=91573,ARM_calls=366292,directed_MPFR_inputs=91528,sNaN_shortcuts=45,
    losing_inputs=0,parent_increase_rows=len(ln['all_historical_candidate_increase_rows'])),
    ln_family=dict(inputs=92160,ARM_calls=552960,directed_MPFR_inputs=92160,losing_inputs=0,
    parent_increase_rows=adm['parent_instruction_increase_state_rows']),original507_ARM_calls=3654,broad30136_ARM_calls=193060),
 candidate_wrong=0,new_correct_reference_loss_rows=[],all_wrong_references_outputs_costs_and_parent_increases_retained=True,
 no_nominal_reference_domain_filter=True,all_nonln_primary_bits_instruction_counts_exact_R15=True,
 all_fresh_parent_admission_outputs_and_costs_match_current_R15=True,
 original507_no_slower=474,original507_strict=468,original507_equal=6,original507_pow_losing_cases=33,
 known_current_ln_losing_inputs=[],known_current_ln_losing_input_count=0,
 fixed_last_ln_input='3FF0E23E6966260F',fixed_input_instructions=dict(READY=700,DIRTY=776,Qfplib=781,saving_vs_R15=130),
 known_other_operations_unchanged_in_prior_replayed_campaigns=dict(exp=214,pow=41),
 known_measured_remaining_operation_input_tuples_before_large_pow_replay=255,
 large120980_pow_replay_in_separate_packet_pending=True,whole_remaining_library_count=False,
 primary_instruction_changed_rows=dict(changed),primary_all_parent_increase_rows=increases,
 ln_all_parent_increases_in_result_and_raw=True,admission_all_parent_increases_in_complete_raw=True,
 CPP_code_delta_bytes_vs_R15=328,linked_flash_load_bytes_delta_vs_R15=328,new_table_RAM_libgcc_bytes=0,
 linked_hotbank_literal_byte_identity=False,linked_hotbank_changed_bytes=17,
 linked_hotbank_address_size_named_targets_preserved=True,M4_default_M0_exact=True,
 source_R12_negative_ROM_loader_disabled_checks_passed=True,
 selected_private_author_candidate=True,whole_independent_runtime_acceptance=False,
 universal_rounding_totality_stack_or_physical_cycles_GO=False,hardware_accessed=False,integration_GO=False,goal_complete=False)
(W/'result.json').write_text(json.dumps(result,indent=2)+'\n')
(W/'HANDOFF.txt').write_text('Private author-qualified R18; no canonical adoption.\n'
 'Full91573lnunion and92160family inputs:0wrong/0correctQfpliblosses. Knownln1->0.\n'
 'Oldlastinput3FF0E23E6966260F700/776vsQfp781, -130vsR15; allparentincreases retained.\n'
 'Freshpublic1115966+gate113664+router100800=1330430ARM; inheritedR12point151536/R15bias17760notfresh.\n'
 'Diagnostic28566ARM/3174MPFR and rejectedR16/R17diagnostics separate.\n'
 'Nonlnprimarybits/counts exactR15; original474/507 remains, knownpriorpow41/exp214.\n'
 'Large120980powcurrentreplay separate/live, must not extrapolate knownprior41.\n'
 'CPP/Flash+328BvsR15; no newtables/RAM/libgcc; M4/default/18others exact.\n'
 'Linkedbank17changedbytes semanticallymapped, no literalidentity claim.\n'
 'No universalbinary64/allstack/generalpowtotality/cycles/independentwholemath/integration/releaseGO.\n')
(W/'FROZEN.json').write_text(json.dumps(dict(status='FROZEN_AUTHOR_QUALIFIED_R18_SMALL_POSITIVE_LN',
 source_FROZEN_sha256=sha(S/'FROZEN.json'),files={str(p.relative_to(W)):dict(bytes=p.stat().st_size,sha256=sha(p))for p in sorted(W.rglob('*'))if p.is_file()},
 hardware_accessed=False,integration_GO=False,goal_complete=False),indent=2)+'\n')
verify(W)
ledger=ROOT/'.build/m0-math-original-goal-status-20261023/status.json';state=read(ledger)
assert state['unified_private_runtime_candidate']['path']==str(PS.relative_to(ROOT))
state['previous_unified_private_runtime_candidate_before_small_ln_R18']=state['unified_private_runtime_candidate']
state['unified_private_runtime_candidate']=dict(path=str(S.relative_to(ROOT)),source_FROZEN_sha256=sha(S/'FROZEN.json'),
 qualification_path=str(W.relative_to(ROOT)),qualification_FROZEN_sha256=sha(W/'FROZEN.json'),result_sha256=sha(W/'result.json'),candidate_ELF_sha256=sha(S/'candidate.elf'),
 source_linked=True,actual_R12_and17_negative_controls_and_source_loader_passed=True,scratch_y_bytes=4080,
 default_M0_M4_objects_exact=True,all9_RP_disabled_objects_empty=True,total_seed_table_bytes=288,new_table_global_RAM_libgcc_bytes=0,
 actual_qualified_ARM_executions=public+private,actual_qualified_public_math_ARM_calls=public,actual_qualified_private_ARM_calls=private,
 full_matrix_math_ARM_calls=196714,expanded_public_ARM_calls=public-196714,
 inherited_R12_point151536_and_R15_bias17760_calls_not_fresh=True,original507_no_slower=474,
 primary_broad_remaining_pow_indexed_cases=35,known_prior_pow_unique_inputs=41,known_current_ln_unique_inputs=0,known_current_exp_unique_inputs=214,
 large_pow_replay_pending=True,whole_remaining_library_count=False,all_nonln_primary_instruction_counts_identical=True,
 current_primary_matrix_parent_increase_rows=len(increases),new_correct_Qfplib_loss_state_variants=0,all_adverse_parent_changes_retained=True,
 linked_hotbank_byte_identity_claim=False,linked_hotbank_changed_bytes_vs_R15=17,linked_hotbank_size_address_named_targets_preserved=True,
 CPP_code_delta_bytes_vs_R15=328,linked_math_ELF_flash_load_bytes_delta_vs_R15=328,
 physical_cycles_measured=False,canonical_runtime_integrated=False,independent_review_complete=False,
 current_author_candidate_independently_accepted=False,integration_GO=False,goal_complete=False)
state['previous_current_measured_loss_union_before_R18']=state['current_measured_loss_union_after_full_ln_exp_replay']
state['current_measured_loss_union_after_full_ln_exp_replay']=dict(ln=0,exp=214,known_prior_pow=41,
 large_pow_replay_pending=True,measured_operation_input_tuples_before_large_pow=255,whole_remaining_library_count=False,
 global_correct_rounding_and_totality_not_proved=True,source_R18_qualification_sha256=sha(W/'FROZEN.json'),known_ln_inputs=[])
state['ln_latest_candidate_path']=str(S.relative_to(ROOT));state['ln_latest_expanded_speed_inputs']=0
state['ln_latest_count_scope']='R18 one-ELF91573union+92160family:0observedcorrectQfp deficits; not allbinary64/cycles'
state['R16_R17_unselected_small_ln_diagnostics']=dict(R16_FROZEN_sha256='47ea089c8f404bd483eb461f976505c6080d8def83ae5d85b5f91fe24e9a165f',
 R17_FROZEN_sha256='8b3697edbfa894f328faf406a73f0cb0d92b18862903cdc24a24c4c9a84ef377',new_Qfp_loss_states_each=2,selected=False)
state['previous_goal_turn_classification']=state['latest_goal_turn_classification']
state['latest_goal_turn_classification']='progress: R18 selected finite 1330430freshARM, observedln1->0,lasttarget-130instr,0wrong/newloss; largepowreplaylive'
ledger.write_text(json.dumps(state,indent=2)+'\n')
with(ledger.parent/'HANDOFF.md').open('a')as f:
    f.write('\n\nPrivate selectedR18 source'+sha(S/'FROZEN.json')[:8]+'/qual'+sha(W/'FROZEN.json')[:8]+'/ELF'+sha(S/'candidate.elf')[:8]+
      ': fresh1115966public+113664pointbundle+100800router=1330430ARM, inheritedR12point151536/R15bias17760notfresh. '
      'Full91573lnunion+92160family0wrong/0correctQfp deficits, knownln1->0. Lasttarget700/776vs781 (-130vsR15). '
      'Allparentincreases retained: '+str(len(increases))+'primary/'+str(len(ln['all_historical_candidate_increase_rows']))+'ln/'+str(adm['parent_instruction_increase_state_rows'])+'admission. '
      'Allnonlnprimarybits/counts exactR15, original474/507; priorpow41/exp214 not universalcounts. '
      'Large120980powfreshcurrentR18/R15/3Qfp+MPFR replay separate andlive, knownpowremainderalreadygrows. '
      'CPP/Flash+328B/no newtables/RAM/libgcc/M4/defaultchanges; whole672Bunitpointbundlebyteexactproduction, verified table namespacealiasrelocs. '
      'Linkedbank17bytesmapped, no literalidentity. R16/R17rejecteddiagnostics immutable/notpooled. '
      'No whole-independent/totality/universalstack/cycles/integration/releaseGO; no canonical/Git/device/USB/Flashchanges.\n')
print('R18 selected PRIVATE',sha(S/'FROZEN.json'),sha(W/'FROZEN.json'),sha(W/'result.json'),flush=True)
print('freshARM',public+private,'ln0','increases',len(increases),len(ln['all_historical_candidate_increase_rows']),adm['parent_instruction_increase_state_rows'],flush=True)

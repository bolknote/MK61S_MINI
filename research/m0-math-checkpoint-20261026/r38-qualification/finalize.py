"""Freeze completed R38 evidence and select only the private author candidate."""
from pathlib import Path
import hashlib, json, sys
sys.dont_write_bytecode = True
W = Path(__file__).resolve().parent; ROOT = W.parents[1]
S = ROOT / '.build/m0-math-unified-exp-row0-midpoint-r38-20261026'
P = ROOT / '.build/m0-math-unified-exp-row0-small-r37-20261026'
read = lambda p: json.loads(p.read_bytes())
def sha(p):
    h = hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda: f.read(1048576), b''): h.update(b)
    return h.hexdigest()
assert not (W / 'FROZEN.json').exists()
a, proof = read(W / 'joined-audit.json'), read(S / 'source-binding-proof.json')
assert (a['union_exp_inputs'], a['union_parent_losing_inputs'], a['union_candidate_losing_inputs'], a['union_fixed_inputs']) == (568856, 542, 512, 30)
assert (a['same_prior_union_inputs'], a['same_prior_union_parent_losses'], a['same_prior_union_candidate_losses']) == (556578, 510, 491)
assert a['candidate_wrong'] == a['union_new_losing_inputs'] == a['primary_parent_increase_rows'] == 0
assert a['actual_qualified_ARM_calls'] == 1740673 and a['actual_qualified_public_ARM_calls'] == 1604695
assert proof['parent_positive21_outer_inner_paths_and_normalized17_pack_preserved'] and proof['actual_new8instructions_Dhi_minus1_and_Dlo_residue2_implies_unsigned_ge2']
terminal = read(W / 'producer-terminal.json'); assert terminal['all_producers_terminal']
ledger = ROOT / '.build/m0-math-original-goal-status-20261023/status.json'; state = read(ledger)
assert state['unified_private_runtime_candidate']['path'] == str(P.relative_to(ROOT))
sys.path.insert(0, str(ROOT / 'tests')); from check_stm32_vectors import ElfImage
e = ElfImage(S / 'candidate.elf')
flash = lambda im: sum(t[4] for t in im.segments if t[0] == 1 and 0x10010000 <= t[3] < 0x10200000)
def code(d):
    return sum(r[4] for r in read(d / 'link-result.json')['outputs']['RP-merged-cpp.o']['fingerprint']['allocated'] if r[0] in ('.m0_exp_core', '.m0_exp_positive_dispatch', '.m0_exp_positive_upper'))
relative = {}
for version, dirname in (
    ('R25', 'm0-math-unified-pow-subnormal-endpoints-r25-20261026'), ('R28', 'm0-math-unified-exp-directed-distance-r28-20261026'),
    ('R29', 'm0-math-unified-exp-bit62-r29-20261026'), ('R30', 'm0-math-unified-exp-cached-index-r30-20261026'),
    ('R33', 'm0-math-unified-exp-positive-bridge-r33-20261026'), ('R35', 'm0-math-unified-exp-row0-reuse-r35-20261026'),
    ('R36', 'm0-math-unified-exp-row0-normalized-r36-20261026'), ('R37', 'm0-math-unified-exp-row0-small-r37-20261026')):
    d = ROOT / '.build' / dirname; pin = read(d / 'FROZEN.json')['files']['candidate.elf']
    assert (d / 'candidate.elf').stat().st_size == pin['bytes'] and sha(d / 'candidate.elf') == pin['sha256']
    old = ElfImage(d / 'candidate.elf'); x, y = e.bytes_at(e.named_sections['.scratch_y']), old.bytes_at(old.named_sections['.scratch_y'])
    assert len(x) == len(y) == 4080
    relative[version] = dict(source_FROZEN_sha256=sha(d / 'FROZEN.json'), linked_bank_changed_bytes=sum(a != b for a, b in zip(x, y)), linked_bank_bytes_identical=x == y, exp_core_and_added_sections_code_delta_bytes=code(S) - code(d), linked_ELF_Flash_load_delta_bytes=flash(e) - flash(old))
assert (relative['R37']['linked_bank_changed_bytes'], relative['R37']['exp_core_and_added_sections_code_delta_bytes'], relative['R37']['linked_ELF_Flash_load_delta_bytes']) == (4, 16, 16)
result = dict(a, status='PASS_PRIVATE_AUTHOR_R38_SMALL_NEGATIVE_MIDPOINT', selected=True, selected_private_author_candidate=True,
    candidate_ELF_sha256=sha(S / 'candidate.elf'), source_binding_proof_sha256=sha(S / 'source-binding-proof.json'),
    bridge_bytes_parent=216, bridge_bytes_current=232, code_delta_bytes_vs_R37=16, Flash_load_delta_bytes_vs_R37=16, relative_current_baselines=relative,
    oldcore5192_helper108_tables_other18objects_M4_default_exact=True, actual_R12_17negative_realROMloader9disabled_pass=True,
    current_positive_and_normalized_private_caller_guards_mandatory_each_changed_release_object=True, new_guard8instructions_only_after_old_inner_mask_decline=True,
    parent_positive21_outer_inner_paths_and_normalized17_pack_preserved=True, new_tables_RAM_libgcc_bytes=0, bank4bytes_symbolically_mapped_not_identity=True,
    inherited_review_pins_sha256=sha(W / 'inherited-review-pin-revalidation.json'), inherited_receipts_are_R30_R33_R35_only=True,
    source_subset_count_erratum_explicitly_preserved_and_rechecked=True, source_subset_count_corrected_old15_new4_total19=True,
    frozen_R36_metadata_label_erratum_preserved=True, producer_terminal_evidence_sha256=sha(W / 'producer-terminal.json'),
    fresh_primary_oracle_accounting={n: {k: v for k, v in read(W / (n + '.json')).items() if 'oracle' in k.lower() or 'MPFR' in k} for n in ('original507', 'broad')},
    previous_receipts_not_R38_independent_performance_or_adoption_GO=True, independent_review_complete=False,
    universal_CR_generalpowtotality_floatFMA_stack_cycles_independent_integration_main_release_GO=False)
(W / 'author-result.json').write_text(json.dumps(result, indent=2) + '\n')
(W / 'TERMINAL.json').write_text(json.dumps(dict(status='TERMINAL_R38_PRIVATE_AUTHOR_PASS', all_producers_terminal=True, selected_private_source='R38', author_result_sha256=sha(W / 'author-result.json'), initial_RUNNING_source_pending_superseded_only_by_completed_qualification=True, goal_complete=False), indent=2) + '\n')
campaigns = '; '.join(f"{n}:{r['parent_increase_rows']} increases" for n, r in a['per_campaign'].items())
c = a['cumulative_R29']['full']
text = f'''PRIVATE R38 author-qualified midpoint shortcut. No independent/performance/adoption/integration GO.
Same old494961 exp260->248/12fix. Prior R37 qualified556422 union462->447/15fix. Diagnostic156new inputs reveal48 R37-preexisting losses; same augmented556578 union510->491/19fix (15old+4new). Fresh12311inputs include12278new and32new parent-preexisting losses: expanded568856 union542->512/30fix,0wrong/new. Current finite ln0/exp512/pow2501=3013, not wholelibrary.
All correct Qfp results compared without nominalfilter; wrong outputs/costs and EVERY parent increase retained. {campaigns}; primary0. CumulativeR29full net{c['net_instruction_delta']}, increased{c['increased_rows']}/decreased{c['decreased_rows']}/same{c['unchanged_rows']}. Primary18+2080 increases remain. All cumulative rows retained; additional73895 inputs have no R29 remeasurement. No workload/cycle blanket speed claim.
Qualified1740673ARM=1604695public(full989922+boundary213912+power31842+edge30939+admission30567+primary196714+freshedge110799)+135978explicit-marker controls NOT public accuracy gold. Boundary/admission include41520 public R12/16NZCV poison over173inputs. Five replay gold/Qfp/parent sets inherited R37 qualification or frozen R38 diagnostic, NOT fresh. Freshedges12311 directedMPFR and36933calls each candidate/parent/Qfp; primaryMPFR/Qfp separate. Source diagnostic78021ARM/8669MPFR, loader2, MPFRgeneration excluded; realhelper921901 inherited/notfresh.
Only bridge216->232B, code/actualFlash+16vsR37. Core5192/helper108/tables/other18 M4/default objects exact, tablesRAMlibgcc0. Linkedbank4bytes symbolically mapped, not identity. Eight instructions after inner decline, Dhi=-1/Dlo residue2 implies the old unsigned bound; strict249/1000<V-q<1751/1000 decides tail512 upward. Actual caller proves q even/error6/ambiguity1,3,5,7,9 and no metadata clobber. Positive21/outer/inner paths and normalized17 pack preserved. Current-object guards mandatory eachchangedrelease. Stack816 observed, not universal.
All source/full/auxiliary/primary/fresh/audit producers terminal; exact evidence in producer-terminal.json. R38 frozen source NUMERIC-PROOF diagnostic subset count12/7 was mistaken: actual15/4, total19 unchanged. Additive correction49abbcd4 preserved without modifying frozen bytes; mathematical theorem/code/controls unaffected. Failed inline host admission assertion before ledger/output0ARM/MPFR recorded in correction. Inherited R30/R33/R35 narrow receipt pins and R36 metadata label erratum rechecked; no transferred R38 GO.
Whole CR/generalpowtotality/floatFMA/globalstack/physicalcycles/independent/performance/adoption/integration/main/release remain OPEN. No canonical handoff/Git/device/ports/USB/Flash/UI/main changes.
'''
(W / 'HANDOFF.txt').write_text(text)
files = {str(p.relative_to(W)): dict(bytes=p.stat().st_size, sha256=sha(p)) for p in sorted(W.rglob('*')) if p.is_file() and '__pycache__' not in p.parts}
(W / 'FROZEN.json').write_text(json.dumps(dict(status='FROZEN_AUTHOR_QUALIFIED_R38_MIDPOINT', source_FROZEN_sha256=sha(S / 'FROZEN.json'), files=files, all_producers_terminal=True, selected_private_author_candidate=True, hardware_accessed=False, integration_GO=False, goal_complete=False), indent=2) + '\n')
for n, r in files.items(): assert (W / n).stat().st_size == r['bytes'] and sha(W / n) == r['sha256'], n
state['previous_unified_private_runtime_candidate_before_R38'] = state['unified_private_runtime_candidate']
cur = dict(path=str(S.relative_to(ROOT)), source_FROZEN_sha256=sha(S / 'FROZEN.json'), qualification_path=str(W.relative_to(ROOT)), qualification_FROZEN_sha256=sha(W / 'FROZEN.json'), result_sha256=sha(W / 'author-result.json'), candidate_ELF_sha256=sha(S / 'candidate.elf'), source_linked=True, selected_private_author_candidate=True, source_pending_snapshot_superseded_by_qualification=True,
    actual_R12_and17_negative_controls_and_source_loader_passed=True, scratch_y_bytes=4080, default_M0_M4_objects_exact=True, all9_RP_disabled_objects_empty=True, total_reciprocal_seed_bank_bytes=288, not_whole_library_table_size=True, new_lookup_table_global_RAM_libgcc_bytes=0,
    actual_qualified_ARM_executions=a['actual_qualified_ARM_calls'], actual_qualified_public_math_ARM_calls=a['actual_qualified_public_ARM_calls'], actual_qualified_private_primitive_ARM_calls=a['actual_fresh_qualified_primitive_ARM_calls'], full_exp_inputs=a['union_exp_inputs'], full_matrix_math_ARM_calls=196714,
    replay_gold_Qfp_parent_explicitly_inherited_R37_or_R38_frozen_diagnostic=True, all5replay_fresh_MPFR_Qfp_parent_calls=0, fresh_edge_MPFR_inputs=12311, fresh_edge_public_ARM_calls=110799,
    inherited_R25_pow_R18_ln_qualification_not_fresh=True, original507_no_slower=474, original507_strict=468, original507_equal=6,
    known_current_ln_unique_inputs=0, known_current_exp_unique_inputs=512, known_current_pow_unique_inputs=2501, known_current_primary_and_expanded_unique_losing_operation_arguments=3013, whole_remaining_library_count=False,
    current_primary_matrix_parent_increase_rows=0, parent_increases_by_campaign={n: r['parent_increase_rows'] for n, r in a['per_campaign'].items()}, all_adverse_parent_changes_retained=True, new_correct_Qfplib_loss_state_variants=0, cumulative_R29_cost_audit=str((W / 'joined-audit.json').relative_to(ROOT)),
    current_author_candidate_independently_accepted=False, independent_review_complete=False, performance_or_adoption_GO=False, physical_cycles_measured=False, canonical_runtime_integrated=False, integration_GO=False, goal_complete=False)
for version, r in relative.items():
    cur['linked_hotbank_changed_bytes_vs_' + version] = r['linked_bank_changed_bytes']; cur['linked_bank_actual_bytes_identical_current_' + version] = r['linked_bank_bytes_identical']
    cur['code_and_literal_pool_delta_bytes_vs_' + version] = r['exp_core_and_added_sections_code_delta_bytes']; cur['linked_math_ELF_Flash_load_delta_bytes_vs_' + version] = r['linked_ELF_Flash_load_delta_bytes']
state['unified_private_runtime_candidate'] = cur
state['R38_midpoint_private_followup'].update(status='AUTHOR_QUALIFIED_PRIVATE_R38', selected=True, qualification_FROZEN_sha256=sha(W / 'FROZEN.json'), all_producers_terminal=True, qualification_state=read(W / 'TERMINAL.json'))
state['previous_current_measured_loss_union_before_R38_selection'] = dict(state['current_measured_loss_union_after_full_ln_exp_replay'])
state['current_measured_loss_union_after_full_ln_exp_replay'].update(source_R38_qualification_sha256=sha(W / 'FROZEN.json'), exp=512, pow=2501, ln=0, measured_operation_input_tuples=3013)
for n, key in (('original507', 'current_source_linked_original507'), ('broad', 'current_source_linked_original119_and_independent53')):
    state['previous_' + key + '_before_R38'] = state[key]; p = W / (n + '.json')
    state[key] = dict(state[key], result=str(p.relative_to(ROOT)), result_sha256=sha(p), source=str(p.relative_to(ROOT)), sha256=sha(p), scope='Fresh R38 primary bits/ref/owncosts exactR37; cumulativeR29 adverse rows retained. No blanket performance GO.')
state['current_status_field_scope'] = 'Authoritative PRIVATE author selection R38. Priorqualified556422 exp462->447/15fix; augmented556578510->491/19fix; expanded568856542->512/30fix/0wrong/new. New inputs expose80 R37-preexisting losses versus its frozen qualification, not regressions. Finite ln0/exp512/pow2501=3013, not wholelibrary. Five replay references inherited, freshedges12311MPFR plus primary separate. All increases/cumulativeR29 and source count erratum retained. UniversalCR/totality/floatFMA/stack/cycles/independent/performance/adoption/integration/HW/main/release OPEN.'
state['latest_goal_turn_classification'] = 'progress: R37 qualification completed then R38 source/model+1740673qualifiedARM finished; same augmented510->491 and expanded542->512/30fix, no wrong/new; selectedPRIVATE. Whole goal active.'
ledger.write_text(json.dumps(state, indent=2) + '\n')
with (ledger.parent / 'HANDOFF.md').open('a') as f: f.write('\n\n' + text + f'SourceFR{sha(S / "FROZEN.json")}; qualFR{sha(W / "FROZEN.json")}; author{sha(W / "author-result.json")}.\n')
print(json.dumps(dict(status='R38_PRIVATE_AUTHOR_QUALIFIED', source_FROZEN_sha256=sha(S / 'FROZEN.json'), qualification_FROZEN_sha256=sha(W / 'FROZEN.json'), author_result_sha256=sha(W / 'author-result.json'), ELF_sha256=sha(S / 'candidate.elf'), known_exp_losses=512, known_pow_losses=2501, qualified_ARM=1740673, actualFlashDelta=16, goal_complete=False), indent=2), flush=True)

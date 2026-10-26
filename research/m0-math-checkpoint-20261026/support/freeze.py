"""Freeze completed finite qualification and preserve every failed attempt."""
import collections,gzip,hashlib,json,re,struct
from pathlib import Path
W=Path(__file__).resolve().parent;ROOT=W.parents[1]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(name):return json.loads((W/name).read_text())
def write(name,v):(W/name).write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
f,ma,extra,body,prep=map(read,['float.json','fma.json','addendum.json','body-audit.json','preparation.json'])
assert f['status']==ma['status']=='PASS_FINITE_ARM_QUALIFICATION'
assert extra['status']=='PASS_BOUNDED_WIDTH_AND_STACK_ADDENDUM'
assert f['actual_public_calls']==397848 and ma['actual_public_calls']==ma['resident_public_calls']==30197
assert extra['actual_public_calls']==16869 and extra['resident_FMA_calls']==4560
assert len(extra['full_instruction_SP_probes'])==222
for report in [f,ma,extra]:
    for r in report['operations'].values():
        assert r['status']=='PASS' and r['wrong_rounding_or_value']==r['MPFR_integer_disagreements']==r['resident_fixture_raw_mismatches']==0
assert f['SIO_write_attempts']==ma['SIO_write_attempts']==ma['resident_SIO_write_attempts']==extra['SIO_writes']==extra['resident_SIO_writes']==0
assert len(body['unchanged_resident_allocated_sections'])==49 and len(body['body_records'])==22
assert body['added_section']['bytes']==3864
assert len(prep['objects'])==163 and not prep['source_recompiled']
assert not re.findall(r'\S*libgcc\.a\([^\n)]*\)',(W/'fixture.map').read_text())

# Immutable bindings for successful runs which preceded test-driver repairs.
lineage=read('producer-lineage.json')
for n,d in ma['producer_pins'].items():assert sha(W/lineage['FMA_report_producer_bindings'][n])==d,n
for op,r in f['operation_provenance'].items():
    base=W/r['completed_run'] if r['completed_run'].startswith('attempts/') else W
    for n,d in r['producer_pins'].items():assert sha(base/n)==d,(op,n)
for n,d in extra['shared_producer_pins'].items():assert sha(W/n)==d,n
assert sha(W/'addendum.py')==extra['producer_sha256']

pins={}
for name in ['.build/m0-asin-scaled-bound-v164-20261023/HANDOFF.json',
             '.build/m0-asin-scaled-bound-v164-20261023/FROZEN.json',
             '.build/m0-asin-scaled-bound-v164-20261023/firmware/mk61s-picocalc-pico-h.elf',
             '.build/m0-v138-execution-20261023/reference/reference.elf',
             'research/rp2040-memset-2026-10-21/capture/bootrom.bin',
             '.build/v164-independent-review-20261023/receipt.json']:
    pins[name]=sha(ROOT/name)
assert pins['.build/v164-independent-review-20261023/receipt.json']=='7db3b13ba31dd338e7c90d127130c1969de58fad2c4c4c95680127386f569caf'
assert pins['.build/m0-asin-scaled-bound-v164-20261023/HANDOFF.json']=='5ac1145af551dbe631c06a971fc9229659cf92ed4417de5d370e0bae889dc77f'
assert pins['.build/m0-asin-scaled-bound-v164-20261023/FROZEN.json']=='de4afedeb9d3efb513158f01f3bb81d3602e3b3639c903672354c4bd70738392'
for name,d in body['source_pins'].items():
    p='.build/m0-asin-scaled-bound-v164-20261023/source/'+name;assert sha(ROOT/p)==d;pins[p]=d

raw_sources=[];FMA_inputs=[]
for prefix,report in [('',f),('',ma),('addendum/',extra)]:
    for op,r in report['operations'].items():
        p=W/prefix/r['full_raw_records'];data=gzip.decompress(p.read_bytes())
        assert sha(p)==r['records_sha256'] and hashlib.sha256(data).hexdigest()==r['uncompressed_sha256']
        assert len(data)==48*r['cases']
        raw_sources.append(dict(operation=op,path=str(p.relative_to(W)),cases=r['cases'],sha256=sha(p),input_width=r['input_ABI_width'],result_width=r['result_width']))
        if op=='fma':FMA_inputs.extend(v[:3] for v in struct.iter_unpack('<6Q',data))
performance={}
for op in f['operations']:
    rows=list(f['operations'][op]['instruction_sample'])
    if op in extra['operations']:rows+=extra['operations'][op]['instruction_sample']
    native=[r for r in rows if 'reference_instructions' in r]
    correct=[r for r in native if r['owned_correct'] and r['reference_correct']]
    valid=correct
    if op in ['f2iz','f2uiz']:
        from oracles import float_integer
        valid=[r for r in correct if float_integer(int(r['arguments'][0],16),op=='f2iz')[1]]
    def means(rs):return dict(own=sum(r['own_instructions'] for r in rs)/len(rs),reference=sum(r['reference_instructions'] for r in rs)/len(rs)) if rs else dict(own=None,reference=None)
    slower=[r for r in correct if r['own_instructions']>r['reference_instructions']]
    unique_slow={tuple(r['arguments']) for r in slower}
    performance[op]=dict(sample_calls=len(rows),native_reference_calls=len(native),reference_wrong=sum(not r['reference_correct'] for r in native),
        raw_means=means(native),both_correct_calls=len(correct),both_correct_means=means(correct),
        both_correct_slower_calls=len(slower),distinct_sampled_slower_inputs=len(unique_slow),
        valid_range_both_correct_calls=len(valid),valid_range_both_correct_means=means(valid),
        valid_range_both_correct_slower=sum(r['own_instructions']>r['reference_instructions'] for r in valid),
        coverage='Deterministic instruction samples only; all rows and adverse inputs preserved. Comparison predicates lack matching ABI adapters.')
write('instruction-summary.json',dict(status='OBSERVED_FINITE_SAMPLED_INSTRUCTION_GAPS',operations=performance,
    FMA='No native FMA in pinned Qfplib. No unfused composition substituted.',old174matrix='Unchanged and separate; its507 known individual deficits are not a complete inventory of these new float/cold-conversion samples.',
    physical_cycles_measured=False,speed_goal_complete=False))

write('terminal-observations.json',dict(status='OBSERVED_TERMINAL_RECEIPTS',successful=[
    dict(stage='Diagnostic retained relink',exit_code=0,chunk='f3d53d'),
    dict(stage='Exact linked-body audit',exit_code=0,chunk='5ece2d'),
    dict(stage='Oracle self test after FMA precision tracking',exit_code=0,chunk='ad35e5'),
    dict(stage='Main FMA fixture+resident',exit_code=0,chunk='c74758'),
    dict(stage='Float completion with preserved add/sub',exit_code=0,chunk='3c5c35'),
    dict(stage='Subnormal-width and SP addendum',exit_code=0,chunk='cdcf2d')],
    corrected_author_harness_failures=[
        dict(stage='Ninja path discovery',exit_code=1,chunk='625faa',reason='CMAKE_MAKE_PROGRAM cache type was UNINITIALIZED rather than FILEPATH'),
        dict(stage='First diagnostic relink',exit_code=1,chunk='b0e560',reason='Retained float sections collided with deliberately fixed pow layout; diagnostic-only section introduced',log='fixture-link-first-overlap.log'),
        dict(stage='First float attempt',exit_code=1,chunk='74efb3',reason='Invalid raw word -1 in generator; preserved under attempts/initial'),
        dict(stage='Second float attempt',exit_code=1,chunk='038be7',reason='Wrong test job symbol __aeabi_ffrsub; completed add/sub retained; explicit complete-float.py entry map used')],
    hardware_accessed=False,production_numeric_failures_observed=0))

handoff=dict(status='FROZEN_AUTHOR_FINITE_FLOAT_FMA_QUALIFICATION_WITH_SPEED_GAPS',
    parent='V164/0B3BE556 unchanged',retained_entries=prep['retained'],source_recompiled=False,
    fixture_elf_sha256=sha(W/'fixture.elf'),resident_elf_sha256=body['resident_sha256'],
    copied_original_object_count=163,exact_previous_allocated_sections=49,
    diagnostic_footer_exception=body['diagnostic_footer_exception'],added_diagnostic_bytes=3864,
    exact_object_body_sections=22,libgcc_archive_members=[],
    float_corpus_calls=397848+12005+304,FMA_corpus_calls_each_ELF=30197+4560,
    FMA_distinct_triples=len(set(FMA_inputs)),FMA_total_fixture_and_resident_calls=2*len(FMA_inputs),
    extra_per_instruction_SP_probe_calls=222,total_accepted_public_calls=397848+30197+16869+30197+4560+222,
    count_note='Calls include repeats between corpora; only FMA_distinct_triples is deduplicated. ROM initializers and Qfplib samples are not included in public-call totals.',
    wrong_rounding_or_value=0,MPFR_integer_oracle_disagreements=0,resident_fixture_FMA_mismatches=0,
    oracles=dict(binary32='MPFR directed bounds with mpfr_get_flt, independently checked exact integer/rational RNE',
                 FMA='True ternary MPFR plus independent unbounded integer product+add+single RNE',
                 comparison='Exact bit-order and explicit unordered predicates',integer_conversion='Exact truncation in representable result range; saturating/NaN policy tested separately'),
    subnormal_input_width_coverage=dict(binary32_arithmetic=list(range(1,24)),binary32_unary=list(range(1,24)),binary64_FMA_and_d2f=list(range(1,53))),
    exponent_fields=dict(binary32=256,binary64_FMA_and_d2f=2048),
    FMA_MPFR_hard_cases=dict(main_precision_counts=ma['FMA_MPFR_precision_counts'],addendum_precision_counts=extra['FMA_MPFR_precision_counts'],maximum_bits=2048),
    maximum_observed_written_stack_bytes=196,maximum_instrumented_SP_depth=extra['maximum_probed_SP_depth'],
    stack_limit_enforced_each_call=4096,ABI='R4-R11/restored SP/bounded writes every call; selected222 probes additionally trace SP at every instruction',
    SIO_contexts_preserved_each_qualification_call=['READY clean','READY DIRTY','pending DIRTY'],SIO_write_attempts=0,
    no_ROM_intrinsic_models=not f['ROM_intrinsic_models'] and not ma['ROM_intrinsic_models'],
    current_production_use='Only f2d/d2f and binary64 FMA survive V164 link. Other float helpers and sqrtf are source implementations removed by GC.',
    known_speed_gaps='See instruction-summary.json. Float add/sub/mul/div/i2f/ui2f have substantial comparable instruction deficits; cold d2f and individual f2d/sqrtf paths also lose. No optimization attempted.',
    old174matrix_unchanged=True,independent_review_of_this_packet='Pending; existing V164 focused delta review does not review this new qualification',
    remaining=[
        'Finite qualification is not exhaustive all-input IEEE proof or universal speed acceptance; arbitrary mantissa/triple combinations remain unenumerated.',
        'Generic float arithmetic and integer-to-float remain significantly slower than Qfplib in sampled comparable cases; these functions are currently GC-removed.',
        'Broader resident d2f/f2d domains contain individual speed deficits not covered by the earlier174-group matrix.',
        'Native Qfplib FMA is absent; six comparison predicates have no matching ABI instruction baseline in this packet.',
        'SP maxima are measured on selected vectors and write footprints, not a universal static stack proof. No IRQ/cache/physical-cycle acceptance.',
        'RNE returned values only. NaN payload/sign choice is unspecified; quieting is required. errno/fenv exception flags/other rounding modes are outside runtime contract.',
        'General pow undecided1024-bit trap/all-input totality remains NOT_READY and was not changed or retested here.',
        'Numerical integration onto accepted repaired Pico RAM/USB/memory base, independent review, hardware preservation/restoration and release gates remain open.'
    ],
    raw_records=raw_sources,producer_lineage='producer-lineage.json; float.json operation_provenance; attempts snapshots preserve completed and failed runs',
    reproduction=[
        'Read-only verify.py checks this packet and pinned external inputs without executing Unicorn or repeating numerical qualifications.',
        'Reproduce only in a fresh private copy. Existing diagnostic ELF was relinked from exact original objects; prepare-fixture.py produces only ELF/map and never runs firmware post-build or USB tools.',
        'For a full float replay use complete-float.py --replay-all. qualify.py contains the preserved historical float launcher symbol error; its run_operation helper was used by the corrected explicit job map.',
        'For FMA reproduce the original producer bindings from producer-lineage.json in a fresh copy, then qualify.py --mode fma. Later corpus repair only clamps an invalid float raw word; FMA input digest is unchanged.',
        'addendum.py runs only the documented additional widths and SP vectors. Unicorn JIT needs host permission; no physical device is used.'
    ],
    external_pins=pins,canonical_changed=False,resident_changed=False,M4_changed=False,
    hardware_accessed=False,UF2_BIN_HEX_created=False,new_numeric_version_created=False,
    commit_created=False,pushed=False,production_promoted=False,goal_complete=False)
assert handoff['total_accepted_public_calls']==479893 and handoff['FMA_distinct_triples']==34740
write('HANDOFF.json',handoff)
files={str(p.relative_to(W)):sha(p) for p in W.rglob('*') if p.is_file() and p.name!='FROZEN.json' and '__pycache__' not in p.parts}
write('FROZEN.json',dict(status=handoff['status'],files=files,external_pins=pins,goal_complete=False))
print('FROZEN finite float/FMA packet:',len(files),'files;479893 public calls;0 wrong; substantial sampled speed gaps retained; no numerical/runtime change.')

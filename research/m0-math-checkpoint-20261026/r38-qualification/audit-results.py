"""Join every unfiltered R38 result and retain cumulative R29 costs, CPU only."""
from pathlib import Path
from collections import Counter
from itertools import zip_longest
import gzip, hashlib, json, sys
sys.dont_write_bytecode = True
W = Path(__file__).resolve().parent
ROOT = W.parents[1]
S = ROOT / '.build/m0-math-unified-exp-row0-midpoint-r38-20261026'
P = ROOT / '.build/m0-math-unified-exp-row0-small-r37-qualification-20261026'
R = ROOT / '.build/m0-math-unified-exp-bit62-r29-qualification-20261026'
read = lambda p: json.loads(p.read_bytes())

def quiet_nan(x):
    v = int(x, 16)
    return (v & 0x7ff0000000000000) == 0x7ff0000000000000 and bool(v & (1 << 51))

def gold_equal(x, y):
    return x == y or quiet_nan(x) and quiet_nan(y)

def sha(p):
    h = hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda: f.read(1048576), b''): h.update(b)
    return h.hexdigest()

def verify_manifest(d, pin):
    assert sha(d / 'FROZEN.json') == pin, d
    files = read(d / 'FROZEN.json')['files']
    for n, r in files.items():
        p = d / n
        assert p.stat().st_size == r['bytes'] and sha(p) == r['sha256'], p
    return len(files)

assert not (W / 'joined-audit.json').exists()
manifest_counts = {
    'source_R38': verify_manifest(S, 'da406f31b39e0a01ee415a1ee9d2658d1fbed5ac5ceb04784dc8a25e146a60a2'),
    'parent_R37_qualification': verify_manifest(P, '00dc5efa117f764392cacc06a7d97145ba9cca7650909dd4fc6b68cda5bae8e4')}
assert sha(R / 'FROZEN.json') == 'c1629034ff342e7f7da22d246d360e4548506500a99450d42772107bea4012c5'
reports = {n: read(W / (n + '-result.json')) for n in ('full', 'boundary', 'power', 'edge', 'admission', 'fresh-edge')}
matrix = read(W / 'matrix-comparison.json')
for r in matrix['matrices'].values():
    assert not r['new_correct_Qfplib_loss_rows'] and not r['parent_increase_rows']
    assert set(r['candidate_instruction_delta_histogram']) == {'0'}
for n in ('full', 'boundary', 'power', 'edge', 'admission'):
    r = reports[n]
    assert r['candidate_wrong'] == r['new_losing_inputs'] == r['actual_fresh_parent_Qfp_MPFR_calls'] == 0
    assert not r['new_correct_Qfplib_loss_rows']
    assert r['all_actual_fast_inputs_within_proved_domain'] and r['all_actual_helper_parameters_exact_and_in_domain']
assert (reports['full']['state_rows'], reports['full']['parent_losing_inputs'], reports['full']['candidate_losing_inputs']) == (989922, 260, 248)
assert (reports['boundary']['state_rows'], reports['boundary']['parent_losing_inputs'], reports['boundary']['candidate_losing_inputs'], reports['boundary']['actual_fresh_public_index0_poison16NZCV_calls']) == (176952, 442, 430, 36960)
assert (reports['power']['state_rows'], reports['power']['parent_losing_inputs'], reports['power']['candidate_losing_inputs']) == (31842, 10, 8)

assert (reports['edge']['state_rows'], reports['edge']['parent_losing_inputs'], reports['edge']['candidate_losing_inputs']) == (30939, 20, 17)
assert (reports['admission']['state_rows'], reports['admission']['parent_losing_inputs'], reports['admission']['candidate_losing_inputs']) == (26007, 510, 491)
target = set(read(W / 'fresh-edge-inputs.json')['groups'])
for name in ('boundary', 'power', 'edge', 'admission'):
    with gzip.open(W / (name + '-records.jsonl.gz'), 'rt') as f:
        target.update(json.loads(line)['x'] for line in f)
cache, union, parentloss, childloss, oldfull = {}, set(), set(), set(), set()
details, adverse_union = {}, {}
fields = ('candidate_output', 'candidate_instructions', 'inherited_R37_output', 'inherited_R37_instructions', 'inherited_Qfplib_output', 'inherited_Qfplib_instructions', 'inherited_Qfplib_correct')
for name in ('full', 'boundary', 'power', 'edge', 'admission'):
    report = reports[name]
    count = wrong = overlaps = 0
    hist, pl, cl, increases = Counter(), set(), set(), []
    with gzip.open(W / (name + '-records.jsonl.gz'), 'rt') as f:
        for line in f:
            r = json.loads(line); count += 1
            x, state = r['x'], r['SIO']; key = (x, state)
            union.add(x)
            if name == 'full': oldfull.add(x)
            assert r['candidate_output'] == r['inherited_R37_output']
            assert gold_equal(r['candidate_output'], r['expected_inherited_directed_MPFR'])
            if key in cache:
                overlaps += 1
                assert all(cache[key][k] == r[k] for k in fields), (key, name)
            if x in target: cache[key] = {k: r[k] for k in fields}
            cc, pc, qc = r['candidate_instructions'], r['inherited_R37_instructions'], r['inherited_Qfplib_instructions']
            delta = cc - pc; hist[delta] += 1
            if delta > 0:
                a = dict(x=x, SIO=state, parent=pc, candidate=cc, delta=delta, Qfplib=qc, Qfplib_correct=r['inherited_Qfplib_correct'])
                increases.append(a)
                assert key not in adverse_union or adverse_union[key] == a
                adverse_union[key] = a
            if not r['inherited_Qfplib_correct']: wrong += 1; continue
            if pc > qc: pl.add(x); parentloss.add(x)
            if cc > qc: cl.add(x); childloss.add(x)
    assert count == report['state_rows'] and increases == report['all_parent_increases']
    assert dict(hist) == {int(k): v for k, v in report['instruction_delta_histogram'].items()}
    assert wrong == report['wrong_inherited_Qfplib_rows_retained']
    assert len(pl) == report['parent_losing_inputs'] and cl == set(report['remaining_losing_arguments']) and not cl - pl
    details[name] = dict(state_rows=count, overlap_rows_checked=overlaps, parent_increase_rows=len(increases), instruction_delta_histogram=dict(hist), wrong_reference_rows_retained=wrong, parent_losing_inputs=len(pl), candidate_losing_inputs=len(cl))
    if name=='edge':
        prior_qualified_counts=(len(union),len(parentloss),len(childloss))
        assert prior_qualified_counts==(556422,462,447)
assert len(oldfull) == 494961 and len(union) == 556578
assert len(parentloss) == 510 and len(childloss) == 491 and not childloss - parentloss
oldunion, oldparent, oldchild = set(union), set(parentloss), set(childloss)

edge = reports['fresh-edge']
assert edge['candidate_wrong'] == edge['new_losing_inputs'] == 0 and not edge['new_correct_Qfplib_loss_rows']
assert edge['actual_directed_MPFR_inputs'] == 12311 and edge['actual_qualified_public_ARM_calls'] == 110799
count = wrong = overlaps = 0
hist, pl, cl, edge_unique, fresh_increases = Counter(), set(), set(), set(), []
with gzip.open(W / 'fresh-edge-records.jsonl.gz', 'rt') as f:
    for line in f:
        r = json.loads(line); count += 1
        x, state = r['x'], r['SIO']; key = (x, state)
        edge_unique.add(x); union.add(x)
        cc, pc, qc = (r['instructions'][k] for k in ('candidate', 'parent', 'Qfplib'))
        assert r['correct']['candidate'] and r['correct']['parent']
        assert r['outputs']['candidate'] == r['outputs']['parent'] == r['expected']
        if key in cache:
            overlaps += 1; z = cache[key]
            assert z['candidate_output'] == r['outputs']['candidate'] and z['candidate_instructions'] == cc
            assert z['inherited_R37_output'] == r['outputs']['parent'] and z['inherited_R37_instructions'] == pc
            assert z['inherited_Qfplib_output'] == r['outputs']['Qfplib'] and z['inherited_Qfplib_instructions'] == qc
            assert z['inherited_Qfplib_correct'] == r['correct']['Qfplib']
        delta = cc - pc; hist[delta] += 1
        if delta > 0:
            fresh_increases.append(r)
            a = dict(x=x, SIO=state, parent=pc, candidate=cc, delta=delta, Qfplib=qc, Qfplib_correct=r['correct']['Qfplib'])
            assert key not in adverse_union or adverse_union[key] == a
            adverse_union[key] = a
        if not r['correct']['Qfplib']: wrong += 1; continue
        if pc > qc: pl.add(x); parentloss.add(x)
        if cc > qc: cl.add(x); childloss.add(x)
assert count == edge['state_rows'] == 36933
assert len(edge_unique) == 12311 and len(edge_unique - oldunion) == 12278 and len(union) == 568856
assert fresh_increases == edge['all_parent_increases'] and wrong == edge['wrong_Qfplib_rows_retained']
assert dict(hist) == {int(k): v for k, v in edge['instruction_delta_histogram'].items()}
assert len(pl) == edge['parent_losing_inputs'] and cl == set(edge['remaining_losing_arguments'])
assert not childloss - parentloss
details['fresh-edge'] = dict(state_rows=count, overlap_rows_checked=overlaps, parent_increase_rows=len(fresh_increases), instruction_delta_histogram=dict(hist), wrong_reference_rows_retained=wrong, parent_losing_inputs=len(pl), candidate_losing_inputs=len(cl))

# All cumulative rows are preserved, even when Qfplib is wrong or we were already slower.
cumulative = {}
for name in ('full', 'original507', 'broad'):
    parentfile = R / ('exp-records.jsonl.gz' if name == 'full' else name + '-records.jsonl.gz')
    currentfile = W / (name + '-records.jsonl.gz')
    pin = read(R / 'FROZEN.json')['files'][parentfile.name]
    assert parentfile.stat().st_size == pin['bytes'] and sha(parentfile) == pin['sha256']
    count = total = positive = negative = 0; hist = Counter()
    filename = 'cumulative-R29-' + name + '-records.jsonl.gz'
    with gzip.open(parentfile, 'rt') as old, gzip.open(currentfile, 'rt') as new, gzip.GzipFile(filename=str(W / filename), mode='wb', mtime=0) as out:
        for aa, bb in zip_longest(old, new):
            assert aa is not None and bb is not None
            a, b = json.loads(aa), json.loads(bb); count += 1
            for k in ('operation', 'x', 'y', 'SIO'): assert a.get(k) == b.get(k), (name, count, k)
            if name == 'full':
                ca, cb = a['candidate_instructions'], b['candidate_instructions']
                assert a['candidate_output'] == b['candidate_output']
                for k in ('inherited_Qfplib_instructions', 'inherited_Qfplib_correct', 'inherited_Qfplib_output'): assert a[k] == b[k]
                refs = dict(instructions=b['inherited_Qfplib_instructions'], correct=b['inherited_Qfplib_correct'], output=b['inherited_Qfplib_output'])
            else:
                ca, cb = a['instructions']['candidate'], b['instructions']['candidate']
                assert a['outputs'] == b['outputs'] and a['correct'] == b['correct']
                refs = {k: dict(instructions=v, correct=b['correct'][k], output=b['outputs'][k]) for k, v in b['instructions'].items() if k not in ('candidate', 'zero-control')}
            delta = cb - ca; hist[delta] += 1; total += delta; positive += max(delta, 0); negative += min(delta, 0)
            out.write((json.dumps(dict(operation=b['operation'], x=b['x'], y=b.get('y'), SIO=b['SIO'], R29=ca, R38=cb, delta=delta, references=refs), separators=(',', ':')) + '\n').encode())
    cumulative[name] = dict(state_rows=count, instruction_delta_histogram=dict(hist), net_instruction_delta=total, positive_instruction_sum=positive, negative_instruction_sum=negative, increased_rows=sum(v for k, v in hist.items() if k > 0), decreased_rows=sum(v for k, v in hist.items() if k < 0), unchanged_rows=hist[0], all_rows_retained_file=filename, records_sha256=sha(W / filename))
    print('cumulative', name, count, 'net', total, 'increased', cumulative[name]['increased_rows'], flush=True)
assert cumulative['full']['state_rows'] == 989922
primary = sum(read(W / (n + '.json'))['actual_qualified_math_ARM_calls'] for n in ('original507', 'broad'))
assert primary == 196714
public = primary + sum(reports[n]['actual_qualified_public_ARM_calls'] for n in ('full', 'boundary', 'power', 'edge', 'admission', 'fresh-edge'))
assert public == 1604695
primitive = read(S / 'bridge-control-result.json')['actual_qualified_control_ARM_calls']
assert primitive == 135978 and public + primitive == 1740673

# Receipt names are explicit: avoid the R37 metadata field-label mistake.
checked_pins = {}
for name, receipt_name, expected in (
    ('R30-review-local-pins.json', 'm0-math-unified-exp-cached-index-r30-independent-20261026', 'e36d26d2a5241f76a345b592449a763f93f41a68597a4cad7a71ad76533863d3'),
    ('R33-review-local-pins.json', 'm0-math-unified-exp-positive-bridge-r33-independent-20261026', 'cb914841a63f96fc90f3833b3f522e54ef4b5fcf5694d3bc66a78beb31fddea1')):
    q = read(P / name); assert q['review_sha256'] == expected
    receipt = ROOT / '.build' / receipt_name / 'FINAL-REVIEW.json'
    assert sha(receipt) == expected
    for n, pin in q['pins'].items():
        f = Path(n)
        assert f.stat().st_size == pin['bytes'] and sha(f) == pin['sha256'], f
        checked_pins[n] = pin
    (W / name).write_bytes((P / name).read_bytes())
erratum_path = ROOT / '.build/m0-exp-r36-author-metadata-clarification-20261026.json'
assert sha(erratum_path) == '3aba8efa1eb2ab89818c531a3b404d044a4b9aaeaef323054817c5bc08180101'
erratum = read(erratum_path)
for n, pin in erratum['actual_new_R35_direct_pins'].items():
    f = Path(n)
    assert f.stat().st_size == pin['bytes'] and sha(f) == pin['sha256'], f
    checked_pins[n] = pin
assert sha(ROOT / erratum['actual_new_R35_narrow_receipt_path']) == erratum['actual_new_R35_narrow_receipt_sha256']
(W / 'inherited-review-pin-revalidation.json').write_text(json.dumps(dict(status='PASS_R30_R33_R35_NARROW_RECEIPT_CURRENT_DIRECT_PINS', checked=checked_pins, R37_metadata_erratum_path=str(erratum_path.relative_to(ROOT)), R37_metadata_erratum_sha256=sha(erratum_path), frozen_R37_bytes_unmodified=True, new_ARM_MPFR_calls=0, no_R38_independent_performance_adoption_GO=True), indent=2) + '\n')

scope_correction = ROOT / '.build/m0-exp-r38-source-scope-correction-20261026.json'
assert sha(scope_correction) == '49abbcd4cd4b97ee00ee0e6590abcae25e7512514b864db594f2a953e1bb5c35'
assert read(scope_correction)['source_FROZEN_sha256'] == sha(S / 'FROZEN.json')
assert read(scope_correction)['corrected_counts'] == dict(old462_fixed=15, new48_fixed=4, total_fixed=19)
assert read(W / 'admissions.json')['old462_fixed'] == 15 and read(W / 'admissions.json')['new48_fixed'] == 4
out = dict(status='PASS_R38_ALL_REPLAYS_FRESH_EDGES_PRIMARY_AND_CUMULATIVE_R29', source_FROZEN_sha256=sha(S / 'FROZEN.json'), parent_qualification_FROZEN_sha256=sha(P / 'FROZEN.json'), verified_manifest_file_counts=manifest_counts,
    old_exp_inputs=494961, old_parent_losing_inputs=260, old_candidate_losing_inputs=248, old_fixed_inputs=12,
    same_prior_qualified_union_inputs=556422, same_prior_qualified_parent_losses=462, same_prior_qualified_candidate_losses=447, same_prior_qualified_fixed=15,
    same_prior_union_inputs=len(oldunion), same_prior_union_parent_losses=len(oldparent), same_prior_union_candidate_losses=len(oldchild), same_prior_union_fixed=len(oldparent - oldchild),
    diagnostic_admission_new_inputs=156, diagnostic_admission_new_parent_preexisting_losses=48, diagnostic_admission_new_fixed=4,
    union_exp_inputs=len(union), union_parent_losing_inputs=len(parentloss), union_candidate_losing_inputs=len(childloss), union_fixed_inputs=len(parentloss - childloss), union_new_losing_inputs=0, candidate_wrong=0,
    fresh_edge_unique_inputs=12311, fresh_edge_new_inputs=12278, fresh_edge_new_parent_preexisting_losses=len(parentloss - oldparent), fresh_edge_new_remaining_losses=len(childloss - oldchild),
    fresh_edge_actual_directed_MPFR_inputs=12311, fresh_edge_public_ARM_calls=110799, fresh_edge_actual_parent_Qfp_calls=73866,
    remaining_losing_arguments=sorted(childloss), fixed_losing_arguments=sorted(parentloss - childloss), new_parent_preexisting_losing_arguments=sorted(parentloss - oldparent), per_campaign=details,
    all_parent_increases_deduplicated_state_rows=sorted(adverse_union.values(), key=lambda r: (r['x'], r['SIO'])), all_parent_cost_increases_and_wrong_refs_retained=True, no_nominal_reference_filter=True,
    actual_qualified_public_ARM_calls=public, actual_fresh_full_public_ARM_calls=989922, actual_fresh_boundary_public_ARM_calls=213912, actual_fresh_inherited_power_public_ARM_calls=31842, actual_fresh_inherited_edge_public_ARM_calls=30939, actual_fresh_diagnostic_admission_public_ARM_calls=30567, actual_fresh_primary_public_ARM_calls=196714,
    actual_fresh_qualified_primitive_ARM_calls=primitive, actual_qualified_ARM_calls=public + primitive, primitive_marker_controls_not_public_gold=True, inherited_real_helper921901_not_fresh=True,
    all5replays_actual_fresh_MPFR_Qfp_parent_calls=0, replay_gold_Qfp_parent_inherited_from_R37_qualification_or_R38_frozen_diagnostic=True,
    diagnostics78021_ARM_8669MPFR_and_source_loader2_not_pooled=True, generation_log2_mul_sub_and_delta_MPFR_not_validation_pool=True,
    all_primary_outputs_refs_and_own_instruction_counts_exact_R37=True, primary_parent_increase_rows=0,
    cumulative_R29=cumulative, cumulative_R29_scope='Original494961 full plus primary only. Additional73895 inputs have no R29 remeasurement here. State-row sums are not workload weighted or physical cycles.',
    current_pow_losing_pairs_inherited=2501, current_ln_losing_inputs_inherited=0, known_finite_losing_operation_argument_tuples=2501 + len(childloss), whole_remaining_library_count=False,
    actual_public_row0_poison16NZCV_calls=41520, actual_public_row0_poison_unique_inputs=173, all_row0_bits_costs_and_private_inputs_valid=True, observed_exp_stack=max(reports[n].get('observed_stack', 0) for n in ('full', 'boundary', 'power', 'edge', 'admission')), not_universal_stack_bound=True,
    additive_source_subset_count_erratum=str(scope_correction.relative_to(ROOT)), additive_source_subset_count_erratum_sha256=sha(scope_correction), frozen_source_bytes_unmodified=True,
    selected=False, independent_acceptance=False, performance_or_adoption_GO=False, hardware_accessed=False, physical_cycles_measured=False, integration_GO=False, goal_complete=False)
(W / 'joined-audit.json').write_text(json.dumps(out, indent=2) + '\n')
print(json.dumps({k: v for k, v in out.items() if k not in ('remaining_losing_arguments', 'fixed_losing_arguments', 'new_parent_preexisting_losing_arguments', 'all_parent_increases_deduplicated_state_rows')}, indent=2), flush=True)

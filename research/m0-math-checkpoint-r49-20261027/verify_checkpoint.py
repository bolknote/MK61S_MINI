"""Portable read-only archive consumer; never imports or executes producers."""
from pathlib import Path, PurePosixPath
from collections import Counter
import argparse, contextlib, gzip, hashlib, json, re, sys
sys.dont_write_bytecode = True
W = Path(__file__).resolve().parent
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--records', action='store_true')
parser.add_argument('--report', type=Path)
args = parser.parse_args()
def digest_stream(f):
    h, n = hashlib.sha256(), 0
    for b in iter(lambda: f.read(1 << 20), b''):
        h.update(b); n += len(b)
    return h.hexdigest(), n
def digest(p):
    with p.open('rb') as f:
        return digest_stream(f)[0]
reserved = re.compile(r'^(?:CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\.|$)', re.I)
def path(name):
    p = PurePosixPath(name)
    assert p.parts and not p.is_absolute() and all(q not in ('.', '..') for q in p.parts), name
    for q in p.parts:
        assert not reserved.match(q) and q[-1] not in '. ' and not any(c in q for c in '<>:"\\|?*'), name
    result = W.joinpath(*p.parts)
    assert not result.is_symlink(), name
    return result
index = json.loads((W / 'checkpoint.json').read_text())
names = set(index['files']) | {'checkpoint.json'}
assert len(names) == len({s.casefold() for s in names})
assert names == {str(p.relative_to(W)) for p in W.rglob('*') if p.is_file() and '__pycache__' not in p.parts}
for name, pin in index['files'].items():
    assert digest(path(name)) == pin, name
provenance = json.loads((W / 'provenance.json').read_text())
entries = provenance['archived_files']
by_source = {r['source']: r for r in entries}
assert len(by_source) == len(entries)
verified = {}
@contextlib.contextmanager
def original_stream(row):
    if row['encoding'] == 'identity':
        with path(row['path']).open('rb') as f:
            yield f
    else:
        assert row['encoding'] == 'gzip'
        with gzip.open(path(row['path']), 'rb') as f:
            yield f
for r in entries:
    key = r['uncompressed_sha256']
    if key not in verified:
        assert digest(path(r['path'])) == r['sha256'] and path(r['path']).stat().st_size == r['stored_bytes']
        with original_stream(r) as f:
            actual, n = digest_stream(f)
        assert actual == key and n == r['uncompressed_bytes'], r['source']
        verified[key] = (n, r['path'], r['encoding'], r['sha256'], r['stored_bytes'])
    assert verified[key] == (r['uncompressed_bytes'], r['path'], r['encoding'], r['sha256'], r['stored_bytes']), r['source']
def source_json(source):
    with original_stream(by_source[source]) as f:
        return json.load(f)
omitted = {r['source']: r for r in provenance['omitted_binary_files']}
assert len(omitted) == len(provenance['omitted_binary_files'])
packets = json.loads((W / 'packets.json').read_text())
pins = 0
for label, p in packets.items():
    if not p['FROZEN_sha256']:
        continue
    source = p['original_directory']
    assert by_source[source+'/FROZEN.json']['uncompressed_sha256'] == p['FROZEN_sha256']
    m = source_json(source+'/FROZEN.json')
    assert len(m['files']) == p['frozen_pinned_files']
    for name, pin in m['files'].items():
        original = source+'/'+name
        r = by_source.get(original)
        if r:
            assert (r['uncompressed_sha256'], r['uncompressed_bytes']) == (pin['sha256'], pin['bytes']), original
        else:
            r = omitted[original]
            assert (r['sha256'], r['bytes']) == (pin['sha256'], pin['bytes']), original
        pins += 1
report = dict(status='PASS_PRIVATE_INTERMEDIATE_CHECKPOINT', stored_files=len(names), original_payloads_verified=len(entries), unique_payloads_verified=len(verified), frozen_manifest_pins_verified=pins, compiled_binaries_deliberately_omitted=len(omitted), portable_case_unique_paths=True, source_to_archive_path_mapping_verified=True, original_FROZEN_bytes_preserved=True, no_external_archive_or_live_source_dependency=True, new_ARM_MPFR_calls=0, hardware_accessed=False, integration_GO=False, goal_complete=False)
def equal64(got, expected):
    got, expected = int(got, 16), int(expected, 16)
    if expected & 0x7fffffffffffffff > 0x7ff0000000000000:
        return got & 0x7fffffffffffffff > 0x7ff0000000000000 and bool(got & (1 << 51))
    return got == expected
def records(label, filename):
    source = packets[label]['original_directory']+'/'+filename
    with original_stream(by_source[source]) as raw, gzip.GzipFile(fileobj=raw) as f:
        for line in f:
            yield json.loads(line)
if args.records:
    report['recounted_preserved_campaigns'] = {}
    campaigns = [
        ('q85-small', 'targeted', 1536, 512, 1, 3, 'V3', 1503),
        ('q85-small', 'full', 1224907, 568856, 1, 794715, 'V3', 427353),
        ('incremental-r2', 'targeted', 1536, 512, 0, 0, 'Q85', 1467),
        ('incremental-r2', 'full', 1224907, 568856, 0, 809101, 'Q85', 402182),
    ]
    for label, phase, nrows, ninputs, nloss, ninc, other, ninc_other in campaigns:
        result = source_json(packets[label]['original_directory']+'/'+phase+'-result.json')
        adverse = iter(records(label, phase+'-parent-increases.jsonl.gz'))
        adverse_other = iter(records(label, phase+'-'+other+'-increases.jsonl.gz'))
        total = wrong_refs = 0
        masks, losses = {}, set()
        increases, hist, other_hist, paths, newloss = 0, Counter(), Counter(), Counter(), set()
        increases_other = 0
        for row in records(label, phase+'-records.jsonl.gz'):
            total += 1
            assert row['correct']['candidate'] and equal64(row['outputs']['candidate'], row['expected'])
            x, sio = row['x'], row['SIO']
            bit = {'READY':1, 'DIRTY':2, 'PENDING':4}[sio]
            assert not masks.get(x, 0) & bit, (label, phase, x, sio)
            masks[x] = masks.get(x, 0) | bit
            costs = row['instructions']
            delta = costs['candidate'] - costs['parent_R48']
            delta_other = costs['candidate'] - costs['parent_'+other]
            assert delta == row['parent_instruction_delta']
            assert delta_other == row[other+'_instruction_delta']
            hist[delta] += 1; other_hist[delta_other] += 1
            if delta > 0:
                assert next(adverse, None) == row
                increases += 1
            if delta_other > 0:
                assert next(adverse_other, None) == row
                increases_other += 1
            refs = [name for name in row['outputs'] if name == 'Qfplib' or name.startswith('qfp_')]
            assert refs
            for name in refs:
                correct = equal64(row['outputs'][name], row['expected'])
                assert correct == row['correct'][name]
                wrong_refs += not correct
                if correct and costs['candidate'] > costs[name]:
                    losses.add(x)
                    if costs['parent_R48'] <= costs[name]:
                        newloss.add((x, sio))
            key = 'small'+str(row['actual_Q85_small_visits'])
            if 'actual_incremental_visits' in row:
                key += '_incremental'+str(row['actual_incremental_visits'])
            paths[key+'_fallback'+str(row['actual_legacy_exp_visits'])] += 1
        assert next(adverse, None) is None and next(adverse_other, None) is None
        assert (total, len(masks), len(losses), increases, increases_other) == (nrows, ninputs, nloss, ninc, ninc_other)
        assert result['state_rows'] == total and result['unique_inputs'] == len(masks)
        assert result['candidate_losing_unique_inputs'] == len(losses) and not newloss
        assert {int(k):v for k,v in result['parent_R48_delta_histogram'].items()} == hist
        assert {int(k):v for k,v in result['parent_'+other+'_delta_histogram'].items()} == other_hist
        assert result['actual_path_histogram'] == paths
        assert result['wrong_reference_rows_retained'] == wrong_refs
        assert wrong_refs == (414230 if phase == 'full' else 0)
        assert next(iter(records(label, phase+'-new-losses.jsonl.gz')), None) is None
        report['recounted_preserved_campaigns'][label+'/'+phase] = dict(state_rows=total, unique_inputs=len(masks), losing_unique_inputs=len(losses), all_R48_increase_rows=increases, all_other_parent_increase_rows=increases_other, adverse_streams_exact=True, wrong_Qfplib_rows_retained=wrong_refs, new_correct_Qfplib_loss_rows=len(newloss))
        print('RECOUNTED', label, phase, total, len(losses), increases, increases_other, flush=True)
    report['probe_recounts'] = {}
    for label, nrows, nloss, hard in [('q83-prototype',39,5,629), ('incremental-v1',57,1,649), ('incremental-r2',57,0,634), ('r49-source',57,0,634)]:
        total = 0
        losses, hard_states, states = set(), set(), set()
        for row in records(label, 'probe-records.jsonl.gz'):
            total += 1
            state = row['x'], row['SIO']
            assert state not in states
            states.add(state)
            assert row['correct']['candidate'] and equal64(row['outputs']['candidate'], row['expected'])
            correct = equal64(row['outputs']['Qfplib'], row['expected'])
            assert correct == row['correct']['Qfplib']
            if correct and row['instructions']['candidate'] > row['instructions']['Qfplib']:
                losses.add(row['x'])
            if row['x'] == '4068D94447091680':
                assert correct and row['instructions']['candidate'] == hard and row['instructions']['Qfplib'] == 634
                hard_states.add(row['SIO'])
        assert total == nrows and len(losses) == nloss and hard_states == {'READY','DIRTY','PENDING'}, (label, total, len(losses))
        report['probe_recounts'][label] = dict(state_rows=total, losing_unique_inputs=len(losses), hard_case_instructions=hard, Qfplib_hard_case_instructions=634)
    report['legal_caller_recounts'] = {}
    for label in ('q85-small', 'incremental-r2'):
        total, seen, cases = 0, set(), {}
        for row in records(label, 'caller-state-records.jsonl.gz'):
            total += 1
            key = row['x'], row['SIO'], row['NZCV'], row['R12']
            assert key not in seen; seen.add(key)
            assert equal64(row['actual'], row['expected']) and row['instructions'] == row['baseline_instructions']
            cases.setdefault((row['x'], row['SIO']), set()).add((row['NZCV'], row['R12']))
        assert total == 3360 and len(cases) == 42
        for values in cases.values():
            assert len(values) == 80 and {v[0] for v in values} == set(range(16)) and len({v[1] for v in values}) == 5
        report['legal_caller_recounts'][label] = dict(variation_rows=total, input_SIO_cases=len(cases), NZCV_values=16, R12_values=5)
    report['host_recounts'] = {}
    for label in ('q83-host', 'incremental-host', 'incremental-coarse-host', 'incremental-ratio9-host'):
        total, seen = 0, set()
        for row in records(label, 'records.jsonl.gz'):
            total += 1
            assert row['x'] not in seen; seen.add(row['x'])
            m = row['model']
            assert m['kind'] == 'accepted' and f"{m['output']:016X}" == row['expected'] == m['lower_round'] == m['upper_round']
        assert total == 12500
        report['host_recounts'][label] = dict(accepted_inputs=total, candidate_wrong=0, new_ARM_MPFR_calls=0)
    report['R49_preserved_source_gates'] = {}
    for name in ['private-return-proof.json','private-guard-controls.json','loader-layout-proof.json','disabled-isolation.json','div-guard-proof.json','native-caller-proof.json','private-caller-proof.json','normalized-caller-proof.json','prototype-bank-equivalence-proof.json']:
        gate = source_json(packets['r49-source']['original_directory']+'/'+name)
        assert gate['status'].startswith('PASS_'), (name, gate['status'])
        report['R49_preserved_source_gates'][name] = gate['status']
    author = source_json(packets['r49-source']['original_directory']+'/AUTHOR-SOURCE-RESULT.json')
    assert author['coupled_full_qualification_pending'] and not author['selected'] and not author['canonical_runtime_integrated']
    assert index['selected_private_author_source'] == 'R48' and not index['R49_coupled_qualification_started']
if args.report:
    p = args.report.resolve()
    assert p != W and W not in p.parents, 'Receipts must be outside the immutable archive.'
    p.write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps({k:v for k,v in report.items() if k != 'recounted_preserved_campaigns'}, indent=2))

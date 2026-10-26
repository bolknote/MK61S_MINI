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
        ('r48-qualification', 'full-records.jsonl.gz', 281430, 1995, 84),
        ('r48-qualification', 'admission-records.jsonl.gz', 50220, 2045, 6),
        ('r48-qualification', 'exp-records.jsonl.gz', 1224907, 512, 0),
        ('r48-qualification', 'ln-records.jsonl.gz', 360590, 0, 0),
        ('r48-source', 'div-probe-records.jsonl.gz', 8586, 0, 1578),
        ('r48-source', 'boundary-replay-records.jsonl.gz', 231846, 0, 116436),
        ('r48-source', 'probe-records.jsonl.gz', 50220, 2045, 6),
    ]
    # V1's historical result JSON duplicates all adverse rows and is 596 MB.
    # Recount the preserved raw stream instead of materializing that JSON.
    scope = json.loads((W / 'scope.json').read_text())
    for label in ('q73-public-v1', 'q73-public-v2', 'q73-public-v3'):
        for phase in ('targeted', 'full'):
            result = scope['exp_Q73_public_prototypes'][label][phase]
            campaigns.append((label, phase+'-records.jsonl.gz', result['state_rows'], result['losing_unique_inputs'], result['all_parent_increase_rows']))
    for label, filename, expected_rows, expected_losses, expected_increases in campaigns:
        total = increases = wrong_refs = 0
        losses, inputs, states, deltas, newloss = set(), set(), set(), Counter(), set()
        legacy = Counter()
        for row in records(label, filename):
            total += 1
            assert row['correct']['candidate'] and equal64(row['outputs']['candidate'], row['expected']), (label, filename, total)
            key = (row.get('x', row.get('a')), row.get('y', row.get('b')))
            inputs.add(key)
            state = (*key, row['SIO'])
            assert state not in states, (label, filename, state)
            states.add(state)
            costs = row['instructions']
            parent = next(n for n in ('parent_R48', 'parent', 'inherited_R38', 'inherited_R18') if n in costs)
            delta = costs['candidate']-costs[parent]
            increases += delta > 0; deltas[delta] += 1
            if 'parent_instruction_delta' in row:
                assert delta == row['parent_instruction_delta']
            if 'proved_route_equation_delta' in row:
                coeff = dict(GN=-1, GR=3, PN=-10, PR=12, SN=2, SR=5)
                assert delta == row['proved_route_equation_delta'] == sum(coeff[k]*v for k,v in row['actual_R48_route_profile'].items())
            refs = [n for n in costs if n.startswith('qfp_') or n == 'Qfplib']
            assert refs
            for n in refs:
                correct = equal64(row['outputs'][n], row['expected'])
                assert correct == row['correct'][n]
                wrong_refs += not correct
                if correct and costs['candidate'] > costs[n]:
                    losses.add(key)
                    if costs[parent] <= costs[n]:
                        newloss.add(state)
            if 'actual_legacy_exp_visits' in row:
                legacy[row['actual_legacy_exp_visits']] += 1
        assert (total, len(losses), increases) == (expected_rows, expected_losses, expected_increases), (label, filename, total, len(losses), increases, expected_increases)
        report['recounted_preserved_campaigns'][label+'/'+filename] = dict(inputs=len(inputs), state_rows=total, losing_unique_inputs=len(losses), all_parent_increase_rows=increases, new_losing_state_rows=len(newloss), wrong_reference_rows_retained=wrong_refs, legacy_visits=dict(legacy), instruction_delta_histogram=dict(sorted(deltas.items())))
        print('RECOUNTED', label, filename, total, len(losses), increases, flush=True)
    report['host_model_classifications'] = {}
    for label, expected in [('q73-host-512', dict(accepted=482, ambiguous=30)), ('q73-host-full', dict(accepted=167461, ambiguous=4249, unsupported=397146)), ('q73-horner', dict(accepted=167464, ambiguous=4246, unsupported=397146))]:
        kinds = Counter()
        for row in records(label, 'records.jsonl.gz'):
            kinds[row['kind']] += 1
            if row['kind'] == 'accepted':
                m = row['model']
                assert f"{m['output']:016X}" == row['expected'] == m['lower_round'] == m['upper_round']
        assert kinds == expected, (label, kinds)
        report['host_model_classifications'][label] = dict(kinds)
    core_calls = Counter()
    for row in records('q73-thumb-core', 'records.jsonl.gz'):
        assert row['actual'] == row['expected']
        core_calls[row['kind']] += 1
    assert sum(core_calls.values()) == 180528, core_calls
    report['standalone_polynomial_records'] = dict(core_calls)
if args.report:
    p = args.report.resolve()
    assert p != W and W not in p.parents, 'Receipts must be outside the immutable archive.'
    p.write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps({k:v for k,v in report.items() if k != 'recounted_preserved_campaigns'}, indent=2))

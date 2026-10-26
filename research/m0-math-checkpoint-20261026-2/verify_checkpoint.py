"""Portable, read-only archive consumer. Does not execute historical producers.

Usage: python3 verify_checkpoint.py [--records] [--report PATH]
"""
from pathlib import Path, PurePosixPath
from collections import Counter
import argparse, gzip, hashlib, io, json, re, sys
sys.dont_write_bytecode = True
W = Path(__file__).resolve().parent
sha = lambda data: hashlib.sha256(data).hexdigest()
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--records', action='store_true', help='recount the preserved ARM and host-study records; no new ARM/MPFR execution')
parser.add_argument('--report', type=Path)
args = parser.parse_args()
index = json.loads((W / 'checkpoint.json').read_text())
reserved = re.compile(r'^(?:CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\.|$)', re.I)
def path(name):
    parts = PurePosixPath(name).parts
    assert parts and not PurePosixPath(name).is_absolute() and all(p not in ('.', '..') for p in parts), name
    for p in parts:
        assert not reserved.match(p) and p[-1] not in '. ' and not any(c in p for c in '<>:"\\|?*'), name
    result = W.joinpath(*parts)
    assert not result.is_symlink(), name
    return result
names = list(index['files']) + ['checkpoint.json']
assert len(names) == len({name.casefold() for name in names})
for name, pin in index['files'].items():
    assert sha(path(name).read_bytes()) == pin, name
actual = {str(p.relative_to(W)).replace('\\', '/') for p in W.rglob('*') if p.is_file() and '__pycache__' not in p.parts}
assert actual == set(names), (actual - set(names), set(names) - actual)
provenance = json.loads((W / 'provenance.json').read_text())
entries = provenance['archived_files']
by_source = {row['source']: row for row in entries}
assert len(by_source) == len(entries)
cache = {}
def read_source(source):
    row = by_source[source]
    digest = row['uncompressed_sha256']
    if digest not in cache:
        payload = path(row['path']).read_bytes()
        assert sha(payload) == row['sha256'] and len(payload) == row['stored_bytes'], source
        assert row['encoding'] in ('identity', 'gzip'), source
        data = gzip.decompress(payload) if row['encoding'] == 'gzip' else payload
        assert sha(data) == digest and len(data) == row['uncompressed_bytes'], source
        cache[digest] = data
    assert len(cache[digest]) == row['uncompressed_bytes'], source
    return cache[digest]
for row in entries:
    read_source(row['source'])
omitted = {row['source']: row for row in provenance['omitted_binary_files']}
assert len(omitted) == len(provenance['omitted_binary_files'])
packets = json.loads((W / 'packets.json').read_text())
frozen_count = 0
for label, packet in packets.items():
    if not packet['FROZEN_sha256']:
        continue
    source = packet['original_directory']
    data = read_source(source + '/FROZEN.json')
    assert sha(data) == packet['FROZEN_sha256'], label
    manifest = json.loads(data)
    assert len(manifest['files']) == packet['frozen_pinned_files']
    for name, pin in manifest['files'].items():
        original = source + '/' + name
        if original in by_source:
            data = read_source(original)
            assert sha(data) == pin['sha256'] and len(data) == pin['bytes'], original
        else:
            row = omitted[original]
            assert row['sha256'] == pin['sha256'] and row['bytes'] == pin['bytes'], original
        frozen_count += 1
report = dict(status='PASS_PRIVATE_INTERMEDIATE_CHECKPOINT', stored_files=len(names), original_payloads_verified=len(entries), unique_payloads_verified=len(cache), frozen_manifest_pins_verified=frozen_count, compiled_binaries_deliberately_omitted=len(omitted), portable_case_unique_paths=True, source_to_archive_path_mapping_verified=True, original_FROZEN_bytes_preserved=True, new_ARM_MPFR_calls=0, hardware_accessed=False, integration_GO=False, goal_complete=False)
def equal64(got, expected):
    """Project policy: any quiet NaN for NaN; all other bits exact."""
    got, expected = int(got, 16), int(expected, 16)
    if expected & 0x7fffffffffffffff > 0x7ff0000000000000:
        return got & 0x7fffffffffffffff > 0x7ff0000000000000 and bool(got & (1 << 51))
    return got == expected
def records(label, filename):
    original = packets[label]['original_directory'] + '/' + filename
    with gzip.GzipFile(fileobj=io.BytesIO(read_source(original))) as stream:
        for line in stream:
            yield json.loads(line)
if args.records:
    campaigns = [
        ('r47-qualification', 'full-records.jsonl.gz', 281430, 1995, 17158),
        ('r47-qualification', 'admission-records.jsonl.gz', 50220, 2045, 36),
        ('r47-qualification', 'exp-records.jsonl.gz', 1224907, 512, 0),
        ('r47-qualification', 'ln-records.jsonl.gz', 360590, 0, 0),
        ('r47-source', 'div-probe-records.jsonl.gz', 8586, 0, 2568),
        ('r47-source', 'boundary-replay-records.jsonl.gz', 231846, 0, 48426),
        ('r48-source', 'div-probe-records.jsonl.gz', 8586, 0, 1578),
        ('r48-source', 'boundary-replay-records.jsonl.gz', 231846, 0, 116436),
        ('r48-source', 'probe-records.jsonl.gz', 50220, 2045, 6),
    ]
    report['recounted_preserved_campaigns'] = {}
    for label, filename, expected_rows, expected_losses, expected_increases in campaigns:
        total = increases = wrong_refs = 0
        losses, inputs, states = set(), set(), set()
        deltas = Counter()
        for row in records(label, filename):
            total += 1
            assert row['correct']['candidate'] and equal64(row['outputs']['candidate'], row['expected']), (label, filename, row)
            key = (row.get('x', row.get('a')), row.get('y', row.get('b')))
            inputs.add(key)
            state = (*key, row['SIO'])
            assert state not in states, (label, filename, state)
            states.add(state)
            costs = row['instructions']
            parent = next(name for name in ('parent', 'inherited_R38', 'inherited_R18') if name in costs)
            delta = costs['candidate'] - costs[parent]
            increases += delta > 0
            deltas[delta] += 1
            if 'parent_instruction_delta' in row:
                assert delta == row['parent_instruction_delta']
            if 'proved_route_equation_delta' in row:
                assert delta == row['proved_route_equation_delta']
                coefficients = dict(GN=-1, GR=3, PN=-10, PR=12, SN=2, SR=5)
                assert delta == sum(coefficients[k]*v for k,v in row['actual_R48_route_profile'].items())
            references = [name for name in costs if name.startswith('qfp_') or name == 'Qfplib']
            assert references, (label, filename)
            for name in references:
                assert row['correct'][name] == equal64(row['outputs'][name], row['expected']), (label, filename, name, row)
            wrong_refs += sum(not row['correct'][name] for name in references)
            if any(row['correct'][name] and costs['candidate'] > costs[name] for name in references):
                losses.add(key)
        assert total == expected_rows and len(losses) == expected_losses and increases == expected_increases, (label, filename, total, len(losses), increases)
        report['recounted_preserved_campaigns'][label + '/' + filename] = dict(inputs=len(inputs), state_rows=total, losing_unique_inputs=len(losses), all_parent_increase_rows=increases, wrong_reference_rows_retained=wrong_refs, instruction_delta_histogram=dict(sorted(deltas.items())))
    kinds = Counter()
    for row in records('exp-q73-host-study', 'records.jsonl.gz'):
        kinds[row['kind']] += 1
        if row['kind'] == 'accepted':
            assert f"{row['model']['output']:016X}" == row['expected']
            assert row['model']['lower_round'] == row['model']['upper_round'] == row['expected']
    assert kinds == dict(accepted=482, ambiguous=30), kinds
    report['exp_Q73_preserved_host_classification'] = dict(kinds)
    report['exp_Q73_ARM_implemented_or_speed_measured'] = False
if args.report:
    destination = args.report.resolve()
    assert W != destination and W not in destination.parents, 'Write verification receipts outside the immutable archive.'
    destination.write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps({k:v for k,v in report.items() if k != 'recounted_preserved_campaigns'}, indent=2))

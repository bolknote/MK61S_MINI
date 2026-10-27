"""Read-only portable archive verification; no producer imports or device access."""
from pathlib import Path, PurePosixPath
from collections import Counter
import argparse, contextlib, gzip, hashlib, io, json, re, sys
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
@contextlib.contextmanager
def stream(row):
    if row['encoding'] == 'identity':
        with path(row['path']).open('rb') as f:
            yield f
    else:
        assert row['encoding'] == 'gzip'
        with gzip.open(path(row['path']), 'rb') as f:
            yield f
verified = {}
for row in entries:
    key = row['uncompressed_sha256']
    identity = (row['uncompressed_bytes'], row['path'], row['encoding'], row['sha256'], row['stored_bytes'])
    if key not in verified:
        assert digest(path(row['path'])) == row['sha256'] and path(row['path']).stat().st_size == row['stored_bytes']
        with stream(row) as f:
            assert digest_stream(f) == (key, row['uncompressed_bytes']), row['source']
        verified[key] = identity
    assert verified[key] == identity
def source_json(source):
    with stream(by_source[source]) as f:
        return json.load(f)
def source_bytes(source):
    with stream(by_source[source]) as f:
        return f.read()
omitted = {r['source']: r for r in provenance['omitted_binary_files']}
assert len(omitted) == len(provenance['omitted_binary_files']) and not set(omitted) & set(by_source)
manifests = json.loads((W / 'manifests.json').read_text())
pins = 0
for source, info in manifests.items():
    assert by_source[source]['uncompressed_sha256'] == info['sha256']
    manifest = source_json(source)
    assert manifest['all_producers_terminal'] and len(manifest['files']) == info['pins']
    parent = str(PurePosixPath(source).parent)
    for name, pin in manifest['files'].items():
        target = parent + '/' + name
        if target in by_source:
            row = by_source[target]
            assert (row['uncompressed_bytes'], row['uncompressed_sha256']) == (pin['bytes'], pin['sha256']), target
        else:
            row = omitted[target]
            assert (row['bytes'], row['sha256']) == (pin['bytes'], pin['sha256']), target
        pins += 1
H = '.build/m0-math-r55-hil-20261027/'
B = H + 'bootable-r1/'
proof, ram, worker = [source_json(B + name) for name in ['image-proof.json', 'ram-validation.json', 'worker-check.json']]
assert proof['first4096_RAM_bytes_untouched'] and proof['all_blob_bytes_exact'] and proof['core1_bank_untouched']
assert ram['all_candidates_correct_on_pinned_gold'] and not ram['physical_cycles_measured']
assert worker['hardware_IO'] == 0 and worker['HOST_driver_rejected_corruptions'] == ['candidate', 'pending', 'crc']
assert omitted[B + 'build/m0_r55_pow_hil.elf']['sha256'] == proof['ELF_sha256'] == worker['ELF_sha256']
current_source = H + 'stage0-r2-current249-actual-001/current-state.json'
current = source_json(current_source)
result = source_json(H + 'stage0-r2-current249-actual-001/RESULT.json')
exit_record = source_json(H + 'stage0-r2-current249-supervisor-001/ACTUAL-EXIT.json')
assert result['state_sha256'] == by_source[current_source]['uncompressed_sha256']
assert result['status'] == 'PASS_READONLY_CURRENT249_CAPTURE_NOT_RAM_GO'
assert exit_record['exit_code'] == 0 and exit_record['reaped'] and result['serial_closed']
assert result['TX_bytes'] == 49 and result['RX_bytes'] == 36861
assert by_source[H + 'stage0-r2-current249-actual-001/raw-from-open.bin']['uncompressed_bytes'] == result['RX_bytes']
for field in ['device_transition_attempts', 'Flash_writes', 'RTC_setters', 'APP_opens', 'physical_key_actions_sent']:
    assert result[field] == 0
assert current['settings']['RTC_SET'] == 0 and current['physical_keys_baseline'] == 25
assert current['current_zero_data_losslessly_rebootable'] and not current['RAM_launch_or_clock_return_GO']
first = source_json(H + 'stage0-current249-actual-001/RESULT.json')
assert first['status'] == 'HOLD_READONLY_CAPTURE_NO_RESET_OR_RECOVERY' and first['serial_closed']
assert first['device_transition_attempts'] == first['Flash_writes'] == first['RTC_setters'] == 0
closed = source_json('.build/picocalc-device-handoff.json')
assert closed['status'] == 'CLOSED_MATH_STAGE' and not closed['hardware_execution_allowed']
assert not index['operator_envelope_complete'] and not index['physical_cycles_measured'] and not index['goal_complete']
assert H + 'operator-r1/ENVELOPE-FROZEN.json' not in by_source
report = dict(status='PASS_R55_HIL_INTERMEDIATE_CHECKPOINT', stored_files=len(names),
              original_payloads_verified=len(entries), unique_payloads_verified=len(verified),
              frozen_manifest_pins_verified=pins, omitted_compiled_binaries=len(omitted),
              raw_physical_read_logs_preserved=True, readonly_capture_attempts=2,
              successful_readonly_captures=1, physical_cycles_measured=False,
              operator_envelope_complete=False, new_device_IO=0, new_ARM_MPFR_calls=0, goal_complete=False)
def equal(got, expected):
    got, expected = int(got, 16), int(expected, 16)
    if expected & 0x7fffffffffffffff > 0x7ff0000000000000:
        return got & 0x7fffffffffffffff > 0x7ff0000000000000 and bool(got & (1 << 51))
    return got == expected
if args.records:
    rows = wrong = 0
    classes, losing, seen = Counter(), set(), set()
    with stream(by_source[B + 'ram-records.jsonl.gz']) as raw, gzip.GzipFile(fileobj=raw) as f:
        for line in f:
            r = json.loads(line)
            k = (r['x'], r['y'], r['SIO'])
            assert k not in seen; seen.add(k); rows += 1
            assert equal(r['outputs']['candidate'], r['expected'])
            assert set(r['outputs']) == {'candidate', 'qfp_composed_pow', 'qfp_composed_pow_exact', 'qfp_composed_pow_integer'}
            for name, bits in r['outputs'].items():
                correct = equal(bits, r['expected'])
                assert correct == r['correct'][name]
                if name == 'candidate':
                    continue
                if not correct:
                    wrong += 1; continue
                c, q = r['instructions']['candidate'], r['instructions'][name]
                classes['slower' if c > q else 'equal' if c == q else 'strict'] += 1
                if c > q:
                    losing.add((r['x'], r['y']))
    assert rows == ram['state_rows'] == 68502 and 4 * rows == ram['actual_public_ARM_calls'] == 274008
    assert wrong == ram['wrong_Qfplib_comparisons_and_costs_retained'] == 79762
    assert classes == ram['correct_reference_state_comparison_classes']
    assert len(losing) == ram['RAM_known_losing_pairs'] == 1435
    assert [list(k) for k in sorted(losing)] == ram['RAM_losing_pairs']
    report.update(recounted_states=rows, recounted_public_ARM_calls=4 * rows,
                  all_wrong_reference_outputs_and_costs_retained=wrong, remaining_RAM_pow_pairs=len(losing))
if args.report:
    args.report.write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps(report, indent=2))

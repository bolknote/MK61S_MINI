#!/usr/bin/env python3
"""Verify the fifth offline M0+ math checkpoint and optional code rebuilds."""
from pathlib import Path
from collections import Counter
import argparse
import gzip
import hashlib
import importlib.util
import json
import shutil
import struct
import subprocess
import sys

sys.dont_write_bytecode = True
W = Path(__file__).resolve().parent
ROOT = W.parents[1]
PREVIOUS = W.parent / 'm0-math-checkpoint-20261024-4'
SOURCE_SUFFIXES = {'.cpp', '.hpp', '.inc', '.S', '.ld'}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def raw(name, directory=W):
    p = directory / name
    return p.read_bytes() if p.exists() else gzip.decompress(p.with_suffix(p.suffix + '.gz').read_bytes())


def report(name, directory=W):
    return json.loads(raw(name, directory))


def image_fingerprint(data):
    """Describe actual allocated ARM32 bytes, symbols and semantic REL records.

    File/debug paths and nonallocated sections do not affect execution. Undefined
    symbol names and relocation targets are retained, including section symbols.
    """
    assert data[:7] == b'\x7fELF\x01\x01\x01'
    assert struct.unpack_from('<H', data, 18)[0] == 40
    off = struct.unpack_from('<I', data, 32)[0]
    size, count, names_index = struct.unpack_from('<HHH', data, 46)
    sections = [struct.unpack_from('<10I', data, off + i * size) for i in range(count)]

    def contents(s):
        return data[s[4]:s[4] + s[5]]

    def string(blob, index):
        return blob[index:blob.index(b'\0', index)].decode()

    section_strings = contents(sections[names_index])
    names = [string(section_strings, s[0]) for s in sections]
    allocated = {i for i, s in enumerate(sections) if s[2] & 2}
    descriptions = []
    for i in sorted(allocated, key=lambda i: names[i]):
        s = sections[i]
        descriptions.append([names[i], s[1], s[2], s[3], s[5], s[8],
                             None if s[1] == 8 else sha(contents(s))])
    tables, symbols = {}, []
    for i, s in enumerate(sections):
        if s[1] != 2:
            continue
        strings = contents(sections[s[6]])
        table = []
        for p in range(s[4], s[4] + s[5], s[9]):
            name, value, length, info, other, sec = struct.unpack_from('<IIIBBH', data, p)
            label = string(strings, name)
            if not label and sec < len(names) and (info & 15) == 3:
                label = names[sec]
            table.append(label)
            if (sec in allocated or sec == 0 or sec == 0xfff1) and (info & 15) != 4:
                symbols.append([label, value, length, info, other,
                                names[sec] if sec < len(names) else sec])
        tables[i] = table
    relocations = []
    for s in sections:
        if s[1] != 9 or s[7] not in allocated:
            continue
        table = tables[s[6]]
        for p in range(s[4], s[4] + s[5], s[9]):
            offset, info = struct.unpack_from('<II', data, p)
            relocations.append([names[s[7]], offset, info & 255, table[info >> 8]])
    return dict(allocated=descriptions, symbols=sorted(symbols, key=repr),
                relocations=sorted(relocations, key=repr))


def qualified_rows(name, q):
    path = W / 'components' / name / 'qualification-records.jsonl.gz'
    if path.exists():
        with gzip.open(path, 'rt') as stream:
            for line in stream:
                yield json.loads(line)
    else:
        yield from q['rows']


def recount(name, q):
    inputs, states, losses, regressions, comparison = set(), set(), set(), Counter(), Counter()
    wrong_ref = count = compared_parent = 0
    for row in qualified_rows(name, q):
        inp = (row['x'], row['y']) if 'y' in row else row['x']
        key = (inp, row['SIO'])
        assert key not in states, (name, key)
        states.add(key)
        inputs.add(inp)
        if 'outputs' in row:
            assert row['correct']['candidate'], (name, key)
            reference_ok = row['correct']['Qfplib']
            a, b = row['instructions']['candidate'], row['instructions']['Qfplib']
            # The first exp packet names its reconstructed baseline "control".
            parent = row['instructions'].get('parent', row['instructions'].get('control'))
            assert parent is not None
        else:
            if row['candidate'] != row['expected']:
                # MPFR canonicalizes NaNs; the saved unary-exp policy instead
                # quiets the input while preserving its sign and payload.
                bits = int(row['x'], 16)
                assert (bits & 0x7ff0000000000000) == 0x7ff0000000000000
                assert bits & 0x000fffffffffffff
                assert int(row['candidate'], 16) == bits | 0x0008000000000000, (name, key)
            reference_ok = row['Qfplib_correct']
            a, b, parent = (row['candidate_instructions'], row['Qfplib_instructions'],
                            row['parent_instructions'])
        assert isinstance(a, int) and a > 0 and isinstance(b, int) and b > 0
        if reference_ok:
            direction = 'faster' if a < b else 'equal' if a == b else 'slower'
            comparison[direction] += 1
            if direction == 'slower':
                losses.add(inp)
        else:
            wrong_ref += 1
        # Later exp packets inherit old parent rows and freshly audit new
        # losing rows. Nonlosing new controls need not have a parent timing.
        if parent is not None:
            compared_parent += 1
            if a > parent:
                regressions[a - parent] += 1
        count += 1
    assert len(inputs) == q['unique_inputs'], name
    assert count == 2 * len(inputs), name
    return dict(unique_inputs=len(inputs), state_rows=count, candidate_wrong=0,
                raw_loss_inputs=len(losses), correct_Qfplib_state_comparison=dict(comparison),
                wrong_Qfplib_state_rows_retained=wrong_ref,
                parent_cost_comparison_states=compared_parent,
                parent_cost_increase_states=sum(regressions.values()),
                parent_cost_increase_histogram=dict(sorted(regressions.items())))


def verify(check_local=False):
    index = report('checkpoint.json')
    assert sha((PREVIOUS / 'checkpoint.json').read_bytes()) == index['base_checkpoint_sha256']
    spec = importlib.util.spec_from_file_location('checkpoint_r4', PREVIOUS / 'verify.py')
    previous = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(previous)
    previous.verify(False)
    for name, digest in index['files'].items():
        assert sha((W / name).read_bytes()) == digest, name
    provenance = report('provenance.json')
    by_source = {}
    for entry in provenance['archived_files']:
        data = (W / entry['path']).read_bytes()
        assert sha(data) == entry['sha256'], entry['path']
        if entry['encoding'] == 'gzip':
            data = gzip.decompress(data)
        assert len(data) == entry['uncompressed_bytes']
        assert sha(data) == entry['uncompressed_sha256'], entry['path']
        assert entry['source'] not in by_source
        by_source[entry['source']] = entry
        if check_local:
            assert (ROOT / entry['source']).read_bytes() == data, entry['source']
    for name, pin in index['review_pins'].items():
        path = 'reviews/' + name + '/FINAL-REVIEW.json'
        assert sha(raw(path)) == pin['sha256']
        r = report(path)
        assert r['status'] == pin['status']
        for key in pin['empty_finding_keys']:
            assert r[key] == []
    summaries, frozen_files_checked = {}, 0
    for name, binding in index['components'].items():
        prefix = 'components/' + name + '/'
        assert sha(raw(prefix + 'result.json')) == binding['result_sha256']
        r, q = report(prefix + 'result.json'), report(prefix + 'qualification.json')
        assert r['status'] == binding['result_status']
        assert q['candidate_ELF_sha256'] == r['candidate_ELF_sha256']
        assert q.get('wrong', q.get('candidate_wrong', 0)) == 0
        result_source = r.get('source_sha256', r.get('full_CPP_source_sha256'))
        component_sources = [entry['uncompressed_sha256'] for entry in provenance['archived_files']
                             if entry['path'].startswith(prefix) and
                             Path(entry['source']).suffix in SOURCE_SUFFIXES]
        if result_source:
            assert result_source in component_sources, name
        summaries[name] = recount(name, q)
        frozen = W / prefix / 'FROZEN.json'
        if frozen.exists():
            for rel, pin in json.loads(frozen.read_bytes())['files'].items():
                origin = binding['original_directory'] + '/' + rel
                if origin in by_source:
                    assert by_source[origin]['uncompressed_sha256'] == pin['sha256'], origin
                    assert by_source[origin]['uncompressed_bytes'] == pin['bytes'], origin
                if check_local:
                    data = (ROOT / origin).read_bytes()
                    assert len(data) == pin['bytes'] and sha(data) == pin['sha256'], origin
                    frozen_files_checked += 1
    assert len(index['components']) == 19 and len(index['review_pins']) == 19
    root_receipt = report('root-receipts/near-one-exp-RECEIPT.json')
    assert root_receipt['independent_review_sha256'] == index['review_pins']['exp-near-one']['sha256']
    assert root_receipt['clarification_sha256'] == sha(raw('reviews/exp-near-one/INTERVAL-CLARIFICATION.json'))
    assert len(root_receipt['pins']) == root_receipt['validated_unique_pins'] == 51
    original_root = Path(report('rebuild-recipes.json')['original_root'])
    for pin in root_receipt['pins']:
        origin = str(Path(pin['path']).relative_to(original_root))
        if origin in by_source:
            entry = by_source[origin]
            assert entry['uncompressed_sha256'] == pin['sha256']
            assert entry['uncompressed_bytes'] == pin['bytes']
        if check_local:
            data = (ROOT / origin).read_bytes()
            assert len(data) == pin['bytes'] and sha(data) == pin['sha256'], origin
    for name, n, losses in [('ln-main-quarter-fifth', 88589, 5),
                             ('d2f-leaf', 231984, 0), ('f2d-leaf', 132959, 0),
                             ('exp-directed-product', 467366, 1896),
                             ('exp-near-one', 490031, 214)]:
        assert summaries[name]['unique_inputs'] == n
        assert summaries[name]['raw_loss_inputs'] == losses
    exp = summaries['exp-near-one']
    assert exp['correct_Qfplib_state_comparison'] == dict(faster=571806, equal=8, slower=428)
    assert exp['wrong_Qfplib_state_rows_retained'] == 407820
    assert exp['parent_cost_increase_states'] == 5712
    r = report('components/exp-near-one/result.json')
    assert r['same_old467366_exp_losses'] == [1896, 196]
    assert r['old_inputs_fixed'] == 1700 and r['new_raw_speed_losses'] == 0
    assert r['total_qualified_fresh_ARM_calls'] == 1203570
    assert r['actual_directed_MPFR_validation_inputs'] == 490029
    assert r['independent_review_pending'] is True and not r['goal_complete']
    scope = report('work-in-progress/pow-exp-table-product/WORK-SCOPE.json')
    assert scope['status'] == 'SOURCE_STUDY_NOT_BUILT_OR_QUALIFIED'
    assert not (W / 'work-in-progress/pow-exp-table-product/qualification.json').exists()
    return dict(status='PASS_INTERMEDIATE_RESEARCH_CHECKPOINT',
                archive_files=len(index['files']), original_artifacts=len(by_source),
                preceding_archives_verified=4, independent_receipts=19,
                near_one_root_direct_pins=51,
                local_originals_checked=check_local, local_frozen_files_checked=frozen_files_checked,
                qualification_recount=summaries, fresh_ARM_or_MPFR_campaign=False,
                canonical_runtime_integrated=False, hardware_accessed=False, goal_complete=False)


def materialize(output):
    target = output / 'materialized'
    archives = ['m0-math-checkpoint-20261024', 'm0-math-checkpoint-20261024-2',
                'm0-math-checkpoint-20261024-3', 'm0-math-checkpoint-20261024-4', W.name]
    for name in archives:
        directory = W.parent / name
        for entry in report('provenance.json', directory)['archived_files']:
            path = Path(entry['source'])
            assert not path.is_absolute() and '..' not in path.parts and '.git' not in path.parts
            if path.suffix not in SOURCE_SUFFIXES:
                continue
            data = (directory / entry['path']).read_bytes()
            if entry['encoding'] == 'gzip':
                data = gzip.decompress(data)
            out = target / path
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_bytes(data)
    return target


def build(output, tc):
    output = output.resolve()
    assert ROOT / '.build' in output.parents, 'Use a fresh directory below .build'
    output.mkdir(parents=True, exist_ok=False)
    target = materialize(output)
    saved = report('rebuild-recipes.json')
    original = saved['original_root']

    def remap(arg):
        return arg.replace(original + '/', str(target) + '/')

    counts, commands = {}, []
    # The only object from another component needed by the near-one control.
    order = ['directed-product-prerequisite', 'ln-main-quarter-fifth',
             'pow-square-ordinary', 'pow-rsqrt-asm', 'd2f-leaf', 'f2d-leaf', 'exp-near-one']
    for name in order:
        recipe = saved['recipes'][name]
        for original_cmd in recipe['commands']:
            cmd = [str(tc / Path(original_cmd[0]).name)] + [remap(s) for s in original_cmd[1:] if s != '-g']
            for i, arg in enumerate(cmd):
                if arg.startswith('-I'):
                    Path(arg[2:]).mkdir(parents=True, exist_ok=True)
                elif arg == '-isystem':
                    Path(cmd[i + 1]).mkdir(parents=True, exist_ok=True)
            cwd = Path(remap(recipe['cwd']))
            cwd.mkdir(parents=True, exist_ok=True)
            commands.append(cmd)
            subprocess.run(cmd, cwd=cwd, check=True)
        for path, expected in recipe['outputs'].items():
            assert image_fingerprint((target / path).read_bytes()) == expected, (name, path)
        counts[name] = len(recipe['outputs'])
    (output / 'build-commands.json').write_text(json.dumps(commands, indent=2) + '\n')
    return dict(allocated_bytes_symbols_semantic_relocations_exact=counts,
                debug_path_bytes_compared=False, actual_ARM_calls=0, device_accessed=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check-local', action='store_true')
    parser.add_argument('--build-output', type=Path)
    parser.add_argument('--toolchain', type=Path)
    args = parser.parse_args()
    result = verify(args.check_local)
    if args.build_output:
        tc = args.toolchain
        if tc is None:
            exe = shutil.which('arm-none-eabi-gcc')
            if not exe:
                parser.error('Specify --toolchain /path/to/arm-none-eabi/bin')
            tc = Path(exe).parent
        result['code_rebuild'] = build(args.build_output, tc)
        (args.build_output / 'verification.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()

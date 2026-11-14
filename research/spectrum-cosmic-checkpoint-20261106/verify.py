#!/usr/bin/env python3
"""Verify the checkpoint and optionally replay HOST tests; never access devices."""
import argparse
import hashlib
import json
import os
import re
import subprocess
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def sha(data):
    return hashlib.sha256(data).hexdigest()


def git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--replay-host', action='store_true')
    args = parser.parse_args()
    manifest = json.loads((HERE / 'MANIFEST.json').read_text())
    actual_files = {str(path.relative_to(HERE)) for path in HERE.rglob('*') if path.is_file()
                    and path.name != 'MANIFEST.json' and '__pycache__' not in path.parts}
    assert actual_files == set(manifest), 'Checkpoint file set differs'
    for name, expected in manifest.items():
        assert sha((HERE / name).read_bytes()) == expected, name
    checkpoint = json.loads((HERE / 'checkpoint.json').read_text())
    base = checkpoint['base_commit']
    for name, item in checkpoint['candidate_files'].items():
        if item['base_sha256']:
            assert sha(git('show', base + ':' + name)) == item['base_sha256'], name
    for measurement in checkpoint['hardware_measurements']:
        raw = (HERE / measurement['record']).read_bytes()
        rows = re.findall(rb'SPWIN n=(\d+) frames=(\d+) cycles=(\d+) wall=(\d+) phase=(\d+)/(\d+) late=(\d+)/(\d+)', raw)
        assert len(rows) == 10
        windows = [list(map(int, row)) for row in rows]
        for i, row in enumerate(windows):
            index, frames, cycles, wall, first, last, firstlate, lastlate = row
            assert index == i and frames == 300 and wall > 1 and max(first, last) < 4096
            assert cycles == 300 * 71680 + last - first
            if i:
                assert first == windows[i - 1][5] and firstlate == windows[i - 1][7]
        steady = measurement['steady']
        assert sum(row[2] for row in windows) == steady['cycles']
        assert sum(row[3] for row in windows) == steady['wall_us']
        assert windows[0][4] == steady['first_phase'] and windows[-1][5] == steady['last_phase']
        strict = measurement['pacing']['resyncs'] == 0 and steady['cycles'] * 2 >= (steady['wall_us'] + 1) * 7
        assert strict == measurement['strict_3_5_lower_bound_reached']
        receipt = json.loads((HERE / measurement['receipt']).read_text())
        assert receipt['status'] == 'PASS' and receipt['lease'] == 'released'
        assert receipt['cleanup_native_verified'] and receipt['cdc_descriptor_closed'] and not receipt['port_close_errors']
        result = receipt['variants'][0]
        for key in ('steady', 'pacing', 'sound', 'display', 'strict_3_5_lower_bound_reached'):
            assert measurement[key] == result[key], (measurement['label'], key)
        supervisor = HERE / Path(measurement['receipt']).with_name('supervisor.json')
        if supervisor.exists():
            proof = json.loads(supervisor.read_text())
            assert all(proof[key] == value for key, value in
                       dict(child_pid=receipt['pid'], reaped=True, exit_code=0, timed_out=False).items())
    print(f'{len(manifest)} archived files and three complete ten-window measurements verified', flush=True)
    if not args.replay_host:
        return
    names = git('ls-tree', '-r', '--name-only', base).decode().splitlines()
    selected = set(checkpoint['candidate_files'])
    prefixes = ('examples/portable-apps/SPECTRUM/', 'third_party/z80/', 'third_party/emu2149/', 'sdk/portable/include/')
    names = [name for name in names if name in selected or name.startswith(prefixes) or
             (name.startswith('code/') and name.endswith(('.h', '.def')))]
    environment = dict(os.environ, ASAN_OPTIONS='detect_stack_use_after_return=1')
    with tempfile.TemporaryDirectory(prefix='spectrum-checkpoint-host-') as directory:
        build = Path(directory)
        for name in names:
            path = build / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(git('show', base + ':' + name))
        subprocess.run(['git', 'apply', '--check', str(HERE / 'candidate.patch')], cwd=build, check=True)
        subprocess.run(['git', 'apply', str(HERE / 'candidate.patch')], cwd=build, check=True)
        for name, item in checkpoint['candidate_files'].items():
            assert sha((build / name).read_bytes()) == item['candidate_sha256'], name
        flags = ['clang', '-std=c11', '-O2', '-Wall', '-Wextra', '-Werror', '-DMK61_TARGET_PICOCALC=1',
                 '-fsanitize=address,undefined', '-fno-omit-frame-pointer',
                 '-I' + str(build / 'sdk/portable/include'), '-I' + str(build / 'code')]
        core = [str(build / name) for name in checkpoint['core_sources']]
        for label, source, linked in (
            ('filter', HERE / 'host/filter_identity_self_test.c', []),
            ('quality', build / 'tests/emu2149_quality_self_test.c', []),
            ('scheduler', build / 'tests/pipeline_scheduler_self_test.c', core),
            ('presentation', build / 'tests/presentation_stats_self_test.c', core),
            ('profile', build / 'tests/profile_audio_self_test.c', core),
            ('audio', HERE / 'audio-check/self_test.c', [])):
            executable = build / label
            subprocess.run(flags + [str(source), *linked, '-o', str(executable)], check=True)
            arguments = [str(executable)]
            if label == 'presentation':
                arguments.append(str(build / 'presentation-wire.txt'))
            subprocess.run(arguments, check=True, env=environment)
    print('Six archived HOST tests passed with ASan/UBSan; no device access')


if __name__ == '__main__':
    main()

#!/usr/bin/env python3
"""Classic VM A/B/A or cache A/B/C/A with exact APP and VMC restoration.

Requires exclusive ownership of the verified Classic and a pinned recovery BIN.
Three searches per stage by default; compare warm searches after cache creation.
"""
from dataclasses import asdict
import argparse
import errno
import hashlib
import json
import re
from pathlib import Path
import sys
import time
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
import hil_packbits_firmware as storage_hil
import hil_system_memory as memory_hil
from hil_c5_stack import read_file
from hil_c6_system_bootstrap import write_file
from hil_multi_device_identity import parse_identity
from hil_rtc_alarm import canonical_state_reply, warm_reset

PORT = '/dev/cu.usbmodem2068336B47311'
PUBLIC = 'AEB505B6E0067623'
original_connect = memory_hil.connect
raw_read_file = read_file
read_retries = []


def read_file(port, remote):
    for attempt in range(3):
        try:
            return raw_read_file(port, remote)
        except (AssertionError, TimeoutError) as error:
            read_retries.append(dict(remote=remote, attempt=attempt + 1, error=str(error)[:120]))
            print('Checked read retry', remote, attempt + 1, flush=True)
            if attempt == 2:
                raise
            port.drain()
            time.sleep(.2)


storage_hil.read_file = read_file


def connect(path, build=None, wait=45):
    deadline = time.monotonic() + wait
    while True:
        try:
            return original_connect(path, build, wait=0)
        except OSError as error:
            if error.errno not in (errno.ENOENT, errno.ENXIO, errno.EIO, errno.EBUSY) or time.monotonic() >= deadline:
                raise
        except TimeoutError:
            if time.monotonic() >= deadline:
                raise
        except AssertionError as error:
            # A reset banner can precede the first ASCII identity response.
            # Retry a fresh, fully checked identity; never accept a malformed
            # response or relax the required Classic UID/profile/build.
            if ('not a canonical MK61 identity response:' not in str(error) or
                    'MK61s-Classic-V3 ver.' not in str(error) or time.monotonic() >= deadline):
                raise
        time.sleep(.3)


memory_hil.connect = connect  # Includes flash/chess reset, not their ID/CRC checks.


def save(path, data):
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + '\n')


def reset():
    with connect(PORT) as port:
        fresh, path, _ = warm_reset(port, PORT, PUBLIC)
        fresh.close()
        assert path == PORT, ('Unexpected port change; use verified new identity', path)


def snapshot_files(port, output):
    # Capture bytes during the existing hash scan, not by reading each file twice.
    saved_read = storage_hil.read_file
    def capture(port, remote):
        parts = remote.lstrip('/').split('/')
        assert parts and all(part not in ('', '.', '..') for part in parts)
        data = saved_read(port, remote)
        local = output.joinpath(*parts)
        local.parent.mkdir(parents=True, exist_ok=True)
        local.write_bytes(data)
        return data
    storage_hil.read_file = capture
    try:
        return storage_hil.fingerprint(port)
    finally:
        storage_hil.read_file = saved_read


def alarms_off(port):
    response = port.command('alarm')
    assert 'RTC ALARM A off' in response and 'RTC ALARM B off' in response
    return response


def capture_image(source, destination):
    info = storage_hil.firmware_info(source)
    data = source.read_bytes()
    assert hashlib.sha256(data).hexdigest() == info['sha256']
    destination.write_bytes(data)
    captured = storage_hil.firmware_info(destination)
    assert captured['sha256'] == info['sha256']
    captured['source'] = str(source.resolve())
    return captured


def is_vm_cache(path):
    return re.fullmatch(r'/System/VMCache/VMC-[0-9a-f]{4}\.app',path,re.IGNORECASE) is not None


def restore_cache(port, snapshot, saved_directory):
    """Restore only VMC to the original snapshot; preserve all other files."""
    current=storage_hil.fingerprint(port)
    removed=sorted(set(current['files'])-set(snapshot['files']))
    assert all(is_vm_cache(path) for path in removed),removed
    for remote in removed:
        assert 'Removed 1 entry.' in port.command('rm "'+remote+'"',30)
    replaced=[]
    for remote, detail in snapshot['files'].items():
        if not is_vm_cache(remote) or current['files'].get(remote)==detail:
            continue
        payload=(saved_directory/remote.lstrip('/')).read_bytes()
        assert hashlib.sha256(payload).hexdigest()==detail['sha256']
        write_file(port,remote,payload)
        assert read_file(port,remote)==payload
        replaced.append(remote)
    return removed,replaced


def stage_plan(baseline, candidate, baseline_system, candidate_system, *, raw32=None, single=False):
    if raw32 is not None:
        assert not single, 'Cache comparison needs all four stages'
        return [('baseline', baseline, baseline_system),
                ('candidate', candidate, candidate_system),
                ('raw32', raw32, baseline_system),
                ('control', baseline, baseline_system)]
    if single:
        return [('qualification', candidate, candidate_system)]
    return [('baseline', baseline, baseline_system),
            ('candidate', candidate, candidate_system),
            ('control', baseline, baseline_system)]


def require_common_apps(stages, bundles):
    first = bundles[stages[0][2]]
    assert all(bundles[directory] == first for _, _, directory in stages), 'Cache comparison must use byte-identical System APPs'


def graphics_measure(target, output):
    """Run the existing two-page oracle outside the timed chess interval."""
    import hil_basic_graphics as graphics
    saved_port, saved_argv = graphics.ScreenPort, sys.argv
    graphics.ScreenPort = memory_hil.ExclusiveScreenPort
    sys.argv = ['hil_basic_graphics.py', '--port', PORT, '--public-id', PUBLIC,
                '--build-id', target['build'], '--output-dir', str(output)]
    try:
        graphics.main()
    finally:
        graphics.ScreenPort, sys.argv = saved_port, saved_argv
    result = json.loads((output / 'result.json').read_text())
    assert result['status'] == 'PASS', result
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--original', type=Path, required=True)
    parser.add_argument('--original-build', required=True)
    parser.add_argument('--original-sha256', required=True)
    parser.add_argument('--baseline', type=Path, required=True)
    parser.add_argument('--candidate', type=Path, required=True)
    parser.add_argument('--raw32', type=Path, help='Compare baseline raw24, candidate mixed24, raw32, baseline control; same APPs required')
    parser.add_argument('--baseline-system', type=Path, required=True)
    parser.add_argument('--candidate-system', type=Path, required=True)
    parser.add_argument('--runs', type=int, default=3, choices=range(2,8))
    parser.add_argument('--with-graphics', action='store_true',
                        help='verify both Graphics.tbi pages after every timed chess stage')
    parser.add_argument('--single-candidate',action='store_true',help='Ordinary combined-main qualification only; no matched speedup claim')
    parser.add_argument('--output-dir', type=Path, required=True)
    options = parser.parse_args()
    if options.raw32 and options.single_candidate:
        parser.error('--raw32 cannot be combined with --single-candidate')
    output = options.output_dir.resolve()
    assert not output.exists(), 'Keep prior attempts and recovery evidence intact'
    output.mkdir(parents=True)
    (output / 'images').mkdir()
    original = capture_image(options.original, output / 'images/original.bin')
    assert original['build'] == options.original_build.upper()
    assert original['sha256'] == options.original_sha256.lower()
    baseline = capture_image(options.baseline, output / 'images/baseline.bin')
    candidate = capture_image(options.candidate, output / 'images/candidate.bin')
    raw32 = capture_image(options.raw32, output / 'images/raw32.bin') if options.raw32 else None
    stages = stage_plan(baseline, candidate, options.baseline_system, options.candidate_system,
                        raw32=raw32, single=options.single_candidate)
    bundles = {}
    for _, _, directory in stages:
        if directory not in bundles:
            bundles[directory] = {app:(directory/app).read_bytes() for app in (
                'LANGVM.APP','LANGIN.APP','BASIC.APP','FOCAL.APP','VMCache/VMSTORE.APP')}
            # Refuse damaged/mismatched transport payloads before flashing.
            from check_app_memory_elf import app_memory_size
            for app in bundles[directory]:app_memory_size(directory/app)
    if options.raw32:
        require_common_apps(stages, bundles)
    args = SimpleNamespace(port=PORT, runs=options.runs, dfu_util=Path(
        '/Users/bolk/Library/Arduino15/packages/arduino/tools/dfu-util/0.11.0-arduino5/dfu-util'))
    print('Fresh pinned Classic snapshot:', original['build'], flush=True)
    with connect(PORT, original['build'], wait=0) as port:
        before = memory_hil.health(port, original['build'])
        memory_hil.require_empty(before)
        alarms = alarms_off(port)
        files = snapshot_files(port, output / 'original-files')
        save(output / 'snapshot.json', dict(identity=asdict(parse_identity(port.command('identity'))),
             health=before, files=files, alarms=alarms, firmware=original))
    print('Snapshot complete:', len(files['files']), 'files,', len(files['directories']), 'directories', flush=True)
    scenario = 'Ordinary combined-main qualification; not matched A/B/A' if options.single_candidate else 'A/B/A, per-stage System APP and original VMC snapshot'
    if options.raw32:
        scenario = 'raw24 / mixed24 / raw32 / raw24 control; common APPs and original VMC snapshot'
    result = dict(status='RUNNING', scenario=scenario, original=original, stages=[], restored=False,
        runs_per_stage=options.runs, vm_cache_normalized_before_each_stage=True)
    if options.raw32:
        result['cache_configurations'] = dict(baseline=dict(bytes=24576,mixed=False),
            candidate=dict(bytes=24576,mixed=True),raw32=dict(bytes=32768,mixed=False),
            control=dict(bytes=24576,mixed=False))
        result['same_system_apps_required'] = True
    save(output / 'report.json', result)
    changed = set()
    touched = False
    passed = False
    try:
        for name, target, directory in stages:
            print('Stage', name, target['build'], flush=True)
            touched = True
            memory_hil.flash(args, target, output / (name + '-flash.json'))
            with connect(PORT, target['build']) as port:
                # A previous wire version cannot claim ownership of a future cache.
                # Start every stage with the exact original cache contents:
                # remove only added VMC, and restore original bytes in place.
                removed,replaced=restore_cache(port,files,output/'original-files')
                app_images=bundles[directory]
                for app, data in app_images.items():
                    remote = next(p for p in files['files'] if p.casefold() == ('/System/' + app).casefold())
                    if read_file(port, remote) != data:
                        changed.add(remote)
                        write_file(port, remote, data)
                        assert read_file(port, remote) == data
            chess = memory_hil.chess_measure(args, target, output / ('chess-' + name))
            graphics = graphics_measure(target, output / ('graphics-' + name)) if options.with_graphics else None
            result['stages'].append(dict(name=name, firmware=target, chess=chess, graphics=graphics,
                original_cache_restored=replaced,test_cache_removed=removed,
                system_apps={app:dict(bytes=len(data),sha256=hashlib.sha256(data).hexdigest())
                             for app,data in app_images.items()}))
            save(output / 'report.json', result)
        boards = {run['board_frame_sha256'] for stage in result['stages'] for run in stage['chess']['runs']}
        assert len(boards) == 1
        if options.with_graphics:
            pages = {tuple(page['sha256'] for page in stage['graphics']['pages']) for stage in result['stages']}
            assert len(pages) == 1, 'Graphics pages changed between cache variants'
        passed = True
    except BaseException as error:
        result.update(status='FAIL', error=repr(error))
        raise
    finally:
        try:
            if touched:
                print('Restoring exact original image/files/state', flush=True)
                # Release VM/APP handles, then restore the pinned image BEFORE
                # the large readback. On transport loss flash() itself still
                # requires the exact Classic ROM UID; never broad erase.
                try:
                    reset()
                except (OSError, TimeoutError) as error:
                    result['reset_transport_error'] = repr(error)
                memory_hil.flash(args, original, output / 'restore-flash.json')
                with connect(PORT, original['build']) as port:
                    after = storage_hil.fingerprint(port)
                    added = set(after['files']) - set(files['files'])
                    for remote in added:
                        assert is_vm_cache(remote), remote
                        assert 'Removed 1 entry.' in port.command('rm "' + remote + '"', 30)
                    for remote, detail in files['files'].items():
                        if after['files'].get(remote) == detail:
                            continue
                        assert remote in changed or is_vm_cache(remote), remote
                        data = (output / 'original-files' / remote.lstrip('/')).read_bytes()
                        assert hashlib.sha256(data).hexdigest() == detail['sha256']
                        write_file(port, remote, data)
                    assert storage_hil.fingerprint(port) == files
                with connect(PORT, original['build']) as port:
                    final = memory_hil.health(port, original['build'])
                    memory_hil.require_empty(final)
                    for key in ('reg', 'stk', 'dump', 'pwd'):
                        assert canonical_state_reply(final[key]) == canonical_state_reply(before[key]), key
                    assert storage_hil.fingerprint(port) == files
                    alarms_off(port)
                result.update(restored=True, files_preserved=True, calculator_preserved=True,
                    serial_closed=True, mini_touched=False, health_after=final,
                    terminal_state_prompt_space_normalized=True,
                    original_files=len(files['files']), original_directories=len(files['directories']),
                    added_cache_files_removed=len(added), read_retries=read_retries)
                print('Exact restoration PASS; CDC closed:', original['build'], flush=True)
            result['status'] = 'PASS' if passed and result['restored'] else 'FAIL'
        except BaseException as error:
            result.update(status='FAIL', cleanup_error=repr(error))
            raise
        finally:
            save(output / 'report.json', result)
    print(scenario, result['status'], [(s['name'], s['chess']['warm_median_seconds']) for s in result['stages']], flush=True)


if __name__ == '__main__':
    main()

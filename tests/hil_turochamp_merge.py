#!/usr/bin/env python3
"""Same-firmware Classic A/B/A for frozen Turochamp source packages.

Only /TCMERGE and VM-generated VMC files may change; explicit APP options also
permit temporary BASIC.APP/VMSTORE.APP replacements. No flashing, formatting or budget
changes. Byte-exact filesystem/calculator
restoration is required even after a failed stage.
"""
import argparse
import hashlib
import json
from pathlib import Path
import statistics
import sys
from types import SimpleNamespace

from hil_c6_system_bootstrap import write_file
from hil_multi_device_identity import parse_identity
import hil_packbits_firmware as storage_hil
import hil_system_memory as memory_hil
from hil_rtc_alarm import canonical_state_reply, warm_reset
from hil_turochamp_performance import Font, TimedScreenPort, search, stop_game
from hil_vm_compiled_blocks import (PORT, PUBLIC, alarms_off, connect, is_vm_cache,
                                    read_file, snapshot_files)

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'tools'))
from m8_codec import encode

REMOTE = '/TCMERGE'
BASIC = '/System/BASIC.app'
VMSTORE = '/System/VMCache/VMSTORE.app'


def save(path, data):
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False)+'\n')


def package(directory):
    files = {p.name: p.read_bytes() if p.suffix.lower() == '.fmk' else encode(p.read_text())
             for p in directory.iterdir() if p.is_file()}
    assert 'autoexec.m61' in files and 'legal.tbi' in files and 'Turochamp.FMK' in files
    assert all('/' not in name and '"' not in name for name in files)
    return files


def restore_vm_cache(port, original, backup, replace_basic=False, replace_vmstore=False,
                     app_targets=None, app_writes=None):
    # Unlike the firmware-variant helper, this fixture also owns /TCMERGE.
    current = storage_hil.fingerprint(port)
    added = sorted(set(current['files'])-set(original['files']))
    assert all(is_vm_cache(remote) or remote.startswith(REMOTE+'/') for remote in added), added
    allowed = ({BASIC} if replace_basic else set()) | ({VMSTORE} if replace_vmstore else set())
    app_targets = app_targets or {}
    assert set(app_targets) <= allowed & set(original['files']), 'Unapproved APP target'
    replacements = {}
    for remote, detail in original['files'].items():
        target = app_targets.get(remote)
        if target is not None:
            detail = dict(bytes=len(target), sha256=hashlib.sha256(target).hexdigest())
        if current['files'].get(remote) == detail:
            continue
        assert is_vm_cache(remote) or remote in allowed, ('Unexpected original file change', remote)
        data = target if target is not None else (backup/remote.lstrip('/')).read_bytes()
        assert hashlib.sha256(data).hexdigest() == detail['sha256']
        replacements[remote] = data
    removed = []
    for remote in added:
        if is_vm_cache(remote):
            assert 'Removed 1 entry.' in port.command(f'rm "{remote}"', 30)
            removed.append(remote)
    for remote, data in replacements.items():
        write_file(port, remote, data)
        assert read_file(port, remote) == data
        if remote in allowed and app_writes is not None: app_writes.append(remote)
    return removed


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--baseline-game', type=Path, required=True)
    ap.add_argument('--candidate-game', type=Path, required=True)
    ap.add_argument('--build-id', required=True)
    ap.add_argument('--runs', type=int, default=4, choices=range(4, 8))
    ap.add_argument('--timeout', type=float, default=360)
    ap.add_argument('--no-profile', action='store_true')
    ap.add_argument('--candidate-basic', type=Path,
                    help='A/B/A compiler-only comparison; game packages must be identical')
    ap.add_argument('--baseline-basic', type=Path,
                    help='Explicit A/A compiler for --candidate-basic; restore the original afterwards')
    ap.add_argument('--common-basic', type=Path,
                    help='Use the same BASIC compiler in every stage, restoring the original afterwards')
    ap.add_argument('--baseline-vmstore', type=Path)
    ap.add_argument('--candidate-vmstore', type=Path)
    ap.add_argument('--common-vmstore', type=Path,
                    help='Use the same VMSTORE in every stage, restoring the original afterwards')
    ap.add_argument('--output-dir', type=Path, required=True)
    args = ap.parse_args()
    output = args.output_dir.resolve()
    assert not output.exists(), 'Keep previous attempts and restoration evidence'
    baseline, candidate = package(args.baseline_game), package(args.candidate_game)
    assert baseline['Turochamp.FMK'] == candidate['Turochamp.FMK']
    assert not (args.candidate_basic and args.common_basic)
    assert not args.baseline_basic or args.candidate_basic
    assert bool(args.baseline_vmstore) == bool(args.candidate_vmstore)
    assert not (args.common_vmstore and args.candidate_vmstore)
    assert not (args.candidate_basic and args.candidate_vmstore), 'Vary only one APP'
    def checked_app(path, kind):
        from check_app_memory_elf import app_memory_size
        app_memory_size(path)  # Header/payload CRCs and the unchanged 20-KiB cap.
        data = path.read_bytes()
        assert data[14] == kind, 'Incorrect APP kind'
        return data
    basic = checked_app(args.candidate_basic, 2) if args.candidate_basic else None
    base_basic = checked_app(args.baseline_basic, 2) if args.baseline_basic else None
    common = checked_app(args.common_basic, 2) if args.common_basic else None
    common_store = checked_app(args.common_vmstore, 4) if args.common_vmstore else None
    stores = ((checked_app(args.baseline_vmstore, 4), checked_app(args.candidate_vmstore, 4))
              if args.candidate_vmstore else None)
    if common_store is not None: stores = (common_store, common_store)
    if basic is not None or common is not None or stores:
        assert baseline == candidate, 'Do not confound compiler and game changes'
    output.mkdir(parents=True)
    backup = output/'original-files'
    build = args.build_id.upper()
    with connect(PORT, build, wait=0) as port:
        identity = parse_identity(port.command('identity'))
        before = memory_hil.health(port, build)
        memory_hil.require_empty(before)
        alarms_off(port)
        original = snapshot_files(port, backup)
        if basic is not None or common is not None: assert BASIC in original['files']
        if stores: assert VMSTORE in original['files']
        assert REMOTE not in original['directories']
        assert not any(path.startswith(REMOTE+'/') for path in original['files'])
    save(output/'snapshot.json', dict(identity=identity.__dict__, health=before, files=original))
    result = dict(status='RUNNING', build=build, public=PUBLIC, stages=[], restored=False,
                  firmware_writes=0, System_APP_writes=0, limits_weakened=False,
                  timing='USB complete-board wall clock', profiling=not args.no_profile,
                  package_hashes={kind: {name: dict(bytes=len(data), sha256=hashlib.sha256(data).hexdigest())
                                        for name, data in files.items()}
                                  for kind, files in (('baseline', baseline), ('candidate', candidate))})
    if basic is not None:
        result['compiler'] = dict(original=original['files'][BASIC],
            candidate=dict(bytes=len(basic), sha256=hashlib.sha256(basic).hexdigest()))
    variants = {}
    if basic is not None:
        variants[BASIC] = (base_basic if base_basic is not None else
                           (backup/BASIC.lstrip('/')).read_bytes(), basic)
    if common is not None: variants[BASIC] = (common, common)
    if stores: variants[VMSTORE] = stores
    result['app_variants'] = {remote: {stage:dict(bytes=len(data), sha256=hashlib.sha256(data).hexdigest())
        for stage, data in zip(('baseline','candidate'), pair)} for remote, pair in variants.items()}
    app_writes = []
    save(output/'report.json', result)
    touched = False
    passed = False
    try:
        # Keep the baseline's unused pseudo.tbi during B. Inodes/file IDs and
        # directory occupancy then stay identical across all three stages.
        installed = {}
        for stage, files in (('baseline', baseline), ('candidate', candidate), ('control', baseline)):
            with connect(PORT, build) as port:
                if not touched:
                    touched = True
                    port.command(f'mkdir "{REMOTE}"', 15)
                targets = {remote: pair[stage == 'candidate'] for remote, pair in variants.items()}
                removed = restore_vm_cache(port, original, backup, BASIC in variants,
                    VMSTORE in variants, targets, app_writes)
                result['System_APP_writes'] = len(app_writes)
                for name, data in files.items():
                    remote = REMOTE+'/'+name
                    if installed.get(name) != data:
                        write_file(port, remote, data)
                        assert read_file(port, remote) == data
                        installed[name] = data
                # Full byte checks stay outside measured searches.
                for name, data in files.items():
                    assert read_file(port, REMOTE+'/'+name) == data
                fresh, path, _ = warm_reset(port, PORT, PUBLIC)
                assert path == PORT
                fresh.close()
            rows = []
            stage_out = output/stage
            stage_out.mkdir()
            print('Starting', stage, 'same firmware', build, flush=True)
            with TimedScreenPort(PORT) as port:
                current = parse_identity(port.command('identity'))
                assert current == identity, (current, identity)
                config = SimpleNamespace(game_dir=REMOTE, build_id=build, timeout=args.timeout,
                                         reset_before=True, no_profile=args.no_profile)
                font = Font(files['Turochamp.FMK'])
                try:
                    port.attach()
                    port.pump(.2)
                    for index in range(args.runs):
                        run_out = stage_out/f'run-{index}'
                        run_out.mkdir()
                        rows.append(search(port, font, config, index, run_out))
                        save(stage_out/'runs.json', rows)
                finally:
                    if port.attached:
                        try:
                            stop_game(port)
                        finally:
                            port.send(0x13)
                            port.attached = False
                            port.pump(.2)
                    (stage_out/'terminal.txt').write_bytes(port.text)
                health = memory_hil.health(port, build)
                assert 'layout=ok' in health['mpu status']
                frames = len(port.frames)
            assert len({row['board_frame_sha256'] for row in rows}) == 1
            result['stages'].append(dict(name=stage, runs=rows, steady_indices=[args.runs-2, args.runs-1],
                steady_seconds=statistics.median(row['seconds'] for row in rows[-2:]),
                frames_crc_checked=frames, removed_prior_test_cache=removed, health=health))
            save(output/'report.json', result)
        assert len({row['board_frame_sha256'] for stage in result['stages'] for row in stage['runs']}) == 1
        a, b, control = (stage['steady_seconds'] for stage in result['stages'])
        reference = (a+control)/2
        result.update(reference_seconds=reference, candidate_seconds=b, speedup=reference/b,
                      elapsed_reduction_percent=100*(1-b/reference), control_drift_percent=100*(control/a-1))
        a, b, control = (stage['runs'][0]['seconds'] for stage in result['stages'])
        reference = (a+control)/2
        result['cold'] = dict(baseline_seconds=a, candidate_seconds=b, control_seconds=control,
            reference_seconds=reference, speedup=reference/b,
            elapsed_reduction_percent=100*(1-b/reference), control_drift_percent=100*(control/a-1),
            state='Reboot, original VMC snapshot; first compile and RAM fill')
        passed = True
    except BaseException as error:
        result.update(status='FAIL', error=repr(error))
        raise
    finally:
        try:
            if touched:
                with connect(PORT, build) as port:
                    port.command('fsput cancel')
                    port.command('reinit')
                    restore_vm_cache(port, original, backup, BASIC in variants,
                        VMSTORE in variants, app_writes=app_writes)
                    result['System_APP_writes'] = len(app_writes)
                    current = storage_hil.fingerprint(port)
                    for remote in sorted(set(current['files'])-set(original['files'])):
                        assert remote.startswith(REMOTE+'/'), remote
                        assert 'Removed 1 entry.' in port.command(f'rm "{remote}"', 30)
                    assert 'rmdir:' not in port.command(f'rmdir "{REMOTE}"', 30)
                    # DETACH leaves the device offering a new USB Screen
                    # session. Reset also releases its buffers and VM images.
                    fresh, path, _ = warm_reset(port, PORT, PUBLIC)
                    assert path == PORT
                    fresh.close()
                with connect(PORT, build) as port:
                    final = memory_hil.health(port, build)
                    memory_hil.require_empty(final)
                    for key in ('reg', 'stk', 'dump', 'pwd'):
                        assert canonical_state_reply(final[key]) == canonical_state_reply(before[key]), key
                    assert storage_hil.fingerprint(port) == original
                    alarms_off(port)
                    result.update(restored=True, original_files=len(original['files']),
                                  original_directories=len(original['directories']), health_after=final,
                                  mini_touched=False, exact_files_and_calculator_preserved=True,
                                  usb_session_released_by_reset=True)
                print('Original files and calculator restored; firmware unchanged', flush=True)
            result['status'] = 'PASS' if passed and result['restored'] else 'FAIL'
        except BaseException as error:
            result.update(status='FAIL', cleanup_error=repr(error))
            raise
        finally:
            save(output/'report.json', result)
    print(json.dumps({key: result[key] for key in ('status', 'reference_seconds', 'candidate_seconds',
          'speedup', 'elapsed_reduction_percent', 'control_drift_percent', 'cold', 'restored')}, indent=2), flush=True)


if __name__ == '__main__':
    main()

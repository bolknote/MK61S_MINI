#!/usr/bin/env python3
"""Freeze/verify new HOST evidence without changing the original FROZEN.json."""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
from prepare import pin

SOURCE28 = Path('/Users/bolk/Projects/MK61S_MINI/.build/runner-finish-20261030/source')
ACTUAL_SOURCE_FILES = ['code/mpu_guard.cpp', 'code/mpu_guard_policy.hpp', 'code/loadable_module_format.cpp',
    'code/zx0.cpp', 'code/loadable_app_api.h', 'code/loadable_app_services.h', 'code/loadable_system_api.cpp',
    'sdk/portable/start.c', 'sdk/portable/shared_runtime.c', 'sdk/portable/include/mk61_app.h']


def refs(value):
    if isinstance(value, dict):
        if set(value) == {'path', 'bytes', 'sha256'}:
            yield value
        else:
            for x in value.values():
                yield from refs(x)
    elif isinstance(value, list):
        for x in value:
            yield from refs(x)


def verify_ref(ref):
    path = Path(ref['path'])
    if not path.is_absolute():
        path = ROOT / path
    actual = pin(path)
    if (actual['bytes'], actual['sha256']) != (ref['bytes'], ref['sha256']):
        raise ValueError('pin drift: ' + ref['path'])
    return dict(ref, path=str(path.resolve()))


def verify(packet_path):
    packet = json.loads(packet_path.read_text())
    if packet['status'] != 'HOST_REVIEW_READY_PHYSICAL_ADAPTERS_UNBOUND' or packet['physical_IO'] != 0 or packet['hardware_GO'] is not None:
        raise ValueError('HOST package must not imply a physical grant/result')
    seen = {}
    for ref in refs(packet):
        ref = verify_ref(ref)
        seen[ref['path']] = ref
    checked = set()
    while set(seen) - checked:
        path = next(iter(set(seen) - checked))
        ref = seen[path]; verify_ref(ref); checked.add(path)
        if Path(path).suffix.lower() != '.json':
            continue
        value = json.loads(Path(path).read_text())
        for nested in refs(value):
            nested = verify_ref(nested)
            if nested['path'] in seen and seen[nested['path']] != nested:
                raise ValueError('contradictory pin for ' + nested['path'])
            seen[nested['path']] = nested
    return dict(status='PASS_HOST_RECURSIVE_PINS', files=len(checked), physical_IO=0, hardware_GO=None)


def freeze(args):
    files = [args.build, args.model, args.placement, args.workflow, args.workflow_test, args.old_frozen]
    for file in files:
        value = json.loads(file.read_text())
        for ref in refs(value):
            verify_ref(ref)
    checks = [json.loads(x.read_text()) for x in [args.model, args.placement, args.workflow_test]]
    if [x['status'] for x in checks] != ['PASS_HOST_NEW_PACKED_CARRIERS_SYNTHETIC_TIME_ONLY',
            'PASS_HOST_NEW_FLASH_PLACEMENTS', 'PASS_HOST_WORKFLOW_GUARDS_AND_PROCESS_LIFECYCLE']:
        raise ValueError('new HOST qualifications incomplete')
    # Everything outside this chat's untracked research/tests must be exactly
    # the known base. Main and protected worktrees are never modified.
    base = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    if base != '7a01beb4827c05bb2ba34fc0576f85f929b6160f':
        raise ValueError('unexpected research base')
    subprocess.run(['git', 'diff', '--exit-code', '--', 'code', 'sdk', 'tools',
        'tests/check_stm32_vectors.py', 'tests/portable_app_format_self_test.cpp'], cwd=ROOT, check=True, capture_output=True)
    equivalence = []
    for name in ACTUAL_SOURCE_FILES:
        source, actual = ROOT / name, SOURCE28 / name
        if source.read_bytes() != actual.read_bytes():
            raise ValueError('source28 compatibility delta: ' + name)
        equivalence.append(dict(own=pin(source), actual_source28=pin(actual), byte_exact=True))
    args.output_dir.mkdir(parents=True, exist_ok=False)
    sources = []
    for source in sorted(HERE.iterdir()):
        if source.suffix not in ('.py', '.c', '.md'):
            continue
        target = args.output_dir / 'source' / source.relative_to(ROOT)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        sources.append(dict(original=pin(source), snapshot=pin(target)))
    packet = dict(schema=1, status='HOST_REVIEW_READY_PHYSICAL_ADAPTERS_UNBOUND', physical_IO=0,
        hardware_GO=None, hardware_winner=None, production_changes=False, automatic_timer_enabled=False,
        research_base=base, original_frozen=pin(args.old_frozen), build=pin(args.build),
        model=pin(args.model), placements=pin(args.placement), workflow=pin(args.workflow),
        workflow_guards_processes=pin(args.workflow_test), sources=sources,
        source28_compatibility=equivalence,
        scope='M4 new carrier/operator HOST delta; original HOST campaign unchanged; no physical result',
        unbound=['actual released resident/profile/context', 'accepted physical adapters/dependencies/argv',
                 'fresh complete state/RTC and full snapshot', 'actual qualified timer/repetition freeze',
                 'predecessor CLOSED', 'finite lease and Root Go'],
        next='Coordinator HOST review; actual physical suppliers/binding and negative delta must be accepted before physical Go')
    output = args.output_dir / 'PACKET.json'
    output.write_text(json.dumps(packet, indent=2) + '\n')
    return dict(packet=pin(output), verification=verify(output))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--verify', type=Path)
    for name in ['build', 'model', 'placement', 'workflow', 'workflow-test', 'old-frozen', 'output-dir']:
        p.add_argument('--' + name, type=Path)
    args = p.parse_args()
    if args.verify:
        print(json.dumps(verify(args.verify))); return
    if any(getattr(args, x.replace('-', '_')) is None for x in ['build','model','placement','workflow','workflow-test','old-frozen','output-dir']):
        p.error('all freeze inputs are required')
    print(json.dumps(freeze(args)))


if __name__ == '__main__':
    main()

"""APP-body adapter for a separately reviewed Root-owned HIL transaction.

No serial, USB, DFU, lease mutation or cleanup implementation lives here.
The parent must own the entire backup/candidate/restore transaction and its
fresh directory. Importing this module performs no I/O.
"""
import hashlib
import importlib.util
import json
from pathlib import Path


class Hold(RuntimeError):
    pass


def run_phase(parent, experiment_path, output):
    """Run exactly four APPs and all 53 batches on an already admitted image.

    Parent interface (all operations must be lease guarded):
      guard(), check_idle(), put(name, bytes), read(name), open(name, timeout),
      expect_result(predicate, metadata), admit_result(bytes).
    check_idle validates the exact physical identity/build/CRC/clock and typed
    no-owner/no-pending state. open is correlated to completion (M0 also checks
    APP_FLOW_RESULT=0). It must not acknowledge an echo or prompt alone.
    The parent, not this body, owns namespace creation and finally restoration.
    """
    experiment_path = Path(experiment_path).resolve()
    here = Path(__file__).resolve().parent
    spec = importlib.util.spec_from_file_location('strlen_frozen_decoder', here/'decode.py')
    wire = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(wire)
    exp = json.loads(experiment_path.read_text())
    anchor = json.loads(wire.pinned(exp['anchors']))
    corpus = json.loads(wire.pinned(exp['corpus']))
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    parent.guard()
    before = parent.check_idle()
    results = []
    for app in exp['apps']:
        parent.guard()
        app_bytes = wire.pinned(app['APP'])
        parent.put('STLNBEN.APP', app_bytes)
        if parent.read('STLNBEN.APP') != app_bytes:
            raise Hold('APP byte readback mismatch')
        app_out = output/app['name']
        app_out.mkdir()
        for index, batch in enumerate(corpus['batches']):
            parent.guard()
            input_bytes = wire.pinned(batch['input'])
            parent.put('INPUT.bin', input_bytes)
            if parent.read('INPUT.bin') != input_bytes:
                raise Hold('INPUT byte readback mismatch')
            def recognize(raw, app=app, batch=batch, input_bytes=input_bytes):
                try:
                    wire.decode(raw, exp, anchor, app, batch, input_bytes)
                    return True
                except wire.Invalid:
                    return False
            parent.expect_result(recognize, dict(app=app['name'], batch=index, first=batch['first'],
                image_build=anchor['build'], image_crc=anchor['crc32'], directory=exp['directory']))
            parent.guard()
            launch = parent.open('STLNBEN.APP', timeout=180)
            parent.guard()
            raw = parent.read('RESULT.bin')
            (app_out/f'{index:03}.bin').write_bytes(raw)
            parsed = wire.decode(raw, exp, anchor, app, batch, input_bytes)
            parent.admit_result(raw)
            parsed['launch'] = launch
            (app_out/f'{index:03}.json').write_text(json.dumps(parsed, indent=2)+'\n')
            if parsed['status'] != 'PASS_WIRE_ONLY':
                raise Hold(f'Recognized APP failure {parsed["failure_code"]}; parent must return original')
            parent.check_idle()
            results.append(dict(app=app['name'], batch=index, first=batch['first'],
                raw_sha256=hashlib.sha256(raw).hexdigest(), raw_file=str(app_out/f'{index:03}.bin')))
            print('strlen', exp['cpu'], anchor['phase'], app['name'], index+1, '/', len(corpus['batches']), flush=True)
    parent.guard()
    after = parent.check_idle()
    result = dict(status='COMPLETE_APP_BODY_ORIGINAL_RETURN_PENDING', cpu=exp['cpu'], phase=anchor['phase'],
        firmware_build=f'{anchor["build"]:08X}', firmware_crc32=f'{anchor["crc32"]:08X}',
        before=before, after=after, apps=4, batches=len(results), groups=4*corpus['groups'],
        rounds=7, results=results, physical_provenance_and_original_return_owned_by_parent=True)
    (output/'body-result.json').write_text(json.dumps(result, indent=2)+'\n')
    return result

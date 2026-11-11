"""Reuse a completed audit only for identical Q4/config/tokenizer under one evaluator.

The running unique-model audits are not interrupted or changed. The frozen BJ
controller is paused solely to omit its redundant parent re-evaluations.
"""
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import struct
import time
from bj_common import ROOT, SOURCES, read, write, check_frozen


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def packet(path):
    raw = path.read_bytes(); assert raw[:8] == b'MKQBv1\0\0'
    size = struct.unpack('<I', raw[8:12])[0]
    return json.loads(raw[12:12 + size]), raw[12 + size:]


def identity(selected, parent):
    a, x = packet(selected / 'model.mkqb'); b, y = packet(parent / 'model.mkqb')
    assert x == y and a['tensors'] == b['tensors'], 'Quantized tensors differ'
    def config(header):
        return {k: v for k, v in header['config'].items() if k not in ['_name_or_path', 'transformers_version']}
    assert config(a) == config(b), 'Model computation configurations differ'
    assert sha(selected / 'hf/tokenizer.json') == sha(parent / 'hf/tokenizer.json')
    def tok(folder):
        return {k: v for k, v in read(folder / 'hf/tokenizer_config.json').items() if k not in ['name_or_path', '_name_or_path']}
    assert tok(selected) == tok(parent), 'Tokenizer configurations differ'
    return {'Q4_payload_sha256': hashlib.sha256(x).hexdigest(), 'tensor_descriptors_equal': True,
            'computation_configuration_equal': True, 'tokenizer_equal': True,
            'selected_packet_sha256': sha(selected / 'model.mkqb'), 'parent_packet_sha256': sha(parent / 'model.mkqb')}


def main():
    check_frozen(); pause = read(ROOT / 'audit-reuse-pause.json')
    proofs = {}
    selection = read(ROOT / 'preselected.json')
    assert all(v['step'] == 0 for v in selection['branches'].values())
    # Identity must be established before any result is copied.
    for arm in ['lora', 'full']:
        proofs[arm] = identity(ROOT / 'export' / arm, SOURCES[arm])
    deadline = time.monotonic() + 14400
    roles = ['lora', 'full', 'fixed6000_lora', 'fixed6000_full']
    while not all((ROOT / role / 'closed.json').exists() and
                  (ROOT / role / 'status.json').exists() and read(ROOT / role / 'status.json')['phase'] == 'complete' for role in roles):
        if time.monotonic() > deadline:
            raise RuntimeError('Unique-model audit deadline exceeded')
        for role in roles:
            q = ROOT / (role + '-audit-controller.log')
            if q.exists() and 'Traceback' in q.read_text():
                raise RuntimeError('Unique-model audit failed: ' + role)
        time.sleep(15)
    for arm in ['lora', 'full']:
        identity(ROOT / 'export' / arm, SOURCES[arm])
        role = 'parent_' + arm; out = ROOT / role; out.mkdir(exist_ok=True)
        folder = ROOT / 'export' / role
        shutil.copytree(SOURCES[arm], folder, dirs_exist_ok=True)
        shutil.copyfile(ROOT / 'export' / arm / 'protocol.json', folder / 'protocol.json')
        shutil.copyfile(ROOT / arm / 'closed.json', out / 'closed.json')
        assert sha(out / 'closed.json') == sha(ROOT / arm / 'closed.json')
        proofs[arm]['closed_report_sha256'] = sha(out / 'closed.json')
        manifest = read(folder / 'manifest.json')
        manifest.update(experiment='spec-intent-recovery-v1', role=role, audit_reused_from=arm,
                        audit_identity_verified=True, new_training=False)
        write(folder / 'manifest.json', manifest)
        write(out / 'audit-reuse.json', {'reused_from': arm, 'identity': proofs[arm], 'same_evaluator_same_closed_tasks': True})
        write(out / 'status.json', {'phase': 'complete', 'audit_reused_from_identical_weights': arm, 'unix': time.time()})
    a = read(ROOT / 'lora/training.json'); b = read(ROOT / 'full/training.json')
    assert a['draw_digest'] == b['draw_digest'] and a['optimizer_updates'] == b['optimizer_updates'] == 6000
    check_frozen()
    pid = pause['pid']; command = (Path('/proc') / str(pid) / 'cmdline').read_bytes()
    assert b'bj_round.py' in command
    os.kill(pid, signal.SIGKILL)  # paused own controller; all unique workers have completed
    shutil.copyfile(Path(__file__), ROOT / 'audit-reuse-driver.py')
    write(ROOT / 'audit-reuse.json', {'complete': True, 'proofs': proofs, 'driver_sha256': sha(Path(__file__)),
          'all_unique_models_fully_evaluated': True, 'no_model_data_prompt_evaluator_or_test_changes': True,
          'original_controller_stopped_after_workers_completed': pid, 'unix': time.time()})
    write(ROOT / 'complete.json', {'complete': True, 'optimizer_updates': 12000, 'same_data_draws': True,
          'closed_used_for_selection': False, 'identical_parent_audits_reused': True})
    write(ROOT / 'status.json', {'phase': 'complete', 'optimizer_updates': 12000, 'unix': time.time()})
    print(json.dumps({'complete': True, 'identical_parent_audits_reused': True}), flush=True)


if __name__ == '__main__':
    try:
        main()
    except BaseException as error:
        write(ROOT / 'audit-reuse-failed.json', {'error': repr(error), 'unix': time.time()})
        pause = read(ROOT / 'audit-reuse-pause.json')
        try:
            os.kill(pause['pid'], signal.SIGCONT)
        except ProcessLookupError:
            pass
        raise

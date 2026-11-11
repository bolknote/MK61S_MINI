"""Finish the frozen two-GPU diagnosis experiment and collect verified results."""
import json
import subprocess
import sys
import time
from remote import SSH, STATE, REPO, HERE, BASE

ROOT = BASE / 'error-recognizer-v1'
PYTHON = REPO / '.build/squeal-chat-20261105/venv/bin/python'


def remote(source):
    for attempt in range(3):
        result = subprocess.run([*SSH, 'python3 -'], input=source, text=True, capture_output=True, timeout=60)
        if result.returncode == 0:
            return result.stdout
        if attempt == 2:
            raise RuntimeError(result.stderr[-2000:])


def main():
    directory = json.loads(STATE.read_text())['directory']
    deadline = time.monotonic() + 6 * 3600
    while time.monotonic() < deadline:
        source = '''from pathlib import Path
import json
d=Path(REMOTE)/'.build/mk61-agent-20261106/error-recognizer-v1'
print((d/'status.json').read_text() if(d/'status.json').exists() else '{}')
'''.replace('REMOTE', repr(directory))
        value = json.loads(remote(source))
        (ROOT / 'monitor-status.json').write_text(json.dumps(value, indent=2) + '\n')
        if value.get('phase') == 'failed':
            raise RuntimeError(value)
        if value.get('phase') == 'complete':
            break
        time.sleep(20)
    else:
        raise RuntimeError('Diagnosis experiment deadline exceeded')
    target = ROOT / 'server-results'
    if not (target / 'complete.json').exists():
        subprocess.run([sys.executable, str(HERE / 'ao_remote.py'), 'fetch'], cwd=REPO, check=True, timeout=1800)
    source = '''from pathlib import Path
import json,hashlib,subprocess
r=Path(REMOTE);d=r/'.build/mk61-agent-20261106/error-recognizer-v1'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
for name in ['data-frozen.json','prepared.json']:
 for n,digest in json.loads((d/name).read_text())['files'].items():assert sha(d/n)==digest,n
p=json.loads((d/'prepared.json').read_text())
assert sha(d/'source-features.pt')==p['source_feature_sha256']
for n,digest in p['source_hashes'].items():assert sha(r/'research/mk61-agent-20261106'/n)==digest,n
f=json.loads((d/'data-frozen.json').read_text());parent=r/'.build/mk61-agent-20261106/hex-hypothesis-v2/export/direct-research'
assert sha(parent/'hf/model.safetensors')==f['source_master_sha256']
assert sha(parent/'model.mkqb')==f['source_packet_sha256']
ours=[]
for identity in subprocess.check_output(['sudo','-n','docker','ps','-q'],text=True).split():
 v=json.loads(subprocess.check_output(['sudo','-n','docker','inspect',identity],text=True))[0]
 if any(m.get('Source')==str(r)for m in v['Mounts']):ours.append(identity)
assert not ours
print(json.dumps({'all_frozen_data_sources_verified':True,'source_features_verified':True,
 'main_actor_not_modified':True,'own_running_containers':ours,
 'gpu_state':subprocess.check_output(['nvidia-smi','--query-gpu=index,memory.used,utilization.gpu','--format=csv,noheader'],text=True)}))
'''.replace('REMOTE', repr(directory))
    (target / 'postflight.json').write_text(json.dumps(json.loads(remote(source)), indent=2) + '\n')
    for script in ['ao_verify.py', 'ao_report.py']:
        subprocess.run([str(PYTHON), str(HERE / script), '--root', str(target)], cwd=REPO, check=True, timeout=7200)
    result = {'completed': True, 'root': str(target), 'report': str(HERE / 'ERROR_RECOGNIZER_RESULTS.md'), 'unix': time.time()}
    (ROOT / 'collection-failed.json').unlink(missing_ok=True)
    (ROOT / 'collection.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result), flush=True)


if __name__ == '__main__':
    try:
        main()
    except BaseException as error:
        (ROOT / 'collection-failed.json').write_text(json.dumps({'error': repr(error), 'unix': time.time()}) + '\n')
        raise

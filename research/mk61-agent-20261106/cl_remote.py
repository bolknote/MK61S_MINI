"""Start the detached recovery experiment and fetch its results when complete."""

import argparse
import json
import shlex
import subprocess
import tarfile

import ck_remote
from ay_common import read, sha, write
from cl_data import ROOT


ARTIFACT = ROOT / "remote-run.json"
RELATIVE = ".build/mk61-agent-20261106/kon-tiki-composition-recovery-v1"


def deploy():
    if not ARTIFACT.exists():
        path = ck_remote.remote("import tempfile; print(tempfile.mkdtemp(prefix='kon-tiki-recovery-', dir='/home/sad'))").strip()
        if not path.startswith("/home/sad/kon-tiki-recovery-"):
            raise RuntimeError("Unexpected remote directory")
        write(ARTIFACT, {"path": path, "host_gpu": 1, "name": path.rsplit("/", 1)[-1]})
    info = read(ARTIFACT)
    archive = ROOT / "train-deploy.tar.gz"
    unpack = f"import sys,tarfile; tarfile.open(fileobj=sys.stdin.buffer,mode='r|gz').extractall({info['path']!r},filter='data')"
    with archive.open("rb") as stream:
        subprocess.run([*ck_remote.SSH, "python3 -c " + shlex.quote(unpack)], stdin=stream, check=True, timeout=180)
    print({**info, "archive_sha256": sha(archive), "archive_bytes": archive.stat().st_size}, flush=True)


def prefix():
    info = read(ARTIFACT)
    return ("import json, os, subprocess, time\nfrom pathlib import Path\n"
            f"repo=Path({info['path']!r})\nroot=repo/{RELATIVE!r}\nname={info['name']!r}\ngpu={info['host_gpu']}\n")


def start():
    source = prefix() + f"image={ck_remote.IMAGE!r}\n" + '''
import fcntl
with (root/'launch.lock').open('a') as lock:
    fcntl.flock(lock, fcntl.LOCK_EX)
    if (root/'launch.json').exists():
        print((root/'launch.json').read_text())
        raise SystemExit(0)
    free=int(subprocess.check_output(['nvidia-smi','--query-gpu=memory.free','--format=csv,noheader,nounits','-i',str(gpu)],text=True).strip())
    if free < 6144:
        raise RuntimeError(f'Training needs GPU headroom; free MiB={free}')
    command=['sudo','-n','docker','run','-d','--rm','--name',name,'--gpus','device='+str(gpu),
             '--network','none','--cpus=4','--memory=10g','--shm-size=512m','--user',f'{os.getuid()}:{os.getgid()}',
             '--env','HF_HUB_OFFLINE=1','--env','TRANSFORMERS_OFFLINE=1','--env','HF_HOME=/tmp/hf',
             '--env','TOKENIZERS_PARALLELISM=false','--volume',str(repo)+':/work','--workdir','/work',
             '--entrypoint','/bin/sh',image,'-c',
             'exec python3 -u research/mk61-agent-20261106/cl_pipeline.py > '+str(root.relative_to(repo)/'pipeline.log')+' 2>&1']
    container=subprocess.check_output(command,text=True,timeout=20).strip()
    data={'container':container,'name':name,'host_gpu':gpu,'started':time.time(),'free_before_MiB':free}
    path=root/'launch.json';tmp=path.with_suffix('.tmp');tmp.write_text(json.dumps(data));tmp.replace(path)
    print(json.dumps(data))
'''
    print(ck_remote.remote(source).strip(), flush=True)


def status():
    source = prefix() + '''
def read(n):
    path=root/n
    return json.loads(path.read_text()) if path.is_file() else None
running=name in subprocess.check_output(['sudo','-n','docker','ps','--filter','name=^/'+name+'$','--format','{{.Names}}'],text=True).splitlines()
value={'running':running,'preflight':read('preflight.json'),'pipeline':read('pipeline-status.json'),
       'training':read('train-status.json'),'complete':read('complete.json'),'launch':read('launch.json')}
if not running and not value['complete']:
    p=root/'pipeline.log'
    value['log_tail']=''.join(p.read_text(errors='replace').splitlines(keepends=True)[-14:]) if p.exists() else None
print(json.dumps(value))
'''
    result = json.loads(ck_remote.remote(source))
    write(ROOT / "remote-status.json", result)
    print(json.dumps(result, ensure_ascii=False), flush=True)


def fetch():
    source = prefix() + '''
import sys, tarfile
assert json.loads((root/'complete.json').read_text())['complete']
names=('complete.json','comparison.json','KON_TIKI_COMPOSITION_RECOVERY_RESULTS.md','preselected.json','training.json',
       'preflight.json','pipeline.log','pipeline-status.json','train-status.json','launch.json')
with tarfile.open(fileobj=sys.stdout.buffer,mode='w|gz') as bundle:
    paths=[*(root/n for n in names),*(root/'checkpoints').glob('*/*'),*(root/'eval').glob('*/*.json')]
    for p in sorted(paths):
        bundle.add(p,arcname=str(p.relative_to(root)),recursive=False)
'''
    with subprocess.Popen([*ck_remote.SSH, "python3 -c " + shlex.quote(source)], stdout=subprocess.PIPE) as child:
        with tarfile.open(fileobj=child.stdout, mode="r|gz") as archive:
            archive.extractall(ROOT, filter="data")
        if child.wait() != 0:
            raise RuntimeError("Could not retrieve complete Q4 results")
    complete = read(ROOT / "complete.json")
    comparison = read(ROOT / "comparison.json")
    assert sha(ROOT / "comparison.json") == complete["comparison_sha256"]
    assert sha(ROOT / comparison["report"]) == complete["report_sha256"]
    for name in comparison["training"]["checkpoints"]:
        folder = ROOT / name
        receipt = read(folder / "manifest.json")
        assert sha(folder / "model.mkqb") == receipt["Q4_sha256"]
        assert sha(folder / "adapter.safetensors") == receipt["adapter_sha256"]
    print(ROOT / comparison["report"], flush=True)


if __name__ == "__main__":
    args = argparse.ArgumentParser()
    actions = {"deploy": deploy, "start": start, "status": status, "fetch": fetch}
    args.add_argument("stage", choices=actions)
    actions[args.parse_args().stage]()

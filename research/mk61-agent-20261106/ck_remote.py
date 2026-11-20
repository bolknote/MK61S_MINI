"""Run this translator course in a dedicated directory on the user's B200 host."""

import argparse
import json
import shlex
import subprocess
import sys
import tarfile
import time

from ay_common import read, sha, write
from ck_data import ROOT
from remote import SSH
from run_experiment import IMAGE


ARTIFACT = ROOT / "remote-run.json"
RELATIVE = ".build/mk61-agent-20261106/kon-tiki-paired-compositions-v1"
NAME_PREFIX = "kon-tiki-pairs-"


def remote(source):
    return subprocess.check_output([*SSH, "python3 -c " + shlex.quote(source)], text=True, timeout=40)


def deploy():
    if not ARTIFACT.exists():
        path = remote("import tempfile; print(tempfile.mkdtemp(prefix='kon-tiki-pairs-', dir='/home/sad'))").strip()
        if not path.startswith("/home/sad/kon-tiki-pairs-"):
            raise RuntimeError("Unexpected remote run directory")
        write(ARTIFACT, {"path": path, "host_gpu": 1, "name": NAME_PREFIX + path.rsplit("-", 1)[-1]})
    info = read(ARTIFACT)
    archive = ROOT / "train-deploy.tar.gz"
    unpack = f"import sys,tarfile; tarfile.open(fileobj=sys.stdin.buffer,mode='r|gz').extractall({info['path']!r},filter='data')"
    with archive.open("rb") as stream:
        subprocess.run([*SSH, "python3 -c " + shlex.quote(unpack)], stdin=stream, check=True, timeout=180)
    print({**info, "archive_sha256": sha(archive), "archive_bytes": archive.stat().st_size}, flush=True)


def prefix():
    info = read(ARTIFACT)
    return ("import json, os, subprocess, time\nfrom pathlib import Path\n"
            f"repo=Path({info['path']!r})\nroot=repo/{RELATIVE!r}\nname={info['name']!r}\ngpu={info['host_gpu']}\n")


def start():
    source = prefix() + f"image={IMAGE!r}\n" + '''
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
             'exec python3 -u research/mk61-agent-20261106/ck_train.py > '+str(root.relative_to(repo)/'train.log')+' 2>&1']
    container=subprocess.check_output(command,text=True,timeout=20).strip()
    data={'container':container,'name':name,'host_gpu':gpu,'started':time.time(),'free_before_MiB':free}
    path=root/'launch.json';tmp=path.with_suffix('.tmp');tmp.write_text(json.dumps(data));tmp.replace(path)
    print(json.dumps(data))
'''
    print(remote(source).strip(), flush=True)


def status():
    source = prefix() + '''
def read(name_):
    path=root/name_
    return json.loads(path.read_text()) if path.is_file() else None
value={'preflight':read('preflight.json'),'status':read('train-status.json'),'training':read('training.json'),
       'launch':read('launch.json')}
value['running']=name in subprocess.check_output(['sudo','-n','docker','ps','--filter','name=^/'+name+'$','--format','{{.Names}}'],text=True).splitlines()
if not value['running'] and not value['training']:
    p=root/'train.log'
    value['log_tail']=''.join(p.read_text(errors='replace').splitlines(keepends=True)[-14:]) if p.exists() else None
print(json.dumps(value))
'''
    result = json.loads(remote(source))
    write(ROOT / "remote-status.json", result)
    print(json.dumps(result, ensure_ascii=False), flush=True)


def fetch():
    source = prefix() + '''
import sys, tarfile
proof=json.loads((root/'training.json').read_text()); assert proof['optimizer_updates']>0
with tarfile.open(fileobj=sys.stdout.buffer,mode='w|gz') as bundle:
    for p in [*(root/'checkpoints').glob('*/*'), *(root/name for name in ('training.json','preflight.json','train.log','train-status.json','launch.json'))]:
        bundle.add(p,arcname=str(p.relative_to(root)),recursive=False)
'''
    with subprocess.Popen([*SSH, "python3 -c " + shlex.quote(source)], stdout=subprocess.PIPE) as child:
        with tarfile.open(fileobj=child.stdout, mode="r|gz") as bundle:
            bundle.extractall(ROOT, filter="data")
        if child.wait() != 0:
            raise RuntimeError("Fetching B200 checkpoints failed")
    training = read(ROOT / "training.json")
    for name in training["checkpoints"]:
        folder = ROOT / name
        info = read(folder / "manifest.json")
        assert sha(folder / "model.mkqb") == info["Q4_sha256"]
        assert sha(folder / "adapter.safetensors") == info["adapter_sha256"]
    print({"fetched": training["checkpoints"], "updates": training["optimizer_updates"], "elapsed": training["update_elapsed_seconds"]}, flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    operations = {"deploy": deploy, "start": start, "status": status, "fetch": fetch}
    parser.add_argument("action", choices=operations)
    operations[parser.parse_args().action]()

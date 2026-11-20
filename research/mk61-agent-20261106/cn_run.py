"""Seal the distillation inputs and run the paired Q4 experiment on B200."""

import argparse
import json
from pathlib import Path
import shlex
import subprocess
import sys
import tarfile

from ay_common import read, sha, write
from ck_remote import IMAGE, remote, SSH
from ck_train import CURRENT, REPO
from cl_eval import model_path
from cm_eval import STEP
from cn_data import PREVIOUS, ROOT
from cn_train import MILESTONES


RUN_NAME = "kon-tiki-executor-prompt-distill-v1"
SCRIPT = "research/mk61-agent-20261106"


def prepare():
    teacher = read(ROOT / "teacher-frozen.json")
    assert all(sha(ROOT / name) == expected for name, expected in teacher["files"].items())
    assert sha(ROOT / "fresh.jsonl") == read(ROOT / "fresh-frozen.json")["sha256"]
    code = sorted(Path(__file__).resolve().parent.glob("cn_*.py"))
    local = [*code, *(ROOT / name for name in teacher["files"] if name != "teacher-audit.jsonl"),
             ROOT / "teacher-frozen.json", ROOT / "fresh.jsonl", ROOT / "fresh-frozen.json"]
    existing = [CURRENT / "working/model.mkqb", model_path(STEP), PREVIOUS / "preselected.json"]
    for split in ("development", "recovery", "closed"):
        existing.extend((PREVIOUS / f"{split}.jsonl", PREVIOUS / "eval" / f"{split}-{STEP:06d}" / "complete.json"))
    frozen = ROOT / "inputs-frozen.json"
    write(frozen, {"files": {str(p.relative_to(REPO)): sha(p) for p in [*local, *existing]},
                   "teacher": teacher["name"], "translator_step": STEP,
                   "checkpoints": list(MILESTONES), "teacher_queries_to_test": 0})
    with tarfile.open(ROOT / "deploy.tar.gz", mode="w:gz") as archive:
        for path in [*local, frozen]:
            archive.add(path, arcname=str(path.relative_to(REPO)), recursive=False)


def deployment():
    data = read(PREVIOUS / "remote-run.json")
    return data["path"], int(data["host_gpu"])


def prefix():
    path, gpu = deployment()
    return ("import json, os, subprocess, time\nfrom pathlib import Path\n"
            f"repo=Path({path!r})\ngpu={gpu}\nfolder=repo/{str(ROOT.relative_to(REPO))!r}\n"
            f"name={RUN_NAME!r}\nimage={IMAGE!r}\n")


def deploy():
    prepare()
    path, _ = deployment()
    source = f"import sys,tarfile;tarfile.open(fileobj=sys.stdin.buffer,mode='r|gz').extractall({path!r},filter='data')"
    with (ROOT / "deploy.tar.gz").open("rb") as stream:
        subprocess.run([*SSH, "python3 -c " + shlex.quote(source)], stdin=stream, check=True, timeout=90)


def launch():
    source = prefix() + f"path={SCRIPT!r}\n" + '''
import fcntl
with (folder/'launch.lock').open('a') as lock:
    fcntl.flock(lock, fcntl.LOCK_EX)
    receipt=folder/'launch.json'
    if receipt.exists():
        status_file=folder/'status.json'
        failed=status_file.is_file() and json.loads(status_file.read_text()).get('phase')=='failed'
        if not failed or (folder/'training.json').exists() or (folder/'train-status.json').exists():
            print(receipt.read_text())
            raise SystemExit(0)
        running=subprocess.check_output(['sudo','-n','docker','ps','--filter','name=^/'+name+'$','-q'],text=True).strip()
        assert not running
        (folder/'pipeline.log').replace(folder/f'preflight-{int(time.time())}.log')
        status_file.unlink()
    free=int(subprocess.check_output(['nvidia-smi','--query-gpu=memory.free','--format=csv,noheader,nounits',
                                       '-i',str(gpu)],text=True).strip())
    assert free >= 3072, free
    pipeline='exec python3 -u '+path+'/cn_run.py pipeline > '+str(folder.relative_to(repo)/'pipeline.log')+' 2>&1'
    command=['sudo','-n','docker','run','-d','--rm','--name',name,'--gpus','device='+str(gpu),
             '--network','none','--cpus=4','--memory=10g','--shm-size=512m',
             '--user',f'{os.getuid()}:{os.getgid()}','--env','HF_HUB_OFFLINE=1',
             '--env','TRANSFORMERS_OFFLINE=1','--env','HF_HOME=/tmp/hf','--env','TOKENIZERS_PARALLELISM=false',
             '--volume',str(repo)+':/work','--workdir','/work','--entrypoint','/bin/sh',image,'-c',pipeline]
    container=subprocess.check_output(command,text=True,timeout=28).strip()
    result={'container':container,'gpu':gpu,'free_before_MiB':free,'start':time.time()}
    temporary=receipt.with_suffix('.tmp')
    temporary.write_text(json.dumps(result)); temporary.replace(receipt)
    print(json.dumps(result))
'''
    result = json.loads(remote(source))
    write(ROOT / "launch.json", result)
    print(result, flush=True)


def pipeline():
    def run(script, *args):
        label = " ".join((script, *args))
        write(ROOT / "status.json", {"phase": label})
        subprocess.run([sys.executable, "-u", SCRIPT + "/" + script, *args], cwd=REPO, check=True)

    def evaluate(split, mode, step=0):
        run("cn_eval.py", split, "--mode", mode, "--step", str(step))

    try:
        run("cn_train.py")
        for split in ("recovery", "development"):
            evaluate(split, "full")
            evaluate(split, "short")
            for step in MILESTONES:
                evaluate(split, "short", step)
        run("cn_eval.py", "select")
        step = read(ROOT / "preselected.json")["audit_step"]
        for split in ("closed", "fresh"):
            evaluate(split, "full")
            evaluate(split, "short")
            evaluate(split, "short", step)
    except subprocess.CalledProcessError as error:
        write(ROOT / "status.json", {"phase": "failed", "command": error.cmd, "code": error.returncode})
        raise
    write(ROOT / "complete.json", {"complete": True, "step": step,
                                    "training_sha256": sha(ROOT / "training.json"),
                                    "selection_sha256": sha(ROOT / "preselected.json"),
                                    "eval": {p.parent.name: sha(p) for p in sorted((ROOT / "eval").glob("*/complete.json"))}})
    write(ROOT / "status.json", {"phase": "complete"})


def status():
    result = remote(prefix() + '''
def read(file):
    p=folder/file
    return json.loads(p.read_text()) if p.is_file() else None
log=folder/'pipeline.log'
tail=log.read_text(errors='replace').splitlines()[-8:] if log.is_file() else []
running=name in subprocess.check_output(['sudo','-n','docker','ps','--filter','name=^/'+name+'$','--format','{{.Names}}'],text=True).splitlines()
print(json.dumps({'running':running,'status':read('status.json'),'train':read('train-status.json'),
                  'selection':read('preselected.json'),'complete':read('complete.json'),'tail':tail}))
''')
    print(result.strip())


def fetch():
    source = prefix() + '''
import sys,tarfile
assert json.loads((folder/'complete.json').read_text())['complete']
files=['complete.json','training.json','preselected.json','pipeline.log','status.json']
with tarfile.open(fileobj=sys.stdout.buffer,mode='w|gz') as bundle:
    for p in [*(folder/file for file in files),*(folder/'eval').glob('*/*.json'),*(folder/'checkpoints').glob('*/*')]:
        bundle.add(p,arcname=str(p.relative_to(folder)),recursive=False)
'''
    with subprocess.Popen([*SSH, "python3 -c " + shlex.quote(source)], stdout=subprocess.PIPE) as child:
        with tarfile.open(fileobj=child.stdout, mode="r|gz") as archive:
            archive.extractall(ROOT, filter="data")
        if child.wait(timeout=45) != 0:
            raise RuntimeError("Could not download complete Q4 results")
    complete = read(ROOT / "complete.json")
    assert sha(ROOT / "training.json") == complete["training_sha256"]
    assert sha(ROOT / "preselected.json") == complete["selection_sha256"]
    for name, digest in complete["eval"].items():
        folder = ROOT / "eval" / name
        assert sha(folder / "complete.json") == digest
        report = read(folder / "complete.json")
        assert sha(folder / "full.json") == report["full_sha256"]
        assert sha(folder / "metrics.json") == report["metrics_sha256"]
    print(f"Verified {len(complete['eval'])} completed evaluations under {ROOT}", flush=True)


if __name__ == "__main__":
    actions = {"deploy": deploy, "launch": launch, "pipeline": pipeline, "status": status, "fetch": fetch}
    parser = argparse.ArgumentParser()
    parser.add_argument("stage", choices=actions)
    actions[parser.parse_args().stage]()

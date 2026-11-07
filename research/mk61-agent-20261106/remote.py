"""Deploy and inspect only this experiment over the user's explicit SSH route."""
import argparse
import json
from pathlib import Path
import shlex
import subprocess
import tarfile

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
BASE = REPO / ".build/mk61-agent-20261106"
SSH = ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=15", "-o", "ControlMaster=auto", "-o", "ControlPersist=600",
       "-o", "ControlPath=/tmp/mk61-agent-ssh-%r-%h-%p", "-J", "ru3.gt.b-m-z.ru,172.18.141.231,85.233.64.133",
       "sad@10.224.64.2", "-p", "6000"]
STATE = BASE / "remote.json"


def remote_python(source):
    return subprocess.check_output([*SSH, "python3 -c " + shlex.quote(source)], text=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["deploy", "start", "parallel-control", "language-round", "status", "fetch"])
    parser.add_argument("--arm", choices=["plan", "no-plan"])
    args = parser.parse_args()
    state = json.loads(STATE.read_text()) if STATE.exists() else None
    if args.action == "deploy":
        if state is None:
            root = remote_python("import tempfile;print(tempfile.mkdtemp(prefix='mk61-agent-20261106-',dir='/home/sad'))").strip()
            if not root.startswith("/home/sad/mk61-agent-20261106-"):
                raise ValueError("Unexpected remote path")
            state = {"directory": root}
            STATE.write_text(json.dumps(state, indent=2) + "\n")
        files = list(HERE.glob("*.py")) + list(HERE.glob("*.cpp")) + list(HERE.glob("*.md")) + list(HERE.glob("*.json"))
        files += [REPO / "code" / name for name in ["mk61emu_core.cpp", "mk61emu_core.h", "rust_types.h", "firmware_optimization.hpp",
                                                   "mk61emu_standalone.hpp", "stm32_sram_bit_band.hpp", "dwt_profiler.hpp"]]
        for directory in [BASE / "flourish-original", BASE / "training", BASE / "tasks", BASE / "language-data"]:
            files += [path for path in directory.rglob("*") if path.is_file()]
        # Only frozen inputs are sent; remote teacher caches and checkpoints
        # belong to their own round and are never overwritten by deployment.
        for name in ["frozen.json", "validation.jsonl", "fresh-russian.jsonl", "policy.json", "frozen-v2.json", "validation-v2.jsonl", "fresh-russian-v2.jsonl"]:
            path=BASE/"distill-v1"/name
            if path.is_file():files.append(path)
        archive = BASE / "deploy.tar.gz"
        with tarfile.open(archive, "w:gz") as stream:
            for file in files:
                stream.add(file, arcname=str(file.relative_to(REPO)), recursive=False)
        command = "import sys,tarfile;tarfile.open(fileobj=sys.stdin.buffer,mode='r|gz').extractall(" + repr(state["directory"]) + ",filter='data')"
        with archive.open("rb") as source:
            subprocess.run([*SSH, "python3 -c " + shlex.quote(command)], stdin=source, check=True)
        print(json.dumps({**state, "files": len(files), "archive_bytes": archive.stat().st_size}))
    elif args.action == "start":
        if "pid" in state:
            probe = "from pathlib import Path; p=Path('/proc/" + str(state["pid"]) + "/cmdline'); print('running' if p.exists() and b'run_experiment.py' in p.read_bytes() else 'stopped')"
            if remote_python(probe).strip() == "running":
                raise SystemExit("Controller is still running; inspect status instead")
        source = ("import subprocess,pathlib; root=pathlib.Path(" + repr(state["directory"]) + "); "
                  "log=(root/'.build/mk61-agent-20261106/controller.log').open('w'); "
                  "p=subprocess.Popen(['python3','-u',str(root/'research/mk61-agent-20261106/run_experiment.py')],cwd=root,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,start_new_session=True); print(p.pid)")
        state["pid"] = int(remote_python(source).strip())
        STATE.write_text(json.dumps(state, indent=2) + "\n")
        print(json.dumps(state))
    elif args.action == "parallel-control":
        if "parallel_pid" in state:
            probe = "from pathlib import Path; p=Path('/proc/" + str(state["parallel_pid"]) + "/cmdline'); print('running' if p.exists() and b'parallel_control.py' in p.read_bytes() else 'stopped')"
            if remote_python(probe).strip() == "running":
                raise SystemExit("Parallel control is already running")
        source = ("import subprocess,pathlib; root=pathlib.Path(" + repr(state["directory"]) + "); "
                  "log=(root/'.build/mk61-agent-20261106/parallel-controller.log').open('w'); "
                  "p=subprocess.Popen(['python3','-u',str(root/'research/mk61-agent-20261106/parallel_control.py')],cwd=root,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,start_new_session=True);print(p.pid)")
        state["parallel_pid"] = int(remote_python(source).strip())
        STATE.write_text(json.dumps(state, indent=2) + "\n")
        print(json.dumps(state))
    elif args.action == "language-round":
        if "language_pid" in state:
            probe = "from pathlib import Path; p=Path('/proc/" + str(state["language_pid"]) + "/cmdline'); print('running' if p.exists() and b'language_round.py' in p.read_bytes() else 'stopped')"
            if remote_python(probe).strip() == "running":
                raise SystemExit("Language round is already running")
        source = ("import subprocess,pathlib; root=pathlib.Path(" + repr(state["directory"]) + "); "
                  "log=(root/'.build/mk61-agent-20261106/language-controller.log').open('w'); "
                  "p=subprocess.Popen(['python3','-u',str(root/'research/mk61-agent-20261106/language_round.py')],cwd=root,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,start_new_session=True);print(p.pid)")
        state["language_pid"] = int(remote_python(source).strip())
        STATE.write_text(json.dumps(state, indent=2) + "\n")
        print(json.dumps(state))
    elif args.action == "status":
        root = state["directory"]
        source = ("import pathlib,json; p=pathlib.Path(" + repr(root) + ")/'.build/mk61-agent-20261106'; "
                  "s=p/'remote-status.json'; print(s.read_text() if s.exists() else 'not_started'); "
                  "s=p/'language-status.json'; print(s.read_text() if s.exists() else ''); "
                  "[(print(str(f.relative_to(p))),print(f.read_text())) for f in p.glob('*/status.json')]; "
                  "[(print(f.name),print(f.read_text()[-1800:])) for f in [p/'controller.log'] if f.exists()]; "
                  "[(print(f.name),print(f.read_text()[-1400:])) for f in sorted(p.glob('*.log'),key=lambda f:f.stat().st_mtime)[-2:] if f.name!='controller.log']")
        print(remote_python(source))
    else:
        root = state["directory"]
        # Extract only our own experiment's results into a separate local folder.
        source = ("import pathlib,sys,tarfile; p=pathlib.Path(" + repr(root) + ")/'.build/mk61-agent-20261106'; "
                  "t=tarfile.open(fileobj=sys.stdout.buffer,mode='w|gz'); "
                  "[(t.add(f,arcname=str(f.relative_to(p)),recursive=False)) for f in p.rglob('*') if f.is_file() and "
                  "not any(x in f.parts for x in ['flourish-original','training','tasks']) and "
                  "(" + str(args.arm is None) + " or f.relative_to(p).parts[0]==" + repr(args.arm) + ") and "
                  "f.suffix in ['.json','.log','.safetensors','.mkq4']];t.close()")
        target = BASE / "server-results"
        target.mkdir(exist_ok=True)
        process = subprocess.Popen([*SSH, "python3 -c " + shlex.quote(source)], stdout=subprocess.PIPE)
        with tarfile.open(fileobj=process.stdout, mode="r|gz") as stream:
            stream.extractall(target, filter="data")
        if process.wait(): raise RuntimeError("Fetch failed")
        print(target)


if __name__ == "__main__":
    main()

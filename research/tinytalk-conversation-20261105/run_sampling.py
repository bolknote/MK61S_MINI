#!/usr/bin/env python3
"""Run the extra sampling check after the fixed training experiment completes."""
import json
import subprocess
import time

from run_remote import ROOT, container


def main():
    for _ in range(120):
        state = json.loads((ROOT / "status.json").read_text())
        if state["phase"] == "failed":
            raise RuntimeError(state)
        if state["phase"] == "complete":
            break
        time.sleep(5)
    else:
        raise TimeoutError("Main experiment did not finish")
    with (ROOT / "sampling.log").open("w") as log:
        result = subprocess.run(container(0, "evaluate_sampling.py"), cwd=ROOT, stdout=log,
                                stderr=subprocess.STDOUT, timeout=900)
    status = {"phase": "complete" if result.returncode == 0 else "failed", "exit": result.returncode}
    (ROOT / "sampling-status.json").write_text(json.dumps(status) + "\n")


if __name__ == "__main__":
    try:
        main()
    except BaseException as error:
        (ROOT / "sampling-status.json").write_text(json.dumps({"phase": "failed", "error": str(error)}) + "\n")
        raise

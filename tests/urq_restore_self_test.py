#!/usr/bin/env python3
"""Exercise restore at every I/O failure boundary with a live nested procedure."""
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.apps.urq.qst2urq import make_package

SOURCE = (":start\nscore=17\ninv+ 2,key\nbtn done,Continue\n"
          "proc ask & score+=1\nend\n:ask\nproc inner\nend\n:inner\n"
          "input answer\npln #answer$\npause 30\nend\n:done\nquit\n")

if __name__ == "__main__":
    helper = Path(sys.argv[1]).resolve()
    for mode in ("dosurq", "ripurq", "akurq", "urqw"):
        with tempfile.TemporaryDirectory(prefix="urq-restore-") as temporary:
            folder = Path(temporary)
            files, _ = make_package(SOURCE.encode(), mode, "UTF-8")
            for name, data in files.items():
                (folder / name).write_bytes(data)
            subprocess.run([str(helper), str(folder)], check=True)

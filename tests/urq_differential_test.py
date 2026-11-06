#!/usr/bin/env python3
"""Compare authored text conformance stories with the pinned UrqW sources."""
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("qst2urq", ROOT / "tools/apps/urq/qst2urq.py")
packer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(packer)
HOST, UPSTREAM = map(Path, sys.argv[1:3])
del sys.argv[1:3]
LOCK = json.loads((ROOT / "tools/apps/urq/upstream.json").read_text())

STORIES = [
    (":start\nx=-2^2\ny=2^3^2\nz=1=2<3\na=not 1+2\n"
     "b='0' and 1\nc='bad'-1\npln #x$ #y$ #z$ #a$ #b$\nend", []),
    (":start\na=4\nb='a'\npln #(#b$+1)$ #$#%$#/$##1040$\nend", []),
    (":start\nproc one & pln returned\nend\n:one\nproc two & pln one\nend\n"
     ":two\ninput name\npln #name$\nend", ["i:Ёж"]),
    (":start\nbtn x+=1 & pln #x$,Raise\nbtn done,Finish\nend\n"
     ":done\nquit", ["c:0", "c:1"]),
    (":start\ninv+ 3,coin\ninv- 1,coin\nif 2 coin then pln yes\n"
     "instr phrase = a,b\ntokens phrase\npln #tokens_num$ #token1$ #token2$\nend", []),
    (":start\nanykey key\npause 10\npln #key$\nquit", ["k:13", "t:10"]),
    (":start\nwhich='next'\nbtn #which$,Go\nend\n:next\n"
     "if current_loc='next' then pln good\nend", ["c:0"]),
    (":start\nbtn next,Go\nend\n:common\nx+=1\nend\n"
     ":next\npln #x$\nend", ["c:0"]),
    (":start\nx=rnd10\ny=rnd\nz=time\nd=date\nend", []),
    (":start\ninv+ 3,Coin\ncoin=99\ninv- 1,Coin\nvarkill coin\n"
     "pln #urq_inv$ #coin$\nvarkill\npln #coin$\ninvkill Coin\npln #coin$\nend", []),
    (":start\nbtn finish,Go & x=3 & pln #x$\nend\n:finish\nquit", ["c:0"]),
    (":start\nstyle_dos_textcolor=12\npln #style_textcolor$\nstyle_dos_textcolor=6\npln #style_textcolor$\nend", []),
    (":start\nx=0.1+0.2\ns=''+x\npln #s$\nx=0.615\npln #x$\nx=1e21\ns=''+x\npln #s$\nend", []),
    (":START\npln   spaces\ns='##1040$'\npln #s$\nbtn NEXT,Go\nend\n:NEXT\npln #current_loc$\nend",["c:0"]),
    (":start\nx=1\ny=2\nvarkill urq_mode\npln #x$ #y$\nend",[]),
    (":start\npln [[next]]\nend\n:next\npln done\nend",[]),
    (":start\nbtn x=1,one\nbtn x=2,two\nend",["c:0","c:1"]),
    (":start\na='ё'>'я'\nb='А'<'№'\nc='Ё'<'А'\nd='Щ'>'Ш'\nend",[]),
    # Comments are processed by Quest.next(), using the current runtime mode.
    (":start\nurq_mode='urqw'\npln retained; text\nend", []),
    (":start\nurq_mode='dosurq'\npln before; removed\nend", []),
    (":start\nname='urq_mode'\n#name$='urqw'\npln retained; text\nend", []),
    (":start\nif 1 then urq_mode='urqw'\npln retained; text\nend", []),
    (":start\nbtn urq_mode='urqw' & goto following,Change\nend\n"
     ":following\npln fetched; text\nend", ["c:0"]),
    (":start\ninput urq_mode\npln retained; text\nend", ["i:urqw"]),
    # A switch affects fresh source fetches, not an already queued compound tail.
    (":start\nurq_mode='dosurq' & pln queued; text\npln fetched; removed\nend", []),
    # Dynamic printed text can produce an executable assignment link.
    (":start\ninput text\npln #text$\nend\n:following\npln retained; text\nend",
     ["i:[[Change|urq_mode='urqw' & goto following]]", "c:32768"]),
    # Labels are indexed before semicolon comments are applied at execution.
    (":start; part of label\npln #current_loc$\nend", []),
]


def events(output):
    result = [json.loads(line) for line in output.splitlines()]
    for event in result:
        if event["event"] == "state":
            event.pop("pc", None)
            for key in ["urq_mode", "style_backcolor", "style_textcolor"]:
                event["vars"].pop(key, None)
    return result


class DifferentialTests(unittest.TestCase):
    def test_pinned_version(self):
        revision = subprocess.check_output(["git", "-C", str(UPSTREAM), "rev-parse", "HEAD"], text=True).strip()
        self.assertEqual(revision, LOCK["commit"])

    def test_text_semantics(self):
        for mode in ("dosurq", "ripurq", "akurq", "urqw"):
            for index, (source, commands) in enumerate(STORIES):
                if mode in ('dosurq', 'ripurq') and any(command.startswith('c:32768') for command in commands):
                    continue  # The oracle disables HTML/link support in these manifests.
                with self.subTest(mode=mode, story=index), tempfile.TemporaryDirectory(prefix="urq-oracle-") as temp:
                    directory = Path(temp)
                    qst = directory / "source.qst"
                    qst.write_text(source, encoding="utf-8")
                    files, _ = packer.make_package(source.encode(), mode, "UTF-8")
                    for name, data in files.items():
                        (directory / name).write_bytes(data)
                    reference = subprocess.run(["node", str(ROOT / "tools/apps/urq/oracle.js"),
                                                str(UPSTREAM), str(qst), mode, *commands],
                                               capture_output=True, text=True, timeout=15)
                    self.assertEqual(reference.returncode, 0, reference.stderr)
                    actual = subprocess.run([str(HOST), str(directory), *commands], capture_output=True, text=True)
                    self.assertEqual(actual.returncode, 0, actual.stdout + actual.stderr)
                    self.assertEqual(events(actual.stdout), events(reference.stdout))


if __name__ == "__main__":
    unittest.main()

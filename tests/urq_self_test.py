#!/usr/bin/env python3
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("qst2urq", ROOT / "tools/apps/urq/qst2urq.py")
packer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(packer)
HOST = Path(sys.argv.pop(1))


class UrqTests(unittest.TestCase):
    def game(self, source, *commands, mode="dosurq",resources=None,deferred=False):
        with tempfile.TemporaryDirectory(prefix="urq-test-") as directory:
            files, _ = packer.make_package(source.encode("utf-8"), mode, "UTF-8",resources=resources)
            for name, data in files.items():
                (Path(directory) / name).write_bytes(data)
            commands = [command.replace("@SAVE@", str(Path(directory) / "slot.urs"))
                        for command in commands]
            environment=dict(os.environ)
            if deferred:environment['URQ_HOST_DEFER_SAVE']='1'
            result = subprocess.run([str(HOST), directory, *commands], capture_output=True, text=True,env=environment)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            return [json.loads(line) for line in result.stdout.splitlines()]

    def test_modes_and_complete_game(self):
        for mode in ("dosurq", "ripurq", "akurq", "urqw", "urqw1"):
            with self.subTest(mode=mode):
                events = self.game(":start\npln Привет\nbtn next,Дальше\nend\n"
                                   ":next\ninv+ ключ\ninput ответ\n"
                                   "if ответ = 'Ёж' then proc win else goto start\nend\n"
                                   ":win\npln Победа #inv_ключ$\nend\n",
                                   "c:0", "i:Ёж", mode=mode)
                states = [e for e in events if e["event"] == "state"]
                self.assertEqual(states[1]["status"], 4)
                self.assertEqual(states[-1]["error"], 0)
                self.assertIn("Победа 1", [e["text"] for e in events if e["event"] == "text"])
                counter = "next" if mode == "ripurq" else "count_next"
                self.assertEqual(states[-1]["vars"][counter], 1)

    def test_expressions_dynamic_names_and_compound_buttons(self):
        events = self.game(":start\nx = 2+3*4\ns = 'ключ'\n#s$ = x\n"
                           "if x = 14 and ключ == 14 then pln OK else pln FAIL\n"
                           "btn x+=1 & pln #x$,Поднять\nend\n", "c:0")
        texts = [e["text"] for e in events if e["event"] == "text"]
        self.assertEqual(texts, ["OK", "15"])

    def test_runtime_mode_preserves_source_comments(self):
        for mode in ("dosurq", "ripurq", "akurq", "urqw"):
            for assignment in ("urq_mode='urqw'", "name='urq_mode'\n#name$='urqw'",
                               "if 1 then urq_mode='urqw'", "instr urq_mode=urqw"):
                with self.subTest(mode=mode, assignment=assignment):
                    events = self.game(":start\n" + assignment + "\npln keep; this\nend", mode=mode)
                    self.assertEqual([e['text'] for e in events if e['event'] == 'text'], ['keep; this'])
            if mode in ('akurq', 'urqw'):
                events = self.game(":start\ninput text\npln #text$\nend\n"
                                   ":following\npln keep; this\nend",
                                   "i:[[Change|urq_mode='urqw' & goto following]]", "c:32768", mode=mode)
                self.assertIn('keep; this', [e['text'] for e in events if e['event'] == 'text'])
        events = self.game(":start\nfile_content='note.txt'\npln #file_content$\nend\n"
                           ":following\npln keep; this\nend", "c:32768", mode='akurq',
                           resources={'note.txt': "[[Change|urq_mode='urqw' & goto following]]"})
        self.assertIn('keep; this', [e['text'] for e in events if e['event'] == 'text'])
        events = self.game(":start\nurq_mode='dosurq' & pln queued; text\n"
                           "pln fetched; removed\nend", mode='urqw')
        self.assertEqual([e['text'] for e in events if e['event'] == 'text'], ['queued; text', 'fetched'])
        # Raw labels are indexed separately, but a statically removed classic
        # comment still must not consume the 1023-byte execution buffer.
        events = self.game(":start\npln short; " + "x" * 1500 + "\nend", mode='dosurq')
        self.assertEqual([e['text'] for e in events if e['event'] == 'text'], ['short'])

    def test_procedure_continuation_and_snapshot(self):
        events = self.game(":start\nproc ask & pln Вернулись\nend\n"
                           ":ask\ninput имя\npln #имя$\nend\n",
                           "s:@SAVE@", "i:Анна", "l:@SAVE@", "i:Оля")
        texts = [e["text"] for e in events if e["event"] == "text"]
        self.assertEqual(texts, ["Анна", "Вернулись", "Оля", "Вернулись"])

    def test_pause_anykey_and_links(self):
        events = self.game(":start\npause 100\nanykey код\n"
                           "pln [[Ссылка|finish]]\nend\n:finish\npln #код$\nquit\n",
                           "t:50", "t:50", "k:13", "c:32768", mode="urqw")
        states = [e for e in events if e["event"] == "state"]
        self.assertEqual([e["status"] for e in states], [3, 3, 2, 1, 5])

    def test_tokens_inventory_and_garbage_collection(self):
        events = self.game(":start\ninv+ 3,монета\ninv- 1,монета\n"
                           "instr фраза = раз,два\n tokens фраза\n"
                           "pln #tokens_num$ #token1$ #token2$ #монета$\n"
                           "x=0\n:loop\nx+=1\ns='abcdefghijklmnopqrst'\n"
                           "if x<200 then goto loop\npln #x$\nend\n", mode="urqw")
        self.assertEqual([e["text"] for e in events if e["event"] == "text"],
                         ["2 раз два 2", "200"])

    def test_paged_files_and_encoding(self):
        source = ":start\n" + "pln Строка\n" * 400 + "end\n"
        events = self.game(source)
        self.assertEqual(sum(e["event"] == "text" for e in events), 400)
        with self.assertRaisesRegex(ValueError, "ambiguous"):
            packer.make_package("Ёж".encode("cp866"), "dosurq")
        for encoding in ("CP1251", "CP866", "UTF-8"):
            files, report = packer.make_package(":s\npln Ёж\nend".encode(encoding),
                                               "dosurq", encoding)
            self.assertTrue(files["game.urq"].startswith(b"MK61URQ\0"))
            self.assertEqual(report["lines"], 3)

    def test_optimal_pages_keep_format_and_portable_save_identity(self):
        source = (":start\ninput имя\npln #имя$\nbtn story,Читать\nend\n:story\n" +
                  "pln На станции горит свет, за окном видны звёзды.\n" * 80 + "end\n").encode()
        greedy, before = packer.make_package(source, 'urqw', 'UTF-8')
        optimal, after = packer.make_package(source, 'urqw', 'UTF-8', zx0_parser='optimal')
        self.assertEqual(before['id'], after['id'])
        self.assertEqual(before['logical_bytes'], after['logical_bytes'])
        self.assertLessEqual(after['stored_bytes'], before['stored_bytes'])
        self.assertEqual(after['zx0_parser'], 'optimal')
        with tempfile.TemporaryDirectory(prefix='urq-optimal-') as directory:
            root = Path(directory)
            for name, files in (('greedy', greedy), ('optimal', optimal)):
                (root / name).mkdir()
                for file, data in files.items():
                    self.assertLessEqual(len(data), 61440)
                    (root / name / file).write_bytes(data)
            save = root / 'input.urs'
            saved = subprocess.run([str(HOST), str(root / 'greedy'), 's:' + str(save)],
                                   capture_output=True, text=True)
            self.assertEqual(saved.returncode, 0, saved.stderr)
            restored = subprocess.run([str(HOST), str(root / 'optimal'), 'l:' + str(save), 'i:Ёж', 'c:0'],
                                      capture_output=True, text=True)
            self.assertEqual(restored.returncode, 0, restored.stdout + restored.stderr)
            events = [json.loads(line) for line in restored.stdout.splitlines()]
            self.assertTrue(any(e.get('text') == 'Ёж' for e in events))
            self.assertEqual(sum(e['text'].startswith('На станции') for e in events if e['event'] == 'text'), 80)
            self.assertFalse(any(e.get('error') for e in events))

    def test_bad_crc_and_foreign_parts(self):
        with tempfile.TemporaryDirectory(prefix="urq-damage-") as directory:
            files, _ = packer.make_package(b":s\npln OK\nend", "dosurq")
            for name, data in files.items():
                (Path(directory) / name).write_bytes(data)
            path = Path(directory) / "p0000.uqd"
            data = bytearray(path.read_bytes()); data[-1] ^= 1; path.write_bytes(data)
            result = subprocess.run([str(HOST), directory], capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('"error":3', result.stdout)

    def test_demo_full_walkthrough_in_every_mode(self):
        source=(ROOT/"tests/fixtures/urq/demo/source.qst").read_text()
        for mode in ("dosurq","ripurq","akurq","urqw"):
            events=self.game(source,"c:0","c:0","i:Ёж","c:0","t:50","k:13",mode=mode)
            states=[e for e in events if e["event"]=="state"]
            self.assertEqual(states[-1]["status"],5)
            self.assertTrue(any(e.get("text")=="ПОБЕДА!" for e in events))
            self.assertEqual(states[-1]["items"],{"ключ":1})

    def test_long_actions_keep_order_after_selection(self):
        source=":start\n"+"\n".join(f"btn x={i},Действие {i}" for i in range(48))+"\nend"
        events=self.game(source,"c:17","c:47")
        states=[e for e in events if e["event"]=="state"]
        self.assertEqual([a["id"] for a in states[1]["actions"]],[i for i in range(48) if i!=17])
        self.assertEqual(states[-1]["vars"]["x"],47)

    def test_dynamic_text_resources(self):
        events=self.game(':start\nstem="folder"\nfile_content=stem+"/note.txt"\n'
                         'pln #file_content$\nfile_url=" /folder/note.txt "\npln #file_url$\n'
                         'file_content="missing"\npln x#file_content$x\nend',mode='urqw',
                         resources={'folder/note.txt':'Ёж читает записку.'})
        self.assertEqual([e['text'] for e in events if e['event']=='text'],
                         ['Ёж читает записку.','folder/note.txt','xx'])

    def test_deferred_save_inside_common_procedure(self):
        source=':start\nbtn finish,Go\nend\n:common\nproc inner & x+=1\nend\n:inner\nsave & y+=1\nend\n:finish\npln #x$ #y$\nend'
        events=self.game(source,'c:0','s:@SAVE@','f:1','l:@SAVE@',deferred=True)
        self.assertEqual([e['text'] for e in events if e['event']=='text'],['1 1','1 1'])
        states=[e for e in events if e['event']=='state']
        self.assertEqual(states[1]['status'],7)


if __name__ == "__main__":
    unittest.main()

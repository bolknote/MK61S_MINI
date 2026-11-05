#!/usr/bin/env python3
"""Complete text-game routes, input saves and optional original JS comparisons.

URQ_UPSTREAM=/path/to/pinned/UrqW enables the original-game oracle. All normal
tests use the shipped packages and run without downloads or JavaScript.
"""

import sys as _repo_sys
from pathlib import Path as _RepoPath
_repo_sys.path.insert(0, str(_RepoPath(__file__).resolve().parents[1]))
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from tools.apps.urq.qst2urq import make_package
from tools.apps.urq.adaptations import adapt
from tools.apps.urq.library import SOURCES, copy_device_library, copy_licenses

HOST = Path(sys.argv.pop(1)).resolve() if __name__ == "__main__" else ROOT / ".build/urq-tests/urq-host"
UPSTREAM = Path(os.environ["URQ_UPSTREAM"]).resolve() if os.environ.get("URQ_UPSTREAM") else None
LIBRARY = ROOT / "programs/urq"
ANSWERS = [
    "рис крыс кот пёс коров пса девиц пастух петуха".split(),
    "пшениц чулане синиц кот пёс коров пса старушк пастух петуха".split(),
    "зерно крыс кот пёс коров пса девиц мужчин поп петух крестьянин цыплята овечки бараны".split(),
    "пшениц чулане крыс кот собак коров недотрог бездельник священник петух крестьянин".split(),
    "пшениц крыс кот собак коров леди".split(),
    "лепёшк крыс кот пёс подвал коров".split(),
]
LAST = [9, 9, 12, 11, 6, 5]
# Follow the author's published walkthrough, then choose either of its branches.
TRAPPED_ROUTE = ["init", "56", "36", "42", "25", "60", "1",
    "20", "40", "36", "42", "25", "55", "60", "1", "36", "42", "57", "47", "i:1770",
    "36", "13", "2", "12", "51", "37", "34", "64", "7", "26", "73", "27", "25", "60",
    "1", "20", "53", "36", "42", "25", "58", "65"]


class Player:
    def __init__(self, key, reference=False):
        self.temp = tempfile.TemporaryDirectory(prefix="urq-playthrough-")
        self.reference = reference
        environment = dict(os.environ)
        if reference:
            folder = UPSTREAM / "games" / key / "urqw"
            paths = sorted(folder.glob("*.qst"), key=lambda p: (not p.name.startswith("_"), p.name))
            source = Path(self.temp.name) / "original.qst"
            source.write_text("\n".join(p.read_text(encoding="utf-8-sig") for p in paths))
            environment["URQ_ORACLE_ADAPTATION"] = key
            command = ["node", str(ROOT / "tools/apps/urq/oracle.js"), str(UPSTREAM), str(source), "urqw", "-"]
        else:
            command = [str(HOST), str(LIBRARY / key), "-"]
        self.process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, text=True, bufsize=1, env=environment)
        self.steps = 0
        self.read()

    def read(self):
        self.events = []
        while True:
            line = self.process.stdout.readline()
            if not line:
                raise AssertionError("Player stopped: " + self.process.stderr.read())
            event = json.loads(line)
            if event["event"] == "command_failed":
                raise AssertionError("Command was rejected")
            if event["event"] == "state":
                self.state = event
                if event["error"] or event["status"] == 0:
                    raise AssertionError("Game error or instruction limit: " + line)
                return
            self.events.append(event)

    def step(self, command):
        self.process.stdin.write(command + "\n")
        self.process.stdin.flush()
        self.steps += 1
        self.read()

    def choose(self, target):
        matches = [a for a in self.state["actions"] if a["command"] == target]
        if not matches:
            raise AssertionError(f"Unavailable {target!r} at {self.state['vars'].get('current_loc')}: {self.state['actions']}")
        self.step("c:" + str(matches[0]["id"]))

    def field(self, name):
        target = f'insert_var="{name}" & goto insert'
        # Later verses change grammatical forms (пёс -> пса); the earlier
        # editable occurrence remains accessible through ordinary back/next.
        while not any(a["command"] == target for a in self.state["actions"]) and self.state["vars"]["number"] > 1:
            self.choose(self.state["vars"]["label"] + str(self.state["vars"]["number"] - 1))
        while not any(a["command"] == target for a in self.state["actions"]) and self.state["vars"]["number"] < self.state["vars"]["last"]:
            self.choose(self.state["vars"]["label"] + str(self.state["vars"]["number"] + 1))
        self.choose(target)

    def route(self, route):
        for target in route:
            self.step(target) if target.startswith("i:") else self.choose(target)

    def text(self):
        return "\n".join(e["text"] for e in self.events if e["event"] == "text")

    def close(self):
        self.process.stdin.close()
        self.process.wait(timeout=5)
        error = self.process.stderr.read()
        self.process.stdout.close()
        self.process.stderr.close()
        self.temp.cleanup()
        if self.process.returncode:
            raise AssertionError(error)


class LibraryTests(unittest.TestCase):
    def player(self, key, reference=False):
        player = Player(key, reference)
        self.addCleanup(player.close)
        return player

    def house(self, index, reference=False):
        player = self.player("house_that_jack_built", reference)
        player.choose(f"ru_v{index}_0")
        for number in range(1, LAST[index] + 1):
            player.choose(f"ru_v{index}_{number}")
        return player

    def same_story(self, actual, reference):
        self.assertEqual(actual.text(), reference.text())
        self.assertEqual(actual.state["status"], reference.state["status"])
        actions = lambda p: sorted((a["command"].replace('insert_var=кот""', 'insert_var="кот"'), a["caption"])
                                  for a in p.state["actions"])
        self.assertEqual(actions(actual), actions(reference))
        # Implementation-private queue slots/counters differ; story variables do not.
        for key in ("number", "correct", "words", "adventure", "inspect_equipment", "experience",
                    "primary_information", "halvorsen_refuse", "code", "chrono_gun", "near_death_experience",
                    "extra_information", "suicide", "machine_settings", "password", "common"):
            self.assertEqual(actual.state["vars"].get(key), reference.state["vars"].get(key), key)

    def test_packages_are_reproducible_and_javascript_free(self):
        report = json.loads((ROOT / "tools/apps/urq/catalog-report.json").read_text())
        self.assertEqual(set(report["published"]), {"house_that_jack_built", "trapped_in_time_ru"})
        for key in report["published"]:
            with self.subTest(game=key):
                folder = LIBRARY / key
                metadata = SOURCES / key
                source = (metadata / "source.qst").read_bytes()
                manifest = json.loads((metadata / "manifest.json").read_text())
                files, package = make_package(source, "urqw", "UTF-8", manifest)
                self.assertEqual(package, json.loads((metadata / "package.json").read_text()))
                for name, data in files.items():
                    self.assertEqual(data, (folder / name).read_bytes())
                    self.assertLessEqual(len(data), 61440)
                self.assertNotRegex(source.decode(), r"(?i)javascript|<script")
                self.assertEqual({p.name for p in folder.iterdir()}, {"game.urq", "p0000.uqd", "autoexec.wbmp"})
                self.assertTrue((metadata / "AUTHORS.txt").is_file())
                self.assertIn("CC0", (metadata / "LICENSE.txt").read_text())
                if UPSTREAM:
                    text, generated_manifest, _ = adapt(key, UPSTREAM / "games" / key)
                    self.assertEqual(source, text.encode())
                    self.assertEqual(manifest, generated_manifest)

    def test_device_library_contains_only_games_and_icons(self):
        self.assertEqual({p.name for p in LIBRARY.iterdir()},
                         {"README.markdown", "autoexec.wbmp", "house_that_jack_built", "trapped_in_time_ru"})
        with tempfile.TemporaryDirectory(prefix="urq-distribution-") as directory:
            target = Path(directory)
            payload = copy_device_library(target / "URQ")
            licenses = copy_licenses(target / "licenses/urq")
            self.assertEqual(len(payload), 7)
            self.assertEqual(len(licenses), 4)
            self.assertTrue(all(p.suffix in {".urq", ".uqd", ".wbmp"} for p in payload))
            self.assertTrue(all(p.is_relative_to(target / "licenses") for p in licenses))

    def test_house_all_six_translations_complete_and_partial_scores(self):
        for version, answers in enumerate(ANSWERS):
            with self.subTest(version=version):
                player = self.house(version)
                reference = self.house(version, True) if UPSTREAM else None
                # Zero, every intermediate percentage (including thirds/sevenths), victory.
                for count in range(len(answers) + 1):
                    if count:
                        answer = answers[count - 1]
                        for p in filter(None, (player, reference)):
                            p.field(answer)
                            self.assertEqual(p.state["status"], 4)
                            p.step("i:" + answer.upper())
                    for p in filter(None, (player, reference)):
                        p.choose("check")
                    self.assertEqual(player.state["vars"]["correct"], count)
                    if reference:
                        self.same_story(player, reference)
                    if count == len(answers):
                        self.assertEqual(player.state["status"], 5)
                        self.assertIn("Это победа!", player.text())
                    else:
                        expected = ((200 * count + len(answers)) // (2 * len(answers)))
                        self.assertIn(f"{expected}%" if count else "0 правильных", player.text())
                        for p in filter(None, (player, reference)):
                            p.choose(p.state["vars"]["label"] + str(p.state["vars"]["number"]))

    def test_house_input_quotes_and_save_restore(self):
        player = self.house(1)
        player.field("пёс")
        path = Path(player.temp.name) / "input.urs"
        player.step("s:" + str(path))
        player.step('i:Не "тот" & О\'БРАЗ')
        self.assertEqual(player.state["vars"]["пёс"], 'Не "тот" & О\'БРАЗ')
        player.step("l:" + str(path))
        self.assertEqual(player.state["status"], 4)
        player.step("i:ПЁС")
        player.choose("check")
        self.assertEqual(player.state["vars"]["correct"], 1)

    def test_trapped_author_walkthrough_both_branches_and_queue_save(self):
        player = self.player("trapped_in_time_ru")
        reference = self.player("trapped_in_time_ru", True) if UPSTREAM else None
        for target in TRAPPED_ROUTE:
            player.route([target])
            if reference:
                reference.route([target])
                self.same_story(player, reference)
        path = Path(player.temp.name) / "branches.urs"
        player.step("s:" + str(path))
        player.choose("38")
        self.assertEqual(player.state["status"], 5)
        player.step("l:" + str(path))
        player.choose("28")
        if reference:
            reference.choose("28")
            self.same_story(player, reference)
        path = Path(player.temp.name) / "queue.urs"
        player.step("s:" + str(path))
        destinations = []
        # Exercise several six-item permutations, queue exhaustion and no immediate repeat.
        for index in range(30):
            player.choose("travel")
            if reference:
                reference.choose("travel")
                self.same_story(player, reference)
            destination = player.state["vars"]["adventure"]
            if destinations:
                self.assertNotEqual(destination, destinations[-1])
            destinations.append(destination)
        self.assertEqual(set(destinations[:6]), {"11", "48", "52", "62", "70", "1"})
        self.assertEqual(destinations[5], "1")
        player.step("l:" + str(path))
        for destination in destinations:
            player.choose("travel")
            self.assertEqual(player.state["vars"]["adventure"], destination)
        # Reach a story ending through the actual choices in the current era.
        while player.state["vars"]["adventure"] != "11":
            player.choose("travel")
        player.route(["68", "final68"])
        self.assertEqual(player.state["status"], 5)
        self.assertIn("история заканчивается", player.text())

    def test_trapped_all_twelve_ending_routes(self):
        endings = [("11", ["17", "final17"]), ("11", ["68", "final68"]),
            ("48", ["59", "22", "final22"]), ("48", ["59", "72", "final72"]),
            ("52", ["18", "final18and71"]), ("52", ["71", "final18and71"]),
            ("62", ["21", "final21"]), ("62", ["24", "final24"]),
            ("70", ["19", "final19"]), ("70", ["63", "final63"]), ("70", ["final70"])]
        for era, ending in endings + [(None, ["38"])]:
            with self.subTest(era=era, ending=ending):
                player = self.player("trapped_in_time_ru")
                reference = self.player("trapped_in_time_ru", True) if UPSTREAM else None
                for p in filter(None, (player, reference)):
                    p.route(TRAPPED_ROUTE)
                    if era:
                        p.choose("28")
                        for _ in range(6):
                            p.choose("travel")
                            if p.state["vars"]["adventure"] == era:
                                break
                        self.assertEqual(p.state["vars"]["adventure"], era)
                    p.route(ending)
                    self.assertEqual(p.state["status"], 5)
                if reference:
                    self.same_story(player, reference)


if __name__ == "__main__":
    unittest.main()

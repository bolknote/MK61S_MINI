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
import collections
import re
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from tools.apps.urq.qst2urq import make_package
from tools.apps.urq.adaptations import adapt
from tools.apps.urq.library import SOURCES, copy_device_library, copy_licenses
from tools.apps.urq.extra_games import locked_sources, prepare
from tools.apps.urq import extra_games

HOST = Path(sys.argv.pop(1)).resolve() if __name__ == "__main__" else ROOT / ".build/urq-tests/ryu/urq-host"
UPSTREAM = Path(os.environ["URQ_UPSTREAM"]).resolve() if os.environ.get("URQ_UPSTREAM") else None
LIBRARY = ROOT / "programs/urq"


def game_folder(key):
    return ROOT / 'tests/fixtures/urq' / key if key == 'house_that_jack_built' else LIBRARY / key

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
SEMION_ROUTES = {
    'semion_escape': ['introduction', 'beginning', 'koleso', 'beginning', 'poilka', 'tmilk',
        'poilka', 'beginning', 'action', 'beginning', 'koleso', 'krutit', 'bumajka', 'beginning',
        'kormilka', 'eat', 'kormilka', 'gvbum', 'kormilka', 'gvtake', 'beginning', 'escape', 'richag'],
    'semion_road': ['introduction', 'game', 'garb', 'gum', 'garb', 'lujja', 'woda', 'lujja', 'garb',
        'box', 'bum', 'box', 'garb', 'sliver', 'garb', 'box', 'tk', 'right', 'tk', 'bak', 'sem',
        'eat', 'bak', 'tk', 'box', 'bum', 'box', 'tk', 'bak', 'gl', 'bak', 'osm', 'gay', 'osm',
        'gaj', 'osm', 'bak', 'tk', 'box', 'bum', 'box', 'tk', 'bak', 'osm', 'alp', 'osm', 'bak',
        'kop', 'garb', 'box', 'tk', 'zabor', 'vrk', 'zabor', 'tk', 'box', 'bum', 'box', 'tk',
        'bak', 'gl', 'bak', 'tk', 'fh', 'tk', 'fd', 'tk', 'fgaj', 'tk', 'left', 'tk', 'left',
        'tk', 'zabor', 'house', 'zaj', 'house', 'purs', 'bak3', 'fin', 'road'],
    'semion_snow': ['introduction', 'look', 'house', 'sjestsem1', 'house', 'ihouse', 'k:13',
        'lfthouse', 'sjestsem2', 'lfthouse', 'house', 'rhthouse', 'sjestsem3', 'rhthouse', 'house',
        'ruch', 'pit', 'ruch', 'house', 'out', 'iout', 'k:13', 'tree', 'tleaf', 'tree', 'out',
        'kust', 'tship', 'zavship', 'kust', 'out', 'house', 'rhthouse', 'kopat', 'rhthouse',
        'kopat', 'rhthouse', 'ooop', 'rhthouse', 'house', 'out', 'tree', 'tleaf', 'tree', 'out',
        'house', 'rhthouse', 'stek2', 'rhthouse', 'house', 'lfthouse', 'mousehouse', 'atk',
        'mousehouse', 'sjestzer1', 'mousehouse', 'lfthouse', 'house', 'out', 'grass', 'srezat',
        'grass', 'out', 'house', 'splest', 'house', 'out', 'tree', 'ontree', 'branch', 'escape'],
}


class Player:
    def __init__(self, key, reference=False):
        self.temp = tempfile.TemporaryDirectory(prefix="urq-playthrough-")
        self.reference = reference
        environment = dict(os.environ)
        if reference:
            source = Path(self.temp.name) / "original.qst"
            if key in SEMION_ROUTES:
                source.write_text((SOURCES / key / 'original.qst').read_bytes().decode('cp1251'))
                mode = json.loads((SOURCES / key / 'manifest.json').read_text())['urq_mode']
                environment.pop('URQ_ORACLE_ADAPTATION', None)
            else:
                folder = UPSTREAM / "games" / key / "urqw"
                paths = sorted(folder.glob("*.qst"), key=lambda p: (not p.name.startswith("_"), p.name))
                source.write_text("\n".join(p.read_text(encoding="utf-8-sig") for p in paths))
                environment["URQ_ORACLE_ADAPTATION"] = key
                mode = 'urqw'
            command = ["node", str(ROOT / "tools/apps/urq/oracle.js"), str(UPSTREAM), str(source), mode, "-"]
        else:
            command = [str(HOST), str(game_folder(key)), "-"]
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
            self.step(target) if target.startswith(("i:", 'k:', 't:')) else self.choose(target)

    def text(self):
        return "\n".join(e["text"] for e in self.events if e["event"] == "text")

    def close(self):
        if getattr(self,"closed",False):return
        self.closed=True
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
        self.assertEqual(set(report["published"]), {"trapped_in_time_ru", "jim_from_outer_space_ru", *SEMION_ROUTES})
        for key in [*report["published"], 'house_that_jack_built']:
            with self.subTest(game=key):
                folder = game_folder(key)
                metadata = SOURCES / key
                source = (metadata / "source.qst").read_bytes()
                manifest = json.loads((metadata / "manifest.json").read_text())
                files, package = make_package(source, manifest.get('urq_mode', 'urqw'), "UTF-8", manifest)
                self.assertEqual(package, json.loads((metadata / "package.json").read_text()))
                for name, data in files.items():
                    self.assertEqual(data, (folder / name).read_bytes())
                    self.assertLessEqual(len(data), 61440)
                    if package.get('zx0_parser') == 'optimal' and name.endswith('.uqd'):
                        self.assertLessEqual(len(data), 15 * (4096 - 32))
                self.assertNotRegex(source.decode(), r"(?i)javascript|<script")
                self.assertEqual({p.name for p in folder.iterdir()}, {*files, "autoexec.wbmp"})
                self.assertTrue((metadata / "AUTHORS.txt").is_file())
                self.assertIn("MIT License" if key in SEMION_ROUTES else
                              "Attribution-NonCommercial-ShareAlike" if key=="jim_from_outer_space_ru" else "CC0",
                              (metadata / "LICENSE.txt").read_text())
                if key in SEMION_ROUTES:
                    lock, reviewed = locked_sources()
                    game, original, _ = next(row for row in reviewed if row[0]['id'] == key)
                    text, generated_manifest, _ = prepare(game, original, lock)
                    self.assertEqual(source, text.encode())
                    self.assertEqual(manifest, generated_manifest)
                elif UPSTREAM:
                    text, generated_manifest, _ = adapt(key, UPSTREAM / "games" / key)
                    self.assertEqual(source, text.encode())
                    self.assertEqual(manifest, generated_manifest)

    def test_device_library_contains_only_games_and_icons(self):
        self.assertEqual({p.name for p in LIBRARY.iterdir()},
                         {"README.markdown", "autoexec.wbmp", "trapped_in_time_ru", "jim_from_outer_space_ru", *SEMION_ROUTES})
        with tempfile.TemporaryDirectory(prefix="urq-distribution-") as directory:
            target = Path(directory)
            payload = copy_device_library(target / "URQ")
            licenses = copy_licenses(target / "licenses/urq")
            self.assertEqual(len(payload), 18)
            self.assertEqual(len(licenses), 10)
            self.assertFalse(any('house_that_jack_built' in str(path) for path in payload + licenses))
            self.assertTrue(all(p.suffix in {".urq", ".uqd", ".wbmp"} for p in payload))
            self.assertTrue(all(p.is_relative_to(target / "licenses") for p in licenses))

    def test_semion_complete_routes_original_oracle_and_midgame_saves(self):
        wins = {'semion_escape': 'выбираетесь из клетки', 'semion_road': 'прошли пятую серию',
                'semion_snow': 'прошли десятую серию'}
        for key, route in SEMION_ROUTES.items():
            with self.subTest(game=key):
                actual = self.player(key)
                reference = self.player(key, True) if UPSTREAM else None
                snapshot = Path(actual.temp.name) / 'middle.urs'
                for index, command in enumerate(route):
                    actual.route([command])
                    if reference:
                        reference.route([command])
                        self.assertEqual(actual.text(), reference.text(), (key, index, command))
                        self.assertEqual(actual.state['status'], reference.state['status'])
                        self.assertEqual(actual.state['items'], reference.state['items'])
                        choices = lambda p: [(a['command'], a['caption']) for a in p.state['actions']]
                        self.assertEqual(choices(actual), choices(reference))
                        for name, value in reference.state['vars'].items():
                            if name in ('current_loc', 'previous_loc') or name.startswith('count_'):
                                continue
                            self.assertEqual(actual.state['vars'].get(name, 0), value, (key, index, name))
                    if index == len(route) // 2:
                        actual.step('s:' + str(snapshot))
                self.assertIn(wins[key], actual.text().lower())
                final = actual.state
                actual.step('l:' + str(snapshot))
                actual.route(route[len(route) // 2 + 1:])
                self.assertEqual(actual.state, final)
                if reference:
                    reference.close()

    def test_supplementary_sources_require_exact_license_and_qst(self):
        lock, reviewed = locked_sources()
        with tempfile.TemporaryDirectory(prefix='urq-license-proof-') as directory:
            base = Path(directory)
            for game, source, license_text in reviewed:
                folder = base / game['id']
                folder.mkdir()
                (folder / 'original.qst').write_bytes(source)
                (folder / 'LICENSE.txt').write_bytes(license_text)
            first, source, license_text = reviewed[0]
            folder = base / first['id']
            with mock.patch.object(extra_games, 'SOURCES', base):
                self.assertEqual(len(locked_sources()[1]), 3)
                (folder / 'LICENSE.txt').write_bytes(b'No redistribution permission')
                with self.assertRaisesRegex(ValueError, 'license'):
                    locked_sources()
                (folder / 'LICENSE.txt').write_bytes(license_text)
                (folder / 'original.qst').write_bytes(source + b'\npln changed\n')
                with self.assertRaisesRegex(ValueError, 'QST'):
                    locked_sources()

    def test_jim_all_story_locations_endings_and_optional_notes(self):
        source=(SOURCES/"jim_from_outer_space_ru/source.qst").read_text()
        blocks={m[1]:m[2] for m in re.finditer(r"^:([^\n]+)\n([\s\S]*?)(?=^:|\Z)",source,re.M)}
        paths={"1":[]};todo=collections.deque(["1"])
        while todo:
            current=todo.popleft()
            for target in re.findall(r"^btn (\d+),",blocks[current],re.M):
                if target not in paths:
                    paths[target]=paths[current]+[target];todo.append(target)
        self.assertEqual(set(paths),{key for key in blocks if key.isdigit()})
        endings=notes=0
        for location,route in paths.items():
            with self.subTest(location=location):
                player=self.player("jim_from_outer_space_ru")
                player.route(["init"]+route)
                self.assertEqual(player.state["vars"]["current_loc"],location)
                if UPSTREAM:
                    reference=self.player("jim_from_outer_space_ru",True)
                    reference.route(["init"]+route)
                    plot=lambda p:[a["command"] for a in p.state["actions"]
                                   if not a["command"].startswith("proc mk_note_")]
                    self.assertEqual(plot(player),plot(reference))
                    for name in ("current_loc","previous_loc","return_loc",f"count_{location}"):
                        self.assertEqual(player.state["vars"].get(name),reference.state["vars"].get(name),name)
                    reference.close()
                if "proc final_loc" in blocks[location]:
                    endings+=1
                    self.assertIn("КОНЕЦ",player.text())
                    self.assertTrue(any("return_loc" not in a["command"] and a["command"].isdigit()
                                        for a in player.state["actions"]))
                for action in list(player.state["actions"]):
                    if not action["command"].startswith("proc mk_note_"):continue
                    notes+=1
                    before=dict(player.state["vars"])
                    choices=[a for a in player.state["actions"] if a!=action]
                    player.choose(action["command"])
                    self.assertEqual(player.state["vars"]["current_loc"],location)
                    self.assertEqual(player.state["vars"]["previous_loc"],before["previous_loc"])
                    self.assertEqual(player.state["vars"].get("return_loc"),before.get("return_loc"))
                    self.assertEqual(player.state["actions"],choices)
                    self.assertIn("Примечания переводчика",player.text())
                player.close()
        self.assertGreater(endings,20)
        self.assertEqual(notes,33) # one shared note procedure serves locations 73 and 74
        comment=self.player("jim_from_outer_space_ru");comment.choose("mk_about");comment.choose("comment")
        comment.choose(next(a["command"] for a in comment.state["actions"] if a["command"].startswith("proc mk_note_")))
        self.assertEqual(comment.state["vars"]["current_loc"],"comment")

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

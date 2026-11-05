#!/usr/bin/env python3
"""Play the shipped CC0 adaptations on Classic using USB matrix key events."""

import sys as _repo_sys
from pathlib import Path as _RepoPath
_repo_sys.path.insert(0, str(_RepoPath(__file__).resolve().parents[1]))
import argparse
import hashlib
import json
from pathlib import Path
import time

from hil_c6_system_bootstrap import write_file, read_file
from hil_portable_apps import ScreenPort
from hil_portable_system_apps import png
from hil_rtc_alarm import PROMPT
from hil_urq import OK, ESC, USER, DOWN, RIGHT, DIGITS, keys, taps, saved
import urq_library_self_test as library

ROOT = Path(__file__).resolve().parents[1]
UP = 27


def closed(p):
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        p.pump(.1)
        if PROMPT.search(p.text[p.open_text_start:]) or (p.packet and PROMPT.search(p.packet)):
            return
    raise TimeoutError("Game did not exit")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", required=True)
    parser.add_argument("--public-id", required=True)
    parser.add_argument("--host", type=Path, default=library.HOST)
    parser.add_argument("--apps-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--installed", action="store_true", help="Verify already uploaded packages without rewriting them")
    args = parser.parse_args()
    library.HOST = args.host.resolve()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    report = {"physical_key_test": False, "input_source": "USB Screen virtual matrix events", "games": {}}
    with ScreenPort(args.port) as p:
        identity = p.command("identity")
        assert "public=" + args.public_id.upper() in identity
        report["identity"] = identity
        # Use the already accepted APPs; exact read-back prevents a stale player.
        report["apps"] = {}
        for name in ("URQ.APP", "URQUI.APP"):
            data = (args.apps_dir / name).read_bytes()
            read_file(p, "/URQTEST/" + name, data)
            report["apps"][name] = hashlib.sha256(data).hexdigest()
        paths = {"house_that_jack_built": "/URQTEST/house", "trapped_in_time_ru": "/URQTEST/trapped"}
        def install(key, installed=False):
            path = paths[key]
            p.command("mkdir " + path)
            report["games"][key] = {}
            for file in sorted((ROOT / "programs/urq" / key).iterdir()):
                if file.suffix not in (".urq", ".uqd"):
                    continue
                print(("Verifying " if installed else "Uploading ") + key + "/" + file.name, flush=True)
                data = file.read_bytes()
                if not installed:
                    write_file(p, path + "/" + file.name, data)
                read_file(p, path + "/" + file.name, data)
                report["games"][key][file.name] = hashlib.sha256(data).hexdigest()
        install("house_that_jack_built", args.installed)
        # Calibrate the paging footer using a known long text with the same font.
        from tools.apps.urq.qst2urq import make_package
        p.command("mkdir /URQTEST/pages")
        files, _ = make_package((":s\npln " + "Строка " * 60 + "\nend").encode(), "urqw", "UTF-8")
        for name, data in files.items():
            write_file(p, "/URQTEST/pages/" + name, data)
        p.attach()
        p.open("/URQTEST/pages/game.urq")
        p.pump(1)
        # Compare only the last display page. The page above the footer can
        # contain live action glyphs while a buffered text page is arriving.
        paging_footer = p.frames[-1][-192:]
        png(p.frames[-1], args.output_dir / "paging.png")
        keys(p, [ESC, ESC])
        closed(p)

        def settle():
            p.pump(.15)
            for _ in range(200):
                if p.frames[-1][-192:] != paging_footer:
                    return
                p.key(OK)
                p.pump(.1)
            raise TimeoutError("Paging did not finish")

        def menu(p, item, slot=None):
            header = p.frames[-1][:384]
            previous = p.frames[-1]
            start = len(p.frames)
            p.key(USER)
            wait_frame(start, lambda frame: frame != previous)
            previous = p.frames[-1]
            start = len(p.frames)
            keys(p, [DOWN] * item + [OK])
            wait_frame(start, lambda frame: frame != previous)
            if slot is not None:
                start = len(p.frames)
                keys(p, [DOWN] * slot + [OK])
                wait_frame(start, lambda frame: frame[:384] == header)

        def wait_frame(after, predicate):
            deadline = time.monotonic() + 20
            while time.monotonic() < deadline:
                if len(p.frames) > after and predicate(p.frames[-1]):
                    return
                p.pump(.1)
            raise TimeoutError("Expected a new rendered screen")

        def wait_input(p, header):
            deadline = time.monotonic() + 12
            while time.monotonic() < deadline:
                if p.frames and p.frames[-1][:384] == header:
                    return
                p.pump(.1)
            raise TimeoutError("Input screen did not return")

        def choose(model, target):
            index = next(i for i, a in enumerate(model.state["actions"]) if a["command"] == target)
            if index < 10:
                before, previous = len(p.frames), p.frames[-1]
                p.key(DIGITS[(index + 1) % 10])
            else:
                keys(p, [UP] * 48 + [DOWN] * index)
                p.pump(.2)
                before, previous = len(p.frames), p.frames[-1]
                p.key(OK)
            wait_frame(before, lambda frame: frame != previous)
            model.choose(target)
            settle()

        def leave():
            menu(p, 5)
            p.key(OK)
            closed(p)

        def detach():
            p.send(0x13)
            p.attached = False
            p.pump(.2)
            p.packet = None

        def verify_core(key, wire, name):
            size = int.from_bytes(wire[40:44], "little")
            path = args.output_dir / (name + ".core.urs")
            path.write_bytes(wire[48:48 + size])
            host = library.Player(key)
            try:
                host.step("l:" + str(path.resolve()))
                return host.state
            finally:
                host.close()

        print("Playing House: RU input, save/restore and 17% score", flush=True)
        model = library.Player("house_that_jack_built")
        try:
            p.open(paths["house_that_jack_built"] + "/game.urq")
            settle()
            png(p.frames[-1], args.output_dir / "translations.png")
            for target in ("ru_v5_0", "ru_v5_1", "ru_v5_2", 'insert_var="лепёшк" & goto insert'):
                choose(model, target)
            for digits in ("4444", "33", "5555", "333", "8", "444"):
                taps(p, digits)
            p.key(RIGHT)
            p.pump(.2)
            png(p.frames[-1], args.output_dir / "input.png")
            header = p.frames[-1][:384]
            menu(p, 1, 0)
            png(p.frames[-1], args.output_dir / "after-save.png")
            wait_input(p, header)
            taps(p, "2")
            menu(p, 2, 0)
            wait_input(p, header)
            png(p.frames[-1], args.output_dir / "restored.png")
            p.key(OK)
            model.step("i:ЛЕПЁШК")
            settle()
            for target in ("ru_v5_3", "ru_v5_4", "ru_v5_5", "check"):
                choose(model, target)
            png(p.frames[-1], args.output_dir / "score.png")
            menu(p, 1, 1)
            p.pump(.3)
            leave()
        finally:
            model.close()
        detach()
        first, draft = saved(p, paths["house_that_jack_built"] + "/slot1.urs")
        assert draft == "ЛЕПЁШК", draft
        second, draft = saved(p, paths["house_that_jack_built"] + "/slot2.urs")
        assert not draft
        house = verify_core("house_that_jack_built", second, "house")
        assert house["vars"]["correct"] == 1 and house["vars"]["percentage"] == 17, house
        assert house["vars"]["лепёшк"] == "ЛЕПЁШК"
        report["house"] = {"draft": "ЛЕПЁШК", "correct": 1, "percentage": 17,
                           "arm_save_restored_on_host": True}
        (args.output_dir / "input.urs").write_bytes(first)
        (args.output_dir / "score.urs").write_bytes(second)

        # This 512 KiB board also carries earlier tests and System APPs.
        # Keep the two large packages out of the volume at the same time.
        for name in ("game.urq", "p0000.uqd"):
            p.command("rm " + paths["house_that_jack_built"] + "/" + name)
        install("trapped_in_time_ru")
        p.attach()
        print("Playing Trapped: initial shuffle and portable save", flush=True)
        model = library.Player("trapped_in_time_ru")
        try:
            p.open(paths["trapped_in_time_ru"] + "/game.urq")
            settle()
            choose(model, "init")
            png(p.frames[-1], args.output_dir / "trapped.png")
            expected = {f"token{i}": model.state["vars"][f"token{i}"] for i in range(1, 7)}
            menu(p, 1, 2)
            p.pump(.3)
            leave()
        finally:
            model.close()
        detach()
        wire, draft = saved(p, paths["trapped_in_time_ru"] + "/slot3.urs")
        assert not draft
        trapped = verify_core("trapped_in_time_ru", wire, "trapped")
        assert {key: trapped["vars"][key] for key in expected} == expected
        assert trapped["vars"]["queue_position"] == 1
        report["trapped"] = {"initial_queue": expected, "arm_save_restored_on_host": True}
        (args.output_dir / "trapped.urs").write_bytes(wire)
        # Leave the first, input-driven game ready to play after acceptance.
        for name in ("game.urq", "p0000.uqd"):
            p.command("rm " + paths["trapped_in_time_ru"] + "/" + name)
        install("house_that_jack_built")
        report["installation"] = "House left installed; packages tested sequentially on the occupied 512 KiB volume"
        report["health"] = {c: p.command(c, timeout=15) for c in ("df", "crash show")}
        assert "FIRMWARE CRC state=valid" in report["health"]["df"]
        assert "CRASH none" in report["health"]["crash show"]
    report["result"] = "PASS"
    (args.output_dir / "result.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print("Classic adapted URQ library PASS", flush=True)


if __name__ == "__main__":
    main()

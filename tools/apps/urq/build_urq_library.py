#!/usr/bin/env python3
"""Audit the pinned Russian UrqW catalog and publish licensed text packages."""

import sys as _repo_sys
from pathlib import Path as _RepoPath
_repo_sys.path.insert(0, str(_RepoPath(__file__).resolve().parents[3]))
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

from tools.apps.urq.qst2urq import decode_source, make_package
from tools.apps.urq.adaptations import adapt

ROOT = Path(__file__).resolve().parents[3]
LOCK = json.loads((ROOT / "tools/apps/urq/upstream.json").read_text())
PERMITTED = {"CC0-1.0", "CC-BY-4.0", "CC-BY-SA-4.0", "CC-BY-NC-SA-4.0", "MIT", "GPL-2.0-or-later"}


def revision(path):
    return subprocess.check_output(["git", "-C", str(path), "rev-parse", "HEAD"], text=True).strip()


def sources(folder):
    base = folder / "urqw"
    if not base.is_dir():
        base = folder
    manifest_path = base / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig")) if manifest_path.exists() else {}
    paths = sorted(base.glob("*.qst"), key=lambda p: (not p.name.startswith("_"), p.name))
    if not paths:
        raise ValueError("No QST source (encrypted or absent)")
    encoding = manifest.get("game_encoding", "CP1251")
    texts = [decode_source(path.read_bytes(), encoding) for path in paths]
    return manifest, paths, "\n".join(texts)


def license_for(paths):
    identifiers = []
    for path in paths:
        matches = re.findall(rb"SPDX-License-Identifier:\s*([A-Za-z0-9.+-]+)", path.read_bytes())
        if not matches:
            return None
        identifiers.extend(value.decode("ascii") for value in matches)
    return identifiers[0] if len(set(identifiers)) == 1 else None


def smoke(host, files):
    with tempfile.TemporaryDirectory(prefix="urq-catalog-") as temp:
        for name, data in files.items():
            (Path(temp) / name).write_bytes(data)
        process = subprocess.run([str(host), temp], capture_output=True, text=True, timeout=20)
        states = [json.loads(line) for line in process.stdout.splitlines()
                  if line.startswith('{"event":"state"')]
        if not states:
            raise ValueError("Startup produced no state: " + process.stderr[:200])
        state = states[-1]
        if process.returncode or state["error"] or state["status"] == 0:
            raise ValueError(f"Startup error {state['error']} at line {state['pc']} (status {state['status']})")
        return {"status": state["status"], "variables": len(state["vars"]), "actions": len(state["actions"])}


def build(upstream, host, output, audit_all=False, source_output=None, report_path=None):
    source_output = source_output or ROOT / "tools/apps/urq/sources"
    report_path = report_path or ROOT / "tools/apps/urq/catalog-report.json"
    if revision(upstream) != LOCK["commit"]:
        raise ValueError("UrqW revision differs from tools/apps/urq/upstream.json")
    catalog = json.loads((upstream / "games.json").read_text())
    records = []
    published = []
    output.mkdir(parents=True, exist_ok=True)
    shutil.copy2(ROOT / "doc/explorer-icons/games.wbmp", output / "autoexec.wbmp")
    for game in catalog:
        if "ru" not in game.get("lang", "").split(";"):
            continue
        key = game["folder"]
        folder = upstream / "games" / key
        record = {name: game.get(name, "") for name in ("title", "author", "lang")}
        record.update(id=key, revision=revision(folder), source=f"https://github.com/urqw/UrqW/tree/{LOCK['commit']}/games/{key}")
        reasons = []
        try:
            manifest, paths, text = sources(folder)
            license_id = license_for(paths)
            record["license"] = license_id
            record["mode"] = manifest.get("urq_mode", "urqw")
            record["source_files"] = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
            if license_id not in PERMITTED:
                reasons.append("no explicit redistributable license for every QST source")
            adaptation = adapt(key, folder) if license_id in PERMITTED else None
            if adaptation:
                text, manifest, details = adaptation
                record["adaptation"] = details
                record["title"] = manifest["urqw_title"]
                record["lang"] = manifest["urqw_game_lang"]
            normalized = re.sub(r"/\*[\s\S]*?\*/", "", text)
            if re.search(r"(?im)(?:^|&|\bthen\s|\belse\s)\s*javascript\b", normalized):
                reasons.append("JavaScript dependency; game logic is not removed")
            if not reasons or audit_all:
                files, package = make_package(text.encode("utf-8"), record["mode"], "UTF-8", manifest)
                record["package"] = package
                record["startup"] = smoke(host, files)
                if not reasons:
                    target = output / key
                    target.mkdir(exist_ok=True)
                    source_target = source_output / key
                    source_target.mkdir(parents=True, exist_ok=True)
                    for name, data in files.items():
                        (target / name).write_bytes(data)
                    shutil.copy2(ROOT / "doc/explorer-icons/games.wbmp", target / "autoexec.wbmp")
                    # Include the exact licensed sources: the conversion is inspectable and reproducible.
                    if adaptation:
                        (source_target / "source.qst").write_text(text, encoding="utf-8")
                        (source_target / "adaptation.json").write_text(json.dumps(details, ensure_ascii=False, indent=2) + "\n")
                    else:
                        for source in paths:
                            shutil.copy2(source, source_target / source.name)
                    for name in ("LICENSE.txt", "LICENSE", "LICENSE.md"):
                        if (folder / name).is_file():
                            shutil.copy2(folder / name, source_target / "LICENSE.txt")
                            break
                    (source_target / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
                    (source_target / "package.json").write_text(json.dumps(package, ensure_ascii=False, indent=2) + "\n")
                    credits = ("Никита Цейковец; переводы: Самуил Маршак, Геннадий Аминов, "
                               "Игорь Родин, Светлана Сергеева, Екатерина Зеленина" if key == "house_that_jack_built"
                               else "Симон Кристиансен; перевод и портирование: Никита Цейковец"
                               if key == "trapped_in_time_ru" else "Даниэль Родригес Риверо; перевод и портирование: Никита Цейковец"
                               if key == "jim_from_outer_space_ru" else record["author"])
                    origin = record.get("adaptation", {}).get("repository", record["source"])
                    (source_target / "AUTHORS.txt").write_text(f"{record['title']}\n{credits}\n{origin}\nRevision: {record['revision']}\nLicense: {license_id}\nText/M8 adaptation for MK61S and PicoCalc; media omitted.\n", encoding="utf-8")
                    published.append(key)
        except (ValueError, UnicodeError, OSError, subprocess.TimeoutExpired) as error:
            reasons.append(str(error))
        record["published"] = not reasons
        record["reasons"] = reasons
        records.append(record)
        print(key + ": " + ("published" if not reasons else "; ".join(reasons)), flush=True)
    report = {"upstream": LOCK, "profile": {"workspace_bytes": 8192, "line_bytes": 1023,
              "variables": 128, "items": 64, "actions": 48, "frames": 24, "string_pool_bytes": 2560},
              "verification": "Conversion and startup; complete adaptation walkthroughs are in tests/urq_library_self_test.py. Other paths are not certified.",
              "published": published, "games": records}
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--upstream", type=Path, required=True)
    parser.add_argument("--host", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=ROOT / "programs/urq")
    parser.add_argument("--sources-output", type=Path, default=ROOT / "tools/apps/urq/sources")
    parser.add_argument("--report", type=Path, default=ROOT / "tools/apps/urq/catalog-report.json")
    parser.add_argument("--audit-all", action="store_true", help="Also privately convert and start quests without redistribution permission")
    args = parser.parse_args()
    build(args.upstream.resolve(), args.host.resolve(), args.output.resolve(), args.audit_all,
          args.sources_output.resolve(), args.report.resolve())


if __name__ == "__main__":
    main()

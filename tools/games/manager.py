#!/usr/bin/env python3
"""Select, fetch and build third-party games without committing their binaries."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import subprocess
import sys
from urllib.request import Request, urlopen
import zipfile


ROOT = Path(__file__).resolve().parents[2]
CATALOG_PATH = Path(__file__).with_name("catalog.json")
DEFAULT_OUTPUT = ROOT / ".build/game-library"


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def load_catalog() -> dict:
    catalog = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    if catalog.get("format") != 1 or not isinstance(catalog.get("items"), list):
        raise ValueError("Unsupported games catalog format")
    ids = [item.get("id") for item in catalog["items"]]
    if any(not value or not isinstance(value, str) for value in ids) or len(ids) != len(set(ids)):
        raise ValueError("Games catalog contains an empty or duplicate id")
    return catalog


def safe_relative(name: str) -> Path:
    path = PurePosixPath(name)
    if path.is_absolute() or ".." in path.parts or not path.parts:
        raise ValueError("Unsafe catalog path: " + name)
    return Path(*path.parts)


def checked(data: bytes, expected: str, label: str, expected_bytes: int | None = None) -> bytes:
    if expected_bytes is not None and len(data) != expected_bytes:
        raise ValueError(f"Size mismatch for {label}: {len(data)} != {expected_bytes}")
    actual = digest(data)
    if actual != expected:
        raise ValueError(f"SHA-256 mismatch for {label}: {actual} != {expected}")
    return data


def fetch_archive(item: dict, cache_root: Path, *, dry_run: bool) -> Path:
    archive = cache_root / "archives" / item["archive_name"]
    if archive.is_file():
        checked(archive.read_bytes(), item["sha256"], str(archive))
        print("Verified cache: " + str(archive))
        return archive
    if dry_run:
        print("Would download: " + item["url"])
        return archive
    archive.parent.mkdir(parents=True, exist_ok=True)
    request = Request(item["url"], headers={"User-Agent": "MK61S-game-library/1"})
    with urlopen(request, timeout=90) as response:
        data = checked(response.read(), item["sha256"], item["title"])
    temporary = archive.with_suffix(archive.suffix + ".tmp")
    temporary.write_bytes(data)
    temporary.replace(archive)
    print("Downloaded: " + str(archive))
    return archive


def extract_zip(item: dict, output_root: Path, cache_root: Path, *, dry_run: bool) -> None:
    archive_path = fetch_archive(item, cache_root, dry_run=dry_run)
    if dry_run and not archive_path.is_file():
        for member in item["members"]:
            print("Would extract: " + member["target"])
        return
    manifest_files = {}
    with zipfile.ZipFile(archive_path) as archive:
        available = set(archive.namelist())
        for member in item["members"]:
            source = member["source"]
            if source not in available:
                raise ValueError("Missing archive member: " + source)
            data = checked(archive.read(source), member["sha256"], source, member["bytes"])
            relative = safe_relative(member["target"])
            target = output_root / relative
            if not dry_run:
                target.parent.mkdir(parents=True, exist_ok=True)
                temporary = target.with_name(target.name + ".tmp")
                temporary.write_bytes(data)
                temporary.replace(target)
            print("Prepared: " + str(target))
            manifest_files[relative.as_posix()] = {
                "bytes": len(data),
                "sha256": digest(data),
                "archive_member": source,
            }
    if dry_run:
        return
    manifest_dir = output_root / "manifests"
    manifest_dir.mkdir(parents=True, exist_ok=True)
    manifest = {
        "format": 1,
        "id": item["id"],
        "title": item["title"],
        "source_page": item.get("source_page"),
        "download_url": item["url"],
        "archive_sha256": item["sha256"],
        "rights": item.get("rights"),
        "files": manifest_files,
    }
    (manifest_dir / (item["id"] + ".json")).write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def run_command(arguments: list[str], output_root: Path, cache_root: Path, *, dry_run: bool) -> None:
    substitutions = {"{root}": str(ROOT), "{output}": str(output_root), "{cache}": str(cache_root)}
    expanded = []
    for argument in arguments:
        for placeholder, value in substitutions.items():
            argument = argument.replace(placeholder, value)
        expanded.append(argument)
    command = [sys.executable, *expanded]
    print("Command: " + subprocess.list2cmdline(command), flush=True)
    if not dry_run:
        subprocess.run(command, cwd=ROOT, check=True)


def execute(catalog: dict, selected_ids: list[str], output_root: Path, cache_root: Path,
            *, dry_run: bool) -> None:
    by_id = {item["id"]: item for item in catalog["items"]}
    unknown = [item_id for item_id in selected_ids if item_id not in by_id]
    if unknown:
        raise ValueError("Unknown catalog item(s): " + ", ".join(unknown))
    selected = set(selected_ids)
    if not selected:
        raise ValueError("Nothing selected")
    for item in catalog["items"]:
        if item["id"] not in selected:
            continue
        print("\n== " + item["title"] + " ==", flush=True)
        if item.get("rights"):
            print("Note: " + item["rights"], flush=True)
        runner = item["runner"]
        if runner == "download_zip":
            extract_zip(item, output_root, cache_root, dry_run=dry_run)
            if item.get("prepared_cache"):
                directory = output_root / safe_relative(item["prepared_cache"])
                if dry_run:
                    print("Would prepare: " + str(directory / "AWCACHE.BIN"))
                else:
                    from another_cache import prepare
                    count, size = prepare(directory)
                    print(f"Prepared sound cache: {count} sounds, {size} decoded bytes")
        elif runner == "spectrum_package":
            run_command([
                "tools/apps/spectrum/fetch_spectrum_games.py",
                "--archives-only",
                "--package", item["package"],
                "--cache", "{cache}/spectrum",
            ], output_root, cache_root, dry_run=dry_run)
        elif runner == "python":
            arguments = list(item["arguments"])
            required_games = item.get("with_games_when_selected", [])
            if required_games and all(game_id in selected for game_id in required_games):
                arguments.append("--with-games")
            run_command(arguments, output_root, cache_root, dry_run=dry_run)
        else:
            raise ValueError("Unsupported runner: " + str(runner))
    print("\nReady folder: " + str(output_root / "sd"), flush=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    list_parser = subparsers.add_parser("list", help="show catalog items")
    list_parser.add_argument("--json", action="store_true", help="machine-readable item list")
    list_parser.add_argument("--tsv", action="store_true", help="tab-separated item list")
    prepare_parser = subparsers.add_parser("prepare-another", help="prepare a sound cache from local DOS files")
    prepare_parser.add_argument("directory", type=Path)
    run_parser = subparsers.add_parser("run", help="download/build selected catalog items")
    run_parser.add_argument("--select", action="append", default=[], metavar="ID")
    run_parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT)
    run_parser.add_argument("--cache-root", type=Path)
    run_parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    try:
        catalog = load_catalog()
        if args.command == "list":
            if args.json:
                print(json.dumps(catalog["items"], ensure_ascii=False))
            elif args.tsv:
                for item in catalog["items"]:
                    fields = (item["id"], "1" if item.get("default") else "0",
                              item["title"], item.get("description", ""))
                    print("\t".join(str(value).replace("\t", " ").replace("\n", " ") for value in fields))
            else:
                for item in catalog["items"]:
                    marker = "*" if item.get("default") else " "
                    print(f"{marker} {item['id']}: {item['title']}")
            return 0
        if args.command == "prepare-another":
            from another_cache import prepare
            count, size = prepare(args.directory.resolve())
            print(f"Prepared sound cache: {count} sounds, {size} decoded bytes")
            return 0
        output_root = args.output_root.resolve()
        cache_root = (args.cache_root or output_root / "cache").resolve()
        execute(catalog, args.select, output_root, cache_root, dry_run=args.dry_run)
        return 0
    except (OSError, ValueError, zipfile.BadZipFile, subprocess.CalledProcessError) as error:
        print("games: " + str(error), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

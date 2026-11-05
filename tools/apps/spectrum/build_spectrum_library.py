#!/usr/bin/env python3
"""Prepare ready-to-copy Spectrum game media; keep build inputs off the SD."""

import sys as _repo_sys
from pathlib import Path as _RepoPath
_repo_sys.path.insert(0, str(_RepoPath(__file__).resolve().parents[3]))
import argparse
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import unicodedata
import zipfile

from tools.apps.spectrum.spectrum_media import fat_image

ROOT = Path(__file__).resolve().parents[3]
LIBRARY = ROOT / "third_party/spectrum-games"
READY_LIBRARY = ROOT / "programs/spectrum"


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def load_library():
    catalog = json.loads((LIBRARY / "catalog.json").read_text())
    members = {}
    for package in catalog["packages"]:
        archive_data = (LIBRARY / package["archive"]).read_bytes()
        if sha256(archive_data) != package["sha256"]:
            raise ValueError("Game archive checksum mismatch: " + package["archive"])
        expected = {e["member"]: e for e in catalog["entries"] if e["package"] == package["id"]}
        with zipfile.ZipFile(io.BytesIO(archive_data)) as archive:
            actual = [i.filename for i in archive.infolist() if not i.is_dir()]
            if len(actual) != len(expected) or set(actual) != set(expected):
                raise ValueError("Game archive member list mismatch: " + package["archive"])
            for name, entry in expected.items():
                path = PurePosixPath(name)
                if path.is_absolute() or ".." in path.parts:
                    raise ValueError("Invalid game archive path")
                data = archive.read(name)
                if len(data) != entry["bytes"] or sha256(data) != entry["sha256"]:
                    raise ValueError("Game file checksum mismatch: " + name)
                members[(package["id"], name)] = data
    for name, digest in catalog["support_files"].items():
        if sha256((LIBRARY / name).read_bytes()) != digest:
            raise ValueError("Game notice checksum mismatch: " + name)
    return catalog, members


def image_files(catalog, members):
    """Give original media readable, deterministic, collision-free 8.3 aliases."""
    aliases, used = {}, {}

    def alias(parent, name):
        key = (parent, name)
        if key in aliases:
            return aliases[key]
        base, dot, ext = name.rpartition(".")
        if not dot:
            base, ext = name, ""

        def clean(text):
            ascii_text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().upper()
            return "".join(c for c in ascii_text if c.isalnum() or c in "_-~")

        base, ext = clean(base) or "FILE", clean(ext)[:3]
        taken = used.setdefault(parent, set())
        stem, number = base[:8], 0
        while stem + ("." + ext if ext else "") in taken:
            number += 1
            suffix = "~" + str(number)
            stem = base[:8 - len(suffix)] + suffix
        result = stem + ("." + ext if ext else "")
        taken.add(result)
        aliases[key] = result
        return result

    files, index = {}, []
    directories = {p["id"]: p.get("image_directory", p["id"].upper()[:8]) for p in catalog["packages"]}
    for entry in catalog["entries"]:
        if entry["kind"] == "notice":
            continue
        name, package = entry["member"], entry["package"]
        if package == "ianna":
            parts = ["IANNA", *PurePosixPath(name).parts[1:]] if name.startswith("iannasd/") else ["IANNA", name]
        else:
            parts = [directories[package], *PurePosixPath(name).parts]
        path = []
        for part in parts:
            path.append(alias("/".join(path), part))
        target = "/".join(path)
        files[target] = members[(package, name)]
        index.append({"path": target, "package": package, "kind": entry["kind"],
                      "title": entry.get("title", name), "original": name, "sha256": entry["sha256"]})
    return files, index


def redistribution_notices(catalog, members):
    """Distribution paperwork stays outside apps/ and the device image."""
    prefix = "licenses/SPECTRUM-GAMES/"
    notices = {prefix + entry["package"] + "/" + entry["member"]:
               members[(entry["package"], entry["member"])]
               for entry in catalog["entries"] if entry["kind"] == "notice"}
    for name in ("ianna/LICENSE.txt", "ianna/CREDITS.txt", "ulaplus/CC-BY-NC-SA-3.0.txt",
                 "esxdos/README.TXT", "esxdos/ESX089.NFO"):
        notices[prefix + name] = (LIBRARY / name).read_bytes()
    return notices


def prepare(output, esxdos=None, *, report_dir=None):
    catalog, members = load_library()
    files, index = image_files(catalog, members)
    catalog_sha = sha256((LIBRARY / "catalog.json").read_bytes())
    if esxdos:
        data = Path(esxdos).read_bytes()
        if sha256(data) != catalog["esxdos"]["sha256"]:
            raise ValueError("Use the pinned, unmodified esxDOS 0.8.9 archive")
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            files.update({n: archive.read(n) for n in archive.namelist()
                          if not n.endswith("/") and n.startswith(("SYS/", "BIN/"))})
            for name in ("README.TXT", "ESX089.NFO"):
                if archive.read(name) != (LIBRARY / "esxdos" / name).read_bytes():
                    raise ValueError("esxDOS attribution does not match the original release")
        image = fat_image(files, size_mib=32)
    else:
        ready = json.loads((LIBRARY / "runtime.json").read_text())
        image = (READY_LIBRARY / "GAMES.img").read_bytes()
        if ready["source_catalog_sha256"] != catalog_sha or ready["image_sha256"] != sha256(image):
            raise ValueError("Ready game image is stale; rebuild programs/spectrum with --esxdos")
    output.mkdir(parents=True, exist_ok=True)
    # Remove only unchanged files owned by the previous library builder.
    legacy_manifest = output / "manifest.json"
    if legacy_manifest.is_file():
        legacy = json.loads(legacy_manifest.read_text())
        for name, expected in legacy.get("files", {}).items():
            path = PurePosixPath(name)
            if path.is_absolute() or ".." in path.parts:
                raise ValueError("Invalid legacy library path")
            target = output / name
            if name != "GAMES.img" and target.is_file() and sha256(target.read_bytes()) == expected:
                target.unlink()
        legacy_manifest.unlink()
        for directory in sorted((p for p in output.rglob("*") if p.is_dir()), key=lambda p: len(p.parts), reverse=True):
            if not any(directory.iterdir()):
                directory.rmdir()
    (output / "GAMES.img").write_bytes(image)
    report = {"format": 2, "hardware_verified": False, "image": "GAMES.img",
              "source_catalog_sha256": catalog_sha,
              "esxdos_sha256": catalog["esxdos"]["sha256"],
              "files": {"GAMES.img": sha256(image)},
              "redistribution_notices": {name: sha256(data) for name, data in
                                         redistribution_notices(catalog, members).items()}}
    if output.resolve() == READY_LIBRARY.resolve():
        (LIBRARY / "runtime.json").write_text(json.dumps({"source_catalog_sha256": catalog_sha,
            "image_sha256": sha256(image), "image_bytes": len(image)}, indent=2) + "\n")
    if report_dir:
        if report_dir.resolve().is_relative_to(output.resolve()):
            raise ValueError("Build reports must be outside the device folder")
        report_dir.mkdir(parents=True, exist_ok=True)
        (report_dir / "manifest.json").write_text(json.dumps(report, indent=2) + "\n")
        (report_dir / "image-index.json").write_text(json.dumps(index, ensure_ascii=False, indent=2) + "\n")
    return ["GAMES.img"]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=READY_LIBRARY)
    parser.add_argument("--esxdos", type=Path, help="pinned esxdos089.zip; rebuild the ready image from source packages")
    parser.add_argument("--report-dir", type=Path, default=ROOT / ".build/spectrum-library",
                        help="host-only manifests and index; never copied to the SD folder")
    parser.add_argument("--zip", type=Path, help="write a games-only SD add-on, with every required notice")
    args = parser.parse_args()
    names = prepare(args.output_dir, args.esxdos, report_dir=args.report_dir)
    if args.zip:
        args.zip.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(args.zip, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
            payload = {"apps/SPECTRUM/games/" + name: (args.output_dir / name).read_bytes() for name in names}
            catalog, members = load_library()
            payload.update(redistribution_notices(catalog, members))
            for name, data in sorted(payload.items()):
                info = zipfile.ZipInfo(name, (1980, 1, 1, 0, 0, 0))
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = 0o100644 << 16
                archive.writestr(info, data)
        print("Games SD add-on: " + str(args.zip))
    print("Spectrum game library: " + str(args.output_dir))


if __name__ == "__main__":
    main()

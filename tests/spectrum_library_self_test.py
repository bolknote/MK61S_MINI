#!/usr/bin/env python3
"""Audit packaged games and independently read every file from the FAT16 image."""
import argparse
import hashlib
import io
import json
from pathlib import Path
import struct
import zipfile

ROOT = Path(__file__).resolve().parents[1]
SOURCES = ROOT / "third_party/spectrum-games"


def digest(data):
    return hashlib.sha256(data).hexdigest()


def read_fat16(image):
    assert image[510:512] == b"\x55\xAA"
    assert image[450] == 6  # FAT16 MBR partition
    start, sectors = struct.unpack_from("<II", image, 454)
    volume = memoryview(image)[start * 512:(start + sectors) * 512]
    sector_bytes, cluster_sectors = struct.unpack_from("<HB", volume, 11)
    reserved = struct.unpack_from("<H", volume, 14)[0]
    copies = volume[16]
    root_entries, total_sectors = struct.unpack_from("<HH", volume, 17)
    fat_sectors = struct.unpack_from("<H", volume, 22)[0]
    assert sector_bytes == 512 and total_sectors == sectors
    fat = volume[reserved * 512:(reserved + fat_sectors) * 512]
    for copy in range(1, copies):
        at = (reserved + copy * fat_sectors) * 512
        assert volume[at:at + len(fat)] == fat
    root_start = (reserved + copies * fat_sectors) * 512
    data_start = root_start + root_entries * 32
    cluster_bytes = cluster_sectors * sector_bytes
    count = (len(volume) - data_start) // cluster_bytes
    assert 4085 <= count < 65525 and (count + 2) * 2 <= len(fat)
    seen = set()

    def chain(cluster):
        parts = []
        while cluster < 0xFFF8:
            assert 2 <= cluster < count + 2 and cluster not in seen
            seen.add(cluster)
            at = data_start + (cluster - 2) * cluster_bytes
            parts.append(bytes(volume[at:at + cluster_bytes]))
            cluster = struct.unpack_from("<H", fat, cluster * 2)[0]
        return b"".join(parts)

    files = {}

    def directory(data, prefix=""):
        for at in range(0, len(data), 32):
            entry = data[at:at + 32]
            if entry[0] == 0:
                break
            if entry[0] == 0xE5 or entry[11] & 8:
                continue
            base, ext = entry[:8].decode("ascii").rstrip(), entry[8:11].decode("ascii").rstrip()
            if base in (".", ".."):
                continue
            name = prefix + base + ("." + ext if ext else "")
            contents = chain(struct.unpack_from("<H", entry, 26)[0])
            if entry[11] & 16:
                directory(contents, name + "/")
            else:
                size = struct.unpack_from("<I", entry, 28)[0]
                assert size <= len(contents) and name not in files
                files[name] = contents[:size]

    directory(bytes(volume[root_start:data_start]))
    return files


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--folder", type=Path, required=True)
    parser.add_argument("--report-dir", type=Path, default=ROOT / ".build/spectrum-library")
    parser.add_argument("--zip", type=Path)
    args = parser.parse_args()
    folder = args.folder
    manifest = json.loads((args.report_dir / "manifest.json").read_text())
    catalog = json.loads((SOURCES / "catalog.json").read_text())
    assert manifest["source_catalog_sha256"] == digest((SOURCES / "catalog.json").read_bytes())
    assert {str(p.relative_to(folder)) for p in folder.rglob("*") if p.is_file()} == {"GAMES.img"}
    for name, expected in manifest["files"].items():
        assert digest((folder / name).read_bytes()) == expected, name
    for name, expected in catalog["support_files"].items():
        assert digest((SOURCES / name).read_bytes()) == expected, name
    assert {p["id"] for p in catalog["packages"]} == {"ianna", "ulaplus", "cosmic-payback"}
    expected = {}
    for package in catalog["packages"]:
        data = (SOURCES / package["archive"]).read_bytes()
        assert digest(data) == package["sha256"]
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            assert archive.testzip() is None
            for entry in [e for e in catalog["entries"] if e["package"] == package["id"]]:
                data = archive.read(entry["member"])
                assert digest(data) == entry["sha256"] and len(data) == entry["bytes"]
                if entry["kind"] != "notice":
                    expected[(package["id"], entry["member"])] = data
            assert not any(Path(n).suffix.lower() in (".exe", ".msi", ".linux") for n in archive.namelist())
            if package["id"] == "ulaplus":
                games = [n for n in archive.namelist() if n.startswith("games/") and n.endswith(".tap")]
                assert len(games) == 337
                for name in games:
                    parent = name.rsplit("/", 1)[0]
                    assert any(n.lower() == (parent + "/legal.txt").lower() for n in archive.namelist()), name
                assert archive.read("VORTEX.TXT") == archive.read("games/Vortex/legal.txt")
    index = json.loads((args.report_dir / "image-index.json").read_text())
    assert len(index) == len(expected) == len({e["path"] for e in index})
    if manifest["image"]:
        image = (folder / manifest["image"]).read_bytes()
        assert len(image) == 32 * 1024 * 1024
        actual = read_fat16(image)
        assert set(actual) == {entry["path"] for entry in index} | set(catalog["esxdos"]["files"])
        for name, expected_sha in catalog["esxdos"]["files"].items():
            assert digest(actual[name]) == expected_sha, name
        for entry in index:
            assert actual[entry["path"]] == expected[(entry["package"], entry["original"])], entry["path"]
        assert actual["IANNA/LOADER"].startswith(b"PLUS3DOS")
        assert digest(actual["COSMIC/COSMIC.TAP"]) == "e64d1f206f771f2576c28763893b1959a79f5d3ddcb2d70ada57fa9239ba5e8a"
        assert not any(Path(name).suffix.lower() in (".txt", ".nfo", ".md", ".json", ".zip", ".tsv") for name in actual)
        for required in ("SYS/ESXDOS.SYS", "SYS/NMI.SYS", "BIN/TAPEIN"):
            assert required in actual, required
        print(f"FAT16 round-trip: {len(actual)} runtime files, {len(index)} game/media files byte-identical")
    if args.zip:
        with zipfile.ZipFile(args.zip) as archive:
            assert archive.testzip() is None
            prefix = "Games/Spectrum Collection/"
            assert set(archive.namelist()) == {prefix + name for name in manifest["files"]} | {
                prefix + "Play.txt",
            } | set(manifest["redistribution_notices"])
            assert archive.read(prefix + "Play.txt") == b"GAMES.img\n"
            for name in manifest["files"]:
                assert archive.read(prefix + name) == (folder / name).read_bytes()
            for name, expected in manifest["redistribution_notices"].items():
                assert digest(archive.read(name)) == expected, name
            assert archive.read("licenses/SPECTRUM-GAMES/ianna/LICENSE.txt") == (SOURCES / "ianna/LICENSE.txt").read_bytes()
            assert b"This program is freeware, please redistribute!" in archive.read("licenses/SPECTRUM-GAMES/cosmic-payback/LICENSE.TXT")
    print("Spectrum library integrity and redistribution notices: OK")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Fetch pinned original disk-interface firmware and prepare virtual media."""

import sys as _repo_sys
from pathlib import Path as _RepoPath
_repo_sys.path.insert(0, str(_RepoPath(__file__).resolve().parents[3]))
import argparse
import hashlib
import json
from pathlib import Path
from urllib.request import urlopen
import zipfile
from tools.apps.spectrum.spectrum_media import blank_trd, esxdos_image

SOURCES = {
    "trdos.rom": {
        "url": "https://raw.githubusercontent.com/programandala-net/tr-dos/3f58896baf4cba5a9dc54117ea5a1d64d567c213/trdos.rom",
        "sha256": "9ee624153f6ff198267fa57dd7568933a36e2003fbe9dd17799b6d21652a37bb",
        "copyright": "TR-DOS 5.03, (c) 1986 Technology Research Ltd.",
    },
    "esxdos089.zip": {
        "url": "https://zxgit.org/dj-apendix/Div_MMC/raw/commit/587cec36f4da2a51a2fd6fd8d7358c3851f660c9/File_Soft/esxdos089.zip",
        "sha256": "d455888361cd13d455e362a4c841452b6f4568d30f9069443044affdd40de9a4",
        "copyright": "esxDOS 0.8.9, (c) 2005-2021 Papaya Dezign. https://esxdos.org/",
    },
}
ESXMMC_SHA = "89706de560d66432fe19ddb895e7cde49e252e932687dcb57fb92259a0259339"


def prepare(output):
    output.mkdir(parents=True, exist_ok=True)
    for name, source in SOURCES.items():
        path = output / name
        data = path.read_bytes() if path.exists() else b""
        if hashlib.sha256(data).hexdigest() != source["sha256"]:
            with urlopen(source["url"], timeout=45) as response:
                data = response.read()
            if hashlib.sha256(data).hexdigest() != source["sha256"]:
                raise ValueError("Firmware checksum mismatch: " + name)
            path.write_bytes(data)
    with zipfile.ZipFile(output / "esxdos089.zip") as archive:
        rom = archive.read("ESXMMC.BIN")
        if hashlib.sha256(rom).hexdigest() != ESXMMC_SHA:
            raise ValueError("ESXMMC firmware checksum mismatch")
        (output / "esxmmc.rom").write_bytes(rom)
        licenses = output / "licenses"
        licenses.mkdir(exist_ok=True)
        for name in ("README.TXT", "ESX089.NFO"):
            (licenses / ("esxDOS-" + name)).write_bytes(archive.read(name))
    (output / "ESXDOS.img").write_bytes(esxdos_image(output / "esxdos089.zip"))
    (output / "BLANK.trd").write_bytes(blank_trd())
    (output / "devices.json").write_text(json.dumps(SOURCES, indent=2) + "\n")
    (licenses / "devices-copyright.txt").write_text(
        "Original device firmware; it is not covered by this project's MIT licenses.\n" +
        "\n".join(source["copyright"] for source in SOURCES.values()) + "\n" +
        "esxDOS is an unmodified 0.8.9 release; SYS/BIN files are inside ESXDOS.img.\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    prepare(parser.parse_args().output)

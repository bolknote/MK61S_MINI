#!/usr/bin/env python3
"""Ship complete font notices with firmware bundles and standalone releases."""

import argparse
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parents[2]
SOURCES = ROOT / "tools/.fmk-font"
FILES = {
    "licenses/ui-fonts/LICENSE-Ark-Pixel.txt": "ui-atlases/LICENSE-Ark-Pixel.txt",
    "licenses/ui-fonts/LICENSE-DejaVu.txt": "external-fonts/LICENSE-DejaVu.txt",
    "licenses/ui-fonts/FONT-SOURCES.md": "ui-atlases/README.md",
}


def package(bundle=None, archive=None):
    payloads = {name: (SOURCES / source).read_bytes() for name, source in FILES.items()}
    if bundle is not None:
        for name, data in payloads.items():
            target = bundle / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
    if archive is not None:
        archive.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as output:
            for name, data in payloads.items():
                entry = zipfile.ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))
                entry.compress_type = zipfile.ZIP_DEFLATED
                entry.external_attr = 0o100644 << 16
                output.writestr(entry, data)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path, help="add notices inside this firmware directory")
    parser.add_argument("--archive", type=Path, help="write a standalone notices ZIP beside raw BINs")
    args = parser.parse_args()
    if args.bundle is None and args.archive is None:
        parser.error("at least one output is required")
    package(args.bundle, args.archive)


if __name__ == "__main__":
    main()

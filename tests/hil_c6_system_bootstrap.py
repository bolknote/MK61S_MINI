#!/usr/bin/env python3
"""Install and byte-verify an ABI 6 System bundle over the CDC terminal.

This is the bootstrap path for a freshly formatted C6 volume whose firmware
uses external USBDISK.APP. A firmware with resident USB disk passes
``--resident-usbdisk``. The target is pinned by its canonical public identity.
Existing files are never removed; replacement must be requested explicitly.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from m8_codec import encode as encode_m8

from hil_multi_device_identity import parse_identity, require_unchanged
from hil_rtc_alarm import Port
from hil_usb_disk_transaction import (
    listing_entries,
    posix_cksum,
    require_file_contents,
)


CANONICAL_FILES = (
    "HELP0.TXT",
    "HELP1.TXT",
    "FOCAL.APP",
    "BASIC.APP",
    "MARKDOWN.APP",
)
OPTIONAL_FILES = ("SETUP.APP",)  # resident on F411, external on F401
CHUNK_SIZE = 48


def bundle_payload(bundle: Path, name: str) -> bytes:
    payload = (bundle / name).read_bytes()
    if name in ("HELP0.TXT", "HELP1.TXT"):
        # Bundle text is UTF-8 for USB MSC; fsput bypasses USB conversion.
        return encode_m8(payload.decode("utf-8"))
    return payload


def write_file(port: Port, remote_path: str, payload: bytes) -> None:
    checksum = posix_cksum(payload)
    report = port.command(
        f'fsput begin "{remote_path}" {len(payload)} {checksum}', timeout=10
    )
    if f"@MKC:READY {len(payload)}" not in report:
        raise AssertionError(f"upload did not start for {remote_path}:\n{report}")
    try:
        for offset in range(0, len(payload), CHUNK_SIZE):
            chunk = payload[offset:offset + CHUNK_SIZE]
            report = port.command(
                f"fsput data {offset} {chunk.hex().upper()}", timeout=10
            )
            expected = offset + len(chunk)
            if f"@MKC:ACK {expected}" not in report:
                raise AssertionError(
                    f"wrong upload offset for {remote_path}:\n{report}"
                )
        report = port.command("fsput end", timeout=45)
        marker = f"@MKC:DONE {len(payload)} {checksum}"
        if marker not in report:
            raise AssertionError(f"upload did not commit for {remote_path}:\n{report}")
    except BaseException:
        port.command("fsput cancel", timeout=5)
        raise


def read_file(port: Port, remote_path: str, expected: bytes) -> None:
    report = port.command(f'fsget "{remote_path}"', timeout=45)
    require_file_contents(report, expected)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", required=True)
    parser.add_argument("--public-id", required=True)
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--replace", action="store_true")
    parser.add_argument("--resident-usbdisk", action="store_true",
                        help="accept a bundle whose USB disk is resident")
    args = parser.parse_args()

    expected_id = args.public_id.upper()
    if not re.fullmatch(r"[0-9A-F]{16}", expected_id):
        parser.error("--public-id must contain exactly 16 hexadecimal digits")
    required = (() if args.resident_usbdisk else ("USBDISK.APP",)) + \
        CANONICAL_FILES
    missing = [name for name in required
               if not (args.bundle / name).is_file()]
    if missing:
        parser.error(f"bundle is missing: {', '.join(missing)}")
    files = required + tuple(
        name for name in OPTIONAL_FILES if (args.bundle / name).is_file()
    )

    with Port(args.port) as port:
        identity = parse_identity(port.command("identity"))
        if identity.public != expected_id:
            raise AssertionError(
                f"wrong board: expected {expected_id}, got {identity.public}"
            )
        report = port.command("df", timeout=15)
        if "Flash:" not in report or "C5:" in report or "C6:" in report:
            raise AssertionError(f"writable C6 is not mounted:\n{report}")

        root = listing_entries(port.command("ls /", timeout=10))
        if not any(line.split("\t")[-1].rstrip("/").casefold() == "system"
                   and line.startswith("d\t") for line in root):
            port.command('mkdir "/System"', timeout=15)
            root = listing_entries(port.command("ls /", timeout=10))
            if not any(line.split("\t")[-1].rstrip("/").casefold() == "system"
                       and line.startswith("d\t") for line in root):
                raise AssertionError("/System was not created")

        existing = {
            line.split("\t")[-1].casefold()
            for line in listing_entries(port.command("ls /System", timeout=10))
            if line.startswith("f\t")
        }
        conflicts = [name for name in files
                     if name.casefold() in existing]
        if conflicts and not args.replace:
            raise AssertionError(
                "refusing to replace existing files without --replace: "
                + ", ".join(conflicts)
            )

        for name in files:
            payload = bundle_payload(args.bundle, name)
            target = f"/System/{name}"
            print(f"upload {name}: {len(payload)} bytes", flush=True)
            write_file(port, target, payload)
            read_file(port, target, payload)
            print(f"verified {name}", flush=True)

        require_unchanged(identity, parse_identity(port.command("identity")))
        listing = port.command("ls /System", timeout=15)
        for name in files:
            if name.casefold() not in listing.casefold():
                raise AssertionError(f"installed file missing from listing: {name}")
        print("C6 System bootstrap PASS", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

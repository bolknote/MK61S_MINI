#!/usr/bin/env python3
"""Install programs/ on an empty C6 through verified, atomic CDC file writes.

This does not format the device or touch /System.  It refuses a nonempty user
root, checks the board's public ID, converts text to M8, and reads every file
back from C6.  The .markdown sources are intentionally not installed.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import re
import sys

from hil_c6_system_bootstrap import read_file, write_file
from hil_multi_device_identity import parse_identity, require_unchanged
from hil_rtc_alarm import Port
from hil_usb_disk_transaction import listing_entries

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from m8_codec import encode as encode_m8  # noqa: E402


ROOT_DIRECTORIES = ("games", "library", "examples", "app", "CHIP8", "Fonts")
TEXT_SUFFIXES = {".m61", ".foc", ".tbi", ".txt", ".md"}
MAXIMUM_BYTES = {
    ".m61": 1536,
    ".foc": 1536,
    ".tbi": 3584,
    ".txt": 1536,
    ".md": 1536,
    ".fmk": 8192,
    ".wbmp": 1600,
    ".ch8": 3584,
    ".app": 20544,
}


def payload_for(path: Path) -> bytes:
    suffix = path.suffix.casefold()
    if suffix not in MAXIMUM_BYTES:
        raise ValueError(f"unsupported file in programs/: {path}")
    raw = path.read_bytes()
    payload = (encode_m8(raw.decode("utf-8-sig"))
               if suffix in TEXT_SUFFIXES else raw)
    if len(payload) > MAXIMUM_BYTES[suffix]:
        raise ValueError(f"C6 file too long ({len(payload)} bytes): {path}")
    if suffix == ".app" and (
        len(payload) < 16 or payload[:8] != b"MK61APP\0"
        or int.from_bytes(payload[12:14], "little") != 6
    ):
        raise ValueError(f"APP is not ABI 6: {path}")
    return payload


def plan(source: Path) -> tuple[list[str], list[tuple[str, bytes]]]:
    directories: list[str] = []
    files: list[tuple[str, bytes]] = []
    for root in ROOT_DIRECTORIES:
        local_root = source / root
        if not local_root.is_dir():
            raise ValueError(f"missing programs/ directory: {local_root}")
        directories.append("/" + root)
        for path in sorted(local_root.rglob("*")):
            if path.is_symlink():
                raise ValueError(f"symlink cannot be installed: {path}")
            remote = "/" + path.relative_to(source).as_posix()
            if path.is_dir():
                directories.append(remote)
            elif path.is_file() and path.suffix.casefold() != ".markdown":
                files.append((remote, payload_for(path)))
    directories.sort(key=lambda name: (name.count("/"), name.casefold()))
    return directories, files


def directory_present(port: Port, remote: str) -> bool:
    parent, basename = remote.rsplit("/", 1)
    parent = parent or "/"
    return any(
        item.startswith("d\t")
        and item.split("\t")[-1].rstrip("/").casefold() == basename.casefold()
        for item in listing_entries(port.command(f'ls "{parent}"', timeout=15))
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", required=True)
    parser.add_argument("--public-id", required=True)
    parser.add_argument("--source", type=Path, default=Path("programs"))
    args = parser.parse_args()
    expected_id = args.public_id.upper()
    if not re.fullmatch(r"[0-9A-F]{16}", expected_id):
        parser.error("--public-id must contain 16 hexadecimal digits")
    directories, files = plan(args.source)
    print(f"preflight: {len(directories)} directories, "
          f"{len(files)} files, {sum(len(data) for _, data in files)} C6 bytes",
          flush=True)

    with Port(args.port) as port:
        identity = parse_identity(port.command("identity"))
        if identity.public != expected_id:
            raise AssertionError(f"wrong board: {identity.public}")
        df = port.command("df", timeout=15)
        if "Flash: " not in df or "192 total" not in df:
            raise AssertionError(f"unexpected C6 geometry:\n{df}")
        root = listing_entries(port.command("ls /", timeout=15))
        if len(root) != 1 or root[0].casefold() != "d\tsystem/":
            raise AssertionError(f"refusing nonempty user root: {root}")

        for remote in directories:
            report = port.command(f'mkdir "{remote}"', timeout=15)
            if not directory_present(port, remote):
                raise AssertionError(f"mkdir failed: {remote}\n{report}")
            print(f"directory {remote}", flush=True)
        for index, (remote, payload) in enumerate(files, 1):
            write_file(port, remote, payload)
            read_file(port, remote, payload)
            print(f"file {index}/{len(files)} {remote}: {len(payload)} bytes verified",
                  flush=True)

        require_unchanged(identity, parse_identity(port.command("identity")))
        final = port.command("df", timeout=15)
        print(final, flush=True)
        expected_files = len(files) + 7
        expected_directories = len(directories) + 1
        marker = f"Visible: {expected_files} files, {expected_directories} directories, "
        if marker not in final:
            raise AssertionError("C6 visible count mismatch")
    print("C6 programs deployment PASS", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

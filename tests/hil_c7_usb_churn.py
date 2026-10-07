#!/usr/bin/env python3
"""C7 hardware stress: repeated host create/replace/rename/delete and eject.

macOS only. Uses the transaction HIL's identity, USB topology and removable
disk guards. Only a new uniquely named fixture is changed. Any failed run
retains its fixture for diagnosis, but attempts to eject the selected disk.
"""

from __future__ import annotations

import argparse
import fcntl
import json
import os
from pathlib import Path
import random
import re
import subprocess
import time

from hil_multi_device_identity import Target, parse_identity, reset_cycle
from hil_rtc_alarm import Port
from hil_usb_disk_transaction import (
    USB_DISK_PROFILES, console_locked, ensure_mounted, enter_usb_disk,
    find_cdc_location, listing_entries, parse_vfat_diagnostic, reconnect,
    require_file_contents, run_text, system_root, terminal_report, usb_tree,
    wait_for_msc_disk, whole_disks,
)


def uncached_contents(path: Path, expected: bytes) -> None:
    with path.open("rb") as stream:
        fcntl.fcntl(stream.fileno(), 48, 1)  # macOS F_NOCACHE
        actual = stream.read()
    if actual != expected:
        raise AssertionError(f"uncached host readback failed: {path}")


def store(path: Path, payload: bytes, *, replace: bool = False) -> None:
    with path.open("wb" if replace else "xb") as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())
    uncached_contents(path, payload)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", required=True)
    parser.add_argument("--public-id", required=True)
    parser.add_argument("--cycles", type=int, default=3)
    parser.add_argument("--seed", type=int, default=0xC701)
    args = parser.parse_args()
    if not re.fullmatch(r"[0-9a-fA-F]{16}", args.public_id) or not 1 <= args.cycles <= 20:
        parser.error("pin a 16-digit public ID; --cycles must be 1..20")
    with Port(args.port) as port:
        identity = parse_identity(port.command("identity"))
        original = listing_entries(port.command("ls /", timeout=15))
    if identity.public != args.public_id.upper() or identity.profile not in USB_DISK_PROFILES:
        raise AssertionError(f"wrong board/profile: {identity}")
    if console_locked(system_root()):
        raise AssertionError("unlock the Mac for USB-disk HIL")
    target = Target(args.port, identity)
    name = f"C7USB-{identity.short}"
    if any(row.split("\t")[-1].rstrip("/").casefold() == name.casefold() for row in original):
        raise AssertionError(f"fixture already exists: /{name}")
    location = find_cdc_location(usb_tree(), identity)
    rng = random.Random(args.seed)
    stats = dict(sessions=0, writes=0, renames=0, deletes=0, sidecars=0,
                 cdc_readbacks=0, host_readbacks=0, resets=0)
    started = time.monotonic()
    disk = ""

    def payload(binary: bool) -> bytes:
        return bytes(rng.randrange(256) if binary else rng.randrange(32, 127)
                     for _ in range(4096 if binary else 1500))

    try:
        for cycle in range(args.cycles):
            expected: dict[str, bytes] = {}
            for phase in ("create", "replace-rename", "delete"):
                phase_started = time.monotonic()
                if console_locked(system_root()):
                    raise AssertionError("Mac locked before USB reconnect; unlock it and repeat the HIL")
                baseline = whole_disks()
                enter_usb_disk(target)
                disk, info = wait_for_msc_disk(location, identity.usb, baseline, 30)
                mount = ensure_mounted(disk, info)
                mounted_at = time.monotonic()
                fixture = mount / name
                if phase == "create":
                    fixture.mkdir()
                    for index in range(16):
                        leaf = f"F{index:02d}." + ("bin" if index % 4 == 0 else "txt")
                        content = payload(leaf.endswith(".bin"))
                        store(fixture / leaf, content)
                        expected[leaf] = content
                        stats["writes"] += 1
                        stats["host_readbacks"] += 1
                        if (index + 1) % 4 == 0:
                            print(f"USB cycle={cycle + 1} create={index + 1}/16", flush=True)
                    # The host allocates space, but AppleDouble must not
                    # become persistent user files or consume inode quota.
                    for index in range(8):
                        leaf = list(expected)[index]
                        sidecar = fixture / ("._" + leaf)
                        # macOS can already have generated a genuine one
                        # for this fixture. Keep it; synthesize only if absent.
                        if sidecar.exists():
                            if not sidecar.is_file():
                                raise AssertionError(f"unexpected sidecar: {sidecar}")
                        else:
                            with sidecar.open("xb") as stream:
                                stream.write(b"APPLEDOUBLE C7 HIL".ljust(512, b"!"))
                                stream.flush()
                                os.fsync(stream.fileno())
                        stats["sidecars"] += 1
                else:
                    actual = {p.name for p in fixture.iterdir() if not p.name.startswith("._")}
                    if actual != set(expected):
                        raise AssertionError(f"exported directory mismatch: {actual}, expected {set(expected)}")
                    for leaf, content in expected.items():
                        uncached_contents(fixture / leaf, content)
                        stats["host_readbacks"] += 1
                    if phase == "replace-rename":
                        for index, leaf in enumerate(list(expected)):
                            if index % 2 == 0:
                                (fixture / leaf).unlink()
                                del expected[leaf]
                                stats["deletes"] += 1
                            else:
                                content = payload(leaf.endswith(".bin"))
                                store(fixture / leaf, content, replace=True)
                                renamed = "R" + leaf[1:]
                                (fixture / leaf).rename(fixture / renamed)
                                del expected[leaf]
                                expected[renamed] = content
                                stats["writes"] += 1
                                stats["host_readbacks"] += 1
                                stats["renames"] += 1
                        for index in range(8):
                            leaf = f"NEW{index:02d}.txt"
                            content = payload(False)
                            store(fixture / leaf, content)
                            expected[leaf] = content
                            stats["writes"] += 1
                            stats["host_readbacks"] += 1
                    else:
                        for leaf in list(expected):
                            (fixture / leaf).unlink()
                            del expected[leaf]
                            stats["deletes"] += 1
                        # Only sidecars within our own new fixture may remain.
                        for sidecar in fixture.iterdir():
                            if not sidecar.name.startswith("._") or not sidecar.is_file():
                                raise AssertionError(f"unexpected fixture entry: {sidecar}")
                            sidecar.unlink()
                        fixture.rmdir()
                written_at = time.monotonic()
                print(run_text(["diskutil", "eject", disk], timeout=40).strip(), flush=True)
                ejected_at = time.monotonic()
                disk = ""
                reconnect(target, 150)
                cdc_at = time.monotonic()
                stats["sessions"] += 1
                diagnostic = parse_vfat_diagnostic(terminal_report(target, "vlog"))
                if diagnostic is None or diagnostic["code"] != 0:
                    raise AssertionError(f"USB import diagnostic: {diagnostic}")
                if phase == "delete":
                    if listing_entries(terminal_report(target, "ls /")) != original:
                        raise AssertionError("root was not restored after host deletion")
                else:
                    rows = listing_entries(terminal_report(target, f'ls "/{name}"'))
                    actual = {row.split("\t")[-1].casefold() for row in rows}
                    if actual != {leaf.casefold() for leaf in expected}:
                        raise AssertionError(f"imported files/sidecars mismatch: {rows}")
                    with Port(target.path) as port:
                        if parse_identity(port.command("identity")) != identity:
                            raise AssertionError("identity changed after USB")
                        for leaf, content in expected.items():
                            require_file_contents(port.command(f'fsget "/{name}/{leaf}"', timeout=45), content)
                            stats["cdc_readbacks"] += 1
                reset_cycle(target, 30)
                stats["resets"] += 1
                if not expected:
                    if listing_entries(terminal_report(target, "ls /")) != original:
                        raise AssertionError("host deletion did not survive reset")
                else:
                    with Port(target.path) as port:
                        if parse_identity(port.command("identity")) != identity:
                            raise AssertionError("identity changed after reset")
                        for leaf, content in expected.items():
                            require_file_contents(port.command(f'fsget "/{name}/{leaf}"', timeout=45), content)
                            stats["cdc_readbacks"] += 1
                crash = terminal_report(target, "crash")
                if "CRASH none" not in crash:
                    raise AssertionError(crash)
                print(json.dumps(dict(phase=phase, cycle=cycle + 1,
                                      elapsed_s=round(time.monotonic() - started, 2),
                                      connect_s=round(mounted_at - phase_started, 2),
                                      host_io_s=round(written_at - mounted_at, 2),
                                      eject_s=round(ejected_at - written_at, 2),
                                      cdc_return_s=round(cdc_at - ejected_at, 2), **stats)), flush=True)
        print(terminal_report(target, "df"), flush=True)
        print(terminal_report(target, "mpu status"), flush=True)
        print(json.dumps(dict(result="PASS", public=identity.public, build=identity.build,
                              elapsed_s=round(time.monotonic() - started, 2), **stats)), flush=True)
        return 0
    finally:
        if disk:
            subprocess.run(["diskutil", "eject", disk], capture_output=True, timeout=40, check=False)


if __name__ == "__main__":
    raise SystemExit(main())

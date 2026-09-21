#!/usr/bin/env python3
"""Exercise the elastic 512-KiB USB journal with many distinct FAT sectors.

Only a uniquely named fixture directory is created. The target and new USB
disk are verified by the same identity/topology checks as the transaction HIL.
The test does not format the filesystem and removes its own files afterward.
"""

from __future__ import annotations

import argparse
import fcntl
import os
import subprocess
import sys

from hil_multi_device_identity import Target, parse_identity, request_transition
from hil_rtc_alarm import Port
from hil_usb_disk_transaction import (
    USB_DISK_PROFILES,
    console_locked,
    ensure_mounted,
    enter_usb_disk,
    find_cdc_location,
    listing_entries,
    parse_vfat_diagnostic,
    reconnect,
    require_file_contents,
    run_text,
    system_root,
    terminal_report,
    usb_tree,
    wait_for_msc_disk,
    whole_disks,
)


FILE_COUNT = 16
FILE_BYTES = 1500


def free_bytes(path: str | os.PathLike[str]) -> int:
    info = os.statvfs(path)
    return info.f_bavail * info.f_frsize


def payload(index: int) -> bytes:
    line = f"JOURNAL STRESS FILE {index:02d} / ".encode("ascii")
    return (line * (FILE_BYTES // len(line) + 1))[:FILE_BYTES]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", required=True)
    parser.add_argument("--public-id", required=True)
    parser.add_argument("--count", type=int, default=FILE_COUNT)
    parser.add_argument("--sync-each", action="store_true")
    parser.add_argument("--no-file-fsync", action="store_true")
    parser.add_argument("--uncached-read", action="store_true")
    args = parser.parse_args()
    if not 0 < args.count <= FILE_COUNT:
        parser.error(f"--count must be 1..{FILE_COUNT}")

    with Port(args.port) as port:
        identity = parse_identity(port.command("identity"))
        original = listing_entries(port.command("ls /", timeout=10.0))
        capacity = port.command("df", timeout=10.0)
    if identity.public != args.public_id.upper():
        raise AssertionError(f"wrong board: {identity.public}")
    if identity.profile not in USB_DISK_PROFILES or "Flash: 524288 bytes" not in capacity:
        raise AssertionError("this test requires the 512-KiB USB-disk board")
    if console_locked(system_root()):
        raise AssertionError("unlock the Mac before the USB-disk test")

    fixture_dir = f"JRN{identity.short[-4:]}"
    if any(item.casefold().endswith((fixture_dir + "/").casefold())
           for item in original):
        raise AssertionError(f"fixture directory already exists: {fixture_dir}")

    target = Target(args.port, identity)
    location_id = find_cdc_location(usb_tree(), identity)
    baseline = whole_disks()
    disk_identifier = ""
    fixture_started = False
    try:
        request_transition(target, "rst now", timeout=5.0)
        reconnect(target, 30.0)
        enter_usb_disk(target)
        disk_identifier, info = wait_for_msc_disk(
            location_id, identity.usb, baseline, 30.0
        )
        mount = ensure_mounted(disk_identifier, info)
        fixture = mount / fixture_dir
        fixture.mkdir()
        fixture_started = True
        print(f"USB stress: {disk_identifier} {fixture}, {args.count} files, "
              f"free={free_bytes(mount)}", flush=True)
        for index in range(args.count):
            try:
                with (fixture / f"J{index:02d}.TXT").open("xb") as output:
                    output.write(payload(index))
                    output.flush()
                    if not args.no_file_fsync:
                        os.fsync(output.fileno())
            except OSError:
                print(f"USB stress: failure at file {index + 1}, "
                      f"host_free={free_bytes(mount)}", flush=True)
                print(f"USB stress: entries={sorted(os.listdir(fixture))}", flush=True)
                print(f"USB stress: root={sorted(os.listdir(mount))}", flush=True)
                raise
            if args.sync_each:
                os.sync()
            if (index + 1) % 8 == 0:
                print(f"USB stress: wrote {index + 1}/{args.count}, "
                      f"free={free_bytes(mount)}", flush=True)
                print(f"USB stress: entries={sorted(os.listdir(fixture))}", flush=True)
                print(f"USB stress: sidecars="
                      f"{[(name, (fixture / name).stat().st_size) for name in os.listdir(fixture) if name.startswith('._')]}",
                      flush=True)
        for index in range(args.count):
            if (fixture / f"J{index:02d}.TXT").read_bytes() != payload(index):
                raise AssertionError(f"host readback failed for file {index}")
            if args.uncached_read:
                handle = os.open(fixture / f"J{index:02d}.TXT", os.O_RDONLY)
                try:
                    fcntl.fcntl(handle, 48, 1)  # macOS F_NOCACHE
                    direct = os.read(handle, FILE_BYTES)
                finally:
                    os.close(handle)
                if direct != payload(index):
                    raise AssertionError(f"uncached device readback failed for file {index}")
        os.sync()
        print(run_text(["diskutil", "eject", disk_identifier], timeout=40.0).strip(), flush=True)
        disk_identifier = ""
        # Import is intentionally serialized into durable C6 transactions.
        # A nearly full 512-KiB NOR can take several seconds per file.
        reconnect(target, max(30.0, args.count * 8.0))
        print(terminal_report(target, "vlog", timeout=10.0), flush=True)

        listing = terminal_report(target, f'ls "/{fixture_dir}"', timeout=15.0)
        entries = listing_entries(listing)
        if len(entries) != args.count:
            raise AssertionError(f"only {len(entries)}/{args.count} files imported:\n{listing}")
        for index in range(args.count):
            require_file_contents(
                terminal_report(target, f'fsget "/{fixture_dir}/J{index:02d}.TXT"', timeout=12.0),
                payload(index),
            )
            if (index + 1) % 8 == 0:
                print(f"USB stress: verified {index + 1}/{args.count}", flush=True)
        diagnostic = parse_vfat_diagnostic(terminal_report(target, "vlog", timeout=10.0))
        if diagnostic is not None and diagnostic["code"] != 0:
            raise AssertionError(f"USB import error: {diagnostic}")

        removed = terminal_report(target, f'rm -r "/{fixture_dir}"', timeout=40.0)
        if "Removed " not in removed:
            raise AssertionError(f"fixture cleanup failed:\n{removed}")
        fixture_started = False
        restored = listing_entries(terminal_report(target, "ls /", timeout=10.0))
        if restored != original:
            raise AssertionError(f"root changed after cleanup: {restored}")
        print(
            f"USB JOURNAL STRESS OK public={identity.public} "
            f"files={args.count} bytes={args.count * FILE_BYTES} "
            "host_readback=all c6_readback=all cleanup=1",
            flush=True,
        )
        return 0
    finally:
        if disk_identifier:
            subprocess.run(["diskutil", "eject", disk_identifier],
                           capture_output=True, timeout=30.0, check=False)
            try:
                reconnect(target, max(30.0, args.count * 8.0))
                print(terminal_report(target, "vlog", timeout=10.0), flush=True)
            except (AssertionError, OSError, TimeoutError):
                pass
        if fixture_started:
            try:
                reconnect(target, 30.0)
                terminal_report(target, f'rm -r "/{fixture_dir}"', timeout=40.0)
            except (AssertionError, OSError, TimeoutError):
                print(f"USB stress: cleanup requires attention: /{fixture_dir}",
                      file=sys.stderr)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (AssertionError, OSError, TimeoutError) as error:
        print(f"USB journal stress: FAIL: {error}", file=sys.stderr)
        raise SystemExit(1)

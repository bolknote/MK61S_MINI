#!/usr/bin/env python3
"""Qualify C9 density and reuse on a pinned board through CDC and macOS FAT.

Creates one reserved subtree; never formats or opens a raw block device.
Requires the matching C9 resident/System to be installed beforehand. A warm
reset checks remount and interrupted fsput; this is not a physical power cut.
"""

import argparse
import json
import os
from pathlib import Path
import re
import time

from hil_c7_storage_stress import Stress
from hil_multi_device_identity import request_transition
from hil_usb_disk_transaction import (
    enter_usb_disk, ensure_mounted, find_cdc_location, listing_entries,
    reconnect, run_text, usb_tree, wait_for_msc_disk, whole_disks,
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", required=True)
    parser.add_argument("--public-id", required=True)
    parser.add_argument("--app", type=Path, required=True)
    parser.add_argument("--count", type=int, default=320)
    args = parser.parse_args()
    if not 256 <= args.count <= 400:
        parser.error("--count must be 256..400")
    app = args.app.read_bytes()
    if not 64 < len(app) <= 20544:
        parser.error("--app must be a valid matched APP container")
    stress = Stress(args.port, args.public_id, 0xC9F12)
    stress.root = f"/C9HIL-{stress.target.identity.short}"
    if any(line.split("\t")[-1].rstrip("/").casefold() == stress.root[1:].casefold()
           for line in stress.original):
        stress.port.close()
        raise AssertionError(f"fixture already exists: {stress.root}")
    disk = ""
    try:
        report = stress.cmd("df")
        if not (re.search(r"(?:C9|format=9|version=9)", report) or
                re.search(r"Nodes: \d+ used, \d+ free, (?:1024|8192) total", report)):
            raise AssertionError(f"C9 is required:\n{report}")
        stress.health()
        stress.change(f'mkdir "{stress.root}"')
        for folder in ("EMPTY", "RAW", "HOST"):
            stress.change(f'mkdir "{stress.root}/{folder}"')
        for index in range(args.count):
            stress.put(f"{stress.root}/EMPTY/E{index:04d}.txt", b"")
            if index % 64 == 63:
                stress.note("empty-density", files=index + 1)
        for index, size in enumerate((1, 100, 500, 511, 512, 513, 1536, 1600, 1601, 4064, 4065, 4096)):
            stress.put(f"{stress.root}/RAW/B{index:02d}.bin", stress.payload(size))
        stress.put(f"{stress.root}/RAW/Длинное имя.txt", b"C9 text\r\n")
        stress.put(f"{stress.root}/RAW/MAX.tbi", (b"10 REM C9\r\n" * 400)[:3584])
        stress.put(f"{stress.root}/RAW/MODULE.app", app)
        stress.reset()

        # Delete every third empty object, reuse IDs, and remount again.
        for index in range(0, args.count, 3):
            stress.remove(f"{stress.root}/EMPTY/E{index:04d}.txt")
            stress.put(f"{stress.root}/EMPTY/N{index:04d}.txt", b"")
        stress.change(f'mv "{stress.root}/RAW/Длинное имя.txt" "{stress.root}/EMPTY/Новое имя.txt"')
        stress.files[f"{stress.root}/EMPTY/Новое имя.txt"] = stress.files.pop(f"{stress.root}/RAW/Длинное имя.txt")
        guard = f"{stress.root}/RAW/B11.bin"
        stress.begin(guard, stress.payload(4096))
        stress.data(stress.payload(513))
        stress.stats["interrupted_uploads"] += 1
        stress.reset()
        stress.note("native-density-reuse")

        # Normal filesystem writes, no custom FAT image or raw disk access.
        location = find_cdc_location(usb_tree(), stress.target.identity)
        baseline = whole_disks()
        stress.port.close()
        enter_usb_disk(stress.target)
        disk, info = wait_for_msc_disk(location, stress.target.identity.usb, baseline, 60)
        mount = ensure_mounted(disk, info)
        folder = mount / stress.root[1:] / "HOST"
        started = time.monotonic()
        for index in range(args.count):
            data = bytes([32 + index % 95])
            with (folder / f"F{index:04d}.txt").open("xb") as output:
                output.write(data)
                output.flush()
                os.fsync(output.fileno())
            stress.files[f"{stress.root}/HOST/F{index:04d}.txt"] = data
            if index % 4 == 3:
                stress.note("host-writing", files=index + 1)
        exit_started = time.monotonic()
        run_text(["diskutil", "eject", disk], timeout=60)
        disk = ""
        reconnect(stress.target, 60)
        stress.note("eject-to-cdc", seconds=round(time.monotonic()-exit_started, 3))
        from hil_rtc_alarm import Port
        stress.port = Port(stress.target.path)
        stress.note("host-create", files=args.count, seconds=round(time.monotonic()-started, 3))
        stress.reset()
        stress.health()

        # Export after reset, host deletion/refill, and a second durable import.
        location = find_cdc_location(usb_tree(), stress.target.identity)
        baseline = whole_disks()
        stress.port.close()
        enter_usb_disk(stress.target)
        disk, info = wait_for_msc_disk(location, stress.target.identity.usb, baseline, 60)
        folder = ensure_mounted(disk, info) / stress.root[1:] / "HOST"
        for index in range(args.count):
            assert (folder/f"F{index:04d}.txt").read_bytes() == stress.files[f"{stress.root}/HOST/F{index:04d}.txt"]
        native_empty = folder.parent / "EMPTY"
        (native_empty/"Новое имя.txt").rename(native_empty/"Проверка имени.txt")
        stress.files[f"{stress.root}/EMPTY/Проверка имени.txt"] = stress.files.pop(
            f"{stress.root}/EMPTY/Новое имя.txt")
        for index in range(0, args.count, 3):
            (folder/f"F{index:04d}.txt").unlink()
            del stress.files[f"{stress.root}/HOST/F{index:04d}.txt"]
            data = b"R"
            with (folder/f"R{index:04d}.txt").open("xb") as output:
                output.write(data)
                output.flush()
                os.fsync(output.fileno())
            stress.files[f"{stress.root}/HOST/R{index:04d}.txt"] = data
            if index % 12 == 9:
                stress.note("host-refilling", replaced=index // 3 + 1)
        exit_started = time.monotonic()
        run_text(["diskutil", "eject", disk], timeout=60)
        disk = ""
        reconnect(stress.target, 60)
        stress.note("eject-to-cdc", seconds=round(time.monotonic()-exit_started, 3))
        stress.port = Port(stress.target.path)
        stress.reset()
        stress.health()
        stress.note("host-delete-refill")
        stress.change(f'rm -r "{stress.root}"')
        stress.files.clear()
        stress.reset()
        assert listing_entries(stress.cmd("ls /")) == stress.original
        stress.health()
        stress.note("PASS", empty_files=args.count, host_files=args.count, cleanup=True)
        return 0
    except BaseException as error:
        stress.note("FAIL", error=str(error), retained_fixture=stress.root)
        raise
    finally:
        if disk:
            try:
                run_text(["diskutil", "eject", disk], timeout=30)
            except (AssertionError, OSError, TimeoutError):
                pass
        stress.port.close()


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Exercise one real MK61 USB-disk transaction without risking another disk.

The target is resolved as CDC by its canonical public identity.  Its physical
USB ``locationID`` is captured before the mode switch and the MSC device must
reappear at that exact topology node.  The block device is accepted only when
it is the sole new whole disk and its read-only metadata also identifies a
small, removable, writable USB MK61S medium.  No raw-device operation or
format command exists in this runner.

The test creates one unique 8.3 text file, fsyncs it, asks macOS to eject the
exact selected disk, verifies automatic MSC->CDC recovery, then warm-resets
the calculator to prove the import survived.  Finally it removes only that
reserved file through the terminal and requires the original root listing to
be restored.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import plistlib
import re
import subprocess
import sys
import time
from typing import Any, Iterable

from hil_multi_device_identity import (
    Identity,
    Target,
    parse_identity,
    request_transition,
    require_unchanged,
    wait_absent,
    wait_for_identity,
)
from hil_rtc_alarm import Port


STM32_VID = 0x0483
CDC_PID = 0x5740
MSC_PID = 0x6161
MAX_SAFE_MSC_BYTES = 32 * 1024 * 1024
MIN_SAFE_MSC_BYTES = 32 * 1024

MENU_KEYS = {
    "mini-v3-ws0010": (0x27, 0x18, 0x1D),
    "classic-v3-uc1609": (0x27, 0x24, 0x25),
}


def run_bytes(command: list[str], timeout: float = 10.0) -> bytes:
    completed = subprocess.run(
        command, capture_output=True, timeout=timeout, check=False
    )
    if completed.returncode != 0:
        output = (completed.stdout + completed.stderr).decode(
            "utf-8", "replace"
        )
        raise AssertionError(
            f"command failed ({completed.returncode}): {' '.join(command)}\n"
            f"{output}"
        )
    return completed.stdout


def run_text(command: list[str], timeout: float = 10.0) -> str:
    return run_bytes(command, timeout).decode("utf-8", "replace")


def read_plist(command: list[str], timeout: float = 10.0) -> Any:
    payload = run_bytes(command, timeout)
    try:
        return plistlib.loads(payload)
    except plistlib.InvalidFileException as error:
        raise AssertionError(
            f"invalid plist from {' '.join(command)}: {payload[:200]!r}"
        ) from error


def usb_tree() -> dict[str, Any]:
    tree = read_plist(["ioreg", "-a", "-p", "IOUSB", "-l"])
    if not isinstance(tree, dict):
        raise AssertionError("IOUSB plist root is not a dictionary")
    return tree


def walk_nodes(value: Any) -> Iterable[dict[str, Any]]:
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from walk_nodes(child)
    elif isinstance(value, list):
        for child in value:
            yield from walk_nodes(child)


def console_locked(tree: dict[str, Any]) -> bool:
    return bool(tree.get("IOConsoleLocked", False))


def usb_serial(node: dict[str, Any]) -> str:
    return str(
        node.get("USB Serial Number")
        or node.get("kUSBSerialNumberString")
        or ""
    )


def find_cdc_location(tree: dict[str, Any], identity: Identity) -> int:
    matches = [
        node for node in walk_nodes(tree)
        if node.get("idVendor") == STM32_VID
        and node.get("idProduct") == CDC_PID
        and usb_serial(node).upper() == identity.usb
        and isinstance(node.get("locationID"), int)
    ]
    if len(matches) != 1:
        raise AssertionError(
            f"expected one CDC USB node for {identity.usb}, got {len(matches)}"
        )
    return int(matches[0]["locationID"])


def find_msc_node(
    tree: dict[str, Any], location_id: int, expected_usb_serial: str
) -> dict[str, Any] | None:
    matches = [
        node for node in walk_nodes(tree)
        if node.get("idVendor") == STM32_VID
        and node.get("idProduct") == MSC_PID
        and node.get("locationID") == location_id
        and usb_serial(node).upper() == expected_usb_serial.upper()
    ]
    if len(matches) > 1:
        raise AssertionError(
            f"ambiguous MK61S MSC nodes at location 0x{location_id:08X}"
        )
    return matches[0] if matches else None


def msc_configured(node: dict[str, Any]) -> bool:
    return node.get("kUSBCurrentConfiguration") == 1


def whole_disks() -> set[str]:
    value = read_plist(["diskutil", "list", "-plist"])
    disks = value.get("WholeDisks", []) if isinstance(value, dict) else []
    if not isinstance(disks, list) or not all(
        isinstance(item, str) for item in disks
    ):
        raise AssertionError("diskutil WholeDisks is malformed")
    return set(disks)


def disk_info(identifier: str) -> dict[str, Any]:
    value = read_plist(["diskutil", "info", "-plist", identifier])
    if not isinstance(value, dict):
        raise AssertionError(f"diskutil info for {identifier} is malformed")
    return value


def validate_new_disk(
    before: set[str], after: set[str], info: dict[str, Any]
) -> str:
    added = after - before
    if len(added) != 1:
        raise AssertionError(
            f"expected exactly one new whole disk, got {sorted(added)}"
        )
    identifier = next(iter(added))
    if info.get("DeviceIdentifier") != identifier:
        raise AssertionError(
            f"disk metadata mismatch: expected {identifier}, "
            f"got {info.get('DeviceIdentifier')!r}"
        )
    media_name = str(info.get("MediaName", "")).casefold()
    size = int(info.get("Size", 0) or 0)
    if (
        info.get("BusProtocol") != "USB"
        or info.get("Internal") is not False
        or info.get("WholeDisk") is not True
        or info.get("Writable") is not True
        or info.get("DeviceBlockSize") != 512
        or not (MIN_SAFE_MSC_BYTES <= size <= MAX_SAFE_MSC_BYTES)
        or ("mk61" not in media_name and "program" not in media_name)
    ):
        raise AssertionError(
            f"refusing unsafe/non-MK61 disk {identifier}: {info}"
        )
    return identifier


def listing_entries(report: str) -> tuple[str, ...]:
    return tuple(
        line.rstrip("\r")
        for line in report.splitlines()
        if re.match(r"^[df]\t", line.rstrip("\r"))
    )


def wait_for_msc_disk(
    location_id: int,
    expected_usb_serial: str,
    baseline: set[str],
    timeout: float,
) -> tuple[str, dict[str, Any]]:
    deadline = time.monotonic() + timeout
    last = "MSC USB node not present"
    while time.monotonic() < deadline:
        tree = usb_tree()
        node = find_msc_node(tree, location_id, expected_usb_serial)
        if node is None:
            last = "MSC USB node not present"
            time.sleep(0.10)
            continue
        if not msc_configured(node):
            state = "locked" if console_locked(tree) else "unlocked"
            last = f"MSC enumerated but not configured (console={state})"
            time.sleep(0.10)
            continue
        current = whole_disks()
        added = current - baseline
        if len(added) == 1:
            identifier = next(iter(added))
            info = disk_info(identifier)
            validate_new_disk(baseline, current, info)
            return identifier, info
        last = f"configured MSC has new disks {sorted(added)}"
        time.sleep(0.15)
    raise TimeoutError(
        f"MK61S disk did not become safely selectable at "
        f"location 0x{location_id:08X}: {last}"
    )


def ensure_mounted(identifier: str, info: dict[str, Any]) -> Path:
    mount = str(info.get("MountPoint", "") or "")
    if not mount:
        run_text(["diskutil", "mount", identifier], timeout=20.0)
        info = disk_info(identifier)
        mount = str(info.get("MountPoint", "") or "")
    path = Path(mount)
    if not path.is_absolute() or path.parent != Path("/Volumes"):
        raise AssertionError(
            f"refusing unexpected mount point for {identifier}: {mount!r}"
        )
    if not path.is_dir():
        raise AssertionError(f"MK61S mount point is not accessible: {path}")
    return path


def enter_usb_disk(target: Target) -> None:
    keys = MENU_KEYS.get(target.identity.profile)
    if keys is None:
        raise AssertionError(
            f"unsupported USB Disk menu profile: {target.identity.profile}"
        )
    with Port(target.path) as port:
        require_unchanged(
            target.identity, parse_identity(port.command("identity"))
        )
        for key in keys[:-1]:
            port.command(f"kbd {key:02X}")
            time.sleep(0.15)
        port.drain()
        port.write_line(f"kbd {keys[-1]:02X}")
        time.sleep(0.35)
    wait_absent(target.path, 5.0)


def reconnect(target: Target, timeout: float) -> None:
    path, current = wait_for_identity(target.identity, timeout)
    require_unchanged(target.identity, current)
    target.path = path


def terminal_report(target: Target, command: str, timeout: float = 6.0) -> str:
    with Port(target.path) as port:
        require_unchanged(
            target.identity, parse_identity(port.command("identity"))
        )
        return port.command(command, timeout=timeout)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", required=True)
    parser.add_argument("--public-id", default="")
    parser.add_argument("--msc-timeout", type=float, default=25.0)
    parser.add_argument("--reconnect-timeout", type=float, default=20.0)
    args = parser.parse_args()
    if args.msc_timeout <= 0 or args.reconnect_timeout <= 0:
        parser.error("timeouts must be positive")

    with Port(args.port) as port:
        identity = parse_identity(port.command("identity"))
        initial_entries = listing_entries(port.command("ls /", timeout=10.0))
    if args.public_id and identity.public != args.public_id.upper():
        raise AssertionError(
            f"wrong board: expected {args.public_id.upper()}, "
            f"got {identity.public}"
        )
    if identity.profile not in MENU_KEYS:
        raise AssertionError(f"unsupported profile: {identity.profile}")
    target = Target(args.port, identity)

    tree = usb_tree()
    if console_locked(tree):
        raise AssertionError(
            "macOS console is locked; USB Restricted Mode would reject the "
            "new MSC PID, so the test was not started"
        )
    location_id = find_cdc_location(tree, identity)
    baseline = whole_disks()
    fixture_name = f"HIL{identity.short[-4:]}.TXT"
    if any(line.casefold().endswith(fixture_name.casefold())
           for line in initial_entries):
        raise AssertionError(
            f"reserved fixture already exists; refusing overwrite: {fixture_name}"
        )

    # Reset gives the top-level menu a known active index without changing C5.
    request_transition(target, "rst now", timeout=5.0)
    reconnect(target, args.reconnect_timeout)
    enter_usb_disk(target)

    disk_identifier = ""
    fixture_created = False
    try:
        disk_identifier, info = wait_for_msc_disk(
            location_id, identity.usb, baseline, args.msc_timeout
        )
        mount = ensure_mounted(disk_identifier, info)
        fixture = mount / fixture_name
        payload = (
            f"MK61 USB transactional HIL {identity.public}\n"
        ).encode("ascii")
        with fixture.open("xb") as output:
            output.write(payload)
            output.flush()
            os.fsync(output.fileno())
        fixture_created = True
        if fixture.read_bytes() != payload:
            raise AssertionError("host readback differs from written fixture")

        eject = run_text(
            ["diskutil", "eject", disk_identifier], timeout=30.0
        )
        print(eject.strip())
        disk_identifier = ""
        reconnect(target, args.reconnect_timeout)

        imported = terminal_report(target, "ls /", timeout=10.0)
        if not any(
            line.casefold().endswith(fixture_name.casefold())
            for line in listing_entries(imported)
        ):
            raise AssertionError(
                f"committed fixture is not visible after eject:\n{imported}"
            )
        vlog = terminal_report(target, "vlog", timeout=10.0)

        request_transition(target, "rst now", timeout=5.0)
        reconnect(target, args.reconnect_timeout)
        after_reset = terminal_report(target, "ls /", timeout=10.0)
        if not any(
            line.casefold().endswith(fixture_name.casefold())
            for line in listing_entries(after_reset)
        ):
            raise AssertionError(
                f"fixture did not survive reset:\n{after_reset}"
            )

        removed = terminal_report(target, f"rm /{fixture_name}", timeout=10.0)
        if "Removed 1 entry." not in removed:
            raise AssertionError(f"could not remove HIL fixture:\n{removed}")
        fixture_created = False
        final_listing = terminal_report(target, "ls /", timeout=10.0)
        if listing_entries(final_listing) != initial_entries:
            raise AssertionError(
                "root listing was not restored after HIL cleanup:\n"
                f"before={initial_entries}\nafter={listing_entries(final_listing)}"
            )
        health = terminal_report(target, "df", timeout=10.0)
        crash = terminal_report(target, "crash show", timeout=10.0)
        if "FIRMWARE CRC state=valid" not in health or "CRASH none" not in crash:
            raise AssertionError(f"post-MSC health failed:\n{health}\n{crash}")

        print(vlog.strip())
        print(
            "USB DISK HIL OK "
            f"public={identity.public} profile={identity.profile} "
            f"location=0x{location_id:08X} fixture={fixture_name} "
            "copy=1 eject=1 cdc=1 reset=1 cleanup=1",
            flush=True,
        )
        return 0
    finally:
        if disk_identifier:
            subprocess.run(
                ["diskutil", "eject", disk_identifier],
                capture_output=True, timeout=20.0, check=False,
            )
        if fixture_created:
            try:
                reconnect(target, args.reconnect_timeout)
                terminal_report(
                    target, f"rm /{fixture_name}", timeout=10.0
                )
            except (AssertionError, OSError, TimeoutError):
                pass


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (AssertionError, OSError, TimeoutError) as error:
        print(f"USB Disk HIL: FAIL: {error}", file=sys.stderr)
        raise SystemExit(1)

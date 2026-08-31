#!/usr/bin/env python3
"""Two-phase HIL for automatic USB-suspended STOP and local re-entry.

After ``arm`` closes CDC, suspend the host. The display must turn off without a
terminal command. Press one physical calculator key: MK61 must wake locally
while the host stays asleep. Leave it untouched; after the activity grace
period it must turn off again. Wake the host manually and run ``verify``.
"""

from __future__ import annotations

import argparse
import re
import sys

from hil_rtc_alarm import IDENTITY, Port
from hil_usb_suspend import (
    CLOCK, DEEP, DISPLAY, DISPLAY_UC1609, KEYBOARD_STOP, POWER, open_port,
    usb_fields,
)


AUTOMATIC = re.compile(
    r"(?m)^DEEP AUTO enabled=(?P<enabled>\d+) phase=(?P<phase>[^ ]+) "
    r"holdoff=(?P<holdoff>\d+) requests=(?P<requests>\d+) "
    r"reentries=(?P<reentries>\d+) wait_ms=(?P<wait>\d+)\r?$"
)


def automatic_fields(report: str) -> re.Match[str]:
    match = AUTOMATIC.search(report)
    if not match:
        raise AssertionError(f"automatic STOP telemetry missing:\n{report}")
    return match


def arm(path: str, expected_key_code: int | None) -> int:
    with Port(path) as port:
        identity = port.command("identity")
        identity_match = IDENTITY.search(identity)
        if not identity_match:
            raise AssertionError(f"not an MK61 identity response:\n{identity}")
        port.command("prof deep cancel")
        if "PROF reset" not in port.command("prof reset"):
            raise AssertionError("could not reset STOP counters")
        baseline = port.command("prof")
        usb = usb_fields(baseline)
        automatic = automatic_fields(baseline)
        if (
            usb["backend"] != "STM32-OTGFS-wrap" or
            usb["supported"] != "1" or usb["linked"] != "1" or
            usb["callbacks"] != "1" or usb["stop_preserve"] != "1" or
            usb["host_remote"] != "0" or usb["state"] != "configured" or
            automatic["enabled"] != "1" or
            automatic["phase"] != "host-awake" or
            automatic["holdoff"] != "0"
        ):
            raise AssertionError(
                "automatic local-only STOP is not ready:\n" + baseline
            )

    print(f"device={identity_match.group(1)} path={path} host_remote=0")
    print("HOST_SLEEP_NOW; DISPLAY_MUST_TURN_OFF_AUTOMATICALLY", flush=True)
    print(
        (f"PRESS_PHYSICAL_SCAN_CODE_{expected_key_code}; "
         if expected_key_code is not None else
         "PRESS_ONE_PHYSICAL_MK61_KEY; ") +
        "HOST_MUST_STAY_ASLEEP; "
        "WAIT_12_SECONDS_FOR_DISPLAY_TO_TURN_OFF_AGAIN; "
        "THEN_WAKE_HOST_MANUALLY",
        flush=True,
    )
    return 0


def verify(path: str, expected_key_code: int | None,
           final_wake: str) -> int:
    port = open_port(path)
    try:
        identity = port.command("identity", timeout=6.0)
        identity_match = IDENTITY.search(identity)
        if not identity_match:
            raise AssertionError(f"not an MK61 identity response:\n{identity}")
        report = port.command("prof", timeout=6.0)
        display_report = port.command("display", timeout=6.0)
    finally:
        port.close()

    usb = usb_fields(report)
    automatic = automatic_fields(report)
    keyboard = KEYBOARD_STOP.search(report)
    deep = DEEP.search(report)
    clock = CLOCK.search(report)
    display = DISPLAY.search(report)
    uc1609 = DISPLAY_UC1609.search(display_report)
    power = POWER.search(report)
    if not deep or not clock or (not display and not uc1609) or not power:
        raise AssertionError(
            f"automatic STOP recovery report incomplete:\n"
            f"{report}{display_report}"
        )

    (
        backend, enabled, state, wake, failure,
        _seconds, requested, completed, _attempts, entries,
        rtc_wakes, keyboard_wakes, alarm_wakes, other_wakes,
        failures, _total_ms, _last_ms, blockers,
    ) = deep.groups()

    expected_host_wakes = 1 if final_wake == "host" else 0
    expected_local_wakes = 1 if final_wake == "host" else 2
    expected_keyboard_wakes = 1 if final_wake == "host" else 2
    expected_other_wakes = 1 if final_wake == "host" else 0
    expected_wake = "usb-host" if final_wake == "host" else "keyboard"
    expected_captures = expected_keyboard_wakes

    if (
        usb["state"] != "configured" or usb["host_remote"] != "0" or
        int(usb["suspend"]) < 1 or int(usb["resume"]) < 1 or
        int(usb["stop_arms"]) < 2 or int(usb["stop_aborts"]) != 0 or
        int(usb["host_wakes"]) != expected_host_wakes or
        int(usb["local_wakes"]) != expected_local_wakes or
        int(usb["stop_blockers"], 16) != 0 or
        int(usb["endpoint_blockers"], 16) != 0
    ):
        raise AssertionError(f"USB automatic STOP accounting invalid:\n{report}")
    if (
        backend != "STOP-RTC+KBD" or enabled != "1" or state != "light" or
        wake != expected_wake or failure != "none" or int(failures) != 0 or
        int(blockers, 16) != 0 or int(requested) != 0xFFFF or
        int(completed) < 1 or int(entries) < 2 or
        int(keyboard_wakes) != expected_keyboard_wakes or
        int(alarm_wakes) != 0 or int(other_wakes) != expected_other_wakes
    ):
        raise AssertionError(f"automatic deep-idle accounting invalid:\n{report}")
    if int(rtc_wakes) != int(entries) - 2:
        raise AssertionError(f"unexpected automatic RTC wake count:\n{report}")
    if (
        automatic["enabled"] != "1" or
        automatic["phase"] != "host-awake" or
        automatic["holdoff"] != "0" or
        int(automatic["requests"]) < 2 or
        int(automatic["reentries"]) < 1
    ):
        raise AssertionError(f"automatic re-entry did not occur:\n{report}")
    if expected_key_code is not None:
        if not keyboard:
            raise AssertionError(f"keyboard wake telemetry missing:\n{report}")
        expected_row = 1 << (expected_key_code % 5)
        if (
            keyboard["supported"] != "1" or
            int(keyboard["captures"]) != expected_captures or
            int(keyboard["last"]) != expected_key_code or
            int(keyboard["count"]) != 1 or
            int(keyboard["wake_rows"], 16) != expected_row or
            int(keyboard["captured_rows"], 16) != expected_row
        ):
            raise AssertionError(f"wrong physical wake key captured:\n{report}")
    if clock.group(1) != "96000000":
        raise AssertionError(f"96 MHz clock was not restored:\n{report}")
    if display and (display.group(1) != "0" or display.group(2) != "0" or
                    display.group(3) != "on"):
        raise AssertionError(f"WS0010 did not recover cleanly:\n{report}")
    if power.group(1) != "stable" or power.group(2) != "1":
        raise AssertionError(f"PVD write gate did not recover:\n{report}")

    print(
        f"device={identity_match.group(1)} entries={entries} "
        f"rtc/key/host={rtc_wakes}/{keyboard_wakes}/{other_wakes} "
        f"auto={automatic['requests']}/{automatic['reentries']} "
        f"suspend/resume={usb['suspend']}/{usb['resume']}"
    )
    print("USB automatic suspend/re-entry HIL: OK")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("arm", "verify"))
    parser.add_argument("--port", required=True)
    parser.add_argument("--expected-key-code", type=lambda value: int(value, 0))
    parser.add_argument(
        "--final-wake", choices=("host", "keyboard"), default="host"
    )
    args = parser.parse_args()
    if args.expected_key_code is not None and not 0 <= args.expected_key_code < 40:
        parser.error("--expected-key-code must be in 0..39")
    return (arm(args.port, args.expected_key_code)
            if args.action == "arm" else
            verify(args.port, args.expected_key_code, args.final_wake))


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Two-phase HIL for USB-preserving STOP and local calculator wake.

`arm` closes CDC after scheduling STOP.  Put the host to sleep only after the
printed marker, then press one physical MK61 key.  The calculator must wake
while the host remains asleep.  Wake the host manually afterwards and run
`verify` against the same port.  Splitting the phases keeps the test usable
when the host suspends the Python process together with USB.

The firmware deliberately neither advertises nor signals USB Remote Wakeup.
USB is resumed only after the host wakes for an independent reason.
"""

from __future__ import annotations

import argparse
import re
import sys
import time

from hil_rtc_alarm import IDENTITY, Port


USB_POWER = re.compile(
    r"(?m)^USB POWER backend=(?P<backend>[^ ]+) "
    r"supported=(?P<supported>\d+) linked=(?P<linked>\d+) "
    r"callbacks=(?P<callbacks>\d+) qualification=(?P<qualification>\d+) "
    r"state=(?P<state>[^ ]+) raw=(?P<raw>\d+)/(?P<old>\d+) "
    r"host_remote=(?P<host_remote>\d+) endpoints=(?P<endpoints>\d+) "
    r"age_ms=(?P<age>\d+) "
    r"events=(?P<setup>\d+)/(?P<reset>\d+)/(?P<suspend>\d+)/"
    r"(?P<resume>\d+)/(?P<connect>\d+)/(?P<disconnect>\d+) "
    r"stop=(?P<stop_arms>\d+)/(?P<stop_aborts>\d+)/"
    r"(?P<host_wakes>\d+)/(?P<local_wakes>\d+) "
    r"blockers=0x(?P<stop_blockers>[0-9A-Fa-f]+) "
    r"epblock=0x(?P<endpoint_blockers>[0-9A-Fa-f]+)\r?$"
)
DEEP = re.compile(
    r"(?m)^DEEP backend=([^ ]+) enabled=(\d+) state=([^ ]+) wake=([^ ]+) "
    r"failure=([^ ]+) request=(\d+)x(\d+) completed=(\d+) "
    r"attempts=(\d+) entries=(\d+) wakes=(\d+)/(\d+)/(\d+)/(\d+) "
    r"failures=(\d+) total_ms=(\d+) last_ms=(\d+) "
    r"blockers=0x([0-9A-Fa-f]+)\r?$"
)
CLOCK = re.compile(r"(?m)^PROF state=\S+ clock=(\d+) ")
DISPLAY = re.compile(
    r"(?m)^DISPLAY .*bf-timeouts=(\d+) bf-fault=(\d+).*state=([^ ]+)"
)
POWER = re.compile(r"(?m)^POWER .*state=([^ ]+) gate=(\d+)")


def open_port(path: str, timeout: float = 20.0) -> Port:
    deadline = time.monotonic() + timeout
    last_error: OSError | None = None
    while time.monotonic() < deadline:
        try:
            return Port(path)
        except OSError as error:
            last_error = error
            time.sleep(0.1)
    raise TimeoutError(f"CDC did not resume on {path}: {last_error}")


def usb_fields(report: str) -> re.Match[str]:
    match = USB_POWER.search(report)
    if not match:
        raise AssertionError(f"USB power telemetry missing:\n{report}")
    return match


def arm(path: str, seconds: int, cycles: int) -> int:
    with Port(path) as port:
        identity = port.command("identity")
        identity_match = IDENTITY.search(identity)
        if not identity_match:
            raise AssertionError(f"not an MK61 identity response:\n{identity}")
        port.command("prof deep cancel")
        if "PROF reset" not in port.command("prof reset"):
            raise AssertionError("could not reset qualification counters")
        baseline = port.command("prof")
        usb = usb_fields(baseline)
        if (
            usb["backend"] != "STM32-OTGFS-wrap" or
            usb["supported"] != "1" or usb["linked"] != "1" or
            usb["callbacks"] != "1" or usb["qualification"] != "1" or
            usb["state"] != "configured" or usb["host_remote"] != "0"
        ):
            raise AssertionError(
                "USB is not qualified for local-only suspend wake:\n"
                + baseline
            )
        scheduled = port.command(f"prof deep {seconds} {cycles}")
        if "PROF deep scheduled" not in scheduled or \
           "waiting for host USB suspend" not in scheduled:
            raise AssertionError(f"USB-preserving STOP was rejected:\n{scheduled}")

    print(
        f"device={identity_match.group(1)} path={path} "
        f"request={seconds}x{cycles} host_remote=0"
    )
    print("HOST_SLEEP_NOW_THEN_PRESS_ONE_PHYSICAL_MK61_KEY", flush=True)
    print(
        "MK61_MUST_WAKE_LOCALLY_AND_HOST_MUST_STAY_ASLEEP; "
        "THEN_WAKE_HOST_MANUALLY",
        flush=True,
    )
    return 0


def verify(path: str, expected: str) -> int:
    port = open_port(path)
    try:
        identity = port.command("identity", timeout=6.0)
        identity_match = IDENTITY.search(identity)
        if not identity_match:
            raise AssertionError(f"not an MK61 identity response:\n{identity}")
        report = port.command("prof", timeout=6.0)
    finally:
        port.close()

    usb = USB_POWER.search(report)
    deep = DEEP.search(report)
    clock = CLOCK.search(report)
    display = DISPLAY.search(report)
    power = POWER.search(report)
    if not usb or not deep or not clock or not display or not power:
        raise AssertionError(f"USB STOP recovery report incomplete:\n{report}")

    (
        deep_backend, enabled, deep_state, wake, failure,
        _seconds, _requested, completed, _attempts, entries,
        rtc_wakes, keyboard_wakes, alarm_wakes, other_wakes,
        failures, _total_ms, _last_ms, blockers,
    ) = deep.groups()

    if (
        usb["backend"] != "STM32-OTGFS-wrap" or
        usb["supported"] != "1" or usb["linked"] != "1" or
        usb["callbacks"] != "1" or usb["qualification"] != "1" or
        usb["state"] != "configured" or usb["host_remote"] != "0"
    ):
        raise AssertionError(f"USB did not return configured:\n{report}")
    if int(usb["suspend"]) < 1 or int(usb["resume"]) < 1:
        raise AssertionError(f"host suspend/resume callbacks missing:\n{report}")
    if int(usb["stop_arms"]) < 1 or int(usb["stop_aborts"]) != 0:
        raise AssertionError(f"USB STOP arm accounting invalid:\n{report}")
    if int(usb["stop_blockers"], 16) != 0 or \
       int(usb["endpoint_blockers"], 16) != 0:
        raise AssertionError(f"USB STOP retained a blocker:\n{report}")
    if (
        deep_backend != "STOP-RTC+KBD" or enabled != "1" or
        deep_state != "light" or failure != "none" or int(failures) != 0 or
        int(blockers, 16) != 0
    ):
        raise AssertionError(f"deep-idle recovery failed:\n{report}")
    if clock.group(1) != "96000000":
        raise AssertionError(f"96 MHz clock was not restored:\n{report}")
    if display.group(1) != "0" or display.group(2) != "0" or \
       display.group(3) != "on":
        raise AssertionError(f"WS0010 did not recover cleanly:\n{report}")
    if power.group(1) != "stable" or power.group(2) != "1":
        raise AssertionError(f"PVD write gate did not recover:\n{report}")

    completed_n = int(completed)
    entries_n = int(entries)
    rtc_n = int(rtc_wakes)
    keyboard_n = int(keyboard_wakes)
    alarm_n = int(alarm_wakes)
    other_n = int(other_wakes)
    if expected == "keyboard":
        if (
            wake != "keyboard" or completed_n != entries_n or entries_n < 1 or
            keyboard_n != 1 or rtc_n != entries_n - 1 or alarm_n != 0 or
            other_n != 0 or int(usb["host_wakes"]) != 0 or
            int(usb["local_wakes"]) != 1
        ):
            raise AssertionError(f"local keyboard wake mismatch:\n{report}")
    else:
        if (
            wake != "usb-host" or completed_n != entries_n or entries_n < 1 or
            keyboard_n != 0 or alarm_n != 0 or other_n != 1 or
            int(usb["host_wakes"]) != 1 or int(usb["local_wakes"]) != 0
        ):
            raise AssertionError(f"host resume wake mismatch:\n{report}")

    print(
        f"device={identity_match.group(1)} path={path} wake={wake} "
        f"entries={entries_n} rtc={rtc_n} keyboard={keyboard_n} "
        f"suspend/resume={usb['suspend']}/{usb['resume']} "
        f"host/local={usb['host_wakes']}/{usb['local_wakes']}"
    )
    print("USB suspend/local-wake HIL: OK")
    return 0


def cancel(path: str) -> int:
    with Port(path) as port:
        print(port.command("prof deep cancel"), end="")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("arm", "verify", "cancel"))
    parser.add_argument("--port", required=True)
    parser.add_argument("--seconds", type=int, default=5, choices=range(1, 6))
    parser.add_argument("--cycles", type=int, default=120, choices=range(1, 121))
    parser.add_argument(
        "--expected", choices=("keyboard", "host"), default="keyboard"
    )
    args = parser.parse_args()
    if args.action == "arm":
        return arm(args.port, args.seconds, args.cycles)
    if args.action == "verify":
        return verify(args.port, args.expected)
    return cancel(args.port)


if __name__ == "__main__":
    sys.exit(main())

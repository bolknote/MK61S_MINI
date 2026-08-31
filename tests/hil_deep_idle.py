#!/usr/bin/env python3
"""Exercise qualification-only STOP and verify complete board recovery.

Uses only the Python standard library.  RTC mode is unattended; keyboard mode
prints a marker after CDC disappears and expects one physical key press.
"""

from __future__ import annotations

import argparse
import datetime as dt
import os
import re
import sys
import time

from hil_rtc_alarm import DATE_MS, IDENTITY, Port, reconnect


DEEP = re.compile(
    r"(?m)^DEEP backend=([^ ]+) enabled=(\d+) state=([^ ]+) wake=([^ ]+) "
    r"failure=([^ ]+) "
    r"request=(\d+)x(\d+) completed=(\d+) attempts=(\d+) entries=(\d+) "
    r"wakes=(\d+)/(\d+)/(\d+)/(\d+) failures=(\d+) total_ms=(\d+) "
    r"last_ms=(\d+) blockers=0x([0-9A-Fa-f]+)\r?$"
)
CLOCK = re.compile(r"(?m)^PROF state=\S+ clock=(\d+) ")
DISPLAY = re.compile(
    r"(?m)^DISPLAY .*bf-timeouts=(\d+) bf-fault=(\d+).*state=([^ ]+)"
)
DISPLAY_UC1609 = re.compile(
    r"(?m)^DISPLAY controller=UC1609 mode=graphics\r?$"
)
POWER = re.compile(r"(?m)^POWER .*state=([^ ]+) gate=(\d+)")


def read_date(port: Port) -> str:
    report = port.command("date ms")
    match = DATE_MS.search(report)
    if not match:
        raise AssertionError(f"precise RTC date missing:\n{report}")
    return f"{match.group(1)}.{match.group(2)}"


def parsed_date(value: str) -> dt.datetime:
    return dt.datetime.strptime(value, "%Y-%m-%d %H:%M:%S.%f")


def verify_spi_health(report: str) -> None:
    spi_line = next(
        (
            line for line in report.splitlines()
            if line.startswith("SPI1 backend=")
        ),
        "",
    )
    for token in (
        "state=idle", "owner=none", "failures=0", "contentions=0",
        "double=0", "inactive=0", "wrong=0", "invalid=0", "latched=0",
    ):
        if token not in spi_line:
            raise AssertionError(f"bad SPI1 recovery ({token}):\n{report}")
    dma_line = next(
        (
            line for line in report.splitlines()
            if line.startswith("SPI1 DMA backend=")
        ),
        "",
    )
    if dma_line:
        for token in ("init_errors=0", "errors=0", "timeouts=0"):
            if token not in dma_line:
                raise AssertionError(f"bad DMA recovery ({token}):\n{report}")


def wait_for_disconnect(path: str, timeout: float) -> float:
    started = time.monotonic()
    while time.monotonic() - started < timeout:
        if not os.path.exists(path):
            return time.monotonic() - started
        time.sleep(0.01)
    raise TimeoutError(f"CDC did not disconnect: {path}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", required=True)
    parser.add_argument("--seconds", type=int, default=1, choices=range(1, 6))
    parser.add_argument("--cycles", type=int, default=1, choices=range(1, 1001))
    parser.add_argument(
        "--wake", choices=("rtc", "keyboard", "alarm"), default="rtc"
    )
    args = parser.parse_args()
    if args.wake == "alarm" and args.seconds < 2:
        parser.error("--wake alarm requires --seconds 2..5")

    path = args.port
    with Port(path) as port:
        identity = port.command("identity")
        identity_match = IDENTITY.search(identity)
        if not identity_match:
            raise AssertionError(f"not an MK61 identity response:\n{identity}")
        public_id = identity_match.group(1)
        date_before = read_date(port)
        reset = port.command("prof reset")
        if "PROF reset" not in reset:
            raise AssertionError(f"profile reset failed:\n{reset}")
        if args.wake == "alarm":
            if "ALARM OK" not in port.command("alarm a off"):
                raise AssertionError("could not clear Alarm A")
            alarm_after = max(1, args.seconds - 1)
            armed = port.command(f"alarm a in {alarm_after}")
            if "ALARM OK" not in armed:
                raise AssertionError(f"could not arm Alarm A:\n{armed}")
        scheduled = port.command(f"prof deep {args.seconds} {args.cycles}")
        if "PROF deep scheduled" not in scheduled:
            raise AssertionError(f"STOP request was rejected:\n{scheduled}")

    started = time.monotonic()
    disconnect_seconds = wait_for_disconnect(path, 4.0)
    if args.wake == "keyboard":
        print("PRESS_ANY_PHYSICAL_KEY_NOW", flush=True)

    maximum_sleep = args.seconds * args.cycles + 5.0
    port, path = reconnect(path, public_id, timeout=maximum_sleep + 8.0)
    alarm_report = ""
    try:
        reconnect_seconds = time.monotonic() - started
        report = port.command("prof")
        display_report = port.command("display")
        date_after = read_date(port)
        identity_after = port.command("identity")
        storage_report = port.command("df", timeout=10.0)
        crash_report = port.command("crash")
        if args.wake == "alarm":
            alarm_report = port.command("alarm")
            port.command("alarm a off")
    finally:
        port.close()

    if public_id not in identity_after:
        raise AssertionError(f"device identity changed:\n{identity_after}")
    if "FIRMWARE CRC state=valid" not in storage_report:
        raise AssertionError(f"resident firmware invalid:\n{storage_report}")
    if "CRASH none" not in crash_report:
        raise AssertionError(f"fault during STOP run:\n{crash_report}")
    deep = DEEP.search(report)
    clock = CLOCK.search(report)
    display = DISPLAY.search(report)
    uc1609 = DISPLAY_UC1609.search(display_report)
    power = POWER.search(report)
    if not deep or not clock or (not display and not uc1609) or not power:
        raise AssertionError(
            f"recovery report incomplete:\n{report}{display_report}"
        )

    (backend, enabled, state, wake, failure, seconds, requested, completed,
     attempts, entries, rtc_wakes, keyboard_wakes, alarm_wakes, other_wakes,
     failures, total_ms, last_ms, blockers) = deep.groups()
    numeric = [
        seconds, requested, completed, attempts, entries, rtc_wakes,
        keyboard_wakes, alarm_wakes, other_wakes, failures, total_ms, last_ms,
    ]
    (seconds_n, requested_n, completed_n, attempts_n, entries_n, rtc_n,
     keyboard_n, alarm_n, other_n, failures_n, total_ms_n,
     last_ms_n) = map(int, numeric)

    if enabled != "1" or backend != "STOP-RTC+KBD" or state != "light":
        raise AssertionError(f"invalid STOP backend/state:\n{report}")
    if seconds_n != args.seconds or requested_n != args.cycles:
        raise AssertionError(f"request accounting mismatch:\n{report}")
    if failure != "none" or failures_n != 0 or int(blockers, 16) != 0:
        raise AssertionError(f"STOP failure/blocker recorded:\n{report}")
    if clock.group(1) != "96000000":
        raise AssertionError(f"HCLK was not restored:\n{report}")
    verify_spi_health(report)
    if display and (display.group(1) != "0" or display.group(2) != "0" or
                    display.group(3) != "on"):
        raise AssertionError(f"WS0010 was not restored cleanly:\n{report}")
    if power.group(1) != "stable" or power.group(2) != "1":
        raise AssertionError(f"power write gate was not restored:\n{report}")

    if args.wake == "rtc":
        expected_ms = args.seconds * args.cycles * 1000
        if wake != "rtc-timer" or completed_n != args.cycles or \
           entries_n != args.cycles or rtc_n != args.cycles or \
           keyboard_n != 0 or alarm_n != 0 or other_n != 0:
            raise AssertionError(f"RTC wake accounting mismatch:\n{report}")
        if abs(total_ms_n - expected_ms) > max(20, args.cycles * 4):
            raise AssertionError(
                f"RTC STOP duration {total_ms_n} ms != {expected_ms} ms"
            )
        calendar_ms = int(
            (parsed_date(date_after) - parsed_date(date_before)).total_seconds()
            * 1000
        )
        if abs(calendar_ms - expected_ms) > max(3000, args.cycles * 5):
            raise AssertionError(
                f"RTC calendar advanced {calendar_ms} ms, expected "
                f"approximately {expected_ms} ms"
            )
    elif args.wake == "keyboard":
        # A multi-cycle request provides a human-sized interaction window.
        # Every complete cycle before the press must be an RTC wake; the final
        # cycle must be the one and only keyboard wake and must end early.
        if wake != "keyboard" or completed_n != entries_n or \
           entries_n < 1 or entries_n > args.cycles or \
           keyboard_n != 1 or rtc_n != entries_n - 1 or \
           alarm_n != 0 or other_n != 0:
            raise AssertionError(f"keyboard wake accounting mismatch:\n{report}")
        if last_ms_n >= args.seconds * 1000:
            raise AssertionError(f"keyboard did not preempt RTC timer:\n{report}")
    else:
        if wake != "rtc-alarm" or completed_n != 1 or entries_n != 1 or \
           keyboard_n != 0 or rtc_n != 0 or alarm_n != 1 or other_n != 0:
            raise AssertionError(f"alarm wake accounting mismatch:\n{report}")
        if total_ms_n >= args.seconds * 1000:
            raise AssertionError(f"alarm did not preempt RTC timer:\n{report}")
        if (
            "RTC ALARM A off" not in alarm_report or
            "wake=alarm-a" not in alarm_report
        ):
            raise AssertionError(
                f"Alarm A foreground finalization failed:\n{alarm_report}"
            )

    print(f"device={public_id} path={path} backend={backend}")
    print(
        f"disconnect_s={disconnect_seconds:.3f} reconnect_s={reconnect_seconds:.3f} "
        f"rtc_before={date_before} rtc_after={date_after}"
    )
    print(
        f"wake={wake} attempts={attempts_n} entries={entries_n} "
        f"completed={completed_n} total_ms={total_ms_n} last_ms={last_ms_n}"
    )
    print("deep idle HIL: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())

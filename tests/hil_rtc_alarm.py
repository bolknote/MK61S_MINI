#!/usr/bin/env python3
"""Non-destructive RTC Alarm A/B HIL test using only Python stdlib.

The test changes alarm slots and performs warm MCU resets. It does not change
the calendar, external Flash, or resident firmware. A finalizer cancels both
slots even when a check fails.
"""

from __future__ import annotations

import argparse
import datetime as dt
import glob
import os
import re
import select
import sys
import termios
import time


PROMPT = re.compile(rb"(?:^|[\r\n])[^\r\n]*>\s*$")
IDENTITY = re.compile(r"public=([0-9A-F]{16})")
DATE_MS = re.compile(
    r"(?m)^(20\d\d-\d\d-\d\d \d\d:\d\d:\d\d)\.(\d{3})\r?$"
)


class Port:
    def __init__(self, path: str):
        self.path = path
        self.fd = os.open(path, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
        attrs = termios.tcgetattr(self.fd)
        attrs[0] = 0
        attrs[1] = 0
        attrs[2] &= ~(termios.CSIZE | termios.PARENB | termios.CSTOPB)
        attrs[2] |= termios.CS8 | termios.CREAD | termios.CLOCAL
        attrs[3] = 0
        attrs[4] = termios.B115200
        attrs[5] = termios.B115200
        attrs[6][termios.VMIN] = 0
        attrs[6][termios.VTIME] = 0
        termios.tcsetattr(self.fd, termios.TCSANOW, attrs)

    def close(self) -> None:
        if self.fd >= 0:
            os.close(self.fd)
            self.fd = -1

    def __enter__(self) -> "Port":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def drain(self) -> None:
        while True:
            readable, _, _ = select.select([self.fd], [], [], 0)
            if not readable:
                return
            if not os.read(self.fd, 4096):
                return

    def write_line(self, text: str) -> None:
        payload = text.encode("ascii") + b"\r"
        offset = 0
        while offset < len(payload):
            _, writable, _ = select.select([], [self.fd], [], 1.0)
            if not writable:
                raise TimeoutError(f"serial write timeout: {self.path}")
            offset += os.write(self.fd, payload[offset:])

    def read_prompt(self, timeout: float) -> str:
        deadline = time.monotonic() + timeout
        data = bytearray()
        while time.monotonic() < deadline:
            readable, _, _ = select.select(
                [self.fd], [], [], min(0.1, deadline - time.monotonic())
            )
            if readable:
                block = os.read(self.fd, 4096)
                if block:
                    data.extend(block)
                    if PROMPT.search(data):
                        return data.decode("utf-8", "replace")
        raise TimeoutError(
            f"terminal prompt timeout on {self.path}: {data!r}"
        )

    def command(self, text: str, timeout: float = 4.0) -> str:
        self.drain()
        self.write_line(text)
        return self.read_prompt(timeout)


def require(haystack: str, needle: str) -> None:
    if needle not in haystack:
        raise AssertionError(f"missing {needle!r} in:\n{haystack}")


def status(port: Port) -> str:
    result = port.command("alarm")
    require(result, "RTC META valid=1")
    return result


def boot_count(report: str) -> int:
    match = re.search(r"\bboot=(\d+)\b", report)
    if not match:
        raise AssertionError(f"boot counter missing:\n{report}")
    return int(match.group(1))


def wait_slot_off(port: Port, slot: str, timeout: float) -> tuple[float, str]:
    started = time.monotonic()
    last = ""
    while time.monotonic() - started < timeout:
        last = status(port)
        if f"RTC ALARM {slot.upper()} off" in last:
            return time.monotonic() - started, last
        time.sleep(0.04)
    raise TimeoutError(f"Alarm {slot} did not fire:\n{last}")


def precise_samples(port: Port, count: int = 12) -> None:
    samples: list[dt.datetime] = []
    for _ in range(count):
        report = port.command("date ms")
        match = DATE_MS.search(report)
        if not match:
            raise AssertionError(f"precise date missing:\n{report}")
        value = dt.datetime.strptime(match.group(1), "%Y-%m-%d %H:%M:%S")
        samples.append(value.replace(microsecond=int(match.group(2)) * 1000))
        time.sleep(0.03)
    for previous, current in zip(samples, samples[1:]):
        delta = (current - previous).total_seconds()
        if delta < 0 or delta > 0.5:
            raise AssertionError(
                f"non-coherent RTC subsecond samples: {previous} -> {current}"
            )
    print(
        "date-ms: coherent",
        samples[0].isoformat(timespec="milliseconds"),
        "->",
        samples[-1].isoformat(timespec="milliseconds"),
    )


def reconnect(path: str, public_id: str, timeout: float = 20.0) -> tuple[Port, str]:
    deadline = time.monotonic() + timeout
    preferred_glob = re.sub(r"usbmodem.*$", "usbmodem*", path)
    while time.monotonic() < deadline:
        candidates = [path]
        candidates.extend(p for p in glob.glob(preferred_glob) if p != path)
        for candidate in candidates:
            if not os.path.exists(candidate):
                continue
            try:
                port = Port(candidate)
                time.sleep(0.15)
                report = port.command("identity", timeout=2.0)
                match = IDENTITY.search(report)
                if match and match.group(1) == public_id:
                    return port, candidate
                port.close()
            except (OSError, TimeoutError):
                try:
                    port.close()
                except UnboundLocalError:
                    pass
        time.sleep(0.1)
    raise TimeoutError(f"device {public_id} did not re-enumerate")


def warm_reset(port: Port, path: str, public_id: str) -> tuple[Port, str, float]:
    started = time.monotonic()
    port.drain()
    port.write_line("rst now")
    time.sleep(0.10)
    port.close()
    next_port, next_path = reconnect(path, public_id)
    elapsed = time.monotonic() - started
    print(f"warm-reset-enumeration: {elapsed:.3f}s path={next_path}")
    return next_port, next_path, elapsed


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", required=True)
    parser.add_argument("--skip-reset", action="store_true")
    args = parser.parse_args()

    path = args.port
    port = Port(path)
    public_id = ""
    try:
        identity = port.command("identity")
        match = IDENTITY.search(identity)
        if not match:
            raise AssertionError(f"not an MK61 identity response:\n{identity}")
        public_id = match.group(1)
        print(f"device: {public_id} path={path}")

        precise_samples(port)
        require(port.command("alarm a off"), "ALARM OK")
        require(port.command("alarm b off"), "ALARM OK")
        initial = status(port)
        initial_boot = boot_count(initial)
        print(f"backup: boot={initial_boot}")

        scheduled = time.monotonic()
        require(port.command("alarm a in 3"), "ALARM OK")
        _, report = wait_slot_off(port, "a", 5.0)
        elapsed = time.monotonic() - scheduled
        require(report, "wake=alarm-a")
        if not 2.80 <= elapsed <= 3.45:
            raise AssertionError(f"Alarm A timing outside gate: {elapsed:.3f}s")
        print(f"alarm-a-relative: {elapsed:.3f}s")

        scheduled = time.monotonic()
        require(port.command("alarm b in 3"), "ALARM OK")
        _, report = wait_slot_off(port, "b", 5.0)
        elapsed = time.monotonic() - scheduled
        require(report, "wake=alarm-b")
        if not 2.80 <= elapsed <= 3.45:
            raise AssertionError(f"Alarm B timing outside gate: {elapsed:.3f}s")
        print(f"alarm-b-relative: {elapsed:.3f}s")

        now_report = port.command("date ms")
        now_match = DATE_MS.search(now_report)
        if not now_match:
            raise AssertionError(f"precise date missing:\n{now_report}")
        now = dt.datetime.strptime(
            now_match.group(1), "%Y-%m-%d %H:%M:%S"
        ) + dt.timedelta(milliseconds=int(now_match.group(2)))
        target = now + dt.timedelta(seconds=4)
        require(
            port.command(f"alarm a daily {target:%H:%M:%S}"), "ALARM OK"
        )
        deadline = time.monotonic() + 6.0
        daily_report = ""
        while time.monotonic() < deadline:
            daily_report = status(port)
            if "wake=alarm-a" in daily_report:
                break
            time.sleep(0.05)
        require(daily_report, "wake=alarm-a")
        require(daily_report, "RTC ALARM A daily")
        require(port.command("alarm a off"), "ALARM OK")
        print("alarm-a-daily: fired and remained armed")

        if not args.skip_reset:
            require(port.command("alarm b in 8"), "ALARM OK")
            port, path, _ = warm_reset(port, path, public_id)
            restored = status(port)
            if boot_count(restored) != min(initial_boot + 1, 0xFFFFFFFF):
                raise AssertionError(f"boot counter did not increment:\n{restored}")
            require(restored, "RTC ALARM B one-shot")
            _, restored = wait_slot_off(port, "b", 10.0)
            require(restored, "wake=alarm-b")
            print("alarm-b-reset-restore: OK")

            require(port.command("alarm a in 1"), "ALARM OK")
            port, path, _ = warm_reset(port, path, public_id)
            missed = status(port)
            require(missed, "RTC ALARM A off")
            require(missed, "wake=missed-a")
            print("alarm-a-missed-after-reset: OK")

        print("RTC alarm HIL: OK")
        return 0
    finally:
        try:
            if port.fd >= 0:
                port.command("alarm a off", timeout=2.0)
                port.command("alarm b off", timeout=2.0)
        except (OSError, TimeoutError):
            pass
        port.close()


if __name__ == "__main__":
    sys.exit(main())

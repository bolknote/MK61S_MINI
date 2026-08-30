#!/usr/bin/env python3
"""Measure WFI residency with the USB CDC port genuinely closed."""

from __future__ import annotations

import argparse
import re
import time

from hil_rtc_alarm import IDENTITY, Port


SLEEP = re.compile(
    r"(?m)^SLEEP backend=([^ ]+) enabled=(\d+) attempts=(\d+) "
    r"entries=(\d+) total_us=(\d+) min_us=(\d+) avg_us=(\d+) "
    r"max_us=(\d+) last_blockers=0x([0-9A-Fa-f]+)\r?$"
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", required=True)
    parser.add_argument("--seconds", type=float, default=60.0)
    args = parser.parse_args()
    if not 1.0 <= args.seconds <= 600.0:
        parser.error("--seconds must be in 1..600")

    with Port(args.port) as port:
        identity = port.command("identity")
        match = IDENTITY.search(identity)
        if not match:
            raise AssertionError(f"not an MK61 identity response:\n{identity}")
        public_id = match.group(1)
        reset = port.command("prof reset")
        if "PROF reset" not in reset:
            raise AssertionError(f"firmware did not reset profiling:\n{reset}")

    started = time.monotonic()
    time.sleep(args.seconds)
    elapsed = time.monotonic() - started

    with Port(args.port) as port:
        report = port.command("prof")
    match = SLEEP.search(report)
    if not match:
        raise AssertionError(f"sleep profile missing:\n{report}")
    backend, enabled, attempts, entries, total, minimum, average, maximum, blockers = (
        match.groups()
    )
    if enabled != "1" or int(entries) == 0:
        raise AssertionError(f"WFI did not run:\n{report}")
    print(f"device: {public_id} path={args.port}")
    print(f"closed_seconds={elapsed:.6f}")
    print(
        f"sleep backend={backend} attempts={attempts} entries={entries} "
        f"total_us={total} min_us={minimum} avg_us={average} max_us={maximum} "
        f"last_blockers=0x{blockers.upper()}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

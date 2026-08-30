#!/usr/bin/env python3
"""Repeatable DWT profile of the MK-61 core on a connected device.

The firmware-side ``prof core`` command creates a deterministic volatile core
state and measures exactly the requested number of complete ``core.step``
samples.  It borrows the existing shared context slot and restores the live
calculator bit-for-bit before replying, so this script never clears user state.
"""

from __future__ import annotations

import argparse
import re
import statistics
from hil_rtc_alarm import IDENTITY, Port


CORE_STEP = re.compile(
    r"(?m)^PROF core\.step n=(\d+) min=(\d+) avg=(\d+) "
    r"max=(\d+) total=(\d+)\r?$"
)


def require(haystack: str, needle: str) -> None:
    if needle not in haystack:
        raise AssertionError(f"missing {needle!r} in:\n{haystack}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", required=True)
    parser.add_argument("--steps", type=int, default=40)
    parser.add_argument("--runs", type=int, default=5)
    args = parser.parse_args()

    if args.steps < 1 or args.steps > 1000:
        parser.error("--steps must be in 1..1000")
    if args.runs < 1 or args.runs > 50:
        parser.error("--runs must be in 1..50")

    expected_steps = args.steps
    averages: list[int] = []
    with Port(args.port) as port:
        identity = port.command("identity")
        match = IDENTITY.search(identity)
        if not match:
            raise AssertionError(f"not an MK61 identity response:\n{identity}")
        print(f"device: {match.group(1)} path={args.port}")

        for run in range(1, args.runs + 1):
            report = port.command(
                f"prof core {args.steps}", timeout=max(8.0, args.steps * 0.1)
            )
            require(report, f"PROF corebench steps={args.steps} restored=1")
            match = CORE_STEP.search(report)
            if not match:
                raise AssertionError(f"core.step profile missing:\n{report}")
            count, minimum, average, maximum, total = map(int, match.groups())
            if count != expected_steps:
                raise AssertionError(
                    f"expected {expected_steps} core.step samples, got {count}\n{report}"
                )
            averages.append(average)
            print(
                f"run={run} core.step n={count} min={minimum} avg={average} "
                f"max={maximum} total={total}"
            )

    print(
        f"summary runs={args.runs} steps={args.steps} "
        f"avg_min={min(averages)} avg_median={int(statistics.median(averages))} "
        f"avg_max={max(averages)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

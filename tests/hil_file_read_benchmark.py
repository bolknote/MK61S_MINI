#!/usr/bin/env python3
"""Read-only latency benchmark for real C5 files on one MK61 device."""

from __future__ import annotations

import argparse
import re

from hil_rtc_alarm import IDENTITY, Port


SUMMARY = re.compile(
    r"(?m)^BENCH summary kind=file bytes=(\d+) passes=(\d+) "
    r"min_us=(\d+) avg_us=(\d+) max_us=(\d+) read_Bps=(\d+) "
    r"crc=0x([0-9A-Fa-f]{8})\r?$"
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", required=True)
    parser.add_argument("--passes", type=int, default=5)
    parser.add_argument("files", nargs="+")
    args = parser.parse_args()
    if args.passes < 1 or args.passes > 20:
        parser.error("--passes must be in 1..20")
    if any(not path or any(char.isspace() for char in path) for path in args.files):
        parser.error("file paths must be non-empty and contain no whitespace")

    with Port(args.port) as port:
        identity = port.command("identity")
        match = IDENTITY.search(identity)
        if not match:
            raise AssertionError(f"not an MK61 identity response:\n{identity}")
        print(f"device: {match.group(1)} path={args.port}")

        for path in args.files:
            report = port.command(f"bench file {path} {args.passes}", timeout=15.0)
            match = SUMMARY.search(report)
            if not match:
                raise AssertionError(f"benchmark summary missing for {path}:\n{report}")
            size, passes, minimum, average, maximum, rate, crc = match.groups()
            if int(passes) != args.passes:
                raise AssertionError(f"unexpected pass count for {path}:\n{report}")
            print(
                f"file={path} bytes={size} passes={passes} min_us={minimum} "
                f"avg_us={average} max_us={maximum} Bps={rate} crc={crc.upper()}"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

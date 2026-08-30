#!/usr/bin/env python3
"""Read-only C5 throughput matrix for one connected MK61 device.

The firmware computes a hardware CRC after every pass and rejects a data
mismatch.  This host wrapper verifies identity, runs the same size matrix for
before/after comparisons, and prints the SPI/DMA counters at the end.
"""

from __future__ import annotations

import argparse
import re

from hil_rtc_alarm import IDENTITY, Port


SUMMARY = re.compile(
    r"(?m)^BENCH summary kind=flash bytes=(\d+) passes=(\d+) "
    r"min_us=(\d+) avg_us=(\d+) max_us=(\d+) read_Bps=(\d+) "
    r"crc=0x([0-9A-Fa-f]{8})\r?$"
)
DMA = re.compile(
    r"(?m)^SPI1 DMA backend=([^ ]+) threshold=(\d+) transfers=(\d+) "
    r"bytes=(\d+) wfi=(\d+) fallback=(\d+) init_errors=(\d+) "
    r"errors=(\d+) timeouts=(\d+)\r?$"
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", required=True)
    parser.add_argument("--passes", type=int, default=5)
    parser.add_argument(
        "--sizes", type=int, nargs="+", default=[512, 2048, 8192, 65536, 1048576]
    )
    args = parser.parse_args()
    if args.passes < 1 or args.passes > 20:
        parser.error("--passes must be in 1..20")
    if not args.sizes or any(size < 1 or size > 1048576 for size in args.sizes):
        parser.error("--sizes values must be in 1..1048576")

    with Port(args.port) as port:
        identity = port.command("identity")
        match = IDENTITY.search(identity)
        if not match:
            raise AssertionError(f"not an MK61 identity response:\n{identity}")
        print(f"device: {match.group(1)} path={args.port}")
        if "PROF reset" not in port.command("prof reset"):
            raise AssertionError("firmware did not reset profiling counters")

        for size in args.sizes:
            timeout = max(10.0, args.passes * size / 100000.0 + 8.0)
            report = port.command(
                f"bench flash {size} {args.passes}", timeout=timeout
            )
            match = SUMMARY.search(report)
            if not match:
                raise AssertionError(f"benchmark summary missing:\n{report}")
            measured_size, passes, minimum, average, maximum, rate, crc = (
                match.groups()
            )
            if int(measured_size) != size or int(passes) != args.passes:
                raise AssertionError(f"unexpected benchmark dimensions:\n{report}")
            print(
                f"flash bytes={size} passes={passes} min_us={minimum} "
                f"avg_us={average} max_us={maximum} Bps={rate} crc={crc.upper()}"
            )

        profile = port.command("prof")
        match = DMA.search(profile)
        if not match:
            raise AssertionError(f"SPI1 DMA counters missing:\n{profile}")
        backend, threshold, transfers, byte_count, wfi, fallback, init_errors, errors, timeouts = (
            match.groups()
        )
        if init_errors != "0" or errors != "0" or timeouts != "0":
            raise AssertionError(f"SPI1 DMA errors after benchmark:\n{profile}")
        print(
            f"dma backend={backend} threshold={threshold} transfers={transfers} "
            f"bytes={byte_count} wfi={wfi} fallback={fallback} errors=0 timeouts=0"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Read-only UC1609/Flash SPI1 ownership and DMA hardware qualification."""

from __future__ import annotations

import argparse
import re
import sys

from hil_rtc_alarm import Port


SUMMARY = re.compile(
    r"BENCH summary kind=flash bytes=(\d+) passes=1 .* crc=0x([0-9A-F]{8})"
)


def key_values(report: str, prefix: str) -> dict[str, str]:
    for line in report.splitlines():
        if line.startswith(prefix):
            result: dict[str, str] = {}
            for token in line.split()[1:]:
                if "=" in token:
                    key, value = token.split("=", 1)
                    result[key] = value
            return result
    raise AssertionError(f"missing {prefix!r} in:\n{report}")


def require_zero(values: dict[str, str], names: tuple[str, ...]) -> None:
    for name in names:
        if int(values.get(name, "-1"), 0) != 0:
            raise AssertionError(f"{name} is not zero: {values}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", required=True)
    parser.add_argument("--public-id", default="")
    parser.add_argument("--iterations", type=int, default=100)
    parser.add_argument("--bytes", type=int, default=65536)
    parser.add_argument(
        "--dma", choices=("required", "forbidden"), default="forbidden"
    )
    args = parser.parse_args()
    if args.iterations < 1 or args.iterations > 1000:
        parser.error("--iterations must be in 1..1000")
    if args.bytes < 64 or args.bytes > 1048576:
        parser.error("--bytes must be in 64..1048576")

    with Port(args.port) as port:
        identity = port.command("identity")
        if "profile=classic-v3-uc1609" not in identity:
            raise AssertionError(f"wrong hardware profile:\n{identity}")
        if args.public_id and f"public={args.public_id}" not in identity:
            raise AssertionError(f"wrong physical device:\n{identity}")
        display = port.command("display")
        if "DISPLAY controller=UC1609 mode=graphics" not in display:
            raise AssertionError(f"UC1609 not active:\n{display}")

        port.command("prof reset")
        reference_crc = ""
        for index in range(args.iterations):
            port.command(f'print "SPI1 {index + 1:03d}/{args.iterations:03d}"')
            benchmark = port.command(
                f"bench flash {args.bytes} 1", timeout=15.0
            )
            match = SUMMARY.search(benchmark)
            if not match or int(match.group(1)) != args.bytes:
                raise AssertionError(f"invalid benchmark result:\n{benchmark}")
            checksum = match.group(2)
            if reference_crc and checksum != reference_crc:
                raise AssertionError(
                    f"Flash CRC changed: {reference_crc} -> {checksum}"
                )
            reference_crc = checksum

        port.command('print "SPI1 TEST PASS"')
        profile = port.command("prof")
        spi = key_values(profile, "SPI1 backend=")
        if spi.get("backend") != "polling-arbiter":
            raise AssertionError(f"wrong SPI1 backend: {spi}")
        if spi.get("state") != "idle" or spi.get("owner") != "none":
            raise AssertionError(f"SPI1 lease leaked: {spi}")
        acquisitions = int(spi.get("acquisitions", "-1"), 0)
        releases = int(spi.get("releases", "-2"), 0)
        if acquisitions <= 0 or acquisitions != releases:
            raise AssertionError(f"unbalanced SPI1 ownership: {spi}")
        require_zero(
            spi,
            (
                "failures",
                "contentions",
                "double",
                "inactive",
                "wrong",
                "invalid",
                "latched",
                "recoveries",
            ),
        )

        dma_lines = [
            line for line in profile.splitlines()
            if line.startswith("SPI1 DMA backend=")
        ]
        if args.dma == "forbidden":
            if dma_lines:
                raise AssertionError(f"DMA unexpectedly enabled:\n{profile}")
            dma_transfers = 0
            dma_bytes = 0
        else:
            if len(dma_lines) != 1:
                raise AssertionError(f"DMA telemetry missing:\n{profile}")
            dma = key_values(profile, "SPI1 DMA backend=")
            if dma.get("backend") != "DMA2-S2/S3-C3":
                raise AssertionError(f"wrong DMA backend: {dma}")
            require_zero(dma, ("init_errors", "errors", "timeouts"))
            dma_transfers = int(dma.get("transfers", "0"), 0)
            dma_bytes = int(dma.get("bytes", "0"), 0)
            if dma_transfers <= 0 or dma_bytes <= 0:
                raise AssertionError(f"DMA was not exercised: {dma}")

        storage = port.command("df", timeout=10.0)
        if "FIRMWARE CRC state=valid" not in storage:
            raise AssertionError(f"resident firmware invalid:\n{storage}")
        if "NOR JEDEC=0xEF3013" not in storage:
            raise AssertionError(f"unexpected external Flash:\n{storage}")
        crash = port.command("crash")
        if "CRASH none" not in crash:
            raise AssertionError(f"fault during stress:\n{crash}")

    print(
        "UC1609 SPI1 HIL: OK "
        f"iterations={args.iterations} bytes={args.bytes} crc={reference_crc} "
        f"leases={acquisitions} dma_transfers={dma_transfers} "
        f"dma_bytes={dma_bytes}"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (AssertionError, OSError, TimeoutError) as error:
        print(f"UC1609 SPI1 HIL: FAIL: {error}", file=sys.stderr)
        raise SystemExit(1)

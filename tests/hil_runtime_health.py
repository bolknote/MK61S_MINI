#!/usr/bin/env python3
"""Read-only production health and observed-stack gate for one F411 MK61."""

from __future__ import annotations

import argparse
import re
import sys

from hil_multi_device_identity import parse_identity
from hil_rtc_alarm import Port


MPU = re.compile(
    r"(?m)^MPU backend=([^ ]+) enabled=([01]) layout=([^ ]+) "
    r"regions=([0-9]+)/([0-9]+).* stack_budget=([0-9]+).* "
    r"watermark=([01]) watermark_remaining=([0-9]+) "
    r"observed_remaining=([0-9]+) sram_xn=([01])\r?$"
)
DEEP = re.compile(
    r"(?m)^DEEP backend=([^ ]+) enabled=([01]) state=([^ ]+) wake=([^ ]+) "
    r"failure=([^ ]+) .* failures=([0-9]+).* blockers=0x([0-9A-Fa-f]+)\r?$"
)


def require(report: str, needle: str, description: str) -> None:
    if needle not in report:
        raise AssertionError(f"{description} ({needle!r} missing):\n{report}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", required=True)
    parser.add_argument("--public-id", default="")
    parser.add_argument(
        "--profile", choices=("classic-v3-uc1609", "mini-v3-ws0010"),
        required=True,
    )
    parser.add_argument(
        "--minimum-stack-remaining", type=int, default=12 * 1024
    )
    args = parser.parse_args()
    if args.minimum_stack_remaining < 0:
        parser.error("--minimum-stack-remaining must be non-negative")

    with Port(args.port) as port:
        identity_report = port.command("identity")
        identity = parse_identity(identity_report)
        if identity.profile != args.profile:
            raise AssertionError(
                f"wrong profile: expected {args.profile}, got {identity.profile}"
            )
        if args.public_id and identity.public != args.public_id.upper():
            raise AssertionError(
                f"wrong board: expected {args.public_id.upper()}, "
                f"got {identity.public}"
            )
        # A direct request cannot enter production STOP while USB is active.
        # Cancel any stale laboratory request before evaluating the policy.
        port.command("prof deep cancel")
        mpu_report = port.command("mpu status")
        profile_report = port.command("prof")
        display_report = port.command("display status")
        firmware_report = port.command("df", timeout=10.0)
        crash_report = port.command("crash show")

    mpu = MPU.search(mpu_report)
    if not mpu:
        raise AssertionError(f"invalid MPU report:\n{mpu_report}")
    (backend, enabled, layout, regions, required_regions, stack_budget,
     watermark, watermark_remaining, remaining, sram_xn) = mpu.groups()
    remaining_n = int(remaining)
    if backend != "ARMv7-M" or enabled != "1" or layout != "ok":
        raise AssertionError(f"MPU guard is not active:\n{mpu_report}")
    if int(regions) < int(required_regions):
        raise AssertionError(f"insufficient MPU regions:\n{mpu_report}")
    if int(stack_budget) != 16 * 1024 or sram_xn != "1":
        raise AssertionError(f"unexpected F411 memory policy:\n{mpu_report}")
    if watermark != "1" or int(watermark_remaining) < remaining_n:
        raise AssertionError(f"stack watermark is not active:\n{mpu_report}")
    if remaining_n < args.minimum_stack_remaining:
        raise AssertionError(
            f"observed stack remainder {remaining_n} is below "
            f"{args.minimum_stack_remaining}:\n{mpu_report}"
        )

    deep = DEEP.search(profile_report)
    if not deep:
        raise AssertionError(f"missing production deep-idle report:\n{profile_report}")
    backend, enabled, state, _wake, failure, failures, blockers = deep.groups()
    if (
        backend != "STOP-RTC+KBD" or enabled != "1" or state != "light" or
        failure != "none" or int(failures) != 0 or int(blockers, 16) != 0
    ):
        raise AssertionError(f"deep-idle policy is unhealthy:\n{profile_report}")
    require(
        profile_report,
        "USB POWER backend=STM32-OTGFS-wrap supported=1 linked=1",
        "USB suspend callbacks",
    )
    require(profile_report, "stop_preserve=1", "USB-preserving STOP policy")
    require(firmware_report, "FIRMWARE CRC state=valid", "resident firmware")
    require(firmware_report, f"expected=0x{identity.build}", "firmware build ID")
    require(firmware_report, "backend=hardware", "hardware resident CRC")
    require(crash_report, "CRASH none", "crash state")
    require(crash_report, "layout=ok", "crash layout")
    if args.profile == "classic-v3-uc1609":
        require(display_report, "DISPLAY controller=UC1609 mode=graphics", "UC1609")
    else:
        require(display_report, "DISPLAY controller=WS0010", "WS0010")
        require(display_report, "mode=character owner=none", "WS0010 owner")
        require(display_report, "bf-fault=0", "WS0010 busy flag")

    print(
        "RUNTIME HEALTH OK "
        f"public={identity.public} profile={identity.profile} build={identity.build} "
        f"stack_budget={stack_budget} observed_remaining={remaining_n} "
        f"mpu_regions={regions}/{required_regions}"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (AssertionError, OSError, TimeoutError) as error:
        print(f"Runtime health HIL: FAIL: {error}", file=sys.stderr)
        raise SystemExit(1)

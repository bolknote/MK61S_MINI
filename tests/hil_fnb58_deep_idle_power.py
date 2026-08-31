#!/usr/bin/env python3
"""Measure qualified UC1609 STOP power against ordinary idle with FNB58.

The test verifies the exact calculator and meter, records a stable light-idle
window, schedules bounded RTC STOP cycles, then records only the interior STOP
window while CDC is absent.  Recovery must restore the clock, UC1609, SPI1,
resident CRC and fault-free state. ``bleak`` is the only non-stdlib dependency.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import re
import sys
import time

from hil_fnb58_flash_power import (
    Decoder,
    NOTIFY_UUID,
    REQUEST_INFO,
    START_STREAM,
    STOP_STREAM,
    WRITE_UUID,
    capture_window,
    print_window,
    wait_for,
)
from hil_rtc_alarm import IDENTITY, Port, reconnect
from hil_usb_suspend import CLOCK, DEEP, POWER


async def wait_for_path(path: str, present: bool, timeout: float) -> None:
    await wait_for(
        lambda: os.path.exists(path) == present,
        timeout,
        f"CDC path {path} to become {'present' if present else 'absent'}",
    )


def verify_recovery(report: str, seconds: int, cycles: int) -> None:
    deep = DEEP.search(report)
    clock = CLOCK.search(report)
    power = POWER.search(report)
    if not deep or not clock or not power:
        raise AssertionError(f"STOP recovery telemetry missing:\n{report}")
    (
        backend, enabled, state, wake, failure,
        actual_seconds, requested, completed, attempts, entries,
        rtc_wakes, keyboard_wakes, alarm_wakes, other_wakes,
        failures, total_ms, last_ms, blockers,
    ) = deep.groups()
    expected_ms = seconds * cycles * 1000
    if (
        backend != "STOP-RTC+KBD" or enabled != "1" or state != "light" or
        wake != "rtc-timer" or failure != "none" or
        int(actual_seconds) != seconds or int(requested) != cycles or
        int(completed) != cycles or int(attempts) != 1 or
        int(entries) != cycles or int(rtc_wakes) != cycles or
        int(keyboard_wakes) != 0 or int(alarm_wakes) != 0 or
        int(other_wakes) != 0 or int(failures) != 0 or
        abs(int(total_ms) - expected_ms) > max(20, cycles * 4) or
        abs(int(last_ms) - seconds * 1000) > 5 or
        int(blockers, 16) != 0
    ):
        raise AssertionError(f"STOP recovery accounting mismatch:\n{report}")
    if clock.group(1) != "96000000":
        raise AssertionError(f"96 MHz clock was not restored:\n{report}")
    if power.group(1) != "stable" or power.group(2) != "1":
        raise AssertionError(f"power write gate was not restored:\n{report}")


def verify_spi_health(report: str) -> None:
    spi_line = next(
        (line for line in report.splitlines() if line.startswith("SPI1 backend=")),
        "",
    )
    for token in (
        "backend=polling-arbiter", "state=idle", "owner=none",
        "failures=0", "contentions=0", "double=0", "inactive=0",
        "wrong=0", "invalid=0", "latched=0",
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
    if not dma_line:
        raise AssertionError(f"DMA backend telemetry missing:\n{report}")
    for token in ("init_errors=0", "errors=0", "timeouts=0"):
        if token not in dma_line:
            raise AssertionError(f"bad DMA recovery ({token}):\n{report}")


async def run(args: argparse.Namespace) -> int:
    try:
        from bleak import BleakClient, BleakScanner
    except ImportError as error:
        raise RuntimeError("bleak is required: python3 -m pip install bleak") from error

    device = await BleakScanner.find_device_by_address(
        args.meter_address, timeout=args.scan_timeout
    )
    if device is None:
        raise AssertionError(f"FNB58 not found: {args.meter_address}")

    decoder = Decoder()
    async with BleakClient(device) as client:
        await client.start_notify(
            NOTIFY_UUID, lambda _handle, data: decoder.feed(bytes(data))
        )
        try:
            await client.write_gatt_char(WRITE_UUID, REQUEST_INFO, response=True)
            await asyncio.sleep(2.0)
            await client.write_gatt_char(WRITE_UUID, START_STREAM, response=True)
            await wait_for(
                lambda: decoder.info is not None and len(decoder.samples) >= 3,
                8.0,
                "valid FNB58 info and measurements",
            )
            assert decoder.info is not None
            if args.meter_serial and decoder.info["serial"] != args.meter_serial:
                raise AssertionError(
                    f"wrong FNB58 serial: {decoder.info['serial']}"
                )
            print(
                f"METER name={device.name or '-'} address={device.address} "
                f"model=FNB{decoder.info['model']} "
                f"firmware={decoder.info['firmware']} "
                f"serial={decoder.info['serial']}"
            )

            path = args.port
            with Port(path) as port:
                identity = await asyncio.to_thread(port.command, "identity")
                match = IDENTITY.search(identity)
                if not match or "profile=classic-v3-uc1609" not in identity:
                    raise AssertionError(f"wrong calculator profile:\n{identity}")
                public_id = match.group(1)
                if args.public_id and public_id != args.public_id:
                    raise AssertionError(f"wrong calculator identity:\n{identity}")
                display = await asyncio.to_thread(port.command, "display")
                if "DISPLAY controller=UC1609 mode=graphics" not in display:
                    raise AssertionError(f"UC1609 not active:\n{display}")
                await asyncio.to_thread(port.command, "prof deep cancel")
                if "PROF reset" not in await asyncio.to_thread(
                    port.command, "prof reset"
                ):
                    raise AssertionError("could not reset STOP counters")
                await asyncio.sleep(args.warmup)
                idle = await capture_window(decoder, "light-idle", args.idle_seconds)
                scheduled = await asyncio.to_thread(
                    port.command, f"prof deep {args.seconds} {args.cycles}"
                )
                if "PROF deep scheduled" not in scheduled:
                    raise AssertionError(f"STOP request was rejected:\n{scheduled}")

            await wait_for_path(path, False, 5.0)
            await asyncio.sleep(args.transition_guard)
            stop_duration = (
                args.seconds * args.cycles - 2.0 * args.transition_guard
            )
            stop = await capture_window(decoder, "stop", stop_duration)

            resumed, path = await asyncio.to_thread(
                reconnect,
                path,
                public_id,
                args.seconds * args.cycles + 12.0,
            )
            try:
                report = await asyncio.to_thread(resumed.command, "prof")
                verify_recovery(report, args.seconds, args.cycles)
                verify_spi_health(report)
                display = await asyncio.to_thread(resumed.command, "display")
                if "DISPLAY controller=UC1609 mode=graphics" not in display:
                    raise AssertionError(f"UC1609 did not recover:\n{display}")
                storage = await asyncio.to_thread(resumed.command, "df", 10.0)
                if "FIRMWARE CRC state=valid" not in storage:
                    raise AssertionError(f"resident firmware invalid:\n{storage}")
                crash = await asyncio.to_thread(resumed.command, "crash")
                if "CRASH none" not in crash:
                    raise AssertionError(f"fault during STOP run:\n{crash}")
            finally:
                resumed.close()

            print_window(idle)
            print_window(stop)
            idle_current = idle.average("current_a")
            stop_current = stop.average("current_a")
            saving = (idle_current - stop_current) / idle_current
            print(
                f"SAVING current_percent={saving * 100:.2f} "
                f"current_delta_mA={(idle_current - stop_current) * 1000:.3f} "
                f"threshold_percent={args.minimum_saving * 100:.1f}"
            )
            if saving < args.minimum_saving:
                raise AssertionError(
                    f"STOP current saving {saving * 100:.2f}% is below "
                    f"{args.minimum_saving * 100:.1f}%"
                )
            if decoder.crc_errors:
                raise AssertionError(
                    f"FNB58 stream had {decoder.crc_errors} CRC errors"
                )
            print(
                f"FNB58 frames={decoder.valid_frames} "
                f"crc_errors={decoder.crc_errors} "
                f"format_errors={decoder.format_errors} result=OK"
            )
            return 0
        finally:
            try:
                await client.write_gatt_char(WRITE_UUID, STOP_STREAM, response=True)
                await client.stop_notify(NOTIFY_UUID)
            except Exception:
                pass


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", required=True)
    parser.add_argument("--meter-address", required=True)
    parser.add_argument("--meter-serial", type=int, default=0)
    parser.add_argument("--public-id", default="")
    parser.add_argument("--seconds", type=int, default=5, choices=range(1, 6))
    parser.add_argument("--cycles", type=int, default=6, choices=range(2, 121))
    parser.add_argument("--warmup", type=float, default=3.0)
    parser.add_argument("--idle-seconds", type=float, default=8.0)
    parser.add_argument("--transition-guard", type=float, default=1.0)
    parser.add_argument("--minimum-saving", type=float, default=0.20)
    parser.add_argument("--scan-timeout", type=float, default=10.0)
    args = parser.parse_args()
    total = args.seconds * args.cycles
    if args.warmup < 0 or args.idle_seconds < 2:
        parser.error("invalid idle timing")
    if args.transition_guard < 0 or 2 * args.transition_guard >= total - 2:
        parser.error("transition guard leaves no stable STOP window")
    if not 0.0 <= args.minimum_saving < 1.0:
        parser.error("minimum saving must be in [0, 1)")
    return asyncio.run(run(args))


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (AssertionError, OSError, RuntimeError, TimeoutError) as error:
        print(f"FNB58 deep-idle power HIL: FAIL: {error}", file=sys.stderr)
        raise SystemExit(1)

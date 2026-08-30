#!/usr/bin/env python3
"""Measure MK61 idle and external-Flash workload power with an FNB58 over BLE.

This is a read-only hardware qualification.  It verifies the exact calculator,
the FNB58 packet CRC, resident firmware CRC, SPI1 ownership and DMA telemetry,
then reports energy for an equal amount of Flash data.  ``bleak`` is the only
non-stdlib dependency; serial I/O uses the repository's termios HIL transport.
"""

from __future__ import annotations

import argparse
import asyncio
from dataclasses import dataclass
import re
import statistics
import struct
import sys
import time

from hil_rtc_alarm import Port


NOTIFY_UUID = "0000ffe4-0000-1000-8000-00805f9b34fb"
WRITE_UUID = "0000ffe9-0000-1000-8000-00805f9b34fb"
REQUEST_INFO = bytes((0xAA, 0x81, 0x00, 0xF4))
START_STREAM = bytes((0xAA, 0x82, 0x00, 0xA7))
STOP_STREAM = bytes((0xAA, 0x84, 0x00, 0x01))
KNOWN_LENGTHS = {0x03: 14, 0x04: 12, 0x05: 7, 0x06: 6, 0x07: 4, 0x08: 17}

SUMMARY = re.compile(
    r"(?m)^BENCH summary kind=flash bytes=(\d+) passes=(\d+) "
    r"min_us=(\d+) avg_us=(\d+) max_us=(\d+) read_Bps=(\d+) "
    r"crc=0x([0-9A-Fa-f]{8})\r?$"
)


@dataclass(frozen=True)
class Sample:
    timestamp: float
    voltage_v: float
    current_a: float
    power_w: float


@dataclass(frozen=True)
class Window:
    name: str
    started: float
    ended: float
    samples: tuple[Sample, ...]

    @property
    def duration_s(self) -> float:
        return self.ended - self.started

    def values(self, field: str) -> list[float]:
        return [getattr(sample, field) for sample in self.samples]

    def average(self, field: str) -> float:
        return statistics.fmean(self.values(field))

    def median(self, field: str) -> float:
        return statistics.median(self.values(field))

    def energy_j(self) -> float:
        return self.average("power_w") * self.duration_s


def crc16_xmodem(data: bytes) -> int:
    crc = 0
    for value in data:
        crc ^= value << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) & 0xFFFF if crc & 0x8000 else (
                crc << 1
            ) & 0xFFFF
    return crc


class Decoder:
    def __init__(self) -> None:
        self.buffer = bytearray()
        self.samples: list[Sample] = []
        self.info: dict[str, int] | None = None
        self.valid_frames = 0
        self.crc_errors = 0
        self.format_errors = 0

    def feed(self, chunk: bytes) -> None:
        self.buffer.extend(chunk)
        while self.buffer:
            sync = self.buffer.find(0xAA)
            if sync < 0:
                self.format_errors += len(self.buffer)
                self.buffer.clear()
                return
            if sync:
                self.format_errors += sync
                del self.buffer[:sync]
            if len(self.buffer) < 3:
                return
            frame_type = self.buffer[1]
            payload_length = self.buffer[2]
            if KNOWN_LENGTHS.get(frame_type) != payload_length:
                self.format_errors += 1
                del self.buffer[0]
                continue
            frame_length = payload_length + 4
            if len(self.buffer) < frame_length:
                return
            frame = bytes(self.buffer[:frame_length])
            if (crc16_xmodem(frame[:-1]) & 0xFF) != frame[-1]:
                self.crc_errors += 1
                del self.buffer[0]
                continue
            del self.buffer[:frame_length]
            self.valid_frames += 1
            self._decode(frame_type, frame[3:-1])

    def _decode(self, frame_type: int, payload: bytes) -> None:
        if frame_type == 0x03:
            self.info = {
                "model": struct.unpack_from("<H", payload, 0)[0],
                "firmware": struct.unpack_from("<H", payload, 2)[0],
                "serial": struct.unpack_from("<I", payload, 4)[0],
                "boot_count": struct.unpack_from("<I", payload, 8)[0],
            }
        elif frame_type == 0x04:
            self.samples.append(
                Sample(
                    time.monotonic(),
                    struct.unpack_from("<I", payload, 0)[0] / 10000.0,
                    struct.unpack_from("<I", payload, 4)[0] / 10000.0,
                    struct.unpack_from("<I", payload, 8)[0] / 10000.0,
                )
            )


async def wait_for(predicate, timeout: float, description: str) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        await asyncio.sleep(0.05)
    raise TimeoutError(f"timeout waiting for {description}")


async def capture_window(decoder: Decoder, name: str, duration: float) -> Window:
    started = time.monotonic()
    first_index = len(decoder.samples)
    await asyncio.sleep(duration)
    ended = time.monotonic()
    samples = tuple(
        sample
        for sample in decoder.samples[first_index:]
        if started <= sample.timestamp <= ended
    )
    if len(samples) < 5:
        raise AssertionError(
            f"FNB58 supplied only {len(samples)} samples during {name}"
        )
    return Window(name, started, ended, samples)


def parse_profile(report: str, dma: str) -> None:
    spi_line = next(
        (line for line in report.splitlines() if line.startswith("SPI1 backend=")),
        "",
    )
    if "backend=polling-arbiter" not in spi_line:
        raise AssertionError(f"shared SPI1 arbiter missing:\n{report}")
    for token in (
        "state=idle",
        "owner=none",
        "failures=0",
        "contentions=0",
        "double=0",
        "inactive=0",
        "wrong=0",
        "invalid=0",
        "latched=0",
    ):
        if token not in spi_line:
            raise AssertionError(f"bad SPI1 state ({token}):\n{report}")

    dma_line = next(
        (
            line
            for line in report.splitlines()
            if line.startswith("SPI1 DMA backend=")
        ),
        "",
    )
    if dma == "required":
        if not dma_line:
            raise AssertionError(f"DMA telemetry missing:\n{report}")
        for token in ("init_errors=0", "errors=0", "timeouts=0"):
            if token not in dma_line:
                raise AssertionError(f"bad DMA state ({token}):\n{report}")
        match = re.search(r"\btransfers=(\d+)\b.*\bbytes=(\d+)\b", dma_line)
        if not match or min(map(int, match.groups())) <= 0:
            raise AssertionError(f"DMA was not exercised:\n{report}")
    elif dma_line:
        raise AssertionError(f"DMA unexpectedly enabled:\n{report}")


def print_window(window: Window) -> None:
    currents = window.values("current_a")
    powers = window.values("power_w")
    print(
        f"POWER window={window.name} samples={len(window.samples)} "
        f"duration_s={window.duration_s:.3f} "
        f"voltage_avg_V={window.average('voltage_v'):.5f} "
        f"current_avg_mA={window.average('current_a') * 1000:.3f} "
        f"current_median_mA={window.median('current_a') * 1000:.3f} "
        f"current_min_mA={min(currents) * 1000:.3f} "
        f"current_max_mA={max(currents) * 1000:.3f} "
        f"power_avg_mW={window.average('power_w') * 1000:.3f} "
        f"power_min_mW={min(powers) * 1000:.3f} "
        f"power_max_mW={max(powers) * 1000:.3f} "
        f"energy_mJ={window.energy_j() * 1000:.3f}"
    )


async def run(args: argparse.Namespace) -> int:
    try:
        from bleak import BleakClient, BleakScanner
    except ImportError as error:
        raise RuntimeError(
            "bleak is required: python3 -m pip install bleak"
        ) from error

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

            with Port(args.port) as port:
                identity = await asyncio.to_thread(port.command, "identity")
                if "profile=classic-v3-uc1609" not in identity:
                    raise AssertionError(f"wrong calculator profile:\n{identity}")
                if args.public_id and f"public={args.public_id}" not in identity:
                    raise AssertionError(f"wrong calculator identity:\n{identity}")
                build_match = re.search(r"\bbuild=([0-9A-F]{8})\b", identity)
                if not build_match:
                    raise AssertionError(f"build ID missing:\n{identity}")
                print(
                    f"DEVICE public={args.public_id or 'verified'} "
                    f"build={build_match.group(1)} label={args.label}"
                )
                display = await asyncio.to_thread(port.command, "display")
                if "DISPLAY controller=UC1609 mode=graphics" not in display:
                    raise AssertionError(f"UC1609 not active:\n{display}")

                await asyncio.to_thread(port.command, 'print "POWER IDLE"')
                await asyncio.to_thread(port.command, "prof reset")
                await asyncio.sleep(args.warmup)
                idle = await capture_window(decoder, "idle", args.idle_seconds)

                await asyncio.to_thread(port.command, 'print "POWER FLASH"')
                started = time.monotonic()
                first_sample = len(decoder.samples)
                reference_crc = ""
                rates: list[int] = []
                for _ in range(args.rounds):
                    timeout = max(
                        20.0, args.bytes * args.passes / 500000.0 + 12.0
                    )
                    report = await asyncio.to_thread(
                        port.command,
                        f"bench flash {args.bytes} {args.passes}",
                        timeout,
                    )
                    match = SUMMARY.search(report)
                    if not match:
                        raise AssertionError(f"benchmark summary missing:\n{report}")
                    measured_bytes, passes, _, _, _, rate, crc = match.groups()
                    if int(measured_bytes) != args.bytes or int(passes) != args.passes:
                        raise AssertionError(f"wrong benchmark dimensions:\n{report}")
                    if reference_crc and crc.upper() != reference_crc:
                        raise AssertionError(
                            f"Flash CRC changed: {reference_crc} -> {crc.upper()}"
                        )
                    reference_crc = crc.upper()
                    rates.append(int(rate))
                ended = time.monotonic()
                active_samples = tuple(
                    sample
                    for sample in decoder.samples[first_sample:]
                    if started <= sample.timestamp <= ended
                )
                if len(active_samples) < 5:
                    raise AssertionError(
                        f"FNB58 supplied only {len(active_samples)} active samples"
                    )
                active = Window("flash", started, ended, active_samples)

                await asyncio.to_thread(port.command, 'print "POWER PASS"')
                await asyncio.sleep(args.cooldown)
                profile = await asyncio.to_thread(port.command, "prof")
                parse_profile(profile, args.dma)
                storage = await asyncio.to_thread(port.command, "df", 10.0)
                if "FIRMWARE CRC state=valid" not in storage:
                    raise AssertionError(f"resident firmware invalid:\n{storage}")
                crash = await asyncio.to_thread(port.command, "crash")
                if "CRASH none" not in crash:
                    raise AssertionError(f"fault during power run:\n{crash}")

            print_window(idle)
            print_window(active)
            total_bytes = args.bytes * args.passes * args.rounds
            print(
                f"WORKLOAD bytes={total_bytes} elapsed_s={active.duration_s:.3f} "
                f"effective_Bps={total_bytes / active.duration_s:.0f} "
                f"bench_Bps_median={statistics.median(rates):.0f} "
                f"crc={reference_crc} energy_mJ={active.energy_j() * 1000:.3f} "
                f"energy_mJ_per_MiB="
                f"{active.energy_j() * 1000 / (total_bytes / 1048576):.3f}"
            )
            print(
                f"FNB58 frames={decoder.valid_frames} crc_errors={decoder.crc_errors} "
                f"format_errors={decoder.format_errors} result=OK"
            )
            if decoder.crc_errors:
                raise AssertionError(
                    f"FNB58 stream had {decoder.crc_errors} CRC errors"
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
    parser.add_argument("--label", default="test")
    parser.add_argument("--dma", choices=("required", "forbidden"), required=True)
    parser.add_argument("--bytes", type=int, default=393216)
    parser.add_argument("--passes", type=int, default=20)
    parser.add_argument("--rounds", type=int, default=2)
    parser.add_argument("--warmup", type=float, default=3.0)
    parser.add_argument("--idle-seconds", type=float, default=6.0)
    parser.add_argument("--cooldown", type=float, default=1.0)
    parser.add_argument("--scan-timeout", type=float, default=10.0)
    args = parser.parse_args()
    if not 64 <= args.bytes <= 1048576:
        parser.error("--bytes must be in 64..1048576")
    if not 1 <= args.passes <= 20:
        parser.error("--passes must be in 1..20")
    if not 1 <= args.rounds <= 20:
        parser.error("--rounds must be in 1..20")
    if args.warmup < 0 or args.idle_seconds < 2 or args.cooldown < 0:
        parser.error("invalid timing interval")
    return asyncio.run(run(args))


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (AssertionError, OSError, RuntimeError, TimeoutError) as error:
        print(f"FNB58 Flash power HIL: FAIL: {error}", file=sys.stderr)
        raise SystemExit(1)

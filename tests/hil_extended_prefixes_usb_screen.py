#!/usr/bin/env python3
"""Check 1F execution and all 2F segment planes on the real USB Screen.

This test replaces the volatile calculator program and X. It does not write C6
or firmware. The target is pinned by public and build IDs, and the program is
cleared on exit. PNGs are saved for visual inspection of the received pixels.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import re
import time

from hil_multi_device_identity import parse_identity
from hil_portable_apps import ScreenPort
from hil_portable_system_apps import png


X_LINE = re.compile(r"(?m)^X\s*=\s*([+-]?[0-9.]+)\s+([+-]?[0-9]{2})\r?$")
IP_LINE = re.compile(r"(?m)^IP\s*=\s*(\d+)\r?$")
CELL_COUNT = 12
CELL_WIDTH = 16
FRAME_WIDTH = 192


def command(port: ScreenPort, text: str) -> str:
    report = port.command(text, timeout=8)
    if "failed!" in report or "BAD address!" in report or "Unknown command" in report:
        raise AssertionError(f"command failed: {text}\n{report}")
    return report


def expect_x(port: ScreenPort, value: int, ip: int | None = None) -> None:
    deadline = time.monotonic() + 5
    last = ""
    while time.monotonic() < deadline:
        last = command(port, "stk")
        x = X_LINE.search(last)
        address = IP_LINE.search(last)
        if x and address:
            actual = float(x.group(1)) * 10 ** int(x.group(2))
            if abs(actual - value) < 1e-7 and (ip is None or int(address.group(1)) == ip):
                return
    raise AssertionError(f"expected X={value}, IP={ip}; last stack:\n{last}")


def cell(frame: bytes, position: int) -> bytes:
    """The indicator occupies pages 3..6; omit the independent service row."""
    return b"".join(frame[page * FRAME_WIDTH + position * CELL_WIDTH:
                          page * FRAME_WIDTH + (position + 1) * CELL_WIDTH]
                    for page in range(3, 7))


def matching_segment_frame(frame: bytes, position: int, mask: int) -> bool:
    cells = [cell(frame, index) for index in range(CELL_COUNT)]
    return (bool(any(cells[position])) == bool(mask) and
            all(not any(cells[index]) for index in range(CELL_COUNT)
                if index != position))


def run_segment_case(port: ScreenPort, position: int, mask: int) -> bytes:
    command(port, "reinit")
    command(port, f"hin 0000 2F502F2A2F{position:02X}2F0E50")
    # The first 2F can promote AUTO to 112+RF and reset X. Seed it afterwards.
    command(port, f"poke X {mask}")
    start = len(port.frames)
    command(port, "run")
    expect_x(port, mask, ip=9)
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        for frame in port.frames[start:]:
            if matching_segment_frame(frame, position, mask):
                return frame
        port.pump(.1)
    raise AssertionError(
        f"no 2F framebuffer for position={position}, mask={mask}; "
        f"received {len(port.frames) - start} frames"
    )


def run_display_sequence(port: ScreenPort, code: str, value: int,
                         position: int, expected: bytes) -> bytes:
    command(port, "reinit")
    command(port, f"hin 0000 {code}")
    start = len(port.frames)
    command(port, "run")
    expect_x(port, value, ip=len(bytes.fromhex(code)))
    # RUN returns before the display service has published its final frame.
    port.pump(1.0)
    if len(port.frames) <= start:
        raise AssertionError(f"no USB Screen frame for {code}")
    frame = port.frames[-1]
    if cell(frame, position) != expected or any(
            any(cell(frame, index)) for index in range(CELL_COUNT)
            if index != position):
        raise AssertionError(f"wrong final USB Screen frame for {code}")
    return frame


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", required=True)
    parser.add_argument("--public-id", required=True)
    parser.add_argument("--build-id", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--confirm-ram-overwrite", action="store_true")
    args = parser.parse_args()
    if not args.confirm_ram_overwrite:
        parser.error("this test clears program RAM; pass --confirm-ram-overwrite")

    args.output_dir.mkdir(parents=True, exist_ok=True)
    with ScreenPort(args.port) as port:
        identity = parse_identity(command(port, "identity"))
        if (identity.public != args.public_id.upper() or
                identity.build != args.build_id.upper() or
                identity.profile != "classic-v3-uc1609"):
            raise AssertionError(f"wrong calculator or firmware: {identity}")
        print(f"device={identity.public} build={identity.build} profile={identity.profile}",
              flush=True)

        try:
            port.attach()
            command(port, "reinit")
            command(port, "hin 9968 0750")
            command(port, "hin 0000 1F519968")
            command(port, "run")
            expect_x(port, 7)
            print("1F reaches the highest addressable bank while USB Screen is active: OK",
                  flush=True)

            blank = run_segment_case(port, 0, 0)
            if any(any(cell(blank, index)) for index in range(CELL_COUNT)):
                raise AssertionError("2F zero mask did not leave a blank indicator")
            png(blank, args.output_dir / "mask-00-pos00.png")

            planes = []
            for bit in range(8):
                mask = 1 << bit
                frame = run_segment_case(port, 0, mask)
                plane = cell(frame, 0)
                if not any(plane) or plane in planes:
                    raise AssertionError(f"segment plane {bit} is empty or duplicated")
                planes.append(plane)
                png(frame, args.output_dir / f"mask-{mask:02x}-pos00.png")
                print(f"2F segment bit {bit}: OK", flush=True)

            combined = bytes(a | b | c | d | e | f | g | h
                             for a, b, c, d, e, f, g, h in zip(*planes))
            for position in (0, 9, 11):
                frame = run_segment_case(port, position, 255)
                if cell(frame, position) != combined:
                    raise AssertionError(
                        f"mask FF at position {position} differs from the eight planes"
                    )
                png(frame, args.output_dir / f"mask-ff-pos{position:02d}.png")
                print(f"2F mask FF at position {position}: OK", flush=True)

            seven = bytes(a | b | c for a, b, c in zip(*planes[:3]))
            auto = run_display_sequence(port, "2F0B2F2A0750", 7, 11, seven)
            png(auto, args.output_dir / "auto-seven-pos11.png")
            print("2F automatic publication of X: OK", flush=True)

            blank_cell = bytes(len(combined))
            held = run_display_sequence(port, "2F0B2F2A2F500750", 7, 11,
                                        blank_cell)
            png(held, args.output_dir / "held-blank.png")
            print("2F hold leaves changed X off screen: OK", flush=True)

            cleared = run_display_sequence(port, "2F0B2F2A072F0D50", 7, 11,
                                           blank_cell)
            png(cleared, args.output_dir / "cleared-blank.png")
            print("2F clear blanks the frame without clearing X: OK", flush=True)

            # The intervening 2F 52 ends digit-entry, so 08 enters a new 8
            # rather than appending to the preceding 7.
            resumed = run_display_sequence(
                port, "2F0B2F2A2F50072F520850", 8, 11, planes[3])
            png(resumed, args.output_dir / "resumed-eight-pos11.png")
            print("2F resume republishes later X changes: OK", flush=True)

            health = command(port, "df")
            if (f"expected=0x{identity.build}" not in health or
                    "FIRMWARE CRC state=valid" not in health):
                raise AssertionError(f"firmware CRC failed:\n{health}")
            if "CRASH none" not in command(port, "crash show"):
                raise AssertionError("firmware crash record appeared")
            print("USB Screen pixel planes, firmware CRC and crash status: OK",
                  flush=True)
        finally:
            try:
                command(port, "reinit")
            finally:
                if port.attached:
                    port.send(0x13)
                    port.pump(.3)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

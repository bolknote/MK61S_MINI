#!/usr/bin/env python3
"""Non-destructive WS0010 graphics/character mode-switch qualification.

The target is selected by its CDC path and optionally its canonical public ID.
Every iteration writes one bounded GDRAM pattern, verifies exclusive graphics
ownership, and returns through the full character-controller recovery path.
The test never changes resident firmware or C5 contents.
"""

from __future__ import annotations

import argparse
import re
import time

from hil_rtc_alarm import Port


IDENTITY = re.compile(
    r"(?m)^MK61 ID v=1 public=([0-9A-F]{16}).* "
    r"build=([0-9A-F]{8}) profile=([A-Za-z0-9._-]+)\r?$"
)
DISPLAY_FIELDS = re.compile(
    r"\bmode=(character|graphics)\b.*\bowner=([a-z]+)\b"
)
READBACK = re.compile(
    r"DISPLAY graphics readback pattern=([0-7]) bytes=200 "
    r"expected=([0-9A-F]{8}) actual=([0-9A-F]{8}) "
    r"mismatches=([0-9]+) dummy=0"
)


def require(report: str, needle: str) -> None:
    if needle not in report:
        raise AssertionError(f"missing {needle!r} in:\n{report}")


def display_state(port: Port) -> tuple[str, str, int, int, int]:
    report = port.command("display status", timeout=5.0)
    require(report, "DISPLAY controller=WS0010")
    require(report, "graphics=qualified gdram=100x16 visible=80x16")
    state = DISPLAY_FIELDS.search(report)
    timeouts = re.search(r"\bbf-timeouts=([0-9]+)\b", report)
    fault = re.search(r"\bbf-fault=([01])\b", report)
    reinitializations = re.search(r"\breinit=([0-9]+)\b", report)
    if not state or not timeouts or not fault or not reinitializations:
        raise AssertionError(f"invalid qualified WS0010 status:\n{report}")
    mode, owner = state.groups()
    return (
        mode,
        owner,
        int(timeouts.group(1)),
        int(fault.group(1)),
        int(reinitializations.group(1)),
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", required=True)
    parser.add_argument("--public-id")
    parser.add_argument("--cycles", type=int, default=1000)
    parser.add_argument("--progress-every", type=int, default=100)
    args = parser.parse_args()
    if not 1 <= args.cycles <= 10000:
        parser.error("--cycles must be 1..10000")
    if not 1 <= args.progress_every <= args.cycles:
        parser.error("--progress-every must be 1..cycles")

    started = time.monotonic()
    with Port(args.port) as port:
        identity_report = port.command("identity")
        identity = IDENTITY.search(identity_report)
        if not identity:
            raise AssertionError(f"not a canonical MK61 identity:\n{identity_report}")
        public_id, build_id, profile = identity.groups()
        if args.public_id and public_id != args.public_id.upper():
            raise AssertionError(
                f"wrong target: expected {args.public_id.upper()}, got {public_id}"
            )
        if profile != "mini-v3-ws0010":
            raise AssertionError(f"wrong profile for WS0010 HIL: {profile}")

        initial = display_state(port)
        if initial[0:2] != ("character", "none") or initial[3] != 0:
            raise AssertionError(f"unsafe initial display state: {initial}")

        for pattern in range(8):
            report = port.command(
                f"display test graphics-read {pattern}", timeout=8.0
            )
            result = READBACK.search(report)
            if not result:
                raise AssertionError(
                    f"invalid GDRAM readback report for pattern {pattern}:\n"
                    f"{report}"
                )
            returned_pattern, expected_crc, actual_crc, mismatches = (
                result.groups()
            )
            if (
                int(returned_pattern) != pattern
                or expected_crc != actual_crc
                or int(mismatches) != 0
            ):
                raise AssertionError(
                    f"GDRAM readback mismatch for pattern {pattern}:\n"
                    f"{report}"
                )

        after_readback = display_state(port)
        if after_readback[0:2] != ("character", "none"):
            raise AssertionError(
                f"character owner not restored after readback: {after_readback}"
            )
        if after_readback[2] != initial[2] or after_readback[3] != 0:
            raise AssertionError(
                f"busy-flag failure during GDRAM readback: {after_readback}"
            )
        if after_readback[4] - initial[4] != 8:
            raise AssertionError(
                "not every GDRAM readback used full character recovery: "
                f"reinit {initial[4]} -> {after_readback[4]}"
            )
        print(
            "gdram-readback=8/8 "
            f"reinit={initial[4]}->{after_readback[4]} "
            f"bf_timeouts={after_readback[2]}"
        )
        mode_switch_initial = after_readback

        for cycle in range(args.cycles):
            pattern = cycle & 7
            shown = port.command(
                f"display test graphics {pattern}", timeout=5.0
            )
            require(shown, f"DISPLAY graphics pattern={pattern} shown")

            if cycle == 0 or (cycle + 1) % args.progress_every == 0:
                active = display_state(port)
                if active[0:2] != ("graphics", "qualification"):
                    raise AssertionError(
                        f"graphics owner lost at cycle {cycle + 1}: {active}"
                    )
                if active[2] != mode_switch_initial[2] or active[3] != 0:
                    raise AssertionError(
                        f"busy-flag failure at cycle {cycle + 1}: {active}"
                    )

            restored = port.command("display test restore", timeout=5.0)
            require(restored, "DISPLAY character UI restored")

            if (cycle + 1) % args.progress_every == 0:
                current = display_state(port)
                if current[0:2] != ("character", "none"):
                    raise AssertionError(
                        f"character owner not restored at cycle {cycle + 1}: {current}"
                    )
                print(
                    f"cycles={cycle + 1}/{args.cycles} "
                    f"reinit={current[4]} bf_timeouts={current[2]}"
                )

        final = display_state(port)
        if final[0:2] != ("character", "none") or final[3] != 0:
            raise AssertionError(f"unsafe final display state: {final}")
        if final[2] != mode_switch_initial[2]:
            raise AssertionError(
                "busy-flag timeouts changed: "
                f"{mode_switch_initial[2]} -> {final[2]}"
            )
        if final[4] - mode_switch_initial[4] != args.cycles:
            raise AssertionError(
                "not every graphics transaction used full character recovery: "
                f"reinit {mode_switch_initial[4]} -> {final[4]}, "
                f"cycles={args.cycles}"
            )

        firmware = port.command("df", timeout=8.0)
        require(firmware, "FIRMWARE CRC state=valid")
        require(firmware, f"expected=0x{build_id}")
        require(firmware, f"build=0x{build_id}")
        require(firmware, f"actual=0x{build_id}")
        require(firmware, "backend=hardware")

        crash = port.command("crash show")
        require(crash, "CRASH none")
        require(crash, "layout=ok")

    elapsed = time.monotonic() - started
    print(
        "WS0010 graphics HIL: OK "
        f"public={public_id} build={build_id} cycles={args.cycles} "
        f"readback=8/8 elapsed_s={elapsed:.3f} "
        f"reinit={initial[4]}->{final[4]}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

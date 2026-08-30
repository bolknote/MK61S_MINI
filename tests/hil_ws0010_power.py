#!/usr/bin/env python3
"""Cycle WS0010 display/DC-DC power and verify controller health.

Uses only the Python standard library.  This is a non-destructive HIL test:
the visible display is restored on even when an assertion fails.
"""

from __future__ import annotations

import argparse
import re
import sys

from hil_rtc_alarm import IDENTITY, Port


DISPLAY = re.compile(
    r"(?m)^DISPLAY controller=WS0010 .*"
    r"bf-timeouts=(\d+) bf-fault=(\d+) .*"
    r"mode=([^ ]+) owner=([^ ]+) state=([^ ]+) pwr=([^ ]+) .*"
    r"init=([^ ]+) reinit=(\d+)\r?$"
)


def display_status(port: Port) -> tuple[int, int, str, str, str, str, str, int]:
    report = port.command("display status")
    match = DISPLAY.search(report)
    if not match:
        raise AssertionError(f"WS0010 status missing:\n{report}")
    timeouts, fault, mode, owner, state, power, init, reinit = match.groups()
    return (
        int(timeouts), int(fault), mode, owner, state, power, init, int(reinit)
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", required=True)
    parser.add_argument("--cycles", type=int, default=100, choices=range(1, 1001))
    args = parser.parse_args()

    port = Port(args.port)
    public_id = ""
    error: BaseException | None = None
    try:
        identity = port.command("identity")
        identity_match = IDENTITY.search(identity)
        if not identity_match:
            raise AssertionError(f"not an MK61 identity response:\n{identity}")
        public_id = identity_match.group(1)

        before = display_status(port)
        if before[1] != 0 or before[2:7] != (
            "character", "none", "on", "on", "ready"
        ):
            raise AssertionError(f"invalid initial WS0010 state: {before}")

        for cycle in range(1, args.cycles + 1):
            off = port.command("display off")
            if "DISPLAY off" not in off:
                raise AssertionError(f"display off failed at cycle {cycle}:\n{off}")
            on = port.command("display on")
            if "DISPLAY on" not in on:
                raise AssertionError(f"display on failed at cycle {cycle}:\n{on}")

        after = display_status(port)
        if after[0] != before[0] or after[1] != 0 or after[2:7] != (
            "character", "none", "on", "on", "ready"
        ):
            raise AssertionError(
                f"WS0010 did not recover cleanly: before={before} after={after}"
            )
        print(
            f"device={public_id} cycles={args.cycles} "
            f"bf_timeouts={after[0]} bf_fault={after[1]} "
            f"reinit={before[7]}->{after[7]}"
        )
        print("WS0010 power-cycle HIL: OK")
    except BaseException as exc:
        error = exc
    finally:
        try:
            port.command("display on")
        except BaseException as cleanup_error:
            if error is None:
                error = cleanup_error
        port.close()

    if error is not None:
        raise error
    return 0


if __name__ == "__main__":
    sys.exit(main())

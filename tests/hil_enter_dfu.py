#!/usr/bin/env python3
"""Verify an MK61 identity and request its built-in DFU transition."""

from __future__ import annotations

import argparse
import os
import time

from hil_rtc_alarm import IDENTITY, Port


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", required=True)
    args = parser.parse_args()

    with Port(args.port) as port:
        identity = port.command("identity")
        match = IDENTITY.search(identity)
        if not match:
            raise AssertionError(f"not an MK61 identity response:\n{identity}")
        print(f"device: {match.group(1)} path={args.port}")
        port.drain()
        port.write_line("dfu")
        # Closing a macOS tty immediately after write can discard bytes still
        # queued in the host driver.  The command intentionally has no reply:
        # firmware resets while executing it.
        time.sleep(0.20)

    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline and os.path.exists(args.port):
        time.sleep(0.05)
    if os.path.exists(args.port):
        raise TimeoutError(f"CDC port did not leave for DFU: {args.port}")
    print("DFU requested")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

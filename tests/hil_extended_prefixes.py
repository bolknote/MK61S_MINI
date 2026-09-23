#!/usr/bin/env python3
"""Exercise the 1F/2F extensions on one identified MK61s over its CDC terminal.

This test replaces the calculator's volatile program and stack, but never
modifies C6 files. Pass --confirm-ram-overwrite only after checking that the
current RAM program may be discarded. A successful run leaves RAM cleared.
"""

from __future__ import annotations

import argparse
import re
import time

from hil_multi_device_identity import parse_identity
from hil_rtc_alarm import Port


X_LINE = re.compile(r"(?m)^X\s*=\s*([+-]?[0-9.]+)\s+([+-]?[0-9]{2})\r?$")
IP_LINE = re.compile(r"(?m)^IP\s*=\s*(\d+)\r?$")


def command(port: Port, text: str) -> str:
    report = port.command(text, timeout=6.0)
    if "failed!" in report or "BAD address!" in report:
        raise AssertionError(f"command failed: {text}\n{report}")
    return report


def expect_x(port: Port, value: float, ip: int | None = None) -> None:
    deadline = time.monotonic() + 4.0
    last = ""
    while time.monotonic() < deadline:
        last = command(port, "stk")
        x = X_LINE.search(last)
        address = IP_LINE.search(last)
        if x and address:
            actual = float(x.group(1)) * 10 ** int(x.group(2))
            if (abs(actual - value) < 1e-7 and
                    (ip is None or int(address.group(1)) == ip)):
                return
        time.sleep(0.10)
    raise AssertionError(f"expected X={value}, IP={ip}; last stack:\n{last}")


def check_arithmetic_conditions(port: Port) -> None:
    """No settling NOP: compare all four predicates and both address forms."""
    expressions = ((bytes.fromhex('000E010911'), -19),
                   (bytes.fromhex('01090E010911'), 0),
                   (bytes.fromhex('01090E0011'), 19))
    count = 0
    for expression, value in expressions:
        conditions = ((0x57, 0x77, value == 0), (0x59, 0x97, value < 0),
                      (0x5C, 0xC7, value >= 0), (0x5E, 0xE7, value != 0))
        for direct, indirect, taken in conditions:
            for use_indirect in (False, True):
                command(port, 'reinit')
                setup = bytes.fromhex('02050047') if use_indirect else b''
                predicate = (bytes((0x1F, indirect)) if use_indirect else
                             bytes((0x1F, direct, 0x02, 0x50)))
                program = setup + expression + predicate + b'\x50'
                command(port, 'hin 0000 ' + program.hex().upper())
                command(port, 'hin 0250 50')
                command(port, 'run')
                # stk reports the local IP within a 112-byte bank.
                expect_x(port, value, ip=250 % 112 + 1 if taken else len(program))
                count += 1
    print(f'{count} direct/indirect conditions after subtraction without NOP: OK',
          flush=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", required=True)
    parser.add_argument("--public-id", required=True)
    parser.add_argument("--build-id", default="")
    parser.add_argument("--confirm-ram-overwrite", action="store_true")
    args = parser.parse_args()
    if not args.confirm_ram_overwrite:
        parser.error("this test clears program RAM; pass --confirm-ram-overwrite")

    with Port(args.port) as port:
        identity = parse_identity(command(port, "identity"))
        if identity.public != args.public_id.upper() or identity.profile != "classic-v3-uc1609":
            raise AssertionError(f"wrong calculator: {identity}")
        if args.build_id and identity.build != args.build_id.upper():
            raise AssertionError(
                f"wrong firmware: expected {args.build_id.upper()}, got {identity.build}"
            )
        print(f"device={identity.public} build={identity.build} profile={identity.profile}")

        command(port, "reinit")
        # In AUTO the prefix enables far memory; bank 2 remains unallocated.
        command(port, "hin 0000 1F510250")
        if "hin 0248 000000000000" not in command(port, "hout 0248 6"):
            raise AssertionError("unallocated bank did not read as zeros")
        command(port, "hin 0250 0750")
        if "hin 0250 0750" not in command(port, "hout 0250 2"):
            raise AssertionError("far bank readback differs from written bytes")
        if "hin 0248 000007500000" not in command(port, "hout 0248 6"):
            raise AssertionError("partial write did not leave unwritten bytes zero")
        command(port, "run")
        expect_x(port, 7.0)
        print("1F far jump and banked hin/hout: OK")

        command(port, "reinit")
        command(port, "hin 0250 0752")
        command(port, "hin 0000 1F5302500850")
        command(port, "run")
        expect_x(port, 8.0)
        print("1F far call and return: OK")

        command(port, "reinit")
        command(port, "hin 0000 511F")
        command(port, "hin 0025 0750")
        command(port, "run")
        expect_x(port, 7.0)
        print("ordinary 51 1F operand: OK")

        command(port, "reinit")
        for bank in range(1, 32):
            command(port, f"hin {bank * 112:04d} 0750")
        overflow = port.command("hin 3584 07", timeout=6.0)
        if "Program bank allocation failed!" not in overflow:
            raise AssertionError(f"33rd bank was not rejected:\n{overflow}")
        command(port, "hin 0000 1F513472")
        command(port, "run")
        expect_x(port, 7.0)
        print("32-slot limit and execution of a populated bank: OK")

        command(port, "reinit")
        command(port, "hin 0000 1F519968")
        if "hin 0112 00" not in command(port, "hout 0112 1"):
            raise AssertionError("reinit kept the old far-bank program")
        command(port, "hin 9968 0750")
        command(port, "run")
        expect_x(port, 7.0)
        print("reinit frees all bank slots; bank 89 can be reused: OK")

        command(port, "reinit")
        command(port, "hin 0000 2F2A2F0E50")
        # In AUTO, writing the first 2F switches to expanded memory and
        # reinitializes the core; seed X only after that transition.
        command(port, "poke X 255")
        command(port, "run")
        expect_x(port, 255.0, ip=5)
        if "DISPLAY controller=UC1609 mode=graphics" not in command(port, "display status"):
            raise AssertionError("UC1609 graphics mode is inactive")
        print("2F accepts mask 255 at former sign position: OK")

        check_arithmetic_conditions(port)
        health = command(port, "df")
        if (f"expected=0x{identity.build}" not in health or
                "FIRMWARE CRC state=valid" not in health):
            raise AssertionError(f"resident firmware failed CRC check:\n{health}")
        crash = command(port, "crash show")
        if "CRASH none" not in crash:
            raise AssertionError(f"firmware crash record appeared:\n{crash}")
        command(port, "reinit")
        print("hardware CRC and crash status: OK; program RAM cleared")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

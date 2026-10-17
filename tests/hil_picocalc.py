#!/usr/bin/env python3
"""Bounded USB/UART smoke test for the PicoCalc prototype (POSIX, stdlib only).

Select the Pico's port explicitly; the banner is checked before sending any
calculator keys. This test never sends BOOTSEL/reset or storage commands.
"""
import argparse
import json
import os
from pathlib import Path
import re
import select
import sys
import time


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--observe-seconds", type=float, default=0)
    parser.add_argument("--ui", action="store_true", help="Also check 0.2 menu input, language and independent fonts")
    args = parser.parse_args()
    if os.name != "posix":
        parser.error("This stdlib serial test currently supports macOS/Linux")
    if not 0 <= args.observe_seconds <= 30:
        parser.error("--observe-seconds must be 0..30")
    import termios
    import tty
    fd = os.open(args.port, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
    old = termios.tcgetattr(fd)
    transcript = []

    def read_for(seconds):
        result = bytearray()
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            ready, _, _ = select.select([fd], [], [], max(0, end - time.monotonic()))
            if ready:
                chunk = os.read(fd, 16384)
                if not chunk:
                    raise RuntimeError("Pico disconnected")
                result += chunk
                if len(result) > 1024 * 1024:
                    raise RuntimeError("Unexpected serial output volume")
        text = result.decode("utf-8", errors="replace")
        transcript.append(text)
        print(text, end="", flush=True)
        return text

    def query():
        os.write(fd, b"?")
        return read_for(0.5)

    def settled():
        end = time.monotonic() + 15
        while time.monotonic() < end:
            status = query()
            if "RUN=0 BUSY=0" in status:
                return status
        raise RuntimeError("Calculator input did not settle within 15 seconds")

    def x_value(text):
        matches = re.findall(r"X_RAW=\[([^\]]+)\]", text)
        if not matches or len(matches[-1]) != 14:
            raise RuntimeError("Missing raw X register")
        raw = matches[-1]
        mantissa = raw[:10].replace(" ", "").replace(",", ".")
        exponent = ("-" if raw[11] == "-" else "+") + raw[12:14]
        return float(mantissa) * (10 ** int(exponent))

    try:
        tty.setraw(fd)
        settings = termios.tcgetattr(fd)
        settings[4] = settings[5] = termios.B115200
        settings[2] |= termios.CLOCAL | termios.CREAD
        termios.tcsetattr(fd, termios.TCSANOW, settings)
        read_for(0.2)
        banner = query()
        if "MK61S PICOCALC PICO-H" not in banner:
            raise RuntimeError("Port did not identify as the MK61S PicoCalc prototype")
        settled()
        os.write(fd, b"m")
        math = read_for(1.0)
        if "MATH_TEST=OK failures=0" not in math:
            raise RuntimeError("Device math test failed")
        results = []
        for name, keys, expected in (("12 ENTER 34 +", b"\x0812\n34+", 46),
                                      ("sqrt(9)", b"\x089f-", 3),
                                      ("sin(90 DEG)", b"\x08d90f7", 1)):
            os.write(fd, keys)
            read_for(0.2)
            value = x_value(settled())
            if abs(value - expected) > 1e-7:
                raise RuntimeError(f"{name}: X={value}, expected {expected}")
            results.append({"case": name, "result": value, "passed": True})
        # Leave an empty input register for a subsequent physical-key check.
        os.write(fd, b"\x08")
        read_for(0.2)
        status = settled()
        ui_cases = []
        if args.ui:
            if "UI=CALCULATOR" not in status:
                raise RuntimeError("UI test must start on the calculator screen")

            def ui_step(keys, expected):
                os.write(fd, keys)
                read_for(0.25)
                state = query()
                if expected not in state:
                    raise RuntimeError(f"UI state missing: {expected}")
                return state

            ui_step(b"\t" + bytes([0xB5]) * 6, "UI=MAIN SELECT=0")
            blocked = ui_step(b"123", "UI=MAIN SELECT=0")
            if x_value(blocked) != 0:
                raise RuntimeError("Menu keys changed the calculator's X register")
            ui_cases.append("Menu owns input; X preserved")
            ui_step(bytes([0xB6, 0xB6, 0x0A]), "UI=SETTINGS SELECT=0")
            base = ui_step(bytes([0xB6] * 5), "UI=SETTINGS SELECT=5")
            language = re.search(r"LANG=(RU|EN)", base)[1]
            other = "EN" if language == "RU" else "RU"
            ui_step(bytes([0xB7]), "LANG=" + other)
            ui_step(bytes([0xB7]), "LANG=" + language)
            ui_cases.append("Live RU/EN selection and restoration")
            font_state = ui_step(bytes([0xB6, 0x0A]), "UI=FONTS SELECT=0")
            font, size = map(int, re.search(r"FONT=(\d)/(\d+)", font_state).groups())
            ui_step(bytes([0xB7]), f"FONT={1-font}/{size}")
            ui_step(bytes([0xB4]), f"FONT={font}/{size}")
            ui_cases.append("Independent calculator font selection and restoration")
            ui_step(bytes([0xB1]), "UI=SETTINGS SELECT=6")
            ui_step(bytes([0xB1]), "UI=MAIN SELECT=2")
            status = ui_step(bytes([0xB1]), "UI=CALCULATOR")
            if x_value(status) != 0:
                raise RuntimeError("Returning from menus changed X")
            deadline = time.monotonic() + 5
            while "SETTINGS=PENDING" in status and time.monotonic() < deadline:
                status = query()
            if "SETTINGS=SAVED" not in status:
                raise RuntimeError("Changed menu settings did not save to Pico flash")
            ui_cases.append("Deferred settings save to Pico flash")
        if args.observe_seconds:
            read_for(args.observe_seconds)
            status = query()
        report = {"profile": "picocalc-pico-h", "port": args.port,
                  "math_smoke_passed": True, "calculator_cases": results,
                  "keyboard_online": "KBD=OK" in status,
                  "panel_initialized": "PANEL_INIT=1" in status,
                  "physical_keys": int(re.findall(r"PHYSICAL_KEYS=(\d+)", status)[-1]),
                  "ui_cases": ui_cases,
                  "visual_confirmation": "requires user observation",
                  "transcript": "".join(transcript)}
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps(report, indent=2) + "\n")
        print("PicoCalc USB/core/math smoke test passed")
    finally:
        termios.tcsetattr(fd, termios.TCSANOW, old)
        os.close(fd)


if __name__ == "__main__":
    try:
        main()
    except (OSError, RuntimeError) as error:
        sys.exit(f"PicoCalc HIL failed: {error}")

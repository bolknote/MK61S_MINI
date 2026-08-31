#!/usr/bin/env python3
"""Stress stable MK61 identities across CDC reset and ROM DFU cycles.

The test is intentionally non-destructive for MCU Flash.  A DFU cycle uses a
one-byte *upload* from 0x08000000 followed by the DfuSe ``leave`` request; it
never downloads firmware.  Every return to CDC must reproduce the complete
identity tuple, and all connected targets must remain distinct.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import glob
import os
import re
import subprocess
import tempfile
import time

from hil_rtc_alarm import Port


IDENTITY_REPORT = re.compile(
    r"(?m)^MK61 ID v=1 public=([0-9A-F]{16}) short=([0-9A-F]{8}) "
    r"usb=([0-9A-F]{12}) volume=([0-9A-F]{8}) build=([0-9A-F]{8}) "
    r"profile=([A-Za-z0-9._-]+)\r?$"
)
DFU_STATUS = re.compile(
    r"(?m)^DFU status valid=(0|1) generation=([0-9]+) "
    r"stage=([a-z-]+) sources=0x([0-9A-Fa-f]+)\r?$"
)
DFU_SOURCE_RETRY = 1 << 3


@dataclass(frozen=True)
class Identity:
    public: str
    short: str
    usb: str
    volume: str
    build: str
    profile: str


@dataclass
class Target:
    path: str
    identity: Identity


def parse_identity(report: str) -> Identity:
    match = IDENTITY_REPORT.search(report)
    if not match:
        raise AssertionError(f"not a canonical MK61 identity response:\n{report}")
    identity = Identity(*match.groups())
    if identity.short != identity.public[-8:]:
        raise AssertionError(f"inconsistent public/short identity:\n{report}")
    return identity


def read_identity(path: str, timeout: float = 3.0) -> Identity:
    with Port(path) as port:
        return parse_identity(port.command("identity", timeout=timeout))


def candidate_ports() -> list[str]:
    candidates: list[str] = []
    for pattern in ("/dev/cu.usbmodem*", "/dev/ttyACM*"):
        for path in sorted(glob.glob(pattern)):
            if path not in candidates:
                candidates.append(path)
    return candidates


def wait_absent(path: str, timeout: float) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if not os.path.exists(path):
            return
        time.sleep(0.02)
    raise TimeoutError(f"CDC port did not disappear: {path}")


def wait_for_identity(expected: Identity, timeout: float) -> tuple[str, Identity]:
    deadline = time.monotonic() + timeout
    last_error = "no CDC candidates"
    while time.monotonic() < deadline:
        for path in candidate_ports():
            try:
                current = read_identity(path, timeout=1.5)
            except (OSError, TimeoutError, AssertionError) as error:
                last_error = f"{path}: {error}"
                continue
            if current.public == expected.public:
                return path, current
        time.sleep(0.08)
    raise TimeoutError(
        f"device {expected.public} did not return to CDC ({last_error})"
    )


def require_unchanged(expected: Identity, current: Identity) -> None:
    if current != expected:
        raise AssertionError(
            "device identity changed across re-enumeration:\n"
            f"expected={expected}\ncurrent={current}"
        )


def request_transition(target: Target, command: str, timeout: float) -> None:
    with Port(target.path) as port:
        current = parse_identity(port.command("identity"))
        require_unchanged(target.identity, current)
        port.drain()
        port.write_line(command)
        # A tty closed immediately after write can discard the final bytes on
        # macOS.  Both commands reset before producing another prompt.
        time.sleep(0.20)
    wait_absent(target.path, timeout)


def recovery_diagnostics(target: Target, timeout: float = 4.0) -> str:
    """Collect retained evidence after a failed ROM enumeration attempt."""
    try:
        path, current = wait_for_identity(target.identity, timeout)
        require_unchanged(target.identity, current)
        target.path = path
    except (OSError, TimeoutError, AssertionError) as error:
        return f"application did not return for diagnostics: {error}"

    reports: list[str] = []
    try:
        with Port(target.path) as port:
            for command in ("dfu status", "wdog", "crash"):
                try:
                    reports.append(port.command(command, timeout=3.0).strip())
                except (OSError, TimeoutError) as error:
                    reports.append(f"{command}: {type(error).__name__}: {error}")
    except OSError as error:
        reports.append(f"could not reopen {target.path}: {error}")
    return "\n".join(reports)


def verify_all(targets: list[Target], timeout: float) -> None:
    seen_paths: set[str] = set()
    seen_public: set[str] = set()
    for target in targets:
        path, current = wait_for_identity(target.identity, timeout)
        require_unchanged(target.identity, current)
        if path in seen_paths or current.public in seen_public:
            raise AssertionError("two targets resolved to the same CDC identity")
        seen_paths.add(path)
        seen_public.add(current.public)
        target.path = path


def reset_cycle(target: Target, reconnect_timeout: float) -> float:
    started = time.monotonic()
    request_transition(target, "rst now", timeout=4.0)
    path, current = wait_for_identity(target.identity, reconnect_timeout)
    require_unchanged(target.identity, current)
    target.path = path
    return time.monotonic() - started


def dfu_leave(
    target: Target, dfu_util: str, reconnect_timeout: float
) -> tuple[float, bool]:
    started = time.monotonic()
    request_transition(target, "dfu", timeout=5.0)
    deadline = time.monotonic() + 8.0
    last_output = ""
    last_list_output = ""
    attempt = 0
    with tempfile.TemporaryDirectory(prefix="mk61-dfu-leave-") as temporary:
        while time.monotonic() < deadline:
            # dfu-util intentionally refuses to overwrite an existing upload
            # destination.  A fresh name per retry also prevents a stale byte
            # from making an unsuccessful transfer look complete.
            upload = os.path.join(temporary, f"first-byte-{attempt}.bin")
            attempt += 1
            command = [
                dfu_util,
                "-d", "0483:df11",
                "-S", target.identity.usb,
                "-a", "0",
                "-s", "0x08000000:1:leave",
                "-U", upload,
            ]
            try:
                completed = subprocess.run(
                    command,
                    capture_output=True,
                    text=True,
                    timeout=6.0,
                    check=False,
                )
            except subprocess.TimeoutExpired as error:
                last_output = str(error)
                time.sleep(0.10)
                continue
            last_output = completed.stdout + completed.stderr
            if (
                completed.returncode == 0
                and "Upload done." in last_output
                and "Submitting leave request" in last_output
            ):
                break
            # Keep an unfiltered snapshot as evidence.  A failed exact-serial
            # selection must be distinguishable from a ROM DFU device that
            # enumerated under an unexpected descriptor, and from no USB DFU
            # enumeration at all.
            try:
                listed = subprocess.run(
                    [dfu_util, "-l"],
                    capture_output=True,
                    text=True,
                    timeout=2.0,
                    check=False,
                )
                last_list_output = listed.stdout + listed.stderr
            except subprocess.TimeoutExpired as error:
                last_list_output = str(error)
            time.sleep(0.10)
        else:
            diagnostics = recovery_diagnostics(target)
            raise TimeoutError(
                f"DFU {target.identity.usb} did not accept read+leave:\n"
                f"exact selection:\n{last_output}\n"
                f"unfiltered dfu-util -l:\n{last_list_output}\n"
                f"application diagnostics:\n{diagnostics}"
            )

    path, current = wait_for_identity(target.identity, reconnect_timeout)
    require_unchanged(target.identity, current)
    target.path = path
    with Port(target.path) as port:
        report = port.command("dfu status", timeout=3.0)
    match = DFU_STATUS.search(report)
    if not match:
        raise AssertionError(f"invalid retained DFU status:\n{report}")
    valid, _generation, stage, source_hex = match.groups()
    if valid != "1" or stage != "completed":
        raise AssertionError(f"DFU transaction did not complete cleanly:\n{report}")
    retried = (int(source_hex, 16) & DFU_SOURCE_RETRY) != 0
    return time.monotonic() - started, retried


def bounded_count(parser: argparse.ArgumentParser, value: int, name: str) -> int:
    if not 0 <= value <= 1000:
        parser.error(f"{name} must be in 0..1000")
    return value


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--port", action="append", required=True,
        help="initial MK61 CDC path; pass once per connected target",
    )
    parser.add_argument("--cdc-cycles", type=int, default=100)
    parser.add_argument("--dfu-cycles", type=int, default=20)
    parser.add_argument("--dfu-util")
    parser.add_argument("--reconnect-timeout", type=float, default=15.0)
    parser.add_argument("--progress-every", type=int, default=10)
    args = parser.parse_args()

    cdc_cycles = bounded_count(parser, args.cdc_cycles, "--cdc-cycles")
    dfu_cycles = bounded_count(parser, args.dfu_cycles, "--dfu-cycles")
    if len(args.port) < 2:
        parser.error("multi-device HIL requires at least two --port values")
    if len(set(args.port)) != len(args.port):
        parser.error("duplicate --port value")
    if dfu_cycles and not args.dfu_util:
        parser.error("--dfu-util is required when --dfu-cycles is non-zero")
    if args.dfu_util and not os.path.isfile(args.dfu_util):
        parser.error("--dfu-util does not name a file")
    if args.reconnect_timeout <= 0:
        parser.error("--reconnect-timeout must be positive")
    if args.progress_every <= 0:
        parser.error("--progress-every must be positive")

    targets = [Target(path, read_identity(path)) for path in args.port]
    if len({target.identity.public for target in targets}) != len(targets):
        raise AssertionError("connected ports do not have unique public IDs")
    if len({target.identity.usb for target in targets}) != len(targets):
        raise AssertionError("connected ports do not have unique USB serials")

    for target in targets:
        identity = target.identity
        print(
            f"target public={identity.public} usb={identity.usb} "
            f"build={identity.build} profile={identity.profile} path={target.path}",
            flush=True,
        )

    verify_all(targets, args.reconnect_timeout)
    started = time.monotonic()
    reset_total = 0.0
    for index in range(cdc_cycles):
        target = targets[index % len(targets)]
        reset_total += reset_cycle(target, args.reconnect_timeout)
        verify_all(targets, args.reconnect_timeout)
        completed = index + 1
        if completed % args.progress_every == 0 or completed == cdc_cycles:
            print(
                f"CDC {completed}/{cdc_cycles} last={target.identity.short} "
                f"avg={reset_total / completed:.3f}s",
                flush=True,
            )

    dfu_total = 0.0
    dfu_recovered = 0
    for index in range(dfu_cycles):
        target = targets[index % len(targets)]
        duration, retried = dfu_leave(
            target, args.dfu_util, args.reconnect_timeout
        )
        dfu_total += duration
        if retried:
            dfu_recovered += 1
        verify_all(targets, args.reconnect_timeout)
        completed = index + 1
        if completed % args.progress_every == 0 or completed == dfu_cycles:
            print(
                f"DFU {completed}/{dfu_cycles} last={target.identity.short} "
                f"avg={dfu_total / completed:.3f}s "
                f"recovered={dfu_recovered}",
                flush=True,
            )

    verify_all(targets, args.reconnect_timeout)
    elapsed = time.monotonic() - started
    print(
        f"MULTI IDENTITY OK targets={len(targets)} cdc={cdc_cycles} "
        f"dfu={dfu_cycles} dfu_recovered={dfu_recovered} "
        f"elapsed={elapsed:.3f}s",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

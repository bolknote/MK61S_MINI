#!/usr/bin/env python3
"""Run one evidence-producing qualification across the two F411 boards.

The runner deliberately orchestrates the already qualified, single-purpose HIL
programs instead of reimplementing their protocols.  Targets are selected by
their canonical 64-bit public identity after every reset, never by a mutable
``/dev/cu.*`` name.  An FNB58, when requested, is accepted only for the
Classic V3/UC1609 target; the WS0010 target is never assumed to share the same
power path.

``smoke`` is intended for development.  ``release`` uses the established soak
counts and is deliberately long.  Both modes leave a versioned JSON report,
a human-readable Markdown summary and the complete output of every child HIL.
No test writes MCU firmware or user C5 data.  The optional ROM-DFU test uploads
one byte and leaves, matching ``hil_multi_device_identity.py``.
"""

from __future__ import annotations

import argparse
import asyncio
from dataclasses import asdict, dataclass
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys
import time
from typing import Iterable

from hil_multi_device_identity import (
    Identity,
    Target,
    candidate_ports,
    read_identity,
    wait_for_identity,
)


SCHEMA = "mk61-hil-release-evidence-v1"
UC1609_PROFILE = "classic-v3-uc1609"
WS0010_PROFILE = "mini-v3-ws0010"
F411_MIN_OBSERVED_STACK_REMAINING = 12 * 1024
REQUIRED_PROFILES = (UC1609_PROFILE, WS0010_PROFILE)
ROLE_BY_PROFILE = {
    UC1609_PROFILE: "uc1609",
    WS0010_PROFILE: "ws0010",
}
SAFE_NAME = re.compile(r"[^a-z0-9]+")


@dataclass(frozen=True)
class QualificationStep:
    name: str
    script: str
    arguments: tuple[str, ...]
    timeout_seconds: float
    target_roles: tuple[str, ...] = ()
    requires_meter: bool = False


@dataclass
class StepResult:
    name: str
    status: str
    command: list[str]
    started_utc: str
    duration_seconds: float
    return_code: int | None
    log: str
    log_sha256: str
    error: str = ""


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def slug(value: str) -> str:
    cleaned = SAFE_NAME.sub("-", value.lower()).strip("-")
    return cleaned or "step"


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8", errors="replace")).hexdigest()


def git_value(root: Path, *arguments: str) -> str:
    completed = subprocess.run(
        ["git", *arguments], cwd=root, capture_output=True, text=True,
        check=False,
    )
    return completed.stdout.strip() if completed.returncode == 0 else ""


def identify_ports(paths: Iterable[str]) -> dict[str, Target]:
    """Return the exact required profile pair or raise on ambiguity."""
    by_role: dict[str, Target] = {}
    errors: list[str] = []
    for path in paths:
        try:
            identity = read_identity(path)
        except (OSError, TimeoutError, AssertionError) as error:
            errors.append(f"{path}: {error}")
            continue
        role = ROLE_BY_PROFILE.get(identity.profile)
        if role is None:
            continue
        if role in by_role:
            other = by_role[role]
            raise AssertionError(
                f"ambiguous {role}: {other.path}={other.identity.public}, "
                f"{path}={identity.public}"
            )
        by_role[role] = Target(path, identity)

    missing = [
        ROLE_BY_PROFILE[profile]
        for profile in REQUIRED_PROFILES
        if ROLE_BY_PROFILE[profile] not in by_role
    ]
    if missing:
        detail = "; ".join(errors[-4:]) or "no responsive CDC candidates"
        raise AssertionError(
            f"missing required MK61 target(s): {', '.join(missing)} ({detail})"
        )
    identities = [target.identity for target in by_role.values()]
    if len({identity.public for identity in identities}) != len(identities):
        raise AssertionError("the two hardware profiles resolved to one public ID")
    if len({identity.usb for identity in identities}) != len(identities):
        raise AssertionError("the two hardware profiles resolved to one USB ID")
    return by_role


def require_expected_ids(
    targets: dict[str, Target], uc1609_id: str, ws0010_id: str
) -> None:
    expected = {"uc1609": uc1609_id.upper(), "ws0010": ws0010_id.upper()}
    for role, value in expected.items():
        if value and targets[role].identity.public != value:
            raise AssertionError(
                f"wrong {role} board: expected {value}, "
                f"got {targets[role].identity.public}"
            )


def resolve_target(target: Target, timeout: float = 15.0) -> str:
    path, current = wait_for_identity(target.identity, timeout)
    if current != target.identity:
        raise AssertionError(
            f"identity changed for {target.identity.public}: "
            f"{target.identity} -> {current}"
        )
    target.path = path
    return path


def qualification_plan(
    mode: str, include_meter: bool, include_dfu: bool,
    include_flash_power: bool, include_direct_stop: bool = False,
    include_stop_power: bool = False,
) -> list[QualificationStep]:
    if mode not in ("smoke", "release"):
        raise ValueError(f"unknown qualification mode: {mode}")
    release = mode == "release"
    cdc_cycles = 100 if release else 2
    dfu_cycles = 20 if release and include_dfu else 0
    spi_iterations = 100 if release else 5
    graphics_cycles = 1000 if release else 16

    steps = [
        QualificationStep(
            "two-board identity and reconnect",
            "hil_multi_device_identity.py",
            (
                "--port", "{uc1609_port}",
                "--port", "{ws0010_port}",
                "--cdc-cycles", str(cdc_cycles),
                "--dfu-cycles", str(dfu_cycles),
                "--progress-every", "10" if release else "1",
                "{dfu_arguments}",
            ),
            900.0 if release else 90.0,
            ("uc1609", "ws0010"),
        ),
        QualificationStep(
            "UC1609 shared SPI1 and DMA",
            "hil_uc1609_spi1.py",
            (
                "--port", "{uc1609_port}",
                "--public-id", "{uc1609_public}",
                "--iterations", str(spi_iterations),
                "--bytes", "65536",
                "--dma", "required",
            ),
            1800.0 if release else 120.0,
            ("uc1609",),
        ),
        QualificationStep(
            "WS0010 GDRAM and character recovery",
            "hil_ws0010_graphics.py",
            (
                "--port", "{ws0010_port}",
                "--public-id", "{ws0010_public}",
                "--cycles", str(graphics_cycles),
                "--progress-every", "100" if release else str(graphics_cycles),
            ),
            600.0 if release else 120.0,
            ("ws0010",),
        ),
        QualificationStep(
            "UC1609 production runtime health",
            "hil_runtime_health.py",
            (
                "--port", "{uc1609_port}",
                "--public-id", "{uc1609_public}",
                "--profile", UC1609_PROFILE,
                "--minimum-stack-remaining",
                str(F411_MIN_OBSERVED_STACK_REMAINING),
            ),
            60.0,
            ("uc1609",),
        ),
        QualificationStep(
            "WS0010 production runtime health",
            "hil_runtime_health.py",
            (
                "--port", "{ws0010_port}",
                "--public-id", "{ws0010_public}",
                "--profile", WS0010_PROFILE,
                "--minimum-stack-remaining",
                str(F411_MIN_OBSERVED_STACK_REMAINING),
            ),
            60.0,
            ("ws0010",),
        ),
    ]
    if include_direct_stop:
        stop_cycles = 1000 if release else 5
        steps.extend((
            QualificationStep(
                "UC1609 direct STOP recovery",
                "hil_deep_idle.py",
                (
                    "--port", "{uc1609_port}", "--seconds", "1",
                    "--cycles", str(stop_cycles), "--wake", "rtc",
                ),
                1300.0 if release else 60.0,
                ("uc1609",),
            ),
            QualificationStep(
                "WS0010 direct STOP recovery",
                "hil_deep_idle.py",
                (
                    "--port", "{ws0010_port}", "--seconds", "1",
                    "--cycles", str(stop_cycles), "--wake", "rtc",
                ),
                1300.0 if release else 60.0,
                ("ws0010",),
            ),
        ))
    if include_meter and include_stop_power:
        steps.append(QualificationStep(
            "UC1609 FNB58 idle and STOP power",
            "hil_fnb58_deep_idle_power.py",
            (
                "--port", "{uc1609_port}",
                "--public-id", "{uc1609_public}",
                "--meter-address", "{meter_address}",
                "--meter-serial", "{meter_serial}",
                "--seconds", "5",
                "--cycles", "120" if release else "6",
            ),
            750.0 if release else 120.0,
            ("uc1609",),
            True,
        ))
    if include_meter and include_flash_power:
        steps.append(QualificationStep(
            "UC1609 FNB58 Flash DMA energy",
            "hil_fnb58_flash_power.py",
            (
                "--port", "{uc1609_port}",
                "--public-id", "{uc1609_public}",
                "--meter-address", "{meter_address}",
                "--meter-serial", "{meter_serial}",
                "--label", "release" if release else "smoke",
                "--dma", "required",
                # At the qualified DMA rate three passes finish before five
                # BLE measurement frames arrive.  Sixteen keeps smoke short
                # while providing a statistically usable active window.
                "--passes", "20" if release else "16",
                "--rounds", "2" if release else "1",
                "--idle-seconds", "6" if release else "3",
                "--warmup", "3" if release else "1",
            ),
            900.0 if release else 180.0,
            ("uc1609",),
            True,
        ))
    return steps


def _device_name(device: object) -> str:
    return str(getattr(device, "name", "") or "")


def select_meter(devices: Iterable[object], meter_serial: int) -> object:
    candidates = [device for device in devices if _device_name(device).upper().startswith("FNB58")]
    if meter_serial:
        suffix = f"{meter_serial:06d}"
        candidates = [device for device in candidates if suffix in _device_name(device)]
    if len(candidates) != 1:
        names = ", ".join(_device_name(device) or "<unnamed>" for device in candidates)
        raise AssertionError(
            f"expected one FNB58 for serial {meter_serial or 'any'}, "
            f"found {len(candidates)}: {names or '-'}"
        )
    return candidates[0]


async def discover_meter(meter_serial: int, timeout: float) -> tuple[str, str]:
    try:
        from bleak import BleakScanner
    except ImportError as error:
        raise RuntimeError(
            "FNB58 auto-discovery requires bleak: python3 -m pip install bleak"
        ) from error
    devices = await BleakScanner.discover(timeout=timeout)
    device = select_meter(devices, meter_serial)
    address = str(getattr(device, "address", "") or "")
    if not address:
        raise AssertionError(f"FNB58 {_device_name(device)} has no BLE address")
    return address, _device_name(device)


def materialize_arguments(
    step: QualificationStep,
    targets: dict[str, Target],
    meter_address: str,
    meter_serial: int,
    dfu_util: str,
) -> list[str]:
    values = {
        "uc1609_port": targets["uc1609"].path,
        "uc1609_public": targets["uc1609"].identity.public,
        "ws0010_port": targets["ws0010"].path,
        "ws0010_public": targets["ws0010"].identity.public,
        "meter_address": meter_address,
        "meter_serial": str(meter_serial),
    }
    result: list[str] = []
    for argument in step.arguments:
        if argument == "{dfu_arguments}":
            if dfu_util:
                result.extend(("--dfu-util", dfu_util))
            continue
        result.append(argument.format(**values))
    return result


def run_step(
    root: Path,
    output: Path,
    python: str,
    step: QualificationStep,
    targets: dict[str, Target],
    meter_address: str,
    meter_serial: int,
    dfu_util: str,
) -> StepResult:
    for role in step.target_roles:
        resolve_target(targets[role])
    arguments = materialize_arguments(
        step, targets, meter_address, meter_serial, dfu_util
    )
    command = [python, str(root / "tests" / step.script), *arguments]
    started_utc = utc_now()
    started = time.monotonic()
    return_code: int | None = None
    error = ""
    try:
        completed = subprocess.run(
            command, cwd=root, capture_output=True, text=True,
            timeout=step.timeout_seconds, check=False,
        )
        return_code = completed.returncode
        log_text = completed.stdout + completed.stderr
        status = "passed" if completed.returncode == 0 else "failed"
        if status == "failed":
            error = f"child exited with status {completed.returncode}"
    except subprocess.TimeoutExpired as timeout_error:
        stdout = timeout_error.stdout or ""
        stderr = timeout_error.stderr or ""
        if isinstance(stdout, bytes):
            stdout = stdout.decode(errors="replace")
        if isinstance(stderr, bytes):
            stderr = stderr.decode(errors="replace")
        log_text = stdout + stderr
        status = "failed"
        error = f"timeout after {step.timeout_seconds:.0f}s"
    duration = time.monotonic() - started
    log_name = f"{slug(step.name)}.log"
    (output / log_name).write_text(log_text, encoding="utf-8")
    print(log_text, end="" if not log_text or log_text.endswith("\n") else "\n")
    print(
        f"STEP {status.upper()} name={step.name!r} duration={duration:.3f}s",
        flush=True,
    )
    return StepResult(
        step.name, status, command, started_utc, duration, return_code,
        log_name, sha256_text(log_text), error,
    )


def target_record(role: str, target: Target) -> dict[str, str]:
    return {"role": role, "path": target.path, **asdict(target.identity)}


def markdown_report(evidence: dict[str, object]) -> str:
    lines = [
        "# MK61 hardware qualification",
        "",
        f"- Result: **{str(evidence['result']).upper()}**",
        f"- Mode: `{evidence['mode']}`",
        f"- Git: `{evidence['git']['sha']}`",
        f"- Started: `{evidence['started_utc']}`",
        f"- Finished: `{evidence['finished_utc']}`",
        "",
        "## Targets",
        "",
        "| Role | Public ID | USB ID | Build | Profile |",
        "|---|---|---|---|---|",
    ]
    for target in evidence["targets"]:
        lines.append(
            f"| {target['role']} | `{target['public']}` | `{target['usb']}` | "
            f"`{target['build']}` | `{target['profile']}` |"
        )
    meter = evidence["meter"]
    lines.extend(("", "## Meter", ""))
    if meter["enabled"]:
        lines.append(
            f"FNB58 `{meter['name'] or meter['address']}` serial "
            f"`{meter['serial']}` was assigned only to `uc1609`."
        )
    else:
        lines.append("FNB58 measurements were not requested.")
    lines.extend(("", "## Steps", "", "| Step | Status | Duration | Log |", "|---|---:|---:|---|"))
    for step in evidence["steps"]:
        lines.append(
            f"| {step['name']} | {step['status']} | "
            f"{step['duration_seconds']:.3f} s | [{step['log']}]({step['log']}) |"
        )
    lines.append("")
    return "\n".join(lines)


def write_evidence(output: Path, evidence: dict[str, object]) -> None:
    output.mkdir(parents=True, exist_ok=True)
    temporary_json = output / "evidence.json.tmp"
    temporary_json.write_text(
        json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    os.replace(temporary_json, output / "evidence.json")
    temporary_md = output / "report.md.tmp"
    temporary_md.write_text(markdown_report(evidence), encoding="utf-8")
    os.replace(temporary_md, output / "report.md")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("smoke", "release"), default="smoke")
    parser.add_argument("--port", action="append", default=[])
    parser.add_argument("--uc1609-id", default="")
    parser.add_argument("--ws0010-id", default="")
    parser.add_argument(
        "--fnb58", default="",
        help="BLE address/UUID, 'auto', or omit to skip power tests",
    )
    parser.add_argument("--fnb58-serial", type=int, default=0)
    parser.add_argument("--fnb58-scan-timeout", type=float, default=10.0)
    parser.add_argument(
        "--fnb58-flash", action="store_true",
        help="also measure UC1609 Flash/DMA energy",
    )
    parser.add_argument(
        "--fnb58-stop", action="store_true",
        help="run legacy disconnecting STOP power test; requires a matching qualification image",
    )
    parser.add_argument(
        "--direct-stop", action="store_true",
        help="run direct disconnecting STOP HIL; production USB-aware images normally need real host suspend instead",
    )
    parser.add_argument("--dfu-util", default="")
    parser.add_argument("--skip-dfu", action="store_true")
    parser.add_argument("--keep-going", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    root = Path(__file__).resolve().parent.parent
    paths = args.port or candidate_ports()
    targets = identify_ports(paths)
    require_expected_ids(targets, args.uc1609_id, args.ws0010_id)

    meter_address = args.fnb58
    meter_name = ""
    if meter_address == "auto":
        meter_address, meter_name = asyncio.run(discover_meter(
            args.fnb58_serial, args.fnb58_scan_timeout
        ))
    include_meter = bool(meter_address)
    if (args.fnb58_flash or args.fnb58_stop) and not include_meter:
        parser.error("FNB58 power tests require --fnb58")
    if include_meter and not (args.fnb58_flash or args.fnb58_stop):
        parser.error("--fnb58 requires --fnb58-flash and/or --fnb58-stop")

    dfu_util = args.dfu_util or shutil.which("dfu-util") or ""
    include_dfu = args.mode == "release" and not args.skip_dfu
    if include_dfu and not dfu_util:
        parser.error("release DFU qualification needs --dfu-util or --skip-dfu")

    sha = git_value(root, "rev-parse", "HEAD") or "unknown"
    timestamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    output = args.output or root / ".build" / "hil-release" / f"{timestamp}-{sha[:8]}"
    if output.exists() and any(output.iterdir()):
        parser.error(f"output directory is not empty: {output}")
    output.mkdir(parents=True, exist_ok=True)

    started_utc = utc_now()
    evidence: dict[str, object] = {
        "schema": SCHEMA,
        "result": "running",
        "mode": args.mode,
        "started_utc": started_utc,
        "finished_utc": "",
        "host": {
            "platform": platform.platform(),
            "python": sys.version.split()[0],
        },
        "git": {
            "sha": sha,
            "status": git_value(root, "status", "--porcelain"),
        },
        "targets": [
            target_record(role, targets[role]) for role in ("uc1609", "ws0010")
        ],
        "meter": {
            "enabled": include_meter,
            "role": "uc1609" if include_meter else "",
            "address": meter_address,
            "name": meter_name,
            "serial": args.fnb58_serial,
        },
        "steps": [],
    }
    write_evidence(output, evidence)

    plan = qualification_plan(
        args.mode, include_meter, include_dfu, args.fnb58_flash,
        args.direct_stop, args.fnb58_stop,
    )
    print(f"REPORT directory={output}")
    for role in ("uc1609", "ws0010"):
        identity = targets[role].identity
        print(
            f"TARGET role={role} public={identity.public} usb={identity.usb} "
            f"build={identity.build} profile={identity.profile}"
        )
    if include_meter:
        print(
            f"METER role=uc1609 address={meter_address} "
            f"serial={args.fnb58_serial} name={meter_name or '-'}"
        )

    failed = False
    for step in plan:
        try:
            result = run_step(
                root, output, sys.executable, step, targets,
                meter_address, args.fnb58_serial, dfu_util,
            )
        except (AssertionError, OSError, TimeoutError) as error:
            result = StepResult(
                step.name, "failed", [], utc_now(), 0.0, None, "", "",
                f"{type(error).__name__}: {error}",
            )
        evidence["steps"].append(asdict(result))
        if result.status != "passed":
            failed = True
        evidence["result"] = "failed" if failed else "running"
        evidence["finished_utc"] = utc_now()
        write_evidence(output, evidence)
        if failed and not args.keep_going:
            break

    evidence["result"] = "failed" if failed else "passed"
    evidence["finished_utc"] = utc_now()
    # Paths may change across reset; record the last canonical resolution.
    for role in ("uc1609", "ws0010"):
        try:
            resolve_target(targets[role])
        except (AssertionError, OSError, TimeoutError):
            pass
    evidence["targets"] = [
        target_record(role, targets[role]) for role in ("uc1609", "ws0010")
    ]
    write_evidence(output, evidence)
    print(
        f"QUALIFICATION {str(evidence['result']).upper()} "
        f"report={output / 'report.md'}"
    )
    return 1 if failed else 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (AssertionError, OSError, RuntimeError, TimeoutError) as error:
        print(f"Hardware qualification: FAIL: {error}", file=sys.stderr)
        raise SystemExit(1)

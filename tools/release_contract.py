#!/usr/bin/env python3
"""Validate and expose the MK61 firmware release contract.

The JSON file beside this module is deliberately data-only.  Bash,
PowerShell, CMake and GitHub Actions consume it through this program instead
of maintaining independent profile and budget tables.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import sys
from typing import Any, Iterable, Sequence


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = Path(__file__).with_name("release-contract.json")
ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")
DEFINE_RE = re.compile(r"^[A-Z_][A-Z0-9_]*(?:=[A-Za-z0-9_+.,/-]+)?$")
FEATURE_KEYS = (
    "focal",
    "basic",
    "wbmp",
    "markdown",
    "chip8",
    "usb_screen",
    "ws0010_graphics",
    "extended_font_settings",
    "user_explorer",
    "math_backend",
    "lto",
)
CASE_TSV_FIELDS = (
    "id",
    "profile",
    "optimization",
    "defines",
    "artifact",
    "flash_capacity",
    "flash_min_headroom",
    "ram_capacity",
    "ram_limit",
    "stack_frame_limit",
    "product",
    "publish",
    "usb_suspend",
    "ws0010_graphics",
    *FEATURE_KEYS,
)


class ContractError(ValueError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ContractError(message)


def require_keys(value: dict[str, Any], required: set[str], where: str) -> None:
    missing = required - value.keys()
    require(not missing, f"{where}: missing keys: {', '.join(sorted(missing))}")


def integer(value: Any, where: str, *, minimum: int = 0) -> int:
    require(type(value) is int and value >= minimum,
            f"{where}: expected integer >= {minimum}")
    return value


def boolean(value: Any, where: str) -> bool:
    require(type(value) is bool, f"{where}: expected boolean")
    return value


def identifier(value: Any, where: str) -> str:
    require(isinstance(value, str) and ID_RE.fullmatch(value) is not None,
            f"{where}: invalid identifier {value!r}")
    return value


def definition(value: Any, where: str) -> str:
    require(isinstance(value, str) and DEFINE_RE.fullmatch(value) is not None,
            f"{where}: invalid compiler definition {value!r}")
    return value


def load_contract(path: Path = DEFAULT_MANIFEST) -> dict[str, Any]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ContractError(f"cannot read {path}: {error}") from error
    validate_contract(raw)
    return raw


def validate_contract(raw: Any) -> None:
    require(isinstance(raw, dict), "manifest root must be an object")
    require_keys(raw, {"schema", "toolchain", "profiles", "cases",
                       "comparison_budgets"}, "manifest")
    require(raw["schema"] == 1, "manifest.schema: only version 1 is supported")

    toolchain = raw["toolchain"]
    require(isinstance(toolchain, dict), "toolchain must be an object")
    require_keys(toolchain, {"arduino_cli", "stm32_core",
                             "stm32_package_url", "gnu_arm",
                             "cmsis", "cmsis_dsp",
                             "libraries"},
                 "toolchain")
    for key in ("arduino_cli", "stm32_core", "stm32_package_url",
                "gnu_arm", "cmsis", "cmsis_dsp"):
        require(isinstance(toolchain[key], str) and toolchain[key],
                f"toolchain.{key}: expected non-empty string")
    require(isinstance(toolchain["libraries"], dict)
            and toolchain["libraries"],
            "toolchain.libraries: expected non-empty object")
    for name, version in toolchain["libraries"].items():
        require(isinstance(name, str) and name and isinstance(version, str)
                and version, "toolchain.libraries: invalid name/version")

    profiles = raw["profiles"]
    require(isinstance(profiles, list) and profiles,
            "profiles must be a non-empty array")
    profile_by_id: dict[str, dict[str, Any]] = {}
    for index, profile in enumerate(profiles):
        where = f"profiles[{index}]"
        require(isinstance(profile, dict), f"{where}: expected object")
        require_keys(profile, {"id", "platform", "display", "defines",
                               "graphics", "artifacts"}, where)
        profile_id = identifier(profile["id"], f"{where}.id")
        require(profile_id not in profile_by_id,
                f"duplicate profile id: {profile_id}")
        for key in ("platform", "display"):
            identifier(profile[key], f"{where}.{key}")
        require(isinstance(profile["defines"], list),
                f"{where}.defines: expected array")
        defines = [definition(item, f"{where}.defines")
                   for item in profile["defines"]]
        require(len(defines) == len(set(defines)),
                f"{where}.defines: duplicate definition")
        boolean(profile["graphics"], f"{where}.graphics")
        artifacts = profile["artifacts"]
        require(isinstance(artifacts, dict),
                f"{where}.artifacts: expected object")
        require(set(artifacts) == {"f401", "f411"},
                f"{where}.artifacts: exactly f401 and f411 are required")
        for mcu, artifact in artifacts.items():
            require(isinstance(artifact, str) and artifact
                    and re.fullmatch(r"[A-Za-z0-9._-]+", artifact),
                    f"{where}.artifacts.{mcu}: invalid artifact stem")
        profile_by_id[profile_id] = profile

    cases = raw["cases"]
    require(isinstance(cases, list) and cases,
            "cases must be a non-empty array")
    case_ids: set[str] = set()
    group_counts: dict[str, int] = {}
    for index, case in enumerate(cases):
        where = f"cases[{index}]"
        require(isinstance(case, dict), f"{where}: expected object")
        require_keys(case, {"id", "groups", "mcu", "builder", "profile",
                            "product", "publish", "budgets"}, where)
        case_id = identifier(case["id"], f"{where}.id")
        require(case_id not in case_ids, f"duplicate case id: {case_id}")
        case_ids.add(case_id)
        groups = case["groups"]
        require(isinstance(groups, list) and groups,
                f"{where}.groups: expected non-empty array")
        group_ids = [identifier(item, f"{where}.groups") for item in groups]
        require(len(group_ids) == len(set(group_ids)),
                f"{where}.groups: duplicate group")
        for group in group_ids:
            group_counts[group] = group_counts.get(group, 0) + 1
        require(case["mcu"] in ("f401", "f411"),
                f"{where}.mcu: expected f401 or f411")
        require(case["builder"] in ("arduino", "gcc"),
                f"{where}.builder: expected arduino or gcc")
        require(case["profile"] in profile_by_id,
                f"{where}.profile: unknown profile {case['profile']!r}")
        boolean(case["product"], f"{where}.product")
        boolean(case["publish"], f"{where}.publish")
        require(not case["publish"] or case["product"],
                f"{where}: a published case must be a product")

        defines = case.get("defines", [])
        require(isinstance(defines, list), f"{where}.defines: expected array")
        combined = list(profile_by_id[case["profile"]]["defines"])
        combined.extend(definition(item, f"{where}.defines") for item in defines)
        names = [item.split("=", 1)[0] for item in combined]
        require(len(names) == len(set(names)),
                f"{where}: compiler definition is overridden twice")

        if case["builder"] == "arduino":
            require(case.get("optimization") in ("osstd", "oslto"),
                    f"{where}.optimization: expected osstd or oslto")
            expect = case.get("expect")
            require(isinstance(expect, dict), f"{where}.expect: expected object")
            require_keys(expect, {"usb_suspend", "ws0010_graphics"},
                         f"{where}.expect")
            boolean(expect["usb_suspend"], f"{where}.expect.usb_suspend")
            require(expect["ws0010_graphics"] is None
                    or type(expect["ws0010_graphics"]) is bool,
                    f"{where}.expect.ws0010_graphics: expected boolean/null")
            require("features" not in case,
                    f"{where}: Arduino case must use defines, not features")
        else:
            require("optimization" not in case,
                    f"{where}: GCC optimization is controlled by lto feature")
            features = case.get("features")
            require(isinstance(features, dict),
                    f"{where}.features: expected object")
            require(set(features) == set(FEATURE_KEYS),
                    f"{where}.features: expected exactly {', '.join(FEATURE_KEYS)}")
            for key, value in features.items():
                require(type(value) is int and value in (0, 1),
                        f"{where}.features.{key}: expected 0 or 1")

        artifact = case.get("artifact")
        if artifact is not None:
            require(isinstance(artifact, str)
                    and re.fullmatch(r"[A-Za-z0-9._-]+", artifact),
                    f"{where}.artifact: invalid artifact stem")
        resolved = resolve_artifact(case, profile_by_id)
        require(bool(resolved), f"{where}: no artifact for {case['mcu']}")

        budgets = case["budgets"]
        require(isinstance(budgets, dict), f"{where}.budgets: expected object")
        require_keys(budgets, {"flash_capacity", "flash_min_headroom",
                               "stack_frame_limit"}, f"{where}.budgets")
        flash_capacity = integer(budgets["flash_capacity"],
                                 f"{where}.budgets.flash_capacity", minimum=1)
        flash_headroom = integer(budgets["flash_min_headroom"],
                                 f"{where}.budgets.flash_min_headroom")
        require(flash_headroom <= flash_capacity,
                f"{where}: Flash headroom exceeds capacity")
        integer(budgets["stack_frame_limit"],
                f"{where}.budgets.stack_frame_limit", minimum=1)
        has_ram_capacity = "ram_capacity" in budgets
        has_ram_limit = "ram_limit" in budgets
        require(has_ram_capacity == has_ram_limit,
                f"{where}: RAM capacity and limit must appear together")
        if has_ram_capacity:
            ram_capacity = integer(budgets["ram_capacity"],
                                   f"{where}.budgets.ram_capacity", minimum=1)
            ram_limit = integer(budgets["ram_limit"],
                                f"{where}.budgets.ram_limit", minimum=1)
            require(ram_limit <= ram_capacity,
                    f"{where}: RAM limit exceeds capacity")
        if "markdown_app_max" in budgets:
            integer(budgets["markdown_app_max"],
                    f"{where}.budgets.markdown_app_max", minimum=1)
        if case["mcu"] == "f401" and case["product"]:
            require(flash_headroom >= 8192,
                    f"{where}: F401 product needs at least 8192 B headroom")

    required_groups = {
        "f411-release", "f411-stop", "f401-arduino",
        "f401-product", "f401-capability",
    }
    require(required_groups <= group_counts.keys(),
            "manifest is missing release groups: "
            + ", ".join(sorted(required_groups - group_counts.keys())))

    comparisons = raw["comparison_budgets"]
    require(isinstance(comparisons, dict) and comparisons,
            "comparison_budgets must be a non-empty object")
    for key, value in comparisons.items():
        require(re.fullmatch(r"[a-z][a-z0-9_]*", key) is not None,
                f"comparison_budgets: invalid key {key!r}")
        integer(value, f"comparison_budgets.{key}")


def profile_index(contract: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {profile["id"]: profile for profile in contract["profiles"]}


def case_index(contract: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {case["id"]: case for case in contract["cases"]}


def resolve_artifact(case: dict[str, Any],
                     profiles: dict[str, dict[str, Any]]) -> str:
    explicit = case.get("artifact")
    if explicit:
        return explicit
    return profiles[case["profile"]]["artifacts"][case["mcu"]]


def combined_defines(case: dict[str, Any],
                     profiles: dict[str, dict[str, Any]]) -> list[str]:
    return [*profiles[case["profile"]]["defines"], *case.get("defines", [])]


def cases_in_group(contract: dict[str, Any], group: str) -> list[dict[str, Any]]:
    selected = [case for case in contract["cases"] if group in case["groups"]]
    require(selected, f"unknown or empty release group: {group}")
    return selected


def scalar_text(value: Any) -> str:
    # Bash treats TAB as IFS whitespace and collapses adjacent delimiters.
    # Use an explicit sentinel so every row always has CASE_TSV_FIELDS columns.
    if value is None or value == "":
        return "-"
    if type(value) is bool:
        return "1" if value else "0"
    return str(value)


def flattened_case(case: dict[str, Any],
                   profiles: dict[str, dict[str, Any]]) -> dict[str, Any]:
    budgets = case["budgets"]
    expect = case.get("expect", {})
    features = case.get("features", {})
    return {
        "id": case["id"],
        "profile": case["profile"],
        "optimization": case.get("optimization", ""),
        "defines": " ".join(f"-D{item}" for item in combined_defines(case, profiles)),
        "artifact": resolve_artifact(case, profiles),
        "flash_capacity": budgets["flash_capacity"],
        "flash_min_headroom": budgets["flash_min_headroom"],
        "ram_capacity": budgets.get("ram_capacity", ""),
        "ram_limit": budgets.get("ram_limit", ""),
        "stack_frame_limit": budgets["stack_frame_limit"],
        "product": case["product"],
        "publish": case["publish"],
        "usb_suspend": expect.get("usb_suspend"),
        "ws0010_graphics": expect.get("ws0010_graphics"),
        **{key: features.get(key, "") for key in FEATURE_KEYS},
    }


def write_json(value: Any, destination: Path | None = None) -> str:
    text = json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if destination is not None:
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(text, encoding="utf-8", newline="\n")
    return text


def command_arguments(command: str) -> list[str]:
    if os.name != "nt":
        return shlex.split(command)
    # compile_commands generated by CMake normally provides ``arguments``.
    # Keep the fallback conservative instead of guessing Windows quoting.
    return [command.split(maxsplit=1)[0]]


def discover_binutils(compile_commands: Path) -> tuple[Path, Path]:
    try:
        entries = json.loads(compile_commands.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ContractError(f"cannot read compile database: {error}") from error
    require(isinstance(entries, list) and entries,
            "compile database must be a non-empty array")
    entry = entries[0]
    require(isinstance(entry, dict), "compile database entry must be an object")
    arguments = entry.get("arguments")
    if isinstance(arguments, list) and arguments and isinstance(arguments[0], str):
        compiler = Path(arguments[0])
    else:
        command = entry.get("command")
        require(isinstance(command, str) and command,
                "compile database entry has no compiler command")
        compiler = Path(command_arguments(command)[0])
    if not compiler.is_absolute():
        directory = entry.get("directory")
        require(isinstance(directory, str),
                "relative compiler path has no compile directory")
        compiler = Path(directory) / compiler
    suffix = ".exe" if compiler.suffix.lower() == ".exe" else ""
    prefix = compiler.name
    for ending in ("g++" + suffix, "gcc" + suffix, "c++" + suffix,
                   "cc" + suffix):
        if prefix.endswith(ending):
            prefix = prefix[:-len(ending)]
            break
    size = compiler.with_name(prefix + "size" + suffix)
    nm = compiler.with_name(prefix + "nm" + suffix)
    require(size.is_file(), f"size tool not found beside compiler: {size}")
    require(nm.is_file(), f"nm tool not found beside compiler: {nm}")
    return size, nm


def run_tool(arguments: Sequence[str]) -> str:
    try:
        completed = subprocess.run(arguments, capture_output=True, text=True,
                                   check=False)
    except OSError as error:
        raise ContractError(f"cannot execute {arguments[0]}: {error}") from error
    require(completed.returncode == 0,
            f"{arguments[0]} failed ({completed.returncode}): "
            f"{completed.stderr.strip()}")
    return completed.stdout


def parse_size_summary(output: str) -> dict[str, int]:
    for line in output.splitlines():
        fields = line.split()
        if len(fields) >= 6 and all(item.isdigit() for item in fields[:4]):
            text, data, bss, total = map(int, fields[:4])
            require(text + data + bss == total,
                    "size summary has inconsistent totals")
            return {"text": text, "data": data, "bss": bss,
                    "total": total, "static_ram": data + bss}
    raise ContractError("could not parse size summary")


def parse_sections(output: str) -> list[dict[str, int | str]]:
    sections: list[dict[str, int | str]] = []
    for line in output.splitlines():
        match = re.match(r"^\s*(\.[^\s]+)\s+(\d+)\s+", line)
        if match:
            sections.append({"name": match.group(1),
                             "bytes": int(match.group(2), 10)})
    require(sections, "could not parse ELF section sizes")
    return sorted(sections, key=lambda item: str(item["name"]))


def parse_symbols(output: str, limit: int = 10) -> list[dict[str, Any]]:
    symbols: list[dict[str, Any]] = []
    for line in output.splitlines():
        match = re.match(r"^\s*([0-9]+)\s+([0-9]+)\s+(\S)\s+(.+)$", line)
        if not match:
            continue
        byte_count = int(match.group(2), 10)
        if byte_count == 0:
            continue
        symbols.append({
            "address": int(match.group(1), 10),
            "bytes": byte_count,
            "type": match.group(3),
            "name": match.group(4),
        })
    symbols.sort(key=lambda item: (-item["bytes"], item["name"], item["address"]))
    return symbols[:limit]


def load_stack_summary(path: Path | None) -> dict[str, Any] | None:
    if path is None:
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ContractError(f"cannot read stack summary {path}: {error}") from error
    require(isinstance(value, dict) and value.get("schema") == 1,
            "stack summary has unsupported schema")
    integer(value.get("max_frame"), "stack summary max_frame")
    return value


def resource_report(contract: dict[str, Any], case_id: str, elf: Path,
                    binary: Path, compile_commands: Path | None,
                    size_tool: Path | None, nm_tool: Path | None,
                    stack_summary_path: Path | None) -> dict[str, Any]:
    cases = case_index(contract)
    require(case_id in cases, f"unknown release case: {case_id}")
    case = cases[case_id]
    require(elf.is_file(), f"ELF does not exist: {elf}")
    require(binary.is_file(), f"BIN does not exist: {binary}")
    if size_tool is None or nm_tool is None:
        require(compile_commands is not None,
                "compile database is required to discover binutils")
        discovered_size, discovered_nm = discover_binutils(compile_commands)
        size_tool = size_tool or discovered_size
        nm_tool = nm_tool or discovered_nm
    require(size_tool.is_file(), f"size tool does not exist: {size_tool}")
    require(nm_tool.is_file(), f"nm tool does not exist: {nm_tool}")

    summary = parse_size_summary(run_tool([str(size_tool), "-d", str(elf)]))
    sections = parse_sections(run_tool([str(size_tool), "-A", "-d", str(elf)]))
    section_sizes = {str(item["name"]): int(item["bytes"])
                     for item in sections}
    if ".data" in section_sizes and ".bss" in section_sizes:
        static_ram = (section_sizes[".data"] + section_sizes[".bss"]
                      + section_sizes.get(".noinit", 0))
        reserved_ram = section_sizes.get("._user_heap_stack", 0)
        summary["static_ram"] = static_ram
        summary["linked_ram"] = static_ram + reserved_ram
        summary["linked_reserve"] = reserved_ram
    symbols = parse_symbols(run_tool([
        str(nm_tool), "-S", "--size-sort", "--radix=d", "-C", str(elf)
    ]))
    stack = load_stack_summary(stack_summary_path)
    budgets = case["budgets"]
    binary_size = binary.stat().st_size
    flash_free = budgets["flash_capacity"] - binary_size
    violations: list[str] = []
    if flash_free < budgets["flash_min_headroom"]:
        violations.append(
            f"Flash free {flash_free} < {budgets['flash_min_headroom']}")
    if "ram_limit" in budgets and summary["static_ram"] > budgets["ram_limit"]:
        violations.append(
            f"static RAM {summary['static_ram']} > {budgets['ram_limit']}")
    if stack is not None and stack["max_frame"] > budgets["stack_frame_limit"]:
        violations.append(
            f"stack frame {stack['max_frame']} > {budgets['stack_frame_limit']}")

    profiles = profile_index(contract)
    return {
        "schema": 1,
        "case": case_id,
        "mcu": case["mcu"],
        "profile": case["profile"],
        "artifact": resolve_artifact(case, profiles),
        "product": case["product"],
        "budgets": budgets,
        "binary": {
            "bytes": binary_size,
            "flash_free": flash_free,
            "sha256": hashlib.sha256(binary.read_bytes()).hexdigest(),
        },
        "elf": {"summary": summary, "sections": sections,
                "largest_symbols": symbols},
        "stack": stack,
        "status": "ok" if not violations else "failed",
        "violations": violations,
    }


def report_markdown(report: dict[str, Any]) -> str:
    binary = report["binary"]
    summary = report["elf"]["summary"]
    budgets = report["budgets"]
    lines = [
        f"# Resource report: {report['case']}",
        "",
        f"Status: **{report['status'].upper()}**",
        "",
        "| Resource | Used | Capacity/limit | Free |",
        "|---|---:|---:|---:|",
        f"| Sealed Flash | {binary['bytes']} | {budgets['flash_capacity']} | "
        f"{binary['flash_free']} |",
        f"| Static RAM | {summary['static_ram']} | "
        f"{budgets.get('ram_limit', 'reported only')} | "
        f"{budgets.get('ram_capacity', 0) - summary['static_ram'] if 'ram_capacity' in budgets else '—'} |",
    ]
    stack = report.get("stack")
    if stack is not None:
        lines.append(
            f"| Largest stack frame | {stack['max_frame']} | "
            f"{budgets['stack_frame_limit']} | "
            f"{budgets['stack_frame_limit'] - stack['max_frame']} |")
    lines.extend(["", "## Ten largest ELF symbols", "",
                  "| Bytes | Type | Symbol |", "|---:|:---:|---|"])
    for symbol in report["elf"]["largest_symbols"]:
        safe_name = str(symbol["name"]).replace("|", "\\|")
        lines.append(f"| {symbol['bytes']} | {symbol['type']} | `{safe_name}` |")
    if report["violations"]:
        lines.extend(["", "## Violations", ""])
        lines.extend(f"- {item}" for item in report["violations"])
    return "\n".join(lines) + "\n"


def aggregate_reports(paths: Iterable[Path]) -> dict[str, Any]:
    reports: list[dict[str, Any]] = []
    seen: set[str] = set()
    for path in sorted(paths):
        try:
            report = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as error:
            raise ContractError(f"cannot read resource report {path}: {error}") from error
        require(isinstance(report, dict) and report.get("schema") == 1,
                f"unsupported resource report: {path}")
        case_id = report.get("case")
        require(isinstance(case_id, str) and case_id not in seen,
                f"duplicate/invalid resource report case: {case_id!r}")
        seen.add(case_id)
        reports.append(report)
    require(reports, "no resource reports supplied")
    reports.sort(key=lambda item: item["case"])
    return {
        "schema": 1,
        "status": "ok" if all(item.get("status") == "ok" for item in reports)
        else "failed",
        "reports": reports,
    }


def aggregate_markdown(aggregate: dict[str, Any]) -> str:
    lines = ["# MK61 release resources", "",
             f"Status: **{aggregate['status'].upper()}**", "",
             "| Case | Flash used | Flash free | Static RAM | Max frame | Status |",
             "|---|---:|---:|---:|---:|:---:|"]
    for report in aggregate["reports"]:
        stack = report.get("stack")
        max_frame = stack["max_frame"] if stack is not None else "—"
        lines.append(
            f"| {report['case']} | {report['binary']['bytes']} | "
            f"{report['binary']['flash_free']} | "
            f"{report['elf']['summary']['static_ram']} | {max_frame} | "
            f"{report['status']} |")
    return "\n".join(lines) + "\n"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("validate")

    toolchain = subparsers.add_parser("toolchain")
    toolchain.add_argument("--field", required=True)

    profiles = subparsers.add_parser("profiles")
    profiles.add_argument("--format", choices=("ids", "json"), default="ids")

    profile = subparsers.add_parser("profile")
    profile.add_argument("--id", required=True)
    profile.add_argument("--format", choices=("json", "cmake"), default="json")

    cases = subparsers.add_parser("cases")
    cases.add_argument("--group", required=True)
    cases.add_argument("--format", choices=("tsv", "json", "count"),
                       default="tsv")

    case = subparsers.add_parser("case")
    case.add_argument("--id", required=True)
    case.add_argument("--format", choices=("json", "tsv"), default="json")

    comparison = subparsers.add_parser("comparison")
    comparison.add_argument("--key", required=True)

    report = subparsers.add_parser("resource-report")
    report.add_argument("--case", required=True)
    report.add_argument("--elf", type=Path, required=True)
    report.add_argument("--bin", type=Path, required=True)
    report.add_argument("--compile-commands", type=Path)
    report.add_argument("--size-tool", type=Path)
    report.add_argument("--nm-tool", type=Path)
    report.add_argument("--stack-summary", type=Path)
    report.add_argument("--output-prefix", type=Path, required=True)

    aggregate = subparsers.add_parser("aggregate-reports")
    aggregate.add_argument("--report", type=Path, action="append", default=[])
    aggregate.add_argument("--reports-below", type=Path, action="append",
                           default=[])
    aggregate.add_argument("--output-prefix", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        contract = load_contract(args.manifest)
        profiles = profile_index(contract)
        if args.command == "validate":
            print(
                f"release contract: OK profiles={len(contract['profiles'])} "
                f"cases={len(contract['cases'])}")
        elif args.command == "toolchain":
            if args.field in ("arduino_cli", "stm32_core",
                              "stm32_package_url", "gnu_arm", "cmsis",
                              "cmsis_dsp"):
                print(contract["toolchain"][args.field])
            elif args.field.startswith("library:"):
                name = args.field.split(":", 1)[1]
                require(name in contract["toolchain"]["libraries"],
                        f"unknown toolchain library: {name}")
                print(contract["toolchain"]["libraries"][name])
            else:
                raise ContractError(f"unknown toolchain field: {args.field}")
        elif args.command == "profiles":
            if args.format == "json":
                print(write_json(contract["profiles"]), end="")
            else:
                print("\n".join(profile["id"] for profile in contract["profiles"]))
        elif args.command == "profile":
            require(args.id in profiles, f"unknown profile: {args.id}")
            selected = profiles[args.id]
            if args.format == "cmake":
                print(";".join(selected["defines"]))
            else:
                print(write_json(selected), end="")
        elif args.command in ("cases", "case"):
            if args.command == "cases":
                selected_cases = cases_in_group(contract, args.group)
                output_format = args.format
            else:
                indexed = case_index(contract)
                require(args.id in indexed, f"unknown release case: {args.id}")
                selected_cases = [indexed[args.id]]
                output_format = args.format
            if output_format == "count":
                print(len(selected_cases))
            elif output_format == "json":
                if args.command == "case":
                    value = dict(selected_cases[0])
                    value["resolved_artifact"] = resolve_artifact(
                        selected_cases[0], profiles)
                    value["combined_defines"] = combined_defines(
                        selected_cases[0], profiles)
                else:
                    value = [flattened_case(item, profiles)
                             for item in selected_cases]
                print(write_json(value), end="")
            else:
                for selected in selected_cases:
                    value = flattened_case(selected, profiles)
                    print("\t".join(scalar_text(value[field])
                                    for field in CASE_TSV_FIELDS))
        elif args.command == "comparison":
            require(args.key in contract["comparison_budgets"],
                    f"unknown comparison budget: {args.key}")
            print(contract["comparison_budgets"][args.key])
        elif args.command == "resource-report":
            report = resource_report(
                contract, args.case, args.elf, args.bin, args.compile_commands,
                args.size_tool, args.nm_tool, args.stack_summary)
            json_path = args.output_prefix.with_suffix(".json")
            markdown_path = args.output_prefix.with_suffix(".md")
            write_json(report, json_path)
            markdown_path.parent.mkdir(parents=True, exist_ok=True)
            markdown_path.write_text(report_markdown(report), encoding="utf-8",
                                     newline="\n")
            print(f"resource report: {report['status'].upper()} {args.case}")
            return 0 if report["status"] == "ok" else 1
        elif args.command == "aggregate-reports":
            paths = list(args.report)
            for root in args.reports_below:
                paths.extend(root.rglob("resource-report.json"))
                paths.extend(root.rglob("resource-*.json"))
            aggregate = aggregate_reports(set(paths))
            write_json(aggregate, args.output_prefix.with_suffix(".json"))
            markdown_path = args.output_prefix.with_suffix(".md")
            markdown_path.parent.mkdir(parents=True, exist_ok=True)
            markdown_path.write_text(aggregate_markdown(aggregate),
                                     encoding="utf-8", newline="\n")
            print(f"aggregate resource report: {aggregate['status'].upper()} "
                  f"cases={len(aggregate['reports'])}")
            return 0 if aggregate["status"] == "ok" else 1
        return 0
    except (ContractError, OSError, UnicodeError) as error:
        print(f"release contract: FAIL: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

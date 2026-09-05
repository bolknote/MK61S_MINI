#!/usr/bin/env python3
"""Enforce bounded ARM stack frames from GCC ``-fstack-usage`` reports.

This is deliberately a per-frame gate, not a claim that GCC's ``.su`` files
describe the complete call chain.  Runtime high-water painting and the MPU
guard cover composed call paths; this gate catches a newly oversized frame or
an unbounded dynamic allocation before firmware reaches hardware.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
import re
import sys


# The production MPU policy reserves a 16 KiB stack.  The current largest
# frame is EditFocalSlot at 4904 bytes; 5120 preserves a small build-noise
# margin while still requiring review before any single function consumes
# nearly one third of the complete budget.
DEFAULT_MAX_FRAME = 5120


class StackUsageError(ValueError):
    pass


@dataclass(frozen=True)
class Record:
    report: Path
    description: str
    bytes: int
    qualifier: str

    @property
    def unbounded(self) -> bool:
        tokens = set(self.qualifier.split(","))
        return "dynamic" in tokens and "bounded" not in tokens


def parse_line(report: Path, line_number: int, line: str) -> Record:
    fields = line.rsplit("\t", 2)
    if len(fields) != 3:
        raise StackUsageError(
            f"{report}:{line_number}: malformed stack-usage record"
        )
    description, byte_text, qualifier = fields
    try:
        byte_count = int(byte_text, 10)
    except ValueError as error:
        raise StackUsageError(
            f"{report}:{line_number}: invalid byte count {byte_text!r}"
        ) from error
    if byte_count < 0:
        raise StackUsageError(
            f"{report}:{line_number}: negative byte count {byte_count}"
        )

    tokens = set(qualifier.split(","))
    if not tokens or not tokens <= {"static", "dynamic", "bounded"}:
        raise StackUsageError(
            f"{report}:{line_number}: unknown qualifier {qualifier!r}"
        )
    if ("static" in tokens) == ("dynamic" in tokens):
        raise StackUsageError(
            f"{report}:{line_number}: invalid qualifier {qualifier!r}"
        )
    if "bounded" in tokens and "dynamic" not in tokens:
        raise StackUsageError(
            f"{report}:{line_number}: invalid qualifier {qualifier!r}"
        )
    return Record(report, description, byte_count, qualifier)


def read_records(root: Path) -> tuple[list[Path], list[Record]]:
    reports = sorted(root.rglob("*.su"))
    if not reports:
        raise StackUsageError(f"no .su reports below {root}")
    records: list[Record] = []
    for report in reports:
        for line_number, raw_line in enumerate(
            report.read_text(encoding="utf-8").splitlines(), start=1
        ):
            if raw_line:
                records.append(parse_line(report, line_number, raw_line))
    if not records:
        raise StackUsageError(f"all .su reports below {root} are empty")
    return reports, records


def policy_failures(records: list[Record], maximum: int) -> list[str]:
    failures: list[str] = []
    for record in records:
        if record.unbounded:
            failures.append(
                f"unbounded dynamic frame: {record.description} "
                f"({record.bytes} bytes, {record.report})"
            )
        if record.bytes > maximum:
            failures.append(
                f"frame exceeds {maximum} bytes: {record.description} "
                f"({record.bytes} bytes, {record.report})"
            )
    return failures


def summary(records: list[Record], maximum: int,
            *, compiled_units: int | None = None) -> dict[str, object]:
    """Return a stable, path-free summary suitable for release evidence."""
    if not records:
        raise StackUsageError("cannot summarize an empty stack report")
    ranked = sorted(
        records,
        key=lambda record: (record.bytes, record.description),
        reverse=True,
    )
    failures = policy_failures(records, maximum)
    description = re.sub(r"^.*[/\\](?=[^/\\]+:\d+:\d+:)", "",
                         ranked[0].description)
    result: dict[str, object] = {
        "schema": 1,
        "records": len(records),
        "max_frame": ranked[0].bytes,
        "max_function": description,
        "limit": maximum,
        "dynamic_bounded": sum(
            "dynamic" in record.qualifier.split(",") and not record.unbounded
            for record in records
        ),
        "unbounded": sum(record.unbounded for record in records),
        "status": "ok" if not failures else "failed",
    }
    if compiled_units is not None:
        result["compiled_units"] = compiled_units
    return result


def print_report(
    reports: list[Path], records: list[Record], maximum: int, top: int
) -> bool:
    ranked = sorted(
        records,
        key=lambda record: (record.bytes, record.description),
        reverse=True,
    )
    for record in ranked[:top]:
        print(
            f"STACK frame={record.bytes} qualifier={record.qualifier} "
            f"function={record.description}"
        )

    failures = policy_failures(records, maximum)
    if failures:
        for failure in failures:
            print(f"stack usage: FAIL: {failure}", file=sys.stderr)
        return False

    bounded = sum(
        "dynamic" in record.qualifier.split(",") for record in records
    )
    print(
        f"stack usage: OK files={len(reports)} records={len(records)} "
        f"max={ranked[0].bytes} limit={maximum} "
        f"dynamic_bounded={bounded}"
    )
    return True


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("root", type=Path)
    parser.add_argument("--max-frame", type=int, default=DEFAULT_MAX_FRAME)
    parser.add_argument("--top", type=int, default=5)
    args = parser.parse_args()
    if args.max_frame <= 0:
        parser.error("--max-frame must be positive")
    if args.top < 0:
        parser.error("--top must be non-negative")

    try:
        reports, records = read_records(args.root)
    except (OSError, UnicodeError, StackUsageError) as error:
        print(f"stack usage: FAIL: {error}", file=sys.stderr)
        return 2

    return 0 if print_report(
        reports, records, args.max_frame, args.top
    ) else 1


if __name__ == "__main__":
    raise SystemExit(main())

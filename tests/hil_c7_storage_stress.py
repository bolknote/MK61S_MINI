#!/usr/bin/env python3
"""Stress the physical C7 catalog/data log through the normal CDC protocol.

Requires an explicitly pinned board. Only the new /C7HIL-<short-id> subtree
is changed; an existing fixture is never reused. Failed runs retain it for
diagnosis. A successful run removes it and checks the original root listing.
Warm resets interrupt fsput before commit, not NOR program/erase operations:
this is not a substitute for physical power-cut testing.
"""

from __future__ import annotations

import argparse
import json
import random
import re
import time

from hil_multi_device_identity import Target, parse_identity, reset_cycle
from hil_rtc_alarm import Port
from hil_usb_disk_transaction import listing_entries, posix_cksum, require_file_contents


class UploadError(AssertionError):
    pass


class Stress:
    def __init__(self, path: str, public_id: str, seed: int):
        self.port = Port(path)
        identity = parse_identity(self.port.command("identity"))
        if identity.public != public_id.upper():
            self.port.close()
            raise AssertionError(f"wrong board: {identity}")
        self.target = Target(path, identity)
        self.root = f"/C7HIL-{identity.short}"
        self.original = listing_entries(self.cmd("ls /"))
        if any(line.split("\t")[-1].rstrip("/").casefold() == self.root[1:].casefold()
               for line in self.original):
            self.port.close()
            raise AssertionError(f"fixture already exists: {self.root}")
        self.files: dict[str, bytes] = {}
        self.rng = random.Random(seed)
        self.stats = dict(commands=0, writes=0, verified_files=0,
                          verified_bytes=0, resets=0, mutations=0,
                          cancelled_uploads=0, interrupted_uploads=0,
                          expected_no_space=0, max_command_ms=0)
        self.started = time.monotonic()

    def cmd(self, command: str, timeout: float = 45) -> str:
        started = time.monotonic()
        report = self.port.command(command, timeout=timeout)
        if hasattr(self, "stats"):
            self.stats["commands"] += 1
            self.stats["max_command_ms"] = max(
                self.stats["max_command_ms"], round((time.monotonic() - started) * 1000))
        return report

    def change(self, command: str) -> str:
        report = self.cmd(command)
        verb = command.split()[0]
        if re.search(rf"(?m)^(?:{verb}:|Usage:|@MKC:ERROR)", report):
            raise AssertionError(f"{command}:\n{report}")
        self.stats["mutations"] += 1
        return report

    def payload(self, size: int, *, text: bool = False) -> bytes:
        return bytes(self.rng.randrange(32, 127) if text else self.rng.randrange(256)
                     for _ in range(size))

    def begin(self, path: str, payload: bytes) -> None:
        report = self.cmd(f'fsput begin "{path}" {len(payload)} {posix_cksum(payload)}')
        if f"@MKC:READY {len(payload)}" not in report:
            raise UploadError(report)

    def data(self, payload: bytes) -> None:
        for offset in range(0, len(payload), 96):
            chunk = payload[offset:offset + 96]
            report = self.cmd(f"fsput data {offset} {chunk.hex().upper()}")
            if f"@MKC:ACK {offset + len(chunk)}" not in report:
                raise UploadError(report)

    def put(self, path: str, payload: bytes) -> None:
        try:
            self.begin(path, payload)
            self.data(payload)
            report = self.cmd("fsput end")
            if f"@MKC:DONE {len(payload)} {posix_cksum(payload)}" not in report:
                raise UploadError(report)
        except UploadError:
            self.cmd("fsput cancel")
            raise
        self.files[path] = payload
        self.stats["writes"] += 1
        self.stats["mutations"] += 1

    def verify(self, path: str) -> None:
        expected = self.files[path]
        try:
            require_file_contents(self.cmd(f'fsget "{path}"'), expected)
        except AssertionError as error:
            raise AssertionError(f"readback {path}: {error}") from error
        self.stats["verified_files"] += 1
        self.stats["verified_bytes"] += len(expected)

    def verify_all(self) -> None:
        for path in self.files:
            self.verify(path)

    def remove(self, path: str) -> None:
        report = self.change(f'rm "{path}"')
        if "Removed 1 entry." not in report:
            raise AssertionError(report)
        del self.files[path]
        if "@MKC:ERROR GET_NOT_FOUND" not in self.cmd(f'fsget "{path}"'):
            raise AssertionError(f"removed file remains readable: {path}")

    def reset(self) -> None:
        self.port.close()
        elapsed = reset_cycle(self.target, 30)
        self.port = Port(self.target.path)
        self.stats["resets"] += 1
        self.verify_all()
        self.note("reset", seconds=round(elapsed, 3))

    def note(self, phase: str, **values: object) -> None:
        print(json.dumps(dict(phase=phase, elapsed_s=round(time.monotonic() - self.started, 2),
                              **values, **self.stats), sort_keys=True), flush=True)

    def health(self) -> None:
        for command in ("df", "vlog", "crash", "wdog"):
            report = self.cmd(command)
            print(report.strip(), flush=True)
            if command == "df" and "FIRMWARE CRC state=valid" not in report:
                raise AssertionError("resident CRC is not valid")
            if command == "crash" and "CRASH none" not in report:
                raise AssertionError("a crash was retained")
            if command == "vlog" and not re.search(r"VFAT v=1 code=0\b", report):
                raise AssertionError("a VFAT error was retained")

    def run(self, metadata_cycles: int, rounds: int, interruptions: int,
            refill_rounds: int = 1) -> None:
        self.health()
        self.change(f'mkdir "{self.root}"')
        for name in ("A", "B", "QUOTA", "FULL"):
            self.change(f'mkdir "{self.root}/{name}"')
        guard = f"{self.root}/GUARD.bin"
        self.put(guard, self.payload(4096))
        self.verify(guard)
        self.note("start", identity=self.target.identity.__dict__)

        # Keep live data while rotating many generations of root and WAL.
        for index in range(metadata_cycles):
            name = f"{self.root}/M{index:05d}"
            self.change(f'mkdir "{name}"')
            self.change(f'rmdir "{name}"')
            if (index + 1) % 64 == 0:
                self.verify(guard)
                self.note("metadata", cycles=index + 1)
            if (index + 1) % 256 == 0:
                self.reset()

        # RAW small/large boundaries and compressible multi-cluster CHIP-8.
        for index, size in enumerate((0, 1, 511, 512, 513, 1536)):
            self.put(f"{self.root}/A/T{index}.txt", self.payload(size, text=True))
        for index, size in enumerate((1599, 1600, 1601, 4064, 4065, 4096)):
            self.put(f"{self.root}/B/R{index}.bin", self.payload(size))
        packed = f"{self.root}/A/PACK.ch8"
        self.put(packed, (b"C7-ZX0-TEST" * 400)[:3584])
        self.verify_all()
        for index in range(rounds):
            path = self.rng.choice([p for p in self.files if p != guard and p != packed])
            self.put(path, self.payload(len(self.files[path]), text=path.endswith(".txt")))
            self.verify(path)
            dest = path.replace("/A/", "/B/") if "/A/" in path else path.replace("/B/", "/A/")
            self.change(f'mv "{path}" "{dest}"')
            self.files[dest] = self.files.pop(path)
            self.verify(dest)
            if index % 3 == 0:
                content = self.files[dest]
                self.remove(dest)
                self.put(dest, content)
            if (index + 1) % 16 == 0:
                self.reset()
                self.note("mixed", rounds=index + 1)

        # No commit is issued. Both cancellation and warm reset must preserve
        # the old file, including when every incoming byte reached staging.
        for index in range(interruptions):
            new = self.payload(4096)
            self.begin(guard, new)
            prefix = (1, 511, 512, 513, 2048, 4095, 4096)[index % 7]
            self.data(new[:prefix])
            if index % 2:
                self.stats["interrupted_uploads"] += 1
                self.reset()
            else:
                if "@MKC:CANCELLED" not in self.cmd("fsput cancel"):
                    raise AssertionError("cancel failed")
                self.stats["cancelled_uploads"] += 1
                self.verify(guard)
        self.note("interrupted-uploads")

        # Fill the inode table with empty directories: unlike a physical-full
        # data test, no extra file extents obscure the exact quota boundary.
        quota: list[str] = []
        for index in range(4096):
            path = f"{self.root}/QUOTA/Q{index:04d}"
            report = self.cmd(f'mkdir "{path}"')
            if "mkdir:" in report:
                free = re.search(r"Nodes: (\d+) used, (\d+) free, (\d+) total", self.cmd("df"))
                if not free or int(free[2]) != 0:
                    raise AssertionError(f"mkdir failed before inode quota: {report}")
                self.stats["expected_no_space"] += 1
                break
            self.stats["mutations"] += 1
            quota.append(path)
        else:
            raise AssertionError("inode quota was never reached")
        self.put(guard, self.payload(4096))
        self.reset()
        actual = listing_entries(self.cmd(f'ls "{self.root}/QUOTA"'))
        if len(actual) != len(quota):
            raise AssertionError("directory quota listing lost entries")
        for path in quota:
            self.change(f'rmdir "{path}"')
        self.note("inode-quota", created=len(quota))

        # Incompressible 4096-byte files require two data blocks each. On a
        # 512-KiB volume this reaches physical exhaustion before inode quota.
        full: list[str] = []
        for index in range(4096):
            path = f"{self.root}/FULL/F{index:04d}.bin"
            try:
                self.put(path, self.payload(4096))
            except UploadError as error:
                if "@MKC:ERROR PUT_IO" not in str(error):
                    raise
                if "@MKC:ERROR GET_NOT_FOUND" not in self.cmd(f'fsget "{path}"'):
                    raise AssertionError("failed upload published a partial file")
                self.stats["expected_no_space"] += 1
                break
            full.append(path)
            if len(full) % 8 == 0:
                self.note("fill", files=len(full))
        else:
            raise AssertionError("filesystem exhaustion was never reached")
        if len(full) < 4:
            raise AssertionError("not enough free space to exercise recovery")
        self.reset()
        self.note("full", files=len(full), df=self.cmd("df"))
        for refill_round in range(refill_rounds):
            for path in full[::2]:
                self.remove(path)
            for path in full[::2]:
                self.put(path, self.payload(4096))
            self.reset()
            self.note("full-refill", files=len(full), round=refill_round + 1)
        self.health()
        removed = self.change(f'rm -r "{self.root}"')
        if "Removed " not in removed:
            raise AssertionError(removed)
        self.files.clear()
        self.reset()
        if listing_entries(self.cmd("ls /")) != self.original:
            raise AssertionError("root listing was not restored after cleanup")
        self.health()
        self.note("PASS", cleanup=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", required=True)
    parser.add_argument("--public-id", required=True)
    parser.add_argument("--metadata-cycles", type=int, default=1024)
    parser.add_argument("--rounds", type=int, default=96)
    parser.add_argument("--interruptions", type=int, default=14)
    parser.add_argument("--refill-rounds", type=int, default=1,
                        help="delete/refill cycles at physical capacity (1..32)")
    parser.add_argument("--seed", type=int, default=0xC700)
    args = parser.parse_args()
    if not re.fullmatch(r"[0-9a-fA-F]{16}", args.public_id):
        parser.error("--public-id requires 16 hexadecimal digits")
    if not (1 <= args.metadata_cycles <= 10000 and 1 <= args.rounds <= 10000
            and 1 <= args.interruptions <= 100 and 1 <= args.refill_rounds <= 32):
        parser.error("counts are outside the bounded stress-test limits")
    stress = Stress(args.port, args.public_id, args.seed)
    try:
        stress.run(args.metadata_cycles, args.rounds, args.interruptions,
                   args.refill_rounds)
        return 0
    except BaseException as error:
        stress.note("FAIL", error=str(error), retained_fixture=stress.root)
        raise
    finally:
        stress.port.close()


if __name__ == "__main__":
    raise SystemExit(main())

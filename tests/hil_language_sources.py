#!/usr/bin/env python3
"""Run large BASIC/FOCAL sources on one identity-pinned physical MK61.

Writes only /SRCHIL fixtures and calculator registers. Firmware and matching
System APPs must already be installed. No firmware or data backups are made.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import random
import time

from hil_c6_system_bootstrap import read_file, write_file
from hil_language_vm import health
from hil_multi_device_identity import parse_identity
from hil_portable_apps import ScreenPort, PROMPT
from hil_portable_system_apps import registers

ROOT = "/SRCHIL"


class SourcePort(ScreenPort):
    def command(self, command, timeout=5):
        # Keep servicing binary frames without adding 70 ms to every small
        # fsput chunk. Source uploads contain more than a thousand chunks.
        self.pump(.002)
        start = len(self.text)
        self.write_line(command)
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            self.pump(.003)
            if PROMPT.search(self.text[start:]):
                return self.text[start:].decode("cp1251", "replace")
        raise TimeoutError(f"{command}: {self.text[start:]!r}")

    def run_source(self, loader, focal):
        self.open(loader)
        deadline = time.monotonic() + 120
        next_key = time.monotonic() + .5
        while time.monotonic() < deadline:
            self.pump(.03)
            response = self.text[self.open_text_start:]
            if PROMPT.search(response):
                assert b"Open failed!" not in response, response
                return response.decode("cp1251", "replace")
            if focal and time.monotonic() >= next_key:
                # FOCAL always waits for a final key, including from M61.
                # Zero is harmless during execution (these fixtures have no
                # INPUT); ESC would instead cancel a slow, still-running VM.
                self.key(20 if self.keyboard_layout == 0 else 4)
                next_key = time.monotonic() + .5
        raise TimeoutError("large source did not finish: " + repr(response))


def fixture(language: str, size: int, resources: bool = False) -> bytes:
    """Few logical lines, with executable statements above signed-16-bit offsets.

    Noisy comments also exercise the multi-sector storage path. The optional
    unreachable string forces source-backed resources; the small printed
    marker after it must then be read using its large source offset.
    """
    if language == "basic":
        head = b"10 REM "
        tail = (b'\n20 GOTO 40\n30 PRINT "' + b"z" * 10000 + b'"\n'
                b'40 PRINT "BASIC SOURCE"\n' if resources else b"\n")
        tail += f"50 @(384)={size};.RA=@(384);.RC=SIZE;END\n".encode()
    else:
        assert language == "focal"
        head = b"1.10 C "
        tail = (b'\n1.20 G 1.40\n1.30 P "' + b"z" * 10000 + b'"\n'
                b'1.40 P "FOCAL SOURCE"\n' if resources else b"\n")
        tail += f"1.50 S .RB={size}\n1.60 E\n".encode()
    count = size - len(head) - len(tail)
    assert count >= 0
    rng = random.Random(0x535243)
    # Printable M8, with no physical line separators in the padding comment.
    noise = bytes(rng.randrange(97, 123) for _ in range(count))
    result = head + noise + tail
    assert len(result) == size
    return result


def save_report(path: Path, result: dict) -> None:
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", required=True)
    parser.add_argument("--public-id", required=True)
    parser.add_argument("--build-id", required=True)
    parser.add_argument("--profile", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    report_path = args.output_dir / "result.json"
    result = {"status": "RUNNING", "cases": []}
    with SourcePort(args.port, keyboard_layout=0 if args.profile == "mini-v3-a00" else 1) as port:
        identity = parse_identity(port.command("identity"))
        assert (identity.public, identity.build, identity.profile) == (
            args.public_id.upper(), args.build_id.upper(), args.profile), identity
        result["identity"] = asdict(identity)
        result["before"] = health(port)
        try:
            port.attach()
            port.command("mkdir " + ROOT, timeout=20)
            for size, resources in ((3585, False), (16384, False),
                                    (32768, False), (65534, False),
                                    (65534, True)):
                for language, suffix, register in (("basic", "tbi", "RA"),
                                                   ("focal", "foc", "RB")):
                    source = fixture(language, size, resources)
                    path = ROOT + "/case." + suffix
                    started = time.monotonic()
                    write_file(port, path, source)
                    read_file(port, path, source)
                    stored_seconds = time.monotonic() - started
                    loader = f'open "{path}"\nret\n'.encode()
                    write_file(port, ROOT + "/run.m61", loader)
                    read_file(port, ROOT + "/run.m61", loader)
                    samples = []
                    for repeat in range(2):
                        port.command(register + "= 0")
                        started = time.monotonic()
                        response = port.run_source(ROOT + "/run.m61", language == "focal")
                        elapsed = time.monotonic() - started
                        assert "Open failed!" not in response, response
                        values, register_report = registers(port)
                        assert values[register] == size, register_report
                        if language == "basic":
                            assert values["RC"] == 768, register_report
                        samples.append(elapsed)
                    result["cases"].append(dict(language=language, bytes=size,
                        source_resources=resources, sha256=hashlib.sha256(source).hexdigest(),
                        store_verify_seconds=stored_seconds, run_seconds=samples,
                        register=register, value=size))
                    save_report(report_path, result)
                    print(language, size, "source resources" if resources else "stream",
                          "cold/warm VM PASS", samples, flush=True)
                    # Keep room for C9 replacement and both editor draft banks
                    # even on a 512 KiB device with its full System bundle.
                    response = port.command('rm "' + path + '"', timeout=30)
                    assert "Removed 1 entry." in response, response
            result["after"] = health(port)
            result["status"] = "PASS"
        except BaseException as error:
            result["status"] = "FAIL"
            result["error"] = repr(error)
            try:
                result["after_failure"] = health(port)
            except (OSError, TimeoutError, AssertionError) as diagnostic:
                result["diagnostic_error"] = repr(diagnostic)
            raise
        finally:
            if port.attached:
                port.send(0x13)
                port.attached = False
                port.pump(.2)
            result["crc_checked_frames"] = len(port.frames)
            (args.output_dir / "terminal.txt").write_bytes(port.text)
            save_report(report_path, result)
    print("Physical streaming source HIL PASS", flush=True)


if __name__ == "__main__":
    main()

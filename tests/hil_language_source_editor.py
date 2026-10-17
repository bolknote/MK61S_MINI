#!/usr/bin/env python3
"""Exercise paged source editing through the physical MK61 Explorer workflow.

Own numeric root filenames, calculator registers and warm resets only. Uses
USB Screen keys, not private firmware entry points. Matching System APPs and
firmware must already be installed. The caller allows replacing the fixtures.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict
import hashlib
import json
from pathlib import Path

from hil_c6_system_bootstrap import write_file
from hil_language_sources import SourcePort, save_report, read_file
from hil_language_vm import health
from hil_multi_device_identity import parse_identity
from hil_portable_system_apps import png, registers
from hil_rtc_alarm import warm_reset


def fixture(focal, size):
    head = b"1.10 COMMENT " if focal else b"10 REM "
    tail = (b"\n1.20 COMMENT short\n1.30 SET .RB=42\n1.40 EXIT\n" if focal else
            b"\n20 REM short\n30 .RA=42;END\n")
    source = head + b"x" * (size - len(head) - len(tail)) + tail
    # Two edits at the ends of separate comments, in distant source windows.
    expected = source[:len(head)] + b"7" + source[len(head):]
    expected = expected.replace(b"short\n", b"short5\n", 1)
    if focal:
        for full, compact in ((b"COMMENT", b"C"), (b"SET", b"S"), (b"EXIT", b"E")):
            expected = expected.replace(full, compact)
    assert len(source) == size
    return source, expected


def snapshot(port, path):
    port.pump(.3)
    assert port.frames, "no CRC-checked USB frame"
    png(port.frames[-1], path)


def open_editor(port, focal, output):
    # USER opens the normal Explorer. Numeric search avoids assumptions about
    # directory sorting or whatever else is installed on this particular board.
    port.key(35)
    for key in (19, 19, 19, 8 if focal else 9):  # 7772 / 7771, Classic layout
        port.key(key)
    snapshot(port, output / "selected.png")
    port.send(0x30, bytes((37, 1)))
    port.pump(1.4)  # Normal Explorer long-OK action menu.
    port.send(0x30, bytes((37, 0)))
    port.pump(.15)
    port.key(36)
    port.key(36)  # RUN, VIEW, EDIT.
    snapshot(port, output / "edit-action.png")
    port.key(37)
    snapshot(port, output / "editor.png")


def edit_two_windows(port, focal, output):
    for _ in range(6 if focal else 7):
        port.key(36)  # Address plus the atomic COMMENT token / plain REM.
    port.key(19)  # Insert 7.
    port.key(28)  # Flush draft bank, skip the 34/64 KiB first comment.
    port.pump(2)  # Let the long Flash write finish before the next short tap.
    # Horizontal arrows stay within a physical line. Reach its end without
    # depending on FOCAL's compact/expanded cursor mapping inside COMMENT.
    for _ in range(24):
        port.key(36)
    port.key(13)  # Insert 5.
    port.key(28)  # Flush the other bank and seek to the executable statement.
    port.pump(2)
    snapshot(port, output / "edited.png")


def leave_editor(port, save, output):
    port.key(39)
    snapshot(port, output / "save-question.png")
    port.key(37 if save else 39)
    if save:
        snapshot(port, output / "directory.png")
        port.key(37)  # This directory.
        snapshot(port, output / "filename.png")
        port.key(37)  # Existing filename.
        port.pump(.8)
    snapshot(port, output / "returned.png")
    port.key(39)  # Clear retained Explorer search.
    port.key(39)  # Exit root Explorer to calculator.
    port.pump(.2)


def focal_operator_keys(port, output):
    output.mkdir(exist_ok=True)
    remote = "/7772.foc"
    # An incomplete operator field is editable and can be saved independently
    # of compilation. The original B key must render IF and erase atomically.
    write_file(port, remote, b"1.10 \n1.20 SET .RB=42\n1.30 EXIT\n")
    open_editor(port, True, output)
    for _ in range(5):
        port.key(36)
    port.key(2)
    snapshot(port, output / "if.png")
    port.key(0)
    snapshot(port, output / "atomic-delete.png")
    port.key(2)
    for key in (24, 38, 4, 24, 36):  # K+(, 0, K+).
        port.key(key)
    for branch in range(3):
        if branch:
            port.key(24)
            port.key(20)  # K+PP is comma.
        for key in (9, 3, 8, 4):
            port.key(key)  # 1.20
    snapshot(port, output / "if-complete.png")
    leave_editor(port, True, output)
    expected = b"1.10 B (0)1.20,1.20,1.20\n1.20 S .RB=42\n1.30 E\n"
    read_file(port, remote, expected)
    write_file(port, "/SRCHIL/run.m61", b'open "/7772.foc"\nret\n')
    port.command("RB= 0")
    port.run_source("/SRCHIL/run.m61", True)
    values, report = registers(port)
    assert values["RB"] == 42, report
    response = port.command('rm "' + remote + '"', timeout=30)
    assert "Removed 1 entry." in response, response
    print("FOCAL B key renders IF, atomic erase, compact save and VM branch PASS", flush=True)
    return dict(test="focal-operator-IF", original_key=2, view="IF", stored="B",
                atomic_delete=True, register="RB", value=42, verified=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--port", required=True)
    ap.add_argument("--public-id", required=True)
    ap.add_argument("--build-id", required=True)
    ap.add_argument("--output-dir", required=True, type=Path)
    ap.add_argument("--operators-only", action="store_true")
    args = ap.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    result = {"status": "RUNNING", "cases": []}
    path = args.port
    port = SourcePort(path)
    try:
        identity = parse_identity(port.command("identity"))
        assert (identity.public, identity.build, identity.profile) == (
            args.public_id.upper(), args.build_id.upper(), "classic-v3-uc1609"), identity
        result["identity"] = asdict(identity)
        result["before"] = health(port)
        port.attach()
        cases = () if args.operators_only else (
            (34000, "save"), (34000, "cancel"), (34000, "reset"),
            (65530, "save"), (65530, "cancel"))
        for size, mode in cases:
            for focal in (False, True):
                label = ("focal" if focal else "basic") + f"-{size}-{mode}"
                output = args.output_dir / label
                output.mkdir(exist_ok=True)
                source, expected = fixture(focal, size)
                remote = "/7772.foc" if focal else "/7771.tbi"
                write_file(port, remote, source)
                read_file(port, remote, source)
                open_editor(port, focal, output)
                edit_two_windows(port, focal, output)
                # Drafts must never publish edits before the explicit Save.
                read_file(port, remote, source)
                if mode == "reset":
                    # The UI was opened with USER, so the CDC terminal remains
                    # available for the normal reset command during editing.
                    next_port, path, seconds = warm_reset(port, path, identity.public)
                    next_port.close()
                    port = SourcePort(path)
                    current = parse_identity(port.command("identity"))
                    assert current == identity, current
                    read_file(port, remote, source)
                    port.attach()
                else:
                    leave_editor(port, mode == "save", output)
                    read_file(port, remote, expected if mode == "save" else source)
                result["cases"].append(dict(test=label, source_bytes=len(source),
                    saved_bytes=len(expected) if mode == "save" else len(source),
                    original_sha256=hashlib.sha256(source).hexdigest(),
                    published_before_save=False, verified=True))
                save_report(args.output_dir / "result.json", result)
                print(label, "byte-for-byte PASS", flush=True)
                response = port.command('rm "' + remote + '"', timeout=30)
                assert "Removed 1 entry." in response, response
        result["cases"].append(focal_operator_keys(port, args.output_dir / "focal-operators"))
        result["after"] = health(port)
        result["status"] = "PASS"
    except BaseException as error:
        result["status"] = "FAIL"
        result["error"] = repr(error)
        if port.frames:
            png(port.frames[-1], args.output_dir / "failure.png")
        raise
    finally:
        if port.attached:
            try:
                port.send(0x13)
                port.attached = False
                port.pump(.2)
            except (OSError, TimeoutError, AssertionError) as cleanup:
                result["cleanup_error"] = repr(cleanup)
        result["crc_checked_frames_last_session"] = len(port.frames)
        (args.output_dir / "terminal-last-session.txt").write_bytes(port.text)
        port.close()
        save_report(args.output_dir / "result.json", result)
    print("Physical paged editor HIL PASS", flush=True)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""One separately granted safe-eject recovery; never flashes or writes SD."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import time

import hil_mk61_ai as ai


def recover(phase, output):
    p = None
    report = {"passed": False, "cdc_closed": True, "save_or_restore": False}
    try:
        ai.usb_identity()
        p = ai.Serial(time.monotonic() + 180)
        status = p.status()
        # This is the exact USB-disk foreground started by the predecessor.
        for token in ("BUILD=" + phase["new_build"], "FIRMWARE_CRC=valid",
                      "EXPECTED=" + phase["new_crc"], "ACTUAL=" + phase["new_crc"],
                      "RUN=0", "PHYSICAL_KEYS=0"):
            if not re.search(r"(?<![A-Z_])" + re.escape(token) + r"(?![A-Za-z0-9])", status):
                raise ValueError("recovery native predicate mismatch")
        owned_msc = "USB_DISK=1" in status and "SERVICE=USB_DISK" in status
        idle = "USB_DISK=0" in status and "SERVICE=CLOSED" in status and "RUNTIME=NONE" in status and "UI=CALCULATOR" in status
        if not (owned_msc or idle):
            raise ValueError("foreground is not the owned MSC or idle calculator")
        p.commands()
        ai.identity(p)
        if owned_msc:
            # Guarded native probe: firmware refuses while host still owns SD.
            # Its expected ERROR is an observed ownership state, not a fault.
            answer = p.command("usbdisk off", allow_error=True)
            report["already_ejected"] = b"ERROR" not in answer
            if b"ERROR" in answer:
                disk = ai.bound_whole_disk()
                report["bound_disk"] = disk
                try:
                    run = subprocess.run(["/usr/sbin/diskutil", "eject", disk],
                                         capture_output=True, timeout=90)
                except subprocess.TimeoutExpired as error:
                    (output / "safe-eject.txt").write_bytes((error.stdout or b"") + (error.stderr or b""))
                    raise
                (output / "safe-eject.txt").write_bytes(run.stdout + run.stderr)
                report["safe_eject_returncode"] = run.returncode
                if run.returncode:
                    raise ValueError("safe eject failed; MSC remains active")
                p.command("usbdisk off")
        elif not ("USB_DISK=0" in status and "SERVICE=CLOSED" in status and "RUNTIME=NONE" in status):
            raise ValueError("foreground is not the owned MSC or idle calculator")
        report["final"] = ai.readiness(p.status(), phase["new_build"], phase["new_crc"])
        # Read only the task's model file after successful ownership return.
        command = 'fsget "/AI/MODEL.MKA"'
        reply = p.command(command, 120, allow_error=True)
        if b"ERROR" in reply:
            report["model_present"] = False
        else:
            data = bytearray()
            for offset, block in re.findall(rb"(?m)^@MKC:DATA (\d+) ([0-9A-F]+)\r?$", reply):
                if int(offset) != len(data):
                    raise ValueError("model offset mismatch")
                data.extend(bytes.fromhex(block.decode()))
            checksum = ai.checksum(data)
            if f"@MKC:END {len(data)} {checksum}".encode() not in reply:
                raise ValueError("model CRC mismatch")
            report.update({"model_present": True, "model_bytes": len(data),
                           "model_sha256": hashlib.sha256(data).hexdigest(),
                           "model_matches": hashlib.sha256(data).hexdigest() == phase["model_sha256"]})
        p.send(b"\x1e")
        report["final"] = ai.readiness(p.status(), phase["new_build"], phase["new_crc"])
        report["passed"] = True
    except BaseException as error:
        report["error"] = type(error).__name__ + ": " + str(error)
    finally:
        if p:
            p.close()
        report["cdc_closed"] = p is None or p.fd == -1
        (output / "result.json").write_text(json.dumps(report, indent=2) + "\n")
    if not report["passed"]:
        raise RuntimeError(report["error"])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase", type=Path, required=True)
    parser.add_argument("--grant", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--worker", action="store_true")
    args = parser.parse_args()
    phase = json.loads(args.phase.read_text())
    grant = json.loads(args.grant.read_text())
    if (grant.get("decision") != "GO" or grant.get("coordinator_thread") != ai.COORDINATOR or
            grant.get("phase_sha256") != ai.sha(args.phase) or
            phase.get("script_sha256") != ai.sha(__file__) or
            phase.get("helper_sha256") != ai.sha(ai.__file__) or
            phase.get("uid") != ai.UID or phase.get("port") != ai.PORT or
            phase.get("new_build") != "522F2DEB" or phase.get("new_crc") != "49AB978A"):
        raise ValueError("recovery grant/pins mismatch")
    args.output.mkdir(parents=True, exist_ok=True)
    with (args.output / ("worker-attempt.json" if args.worker else "attempt.json")).open("x") as marker:
        json.dump({"phase_sha256": ai.sha(args.phase)}, marker)
    if args.worker:
        recover(phase, args.output)
    else:
        command = [sys.executable, "-B", str(Path(__file__).resolve()), "--phase", str(args.phase.resolve()),
                   "--grant", str(args.grant.resolve()), "--output", str(args.output.resolve()), "--worker"]
        with (args.output / "worker.log").open("w") as log:
            process = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
            record = {"pid": process.pid, "phase_sha256": ai.sha(args.phase), "reaped": False}
            (args.output / "supervisor.json").write_text(json.dumps(record, indent=2) + "\n")
            try:
                process.wait(timeout=210)
            finally:
                if process.poll() is None:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait(timeout=10)
                    record["forced_stop"] = True
                record.update({"reaped": True, "exit_code": process.returncode})
                (args.output / "supervisor.json").write_text(json.dumps(record, indent=2) + "\n")
            if process.returncode:
                raise SystemExit(process.returncode)


if __name__ == "__main__":
    main()

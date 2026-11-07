#!/usr/bin/env python3
"""Finish measurements of the installed model, with a small SHA-256 APP.

No model writes, USB disk or clock/state operations. An optional separately
pinned firmware update uses one ROM transition. Temporary directories are
either freshly proved or reused with pinned predecessor ownership.
"""
import argparse
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import time

import hil_mk61_ai as ai


def drain(p, maximum=300, quiet=5):
    end = time.monotonic() + p.remaining(maximum)
    last = time.monotonic()
    while time.monotonic() < end:
        size = len(p.data)
        p.pump(0.05)
        if len(p.data) != size:
            last = time.monotonic()
        if time.monotonic() - last >= quiet:
            return len(p.data)
    raise TimeoutError("previous C5 output did not become quiet")


def validate(phase, grant):
    p, g = json.loads(phase.read_text()), json.loads(grant.read_text())
    if (g.get("decision") != "GO" or g.get("coordinator_thread") != ai.COORDINATOR or
            g.get("phase_sha256") != ai.sha(phase) or p.get("script_sha256") != ai.sha(__file__) or
            p.get("helper_sha256") != ai.sha(ai.__file__) or p.get("uid") != ai.UID or p.get("port") != ai.PORT or
            not re.fullmatch(r"[0-9A-F]{8}", p.get("new_build", "")) or
            not re.fullmatch(r"[0-9A-F]{8}", p.get("new_crc", "")) or
            p.get("deadline_seconds") != 1680 or not re.fullmatch(r"HILV2-[A-Z0-9-]{8,32}", p.get("nonce", ""))):
        raise ValueError("finish grant/pins mismatch")
    required = {"launcher", "benchmark", "hashprobe"}
    if p.get("entry_mode") == "flash-installed-model":
        required |= {"uf2", "bin", "firmware_manifest", "picotool"}
    elif p.get("entry_mode", "installed-image") != "installed-image":
        raise ValueError("unexpected entry mode")
    if set(p["payloads"]) != required:
        raise ValueError("unexpected finish payloads")
    for item in p["payloads"].values():
        path = Path(item["path"])
        if not path.is_absolute() or path.stat().st_size != item["bytes"] or ai.sha(path) != item["sha256"]:
            raise ValueError("finish payload mismatch")
    if p.get("entry_mode") == "flash-installed-model":
        manifest = json.loads(Path(p["payloads"]["firmware_manifest"]["path"]).read_text())
        if (manifest["uf2_sha256"] != p["payloads"]["uf2"]["sha256"] or
                manifest["bin_sha256"] != p["payloads"]["bin"]["sha256"] or
                manifest["build_id"].upper() != p["new_build"] or
                manifest["firmware_integrity"]["crc32"].upper() != p["new_crc"]):
            raise ValueError("new firmware manifest mismatch")
    if not p.get("fresh_temporary"):
        ownership = Path(p["ownership"]["path"])
        if ai.sha(ownership) != p["ownership"]["sha256"]:
            raise ValueError("predecessor ownership mismatch")
        paths = json.loads(ownership.read_text())
        if paths != ["/AI/" + p["nonce"], "/Apps/MK61AI/" + p["nonce"]]:
            raise ValueError("predecessor ownership paths mismatch")
    return p


def flash_once(phase, output):
    p = None
    try:
        ai.usb_identity()
        p = ai.Serial(time.monotonic() + 30)
        drain(p, maximum=15)
        ai.readiness(p.status(), phase["old_build"], phase["old_crc"])
        p.commands()
        ai.identity(p)
        p.send(b"\x1e!")  # Raw BOOTSEL: no save_settings() call.
        try:
            for _ in range(10):
                p.pump(0.05)
        except OSError:
            pass
    finally:
        if p:
            p.close()
    tool = phase["payloads"]["picotool"]["path"]
    for _ in range(20):
        check = subprocess.run([tool, "info", "--ser", ai.UID], capture_output=True, timeout=5)
        if check.returncode == 0:
            break
        time.sleep(0.2)
    else:
        raise TimeoutError("approved Pico did not enter ROM")
    flashed = subprocess.run([tool, "load", "-v", phase["payloads"]["uf2"]["path"], "--ser", ai.UID],
                             capture_output=True, timeout=45, check=True)
    (output / "flash-verification.txt").write_bytes(flashed.stdout + flashed.stderr)
    subprocess.run([tool, "reboot", "--ser", ai.UID], capture_output=True, timeout=10, check=True)
    ai.wait_usb_identity(20)
    print("approved candidate flashed/verified once; cached CDC binding restored", flush=True)


def worker(phase, output):
    p = None
    accepted = False
    owned = []
    foreground = set()
    result = {"passed": False, "save_or_restore": False, "model_rewritten": False}
    try:
        ai.usb_identity()
        p = ai.Serial(phase.get("_started", time.monotonic()) + 1680)
        result["drained_previous_bytes"] = drain(p)
        ai.readiness(p.status(), phase["new_build"], phase["new_crc"])
        # If status pumping revealed any still-active DATA stream, wait for
        # quiet again before sending command text into the terminal.
        if b"@MKC:DATA" in p.data:
            drain(p)
            ai.readiness(p.status(), phase["new_build"], phase["new_crc"])
        p.commands()
        ai.identity(p)
        accepted = True
        for path, allowed in (("/AI/" + phase["nonce"], {b"MODEL-UPLOAD.MKA", b"BENCH.JSON", b"BENCH.STATE"}),
                              ("/Apps/MK61AI/" + phase["nonce"], {b"AIBENCH.APP", b"AIHASH.APP"})):
            if phase.get("fresh_temporary"):
                ai.create_owned(p, path, owned, output)
            else:
                command = f'ls "{path}"'
                rows = ai.listing_rows(p.command(command), command)
                if any(not row.startswith(b"f\t") or row.split(b"\t")[-1].upper() not in allowed for row in rows):
                    raise ValueError("unexpected entry in predecessor's temporary directory")
                owned.append(path)
        (output / "owned.json").write_text(json.dumps(owned) + "\n")
        paths = {"launcher": "/Apps/MK61AI/MK61AI.APP",
                 "benchmark": "/Apps/MK61AI/" + phase["nonce"] + "/AIBENCH.APP",
                 "hashprobe": "/Apps/MK61AI/" + phase["nonce"] + "/AIHASH.APP"}
        for name, path in paths.items():
            ai.upload(p, path, Path(phase["payloads"][name]["path"]).read_bytes(), output / "upload-fault.bin")
        print("three small APPs installed/read back; no model write", flush=True)
        ai.mark_foreground(paths["hashprobe"], foreground, output)
        p.data.clear()
        p.send(f'run "{paths["hashprobe"]}"\r'.encode())
        answer = p.wait(lambda b: ai.PROMPT.search(b), 120)
        (output / "model-sha-reply.txt").write_bytes(answer)
        digest = re.findall(rb"AI_MODEL_SHA bytes=(\d+) sha256=([0-9a-f]{64}) ms=(\d+)", answer)
        if len(digest) != 1 or int(digest[0][0]) != 2093896 or digest[0][1].decode() != phase["model_sha256"] or b"ERROR" in answer:
            raise ValueError("on-device model SHA/size mismatch")
        result["model"] = {"bytes": 2093896, "sha256": digest[0][1].decode(), "hash_ms": int(digest[0][2])}
        print("on-device full model SHA-256 matches frozen package", flush=True)
        ai.leave_app(p)
        ai.mark_foreground(paths["benchmark"], foreground, output)
        ai.benchmark(p, paths["benchmark"], progress_path=output / "benchmark-progress.txt",
                     seconds=phase.get("benchmark_seconds",600))
        full = json.loads(ai.download(p, "/AI/" + phase["nonce"] + "/BENCH.JSON"))
        (output / "benchmark.json").write_text(json.dumps(full, indent=2) + "\n")
        if not (full["device"] and not full["cancelled"] and full["matching_greedy_tokens"] and
                full["valid_tool_prefix"] and full["max_session_roundtrip"] and
                all(full[k]["prefill_tokens"] == 8 and full[k]["decode_tokens"] == 4 for k in ("reference", "lut_fp32", "constrained_lut")) and
                0 < full["sampled_heap_peak"] < full["heap_capacity"] and 0 < full["stack_high_water"] < 32768):
            raise ValueError("physical benchmark assertions failed")
        print("36 real forward steps, kernel parity, maximum session and memory PASS", flush=True)
        ai.leave_app(p)
        latency = ai.benchmark(p, paths["benchmark"], cancel=True, progress_path=output / "cancel-progress.txt",
                               seconds=phase.get("cancel_seconds",180), cancel_step=phase.get("cancel_step",8))
        cancelled = json.loads(ai.download(p, "/AI/" + phase["nonce"] + "/BENCH.JSON"))
        cancelled["host_cancel_response_seconds"] = latency
        (output / "cancellation.json").write_text(json.dumps(cancelled, indent=2) + "\n")
        if not cancelled["cancelled"] or not cancelled["max_session_roundtrip"]:
            raise ValueError("cancellation assertions failed")
        ai.leave_app(p)
        ai.mark_foreground(paths["launcher"], foreground, output)
        p.data.clear()
        p.send(f'run "{paths["launcher"]}"\r'.encode())
        end = time.monotonic() + p.remaining(10)
        while time.monotonic() < end:
            if "RUNTIME=APP" in p.status():
                break
        else:
            raise ValueError("installed launcher did not open")
        ai.leave_app(p)
        result["passed"] = True
    except BaseException as error:
        result["error"] = type(error).__name__ + ": " + str(error)
    finally:
        try:
            if p and accepted:
                p.deadline = time.monotonic() + 90
                def partial(port):
                    command = 'fsget "/AI/' + phase["nonce"] + '/BENCH.JSON"'
                    reply = port.command(command, 20, allow_error=True)
                    (output / "partial-benchmark-reply.txt").write_bytes(reply)
                before_remove = partial if not result["passed"] and any(path.endswith("/AIBENCH.APP") for path in foreground) else None
                result["final"] = ai.cleanup(p, phase, owned, foreground, before_remove)
                result["temporary_removed"] = True
        except BaseException as error:
            result["cleanup_error"] = type(error).__name__ + ": " + str(error)
            result["passed"] = False
        finally:
            if p:
                p.close()
            result["cdc_closed"] = p is None or p.fd == -1
            (output / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    if not result["passed"]:
        raise RuntimeError(result.get("error", result.get("cleanup_error")))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase", type=Path, required=True)
    parser.add_argument("--grant", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--worker", action="store_true")
    args = parser.parse_args()
    phase = validate(args.phase, args.grant)
    args.output.mkdir(parents=True, exist_ok=True)
    with (args.output / ("worker-attempt.json" if args.worker else "attempt.json")).open("x") as file:
        json.dump({"phase_sha256": ai.sha(args.phase)}, file)
    if args.worker:
        phase["_started"] = time.monotonic()
        if phase.get("entry_mode") == "flash-installed-model":
            try:
                flash_once(phase, args.output)
            except BaseException as error:
                (args.output / "result.json").write_text(json.dumps({"passed": False, "error": type(error).__name__ + ": " + str(error), "cdc_closed": True, "stage": "flash"}, indent=2) + "\n")
                raise
        worker(phase, args.output)
        return
    command = [sys.executable, "-B", str(Path(__file__).resolve()), "--phase", str(args.phase.resolve()),
               "--grant", str(args.grant.resolve()), "--output", str(args.output.resolve()), "--worker"]
    with (args.output / "worker.log").open("w") as log:
        process = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
        record = {"pid": process.pid, "phase_sha256": ai.sha(args.phase), "reaped": False}
        (args.output / "supervisor.json").write_text(json.dumps(record, indent=2) + "\n")
        try:
            process.wait(timeout=1785)
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

#!/usr/bin/env python3
"""One hash-pinned AI performance phase. No I/O without a fresh ROOT grant.

Flash, normal performance, cancellation and OC are separate reviewed phases.
First unexpected fault holds the device; no reset, replay or speculative
cleanup follows it. Only this phase's newly created SD directories are owned.
"""
import argparse
import errno
import fcntl
import json
import os
from pathlib import Path
import re
import signal
import stat
import subprocess
import sys
import time

import hil_mk61_ai as ai
import hil_mk61_ai_finish as finish

def m3_health(status, startup_limits=None):
    """Only ownership, clocks and counters; no RTC/user/calculator snapshot."""
    keys=("BOOTS", "CRASH", "SYS_HZ", "PERI_HZ", "PHYSICAL_KEYS", "SETTINGS_WRITES", "RTC_SET",
          "APP_BUFFERS", "ERRORS", "QPI_FALLBACKS", "TAIL_TIMEOUTS", "CRC_ERRORS", "DMA_TIMEOUTS",
          "LCD_ERRORS", "SD_SPEED_FALLBACKS", "SD_PROBE_FAILURES", "I2C_TIMEOUTS", "I2C_ABORTS", "SCREEN_ERRORS")
    result={}
    for key in keys:
        found=re.search(r"(?<![A-Za-z0-9_])"+key+r"=([^ \r\n]+)",status)
        if not found: raise ValueError("missing M3 health counter "+key)
        result[key]=found[1]
    limits={} if startup_limits is None else startup_limits
    if limits and limits!={"QPI_FALLBACKS":1,"I2C_ABORTS":64}:
        raise ValueError("unsupported startup-counter bounds")
    if (result["CRASH"] != "NONE" or result["SYS_HZ"] != "125000000" or result["PERI_HZ"] != "48000000" or
            result["APP_BUFFERS"] != "0" or any(not result[k].isdigit() or int(result[k])>limits.get(k,0) for k in keys[8:])):
        raise ValueError("M3 native clocks/resources/error health failed")
    return result


def validate(phase_path, grant_path, now=None):
    p = json.loads(phase_path.read_text())
    g = json.loads(grant_path.read_text())
    now = time.time() if now is None else now
    if (g.get("decision") != "GO" or g.get("coordinator_thread") != ai.COORDINATOR or
            g.get("phase_sha256") != ai.sha(phase_path) or
            not all(isinstance(g.get(k), (int, float)) for k in ("not_before", "start_before", "finish_before")) or
            not g["not_before"] <= now <= g["start_before"] < g["finish_before"] or
            not 30 <= g["finish_before"] - now <= 900):
        raise ValueError("no current GO for this exact phase")
    if (p.get("schema") != 3 or p.get("uid") != ai.UID or p.get("port") != ai.PORT or
            p.get("save_or_restore") is not False or p.get("deadline_seconds") != 850 or
            p.get("action") not in ("flash", "perf", "baseline") or
            p.get("script_sha256") != ai.sha(__file__) or
            p.get("helper_sha256") != ai.sha(ai.__file__) or
            p.get("finish_helper_sha256") != ai.sha(finish.__file__) or
            not re.fullmatch(r"HILV3-[A-Z0-9-]{8,32}", p.get("nonce", ""))):
        raise ValueError("phase controller, identity or scope mismatch")
    for key in ("new_build", "new_crc"):
        if not re.fullmatch(r"[A-F0-9]{8}", p.get(key, "")):
            raise ValueError("missing exact expected firmware")
    for name, digest in p.get("source_pins", {}).items():
        if not Path(name).is_absolute() or ai.sha(name) != digest:
            raise ValueError("source pin changed")
    if not p.get("source_pins"):
        raise ValueError("source pins required")
    required = {"firmware_manifest", "uf2", "bin", "picotool"} if p["action"] == "flash" else {
        "firmware_manifest", "benchmark", "hashprobe", "model"}
    if p["action"] == "perf": required.add("config")
    if p["action"] == "perf" and p.get("config", {}).get("cores") == 3:
        required.add("m3_module")
    if set(p.get("payloads", {})) != required:
        raise ValueError("payload set mismatch")
    for item in p["payloads"].values():
        path = Path(item["path"])
        if not path.is_absolute() or path.stat().st_size != item["bytes"] or ai.sha(path) != item["sha256"]:
            raise ValueError("payload changed")
    m = json.loads(Path(p["payloads"]["firmware_manifest"]["path"]).read_text())
    if m["build_id"].upper() != p["new_build"] or m["firmware_integrity"]["crc32"].upper() != p["new_crc"]:
        raise ValueError("firmware manifest mismatch")
    if p["action"] == "flash":
        if (m["uf2_sha256"] != p["payloads"]["uf2"]["sha256"] or
                m["bin_sha256"] != p["payloads"]["bin"]["sha256"] or
                not all(re.fullmatch(r"[A-F0-9]{8}", p.get(k) or "") for k in ("old_build", "old_crc"))):
            raise ValueError("flash binding mismatch")
    elif p["action"] == "perf":
        c = parse_config(Path(p["payloads"]["config"]["path"]).read_bytes())
        if c != p.get("config") or not isinstance(p.get("alternate_model"), bool):
            raise ValueError("config/model transport mismatch")
        if c["cores"] == 3:
            lease=Path(p.get("root_lease_path", ""))
            if not lease.is_absolute() or lease.name != "ROOT-PICO-LEASE-001.json":
                raise ValueError("M3 requires the shared ROOT hardware lease")
            info=lease.lstat()
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_ino != p.get("root_lease_inode"):
                raise ValueError("ROOT lease identity changed")
        if c["mhz"] != 125 and (not m.get("ai_overclock_diagnostic") or not p.get("expected_usb_reenumerations") == 2):
            raise ValueError("OC requires diagnostic image and two expected USB transitions")
        if c["mhz"] == 125 and p.get("expected_usb_reenumerations") != 0:
            raise ValueError("unexpected USB transition grant")
        if p.get("cancel_at") is not None:
            event = p["cancel_at"]
            if c["mhz"] != 125 or event.get("pass") != 1 or not 0 <= event.get("step", -1) < c["prefill"] + c["decode"] or event.get("key") not in (27, 133):
                raise ValueError("unbounded/unknown cancellation schedule")
    else:
        if p.get("alternate_model") is not False or p.get("expected_usb_reenumerations") != 0 or p.get("cancel_at") is not None:
            raise ValueError("baseline scope must be the frozen full model at stock clocks")
    return p, g


def parse_config(raw):
    text = raw.decode("ascii")
    v2 = text.startswith("AIPERF2\n")
    if (not v2 and not text.startswith("AIPERF1\n")) or len(raw) > 512 or "\r" in text:
        raise ValueError("invalid config header")
    result = {}
    for line in text.splitlines()[1:]:
        key, value = line.split("=")
        if key in result or not re.fullmatch(r"[0-9]+", value):
            raise ValueError("duplicate/non-numeric config")
        result[key] = int(value)
    fields = {"kernel", "arithmetic", "cores", "freeze", "filter", "mhz", "prefill", "decode", "repeat", "stress_ms", "control", "constrained"}
    if v2: fields.add("prefetch")
    if set(result) != fields:
        raise ValueError("config fields mismatch")
    c = result
    if (c["kernel"] not in range(3) or c["arithmetic"] not in range(4) or c["cores"] not in (1, 2, 3) or
            any(c[k] not in (0, 1) for k in ("freeze", "filter", "control", "constrained")) or
            c["mhz"] not in (125, 200, 250, 300) or not 1 <= c["prefill"] <= 16 or
            not 1 <= c["decode"] <= 8 or c["prefill"] + c["decode"] > 24 or
            not 1 <= c["repeat"] <= 4 or not 0 <= c["stress_ms"] <= 300000 or
            c.get("prefetch", 0) not in (0, 1) or
            (c["kernel"] == 0 and (c["cores"] != 1 or c["filter"] or c.get("prefetch", 0))) or (c["filter"] and not c["constrained"])):
        raise ValueError("unsupported performance schedule")
    if c["cores"] == 3 and (not v2 or c["arithmetic"] not in (1, 3) or not c["control"] or c["mhz"] != 125 or c["stress_ms"]):
        raise ValueError("M3 requires controlled stock-clock INT8 or LUT_FLOAT32 A/B")
    return result


def install_alternate(p, phase, output):
    """Exclusive MSC writes one new MODEL.MKA under our proved-empty folder."""
    data = Path(phase["payloads"]["model"]["path"]).read_bytes()
    ai.readiness(p.status(), phase["new_build"], phase["new_crc"])
    p.command("usbdisk")
    status = p.status()
    if "USB_DISK=1" not in status or "SERVICE=USB_DISK" not in status:
        raise ValueError("exclusive MSC did not start")
    disk = None
    end = time.monotonic() + p.remaining(45)
    while time.monotonic() < end:
        try:
            disk = ai.bound_whole_disk()
            mount = ai.mounted_partition(disk)
            break
        except ValueError:
            time.sleep(0.2)
    else:
        raise TimeoutError("bound MSC mount deadline")
    folder = mount / "AI" / phase["nonce"]
    if folder.is_symlink() or not folder.is_dir() or folder.resolve().parent != (mount / "AI").resolve():
        raise ValueError("alternate model folder binding mismatch")
    destination = folder / "MODEL.MKA"
    with destination.open("xb") as file:
        file.write(data);file.flush();os.fsync(file.fileno())
    if destination.read_bytes() != data:
        raise ValueError("MSC alternate model readback mismatch")
    eject = subprocess.run(["/usr/sbin/diskutil", "eject", disk], capture_output=True, timeout=25)
    (output / "msc-eject.txt").write_bytes(eject.stdout + eject.stderr)
    if eject.returncode:
        raise ValueError("safe eject failed; HOLD with MSC active")
    p.command("usbdisk off")
    ai.readiness(p.status(), phase["new_build"], phase["new_crc"])


def run_perf(connection, phase, path, output):
    p = connection[0]
    p.data.clear();p.send(f'run "{path}"\r'.encode())
    markers = set();reconnects = 0;sent = observed = None
    end = p.deadline
    while time.monotonic() < end:
        data = bytes(p.data)
        for marker in re.findall(rb"(?m)^AI_(?:LOAD|PERF|CLOCK|STRESS|CANCEL)[^\r\n]*", data):
            if marker not in markers:
                markers.add(marker)
                line = f"{time.monotonic():.3f} " + marker.decode("ascii")
                print(line, flush=True)
                with (output / "progress.txt").open("a") as file:
                    file.write(line + "\n")
        event = phase.get("cancel_at")
        if event and sent is None and f'AI_PERF pass={event["pass"]} step={event["step"]} begin'.encode() in data:
            enter = time.monotonic() + p.remaining(0.05)
            while time.monotonic() < enter:
                p.pump()
            sent = time.monotonic();p.send(bytes([event["key"]]))
        if sent is not None and observed is None and b"AI_CANCEL" in data:
            observed = time.monotonic() - sent
        if ai.PROMPT.search(data):
            return p, {"usb_reenumerations": reconnects, "cancel_response_seconds": observed,
                       "cancel_sent": sent is not None, "app_error": bool(re.search(rb"(?m)^(?:@MKC:)?ERROR", data))}
        try:
            p.pump()
        except OSError as error:
            if phase["expected_usb_reenumerations"] != 2 or reconnects >= 2 or error.errno not in (None, errno.EIO, errno.ENXIO, errno.ENODEV):
                raise
            p.close();ai.wait_usb_identity(min(20, max(1, end - time.monotonic())))
            p = ai.Serial(end);connection[0] = p;reconnects += 1
            if reconnects == 2:
                # The final prompt may have gone to the disconnected CDC.
                # Native readiness and our unique durable report prove exit;
                # no APP replay or reset is used to recover that prompt.
                status = p.status()
                ai.cleanup_status(status, phase, {path})
                if "RUNTIME=NONE" in status:
                    p.commands()
                    return p, {"usb_reenumerations": reconnects, "cancel_response_seconds": observed,
                               "cancel_sent": sent is not None, "app_error": False}
    raise TimeoutError("performance phase deadline")


def worker(phase, grant, output):
    end = min(time.monotonic() + phase["deadline_seconds"],
              time.monotonic() + grant["finish_before"] - time.time() - 20)
    p = None;connection = [None];owned = [];foreground = set()
    report = {"status": "HOLD", "uid": ai.UID, "save_or_restore": False,
              "temporary_removed": False, "cdc_closed": False}
    try:
        if phase["action"] == "flash":
            finish.flash_once(phase, output)
        ai.wait_usb_identity(20);p = ai.Serial(end);connection[0] = p
        status=p.status()
        report["entry"] = ai.readiness(status, phase["new_build"], phase["new_crc"])
        m3_phase=phase["action"]=="perf" and phase["config"]["cores"]==3
        if m3_phase:
            report["hardware_before"]=m3_health(status,phase.get("startup_error_limits"))
            time.sleep(0.2)
            if m3_health(p.status(),phase.get("startup_error_limits"))!=report["hardware_before"]:
                raise ValueError("native counters/clocks are not stable before inference")
        if phase["action"] in ("perf", "baseline"):
            p.commands();ai.identity(p)
            for path in ("/AI/" + phase["nonce"], "/Apps/MK61AI/" + phase["nonce"]):
                ai.create_owned(p, path, owned, output)
            if phase["alternate_model"]:
                install_alternate(p, phase, output)
            folder = "/Apps/MK61AI/" + phase["nonce"]
            for name, leaf in (("benchmark", "AIBENCH.APP"), ("hashprobe", "AIHASH.APP")):
                ai.upload(p, folder + "/" + leaf, Path(phase["payloads"][name]["path"]).read_bytes(), output / "upload-fault.bin")
            if phase["action"] == "perf":
                ai.upload(p, "/AI/" + phase["nonce"] + "/PERF.CFG",
                          Path(phase["payloads"]["config"]["path"]).read_bytes(), output / "upload-fault.bin")
                if phase["config"]["cores"] == 3:
                    ai.upload(p, "/AI/" + phase["nonce"] + "/M3LINE.S3M",
                              Path(phase["payloads"]["m3_module"]["path"]).read_bytes(), output / "upload-fault.bin")
            probe = folder + "/AIHASH.APP";ai.mark_foreground(probe, foreground, output)
            p.data.clear();p.send(f'run "{probe}"\r'.encode())
            answer = p.wait(lambda b: ai.PROMPT.search(b), 120)
            hashes = re.findall(rb"AI_MODEL_SHA bytes=(\d+) sha256=([0-9a-f]{64}) ms=(\d+)", answer)
            model = phase["payloads"]["model"]
            if len(hashes) != 1 or int(hashes[0][0]) != model["bytes"] or hashes[0][1].decode() != model["sha256"] or b"ERROR" in answer:
                raise ValueError("on-device model identity mismatch")
            report["model_sha256"] = model["sha256"]
            ai.leave_app(p)
            app = folder + "/AIBENCH.APP";ai.mark_foreground(app, foreground, output)
            if phase["action"] == "baseline":
                ai.benchmark(p,app,progress_path=output/"progress.txt",seconds=760)
                result=json.loads(ai.download(p,"/AI/"+phase["nonce"]+"/BENCH.JSON"))
                (output/"baseline.json").write_text(json.dumps(result,indent=2)+"\n")
                if (not result.get("device") or result.get("cancelled") or not result.get("matching_greedy_tokens") or
                        not result.get("valid_tool_prefix") or not result.get("max_session_roundtrip") or
                        not all(result[k]["prefill_tokens"]==8 and result[k]["decode_tokens"]==4 for k in
                                ("reference","lut_fp32","constrained_lut"))):
                    raise ValueError("frozen B0 baseline assertions failed")
            else:
                p, report["transport"] = run_perf(connection, phase, app, output)
                result = json.loads(ai.download(p, "/AI/" + phase["nonce"] + "/PERF.JSON"))
                (output / "performance.json").write_text(json.dumps(result, indent=2) + "\n")
                if (not result.get("device") or result.get("schema") != 3 or result.get("config") != phase["config"] or
                        not result.get("clocks_restored") or result.get("restored_hz") != 125000000 or
                        result.get("actual_hz") != phase["config"]["mhz"] * 1000000 or result.get("freeze_violations") or
                        result.get("freeze_count") != result.get("thaw_count") or
                        not 0 < result.get("sampled_heap_peak", 0) < result.get("heap_capacity", 0) or
                        not 0 < result.get("stack_high_water", 0) < 32768 or
                        not result.get("matching_tokens") or not result.get("matching_checksums") or
                    result.get("i2c_errors") or not result.get("valid_tool_prefix")):
                    raise ValueError("performance invariants failed")
                if phase.get("cancel_at"):
                    if result.get("model_status") != 6 or not result["cancelled"] or not report["transport"]["cancel_sent"] or report["transport"]["cancel_response_seconds"] is None:
                        raise ValueError("cancellation was not observed")
                elif not result.get("ok") or report["transport"]["app_error"]:
                    raise ValueError("model/clock/stability check failed")
                else:
                    c=phase["config"];rows=result.get("results",[])
                    if len(rows)!=c["repeat"]+1 or not all(r["prefill_tokens"]==c["prefill"] and r["decode_tokens"]==c["decode"] and
                            len(r["next"])==c["prefill"]+c["decode"] and len(r["checksums"])==len(r["next"]) for r in rows):
                        raise ValueError("incomplete performance comparison")
                    if c["cores"]>=2 and not all(r["worker_rows"]>0 for r in rows[1:]):
                        raise ValueError("second core was not used")
                    if c.get("prefetch") and ((c["cores"] != 3 and rows[0].get("prefetches") != 0) or
                            not all(r.get("prefetches", 0)>0 and r.get("prefetched_bytes", 0)>0 for r in rows[1:])):
                        raise ValueError("DMA prefetch was not used, or control was not synchronous")
                    if c["cores"] == 3:
                        if (not result.get("matching_kv") or not rows[0].get("worker_rows") or rows[0].get("remote_jobs") or
                                not all(r.get("kv_checksum") == rows[0].get("kv_checksum") and r.get("remote_jobs", 0)>0 and
                                        r.get("remote_rows", 0)>0 and r.get("remote_fallbacks") == 0 and
                                        r["m3"]["jobs"] == r["remote_jobs"] and r["m3"]["rows"] == r["remote_rows"] and
                                        r["m3"]["sent"]>0 and r["m3"]["received"]>0 and r["m3"]["vectors"]>0 and
                                        0<r["m3"]["max_slice_us"]<=2000 and 0<r["m3"]["context_bytes"]<=4096 and
                                        not r["m3"]["error"] and not r["m3"]["uart_errors"] and not r["m3"]["unload_failures"]
                                        for r in rows[1:])):
                            raise ValueError("M3 work/quality/resources/cleanup invariants failed")
                        if c.get("prefetch") and not rows[0].get("prefetches", 0)>0:
                            raise ValueError("M3 control did not use identical prefetch")
                    if c["stress_ms"] and not result.get("stress_iterations",0)>0:
                        raise ValueError("stress loop did not run")
                    if c["stress_ms"] and result.get("control_probe_calls")!=1:
                        raise ValueError("core-1 control path did not complete while LCD was held")
            report["final"] = ai.cleanup(p, phase, owned, foreground)
            report["temporary_removed"] = True
            if m3_phase:
                report["hardware_after"]=m3_health(p.status(),phase.get("startup_error_limits"))
                if report["hardware_before"] != report["hardware_after"]:
                    raise ValueError("M3 native counters/clocks changed")
        else:
            report["final"] = ai.readiness(p.status(), phase["new_build"], phase["new_crc"])
            report["temporary_removed"] = True
        report["status"] = "PASS"
    except BaseException as error:
        report["error"] = type(error).__name__ + ": " + str(error)
        # Close only. Unexpected state is not authority to send Esc, reset,
        # remove directories or try another frequency after this fault.
    finally:
        p = connection[0] or p
        if p: p.close()
        report["cdc_closed"] = p is None or p.fd == -1
        report["owned"] = owned
        (output / "receipt.json").write_text(json.dumps(report, indent=2) + "\n")
    if report["status"] != "PASS":
        raise RuntimeError(report.get("error", "HOLD"))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase", type=Path, required=True)
    parser.add_argument("--grant", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--worker", action="store_true")
    args = parser.parse_args();phase, grant = validate(args.phase, args.grant)
    args.output.mkdir(parents=True, exist_ok=True)
    with (args.output / ("worker-attempt.json" if args.worker else "attempt.json")).open("x") as file:
        json.dump({"phase_sha256": ai.sha(args.phase)}, file)
    if args.worker:
        lease_fd=None
        try:
            if phase["action"] == "perf" and phase["config"]["cores"] == 3:
                lease_fd=os.open(phase["root_lease_path"],os.O_RDONLY|os.O_NOFOLLOW)
                info=os.fstat(lease_fd)
                if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_ino != phase["root_lease_inode"]:
                    raise ValueError("ROOT lease changed before lock")
                fcntl.flock(lease_fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
            worker(phase, grant, args.output)
        finally:
            if lease_fd is not None: os.close(lease_fd)
        return
    command = [sys.executable, "-B", str(Path(__file__).resolve()), "--phase", str(args.phase.resolve()),
               "--grant", str(args.grant.resolve()), "--output", str(args.output.resolve()), "--worker"]
    with (args.output / "worker.log").open("w") as log:
        process = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
        record = {"pid": process.pid, "reaped": False, "phase_sha256": ai.sha(args.phase)}
        try:
            process.wait(timeout=max(1, min(850, grant["finish_before"] - time.time() - 10)))
        finally:
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGKILL);process.wait(timeout=10);record["forced_stop"] = True
            record.update(reaped=True, exit_code=process.returncode)
            (args.output / "supervisor.json").write_text(json.dumps(record, indent=2) + "\n")
        if process.returncode: raise SystemExit(process.returncode)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Finite, hash-pinned PicoCalc AI installation and measurements.

Physical I/O requires a coordinator grant for the exact phase SHA. No old
firmware, calculator, files, settings or clock are inventoried or restored.
This continuation never flashes, resets, enters ROM or executes picotool. All temporary SD paths
are unique to this phase; installed model and launcher remain on the card.
"""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import plistlib
import re
import select
import signal
import subprocess
import sys
import termios
import time

UID = "E6657CD423721C35"
PORT = "/dev/cu.usbmodem11301"
COORDINATOR = "01a164b7-9caa-7011-90d1-807e9630921c"
PROMPT = re.compile(rb"(?:^|[\r\n])mk61> ")
ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def validate(phase_path, grant_path):
    phase = json.loads(phase_path.read_text())
    grant = json.loads(grant_path.read_text())
    if (grant.get("phase_sha256") != sha(phase_path) or
            grant.get("coordinator_thread") != COORDINATOR or
            grant.get("decision") != "GO"):
        raise ValueError("missing GO for this exact phase")
    if (phase.get("schema") != 1 or phase.get("uid") != UID or
            phase.get("port") != PORT or phase.get("save_or_restore") is not False or
            phase.get("controller_sha256") != sha(__file__) or
            phase.get("deadline_seconds") != 1680 or phase.get("entry_mode") != "installed-image" or
            phase.get("model_transport") != "exclusive-msc"):
        raise ValueError("phase identity/controller/deadline mismatch")
    if not re.fullmatch(r"HILV2-[A-Z0-9-]{8,32}", phase.get("nonce", "")):
        raise ValueError("invalid unique directory")
    required = {"uf2", "bin", "firmware_manifest", "model", "launcher", "probe", "picotool"}
    if set(phase["payloads"]) != required:
        raise ValueError("unexpected payloads")
    for name, item in phase["payloads"].items():
        p = Path(item["path"])
        if not p.is_absolute() or p.stat().st_size != item["bytes"] or sha(p) != item["sha256"]:
            raise ValueError("payload mismatch: " + name)
    manifest = json.loads(Path(phase["payloads"]["firmware_manifest"]["path"]).read_text())
    if (manifest["uf2_sha256"] != phase["payloads"]["uf2"]["sha256"] or
            manifest["bin_sha256"] != phase["payloads"]["bin"]["sha256"] or
            manifest["build_id"].upper() != phase["new_build"] or
            manifest["firmware_integrity"]["crc32"].upper() != phase["new_crc"]):
        raise ValueError("firmware manifest mismatch")
    return phase


def checksum(data):
    # POSIX cksum, including length, matching the native C5 endpoint.
    table = []
    for i in range(256):
        c = i << 24
        for _ in range(8):
            c = ((c << 1) ^ (0x04C11DB7 if c & 0x80000000 else 0)) & 0xFFFFFFFF
        table.append(c)
    c = 0
    for b in data:
        c = ((c << 8) & 0xFFFFFFFF) ^ table[(c >> 24) ^ b]
    size = len(data)
    while size:
        c = ((c << 8) & 0xFFFFFFFF) ^ table[(c >> 24) ^ (size & 255)]
        size >>= 8
    return c ^ 0xFFFFFFFF


def usb_identity():
    # Read cached IOKit metadata: this opens no CDC/USB device and sends no
    # bytes to a foreground APP. It is safe even during recovery.
    out = subprocess.run(["/usr/sbin/ioreg", "-a", "-r", "-c", "IOUSBHostDevice", "-l", "-w", "0"],
                         capture_output=True, check=True, timeout=5).stdout
    roots = plistlib.loads(out)

    def nodes(node):
        yield node
        for child in node.get("IORegistryEntryChildren", []):
            yield from nodes(child)

    for root in roots:
        for device in nodes(root):
            if device.get("USB Serial Number") == UID:
                if any(n.get("IOCalloutDevice") == PORT for n in nodes(device)):
                    return
    raise ValueError("cached USB UID/CDC mapping mismatch")


def wait_usb_identity(seconds=20):
    end = time.monotonic() + seconds
    while True:
        try:
            usb_identity()
            return
        except ValueError:
            if time.monotonic() >= end:
                raise
            time.sleep(0.2)


class Serial:
    def __init__(self, deadline):
        self.deadline = deadline
        self.fd = self.lock_fd = -1
        self.data = bytearray()
        key = hashlib.sha256(PORT.encode()).hexdigest()[:20]
        try:
            self.lock_fd = os.open(f"/tmp/mk61-hil-cdc-{os.geteuid()}-{key}.lock",
                                   os.O_CREAT | os.O_RDWR, 0o600)
            fcntl.flock(self.lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            self.fd = os.open(PORT, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
            fcntl.ioctl(self.fd, termios.TIOCEXCL)
            a = termios.tcgetattr(self.fd)
            a[0] = a[1] = a[3] = 0
            a[2] = (a[2] & ~(termios.CSIZE | termios.PARENB | termios.CSTOPB)) | termios.CS8 | termios.CREAD | termios.CLOCAL
            a[4] = a[5] = termios.B115200
            a[6][termios.VMIN] = a[6][termios.VTIME] = 0
            termios.tcsetattr(self.fd, termios.TCSANOW, a)
        except BaseException:
            self.close()
            raise

    def close(self):
        if self.fd >= 0:
            try:
                fcntl.ioctl(self.fd, termios.TIOCNXCL)
            except OSError:
                pass
            os.close(self.fd)
            self.fd = -1
        if self.lock_fd >= 0:
            fcntl.flock(self.lock_fd, fcntl.LOCK_UN)
            os.close(self.lock_fd)
            self.lock_fd = -1

    def remaining(self, seconds):
        n = min(seconds, self.deadline - time.monotonic())
        if n <= 0:
            raise TimeoutError("phase deadline reached")
        return n

    def pump(self, seconds=0.01):
        ready, _, _ = select.select([self.fd], [], [], self.remaining(seconds))
        if ready:
            block = os.read(self.fd, 16384)
            if not block:
                raise OSError("CDC disconnected")
            self.data.extend(block)
            if len(self.data) > 12 * 1024 * 1024:
                raise ValueError("unexpected serial output volume")

    def send(self, data):
        end = time.monotonic() + self.remaining(5)
        at = 0
        while at < len(data):
            if time.monotonic() >= end:
                raise TimeoutError("CDC write deadline")
            try:
                at += os.write(self.fd, data[at:])
            except BlockingIOError:
                self.pump()

    def wait(self, predicate, seconds=10):
        end = time.monotonic() + self.remaining(seconds)
        while time.monotonic() < end:
            if predicate(bytes(self.data)):
                return bytes(self.data)
            self.pump()
        raise TimeoutError("CDC response deadline; tail=" + repr(bytes(self.data[-400:])))

    def commands(self):
        self.data.clear()
        self.send(b"\x1f")
        self.wait(lambda b: b"MK61S PicoCalc terminal;" in b and PROMPT.search(b), 10)

    def command(self, command, seconds=10, allow_error=False):
        self.data.clear()
        self.send(command.encode("ascii") + b"\r")
        out = self.wait(lambda b: PROMPT.search(b), seconds)
        if not allow_error and re.search(rb"(?m)^(?:@MKC:)?ERROR", out):
            raise ValueError(command + ": " + repr(out[-400:]))
        return out

    def status(self):
        self.data.clear()
        self.send(b"\x05")
        return self.wait(lambda b: re.search(rb"MSC_SD_READ_US=[^\r\n]*\r?\n", b), 5).decode("ascii", "replace")


def readiness(status, build, crc):
    required = ["BUILD=" + build, "SERVICE=CLOSED", "RUNTIME=NONE", "UI=CALCULATOR",
                "RUN=0", "USB_DISK=0", "PHYSICAL_KEYS=0", "MATH_TEST=OK failures=0",
                "KBD=OK", "PSRAM=OK BYTES=8388608", "SD=OK", "FIRMWARE_CRC=valid",
                "EXPECTED=" + crc, "ACTUAL=" + crc]
    if not all(re.search(r"(?<![A-Z_])" + re.escape(s) + r"(?![A-Za-z0-9])", status) for s in required):
        raise ValueError("native ready predicates missing: " + repr([s for s in required if s not in status]))
    # Persist only predicates, never a status snapshot with RTC/user values.
    return {"build": build, "crc": crc, "ready": True, "service": "CLOSED",
            "runtime": "NONE", "ui": "CALCULATOR", "run": 0, "physical_keys": 0}


def cleanup_status(status, phase, foreground):
    for token in ("BUILD=" + phase["new_build"], "FIRMWARE_CRC=valid",
                  "EXPECTED=" + phase["new_crc"], "ACTUAL=" + phase["new_crc"],
                  "RUN=0", "PHYSICAL_KEYS=0", "USB_DISK=0"):
        if not re.search(r"(?<![A-Z_])" + re.escape(token) + r"(?![A-Za-z0-9])", status):
            raise ValueError("cleanup refused: expected new firmware predicates missing")
    if "SERVICE=CLOSED" in status and "RUNTIME=NONE" in status and "UI=CALCULATOR" in status:
        return
    if any("PATH=[" + path + "]" in status for path in foreground) and re.search(r"RUNTIME=(?:APP|NONE)\b", status):
        return
    raise ValueError("cleanup refused: foreground is not owned by this phase")


def listing_rows(reply, command):
    prefix, suffix = command.encode() + b"\r\n", b"mk61> "
    if not reply.startswith(prefix) or not reply.endswith(suffix):
        raise ValueError("listing echo/prompt mismatch")
    lines = reply[len(prefix):-len(suffix)].splitlines()
    if not lines or not re.fullmatch(rb"\d+ (?:entry\.|entries\.)", lines[-1]):
        raise ValueError("listing error or missing success count")
    rows = lines[:-1]
    if int(lines[-1].split()[0]) != len(rows) or len(rows) >= 4096:
        raise ValueError("listing count mismatch or truncated parent")
    if not all(re.fullmatch(rb"(?:d\t[^\r\n\t]+/|f\t\d+ B\t[^\r\n\t]+)", row) for row in rows):
        raise ValueError("listing error or malformed row")
    return rows


def create_owned(p, path, owned, output):
    parent, name = path.rsplit("/", 1)
    command = f'ls "{parent}"'
    rows = listing_rows(p.command(command), command)
    entries = [line.split(b"\t")[-1].rstrip(b"/").lower() for line in rows]
    if name.encode().lower() in entries:
        raise ValueError("temporary directory already exists: " + path)
    command = f'mkdir "{path}"'
    # A prompt alone is not success. Require exactly the native echo and
    # success prompt, then a successful empty listing of the created path.
    reply = p.command(command)
    if reply != command.encode() + b"\r\nmk61> ":
        raise ValueError("temporary mkdir was not proven successful")
    command = f'ls "{path}"'
    if listing_rows(p.command(command), command):
        raise ValueError("fresh temporary directory is not empty")
    owned.append(path)
    (output / "owned.json").write_text(json.dumps(owned) + "\n")


def mark_foreground(path, foreground, output):
    foreground.add(path)
    (output / "foreground.json").write_text(json.dumps(sorted(foreground)) + "\n")


def identity(p):
    if ("UID=" + UID).encode() not in p.command("identity"):
        raise ValueError("wrong Pico UID")


def upload(p, path, data, fault_path=None):
    c = checksum(data)
    if f"@MKC:READY {len(data)}".encode() not in p.command(f'fsput begin "{path}" {len(data)} {c}'):
        raise ValueError("upload not ready")
    started = time.monotonic()
    for start in range(0, len(data), 96 * 4):
        offsets = list(range(start, min(start + 96 * 4, len(data)), 96))
        commands = [f"fsput data {at} {data[at:at+96].hex()}\r".encode() for at in offsets]
        expected = [min(at + 96, len(data)) for at in offsets]
        p.data.clear()
        p.send(b"".join(commands))
        reply = p.wait(lambda b: len(PROMPT.findall(b)) >= len(offsets), 10)
        actual = [int(v) for v in re.findall(rb"@MKC:ACK (\d+)\r?\n", reply)]
        if actual != expected or b"ERROR" in reply:
            if fault_path:
                fault_path.write_bytes(reply)
            raise ValueError("ordered upload ACK mismatch: " + repr((actual, expected)))
        if start and start % (96 * 4 * 512) == 0:
            print(f"upload {path}: {expected[-1]}/{len(data)}", flush=True)
    if f"@MKC:DONE {len(data)} {c}".encode() not in p.command("fsput end", 45):
        raise ValueError("upload commit mismatch")
    if download(p, path) != data:
        raise ValueError("readback mismatch: " + path)
    return {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest(),
            "upload_readback_seconds": time.monotonic() - started}


def download(p, path):
    out = p.command(f'fsget "{path}"', 120)
    data = bytearray()
    for at, block in re.findall(rb"(?m)^@MKC:DATA (\d+) ([0-9A-F]+)\r?$", out):
        if int(at) != len(data):
            raise ValueError("readback offset mismatch")
        data.extend(bytes.fromhex(block.decode()))
    n, c = len(data), checksum(data)
    for tag in ("GET", "END"):
        if f"@MKC:{tag} {n} {c}".encode() not in out:
            raise ValueError("readback checksum mismatch")
    return bytes(data)


def disk_plist(*args):
    out = subprocess.run(["/usr/sbin/diskutil", *args], capture_output=True, check=True, timeout=20).stdout
    return plistlib.loads(out)


def bound_whole_disk():
    """Accept an IOMedia descendant of the exact UID, never a name match."""
    out = subprocess.run(["/usr/sbin/ioreg", "-a", "-r", "-c", "IOUSBHostDevice", "-l", "-w", "0"],
                         capture_output=True, check=True, timeout=5).stdout

    def nodes(node):
        yield node
        for child in node.get("IORegistryEntryChildren", []):
            yield from nodes(child)

    candidates = set()
    for root in plistlib.loads(out):
        for device in nodes(root):
            if device.get("USB Serial Number") == UID:
                for media in nodes(device):
                    if media.get("Whole") is True and re.fullmatch(r"disk\d+", str(media.get("BSD Name", ""))):
                        candidates.add(media["BSD Name"])
    if len(candidates) != 1:
        raise ValueError("exact Pico UID has no unique whole MSC disk yet")
    disk = candidates.pop()
    info = disk_plist("info", "-plist", disk)
    if (info.get("DeviceIdentifier") != disk or info.get("BusProtocol") != "USB" or
            info.get("Internal") is not False or info.get("WholeDisk") is not True or
            info.get("Writable") is not True or info.get("DeviceBlockSize") != 512 or
            not 16 * 1024 * 1024 <= int(info.get("Size", 0)) <= 64 * 1024**3):
        raise ValueError("unsafe whole MSC metadata")
    return disk


def mounted_partition(disk):
    record = disk_plist("list", "-plist", disk)["AllDisksAndPartitions"]
    if len(record) != 1 or record[0].get("DeviceIdentifier") != disk:
        raise ValueError("MSC partition tree mismatch")
    partitions = record[0].get("Partitions", [])
    # A superfloppy FAT volume may use the whole device directly.
    if not partitions:
        partitions = [{"DeviceIdentifier": disk}]
    mounts = []
    for part in partitions:
        identifier = part.get("DeviceIdentifier", "")
        if not re.fullmatch(re.escape(disk) + r"(?:s\d+)?", identifier):
            raise ValueError("foreign partition identifier")
        info = disk_plist("info", "-plist", identifier)
        if not info.get("MountPoint"):
            continue
        mount = Path(info["MountPoint"])
        if (mount.parent != Path("/Volumes") or mount.is_symlink() or
                not mount.is_dir() or mount.stat().st_dev == mount.parent.stat().st_dev):
            raise ValueError("unsafe MSC mount point")
        mounts.append(mount)
    if len(mounts) != 1:
        raise ValueError("MSC has no unique mounted partition yet")
    return mounts[0]


def install_model_msc(p, phase, output, data):
    # The native journal logs at most 512 sectors. Transfer a large asset
    # through the normal exclusive USB disk workflow instead of weakening it.
    usb_identity()
    readiness(p.status(), phase["new_build"], phase["new_crc"])
    p.command("usbdisk")
    active = p.status()
    if "USB_DISK=1" not in active or "SERVICE=USB_DISK" not in active:
        raise ValueError("exclusive USB disk did not start")
    disk = mount = None
    failure = None
    started = time.monotonic()
    try:
        end = time.monotonic() + p.remaining(45)
        while time.monotonic() < end:
            try:
                disk = bound_whole_disk()
                mount = mounted_partition(disk)
                break
            except ValueError:
                time.sleep(0.2)
        if mount is None:
            raise TimeoutError("bound MSC mount deadline")
        # Native code already proved/recorded this directory freshly empty.
        folder = mount / "AI" / phase["nonce"]
        destination = mount / "AI/MODEL.MKA"
        if folder.is_symlink() or not folder.is_dir() or folder.resolve().parent != (mount / "AI").resolve():
            raise ValueError("temporary MSC folder binding mismatch")
        if (mount / "AI").is_symlink() or destination.is_symlink() or destination.is_dir():
            raise ValueError("unsafe model destination")
        stage = folder / "MODEL-UPLOAD.MKA"
        with stage.open("xb") as file:
            file.write(data)
            file.flush()
            os.fsync(file.fileno())
        if stage.read_bytes() != data:
            raise ValueError("MSC staging readback mismatch")
        os.replace(stage, destination)
        with destination.open("rb") as file:
            os.fsync(file.fileno())
        if destination.read_bytes() != data:
            raise ValueError("MSC model readback mismatch")
    except BaseException as e:
        failure = e
    finally:
        # Never return SD ownership to firmware unless normal safe eject
        # succeeds for the exact bound disk. No force-unmount command exists.
        if disk is not None:
            result = subprocess.run(["/usr/sbin/diskutil", "eject", disk], capture_output=True, timeout=25)
            (output / "msc-eject.txt").write_bytes(result.stdout + result.stderr)
            if result.returncode:
                raise ValueError("safe MSC eject failed; leave USB disk active")
            p.command("usbdisk off")
            readiness(p.status(), phase["new_build"], phase["new_crc"])
        else:
            raise ValueError("MSC identity unavailable; leave USB disk active")
    if failure:
        raise failure
    if download(p, "/AI/MODEL.MKA") != data:
        raise ValueError("native post-eject model readback mismatch")
    return {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest(),
            "transport": "exclusive MSC, safe eject, native C5 readback", "seconds": time.monotonic() - started,
            "disk": disk, "safe_eject": True}


def leave_app(p):
    # Two Esc presses also cover a native result page. Do not restore state.
    p.send(b"\x1e\x1b\x1b")
    end = time.monotonic() + p.remaining(20)
    while time.monotonic() < end:
        s = p.status()
        if "SERVICE=CLOSED" in s and "RUNTIME=NONE" in s:
            p.commands()
            return
        p.send(b"\x1b")
    raise TimeoutError("foreground did not close")


def benchmark(p, path, cancel=False, progress_path=None, seconds=None, cancel_step=8):
    seconds = (180 if cancel else 600) if seconds is None else seconds
    if not 1 <= seconds <= 1200 or not 0 <= cancel_step < 12:
        raise ValueError("invalid benchmark schedule")
    p.data.clear()
    p.send(f'run "{path}"\r'.encode())
    sent = observed = None
    logged = set()
    end = time.monotonic() + p.remaining(seconds)
    while time.monotonic() < end:
        out = bytes(p.data)
        for marker in re.findall(rb"(?m)^AI_(?:LOAD|BENCH)[^\r\n]*", out):
            if marker not in logged:
                logged.add(marker)
                line = f"{time.monotonic():.3f} " + marker.decode("ascii")
                print(line, flush=True)
                if progress_path:
                    with progress_path.open("a") as file:
                        file.write(line + "\n")
        if cancel and sent is None and f"AI_BENCH mode=0 step={cancel_step} begin".encode() in out:
            # Give forward() time to enter, then measure the actual service
            # callback response, not just reception of the progress marker.
            enter = time.monotonic() + p.remaining(0.05)
            while time.monotonic() < enter:
                p.pump()
            sent = time.monotonic()
            p.send(b"\x1b")
        if sent is not None and observed is None and b"AI_CANCEL\r\n" in out:
            observed = time.monotonic() - sent
        if PROMPT.search(out):
            if not cancel and b"ERROR" in out:
                raise ValueError("benchmark APP returned error")
            if cancel and (sent is None or observed is None):
                raise ValueError("cancellation was not observed")
            return observed
        p.pump()
    raise TimeoutError("benchmark phase deadline")


def cleanup(p, phase, owned, foreground, before_remove=None):
    usb_identity()
    cleanup_status(p.status(), phase, foreground)
    try:
        leave_app(p)
    except BaseException:
        p.close()
        raise
    p.command("fsput cancel")
    if before_remove:
        before_remove(p)
    errors = []
    for path in reversed(owned):
        try:
            # Only directories freshly created by this worker are removed.
            p.command(f'rm -r "{path}"', 30)
        except Exception as e:
            errors.append(str(e))
    p.send(b"\x1e")
    final = readiness(p.status(), phase["new_build"], phase["new_crc"])
    if errors:
        raise ValueError("cleanup failed: " + repr(errors))
    return final


def worker(phase, output):
    with (output / "worker-attempt.json").open("x") as marker:
        json.dump({"phase_sha256": phase["_sha"]}, marker)
    end = time.monotonic() + phase["deadline_seconds"]
    p = None
    initial_accepted = False
    own_hardware_started = False
    foreground = set()
    owned = []
    report = {"phase_sha256": phase["_sha"], "uid": UID, "save_or_restore": False,
              "passed": False, "installed": {}, "temporary_removed": False}
    failure = None
    payloads = phase["payloads"]
    try:
        wait_usb_identity()
        p = Serial(end)
        readiness(p.status(), phase["new_build"], phase["new_crc"])
        initial_accepted = True
        p.commands()
        identity(p)
        print("installed image native build/CRC and UID ready; no flash/reset", flush=True)
        own_hardware_started = True
        for directory in ("/AI", "/Apps/MK61AI"):
            p.command(f'mkdir -p "{directory}"')
        # Temp directory collision is an error, never an excuse to delete it.
        for directory in ("/AI/" + phase["nonce"], "/Apps/MK61AI/" + phase["nonce"]):
            create_owned(p, directory, owned, output)
        model_data = Path(payloads["model"]["path"]).read_bytes()
        report["installed"]["/AI/MODEL.MKA"] = install_model_msc(p, phase, output, model_data)
        print("installed model by exclusive MSC; safe eject and native readback PASS", flush=True)
        destinations = [("launcher", "/Apps/MK61AI/MK61AI.APP"),
                        ("probe", "/Apps/MK61AI/" + phase["nonce"] + "/AIBENCH.APP")]
        for name, path in destinations:
            report["installed"][path] = upload(p, path, Path(payloads[name]["path"]).read_bytes(), output / "upload-fault.bin")
            print("installed and read back " + path, flush=True)
        probe = destinations[-1][1]
        mark_foreground(probe, foreground, output)
        benchmark(p, probe)
        full = json.loads(download(p, "/AI/" + phase["nonce"] + "/BENCH.JSON"))
        (output / "benchmark.json").write_text(json.dumps(full, indent=2) + "\n")
        if not (full["device"] and not full["cancelled"] and full["matching_greedy_tokens"] and
                full["valid_tool_prefix"] and full["max_session_roundtrip"] and
                all(full[k]["prefill_tokens"] == 8 and full[k]["decode_tokens"] == 4
                    for k in ("reference", "lut_fp32", "constrained_lut")) and
                0 < full["sampled_heap_peak"] < full["heap_capacity"] and
                0 < full["stack_high_water"] < 32768):
            raise ValueError("benchmark assertions failed")
        print("36 real model steps, kernel parity, max-session codec and memory PASS", flush=True)
        leave_app(p)
        latency = benchmark(p, probe, cancel=True)
        cancelled = json.loads(download(p, "/AI/" + phase["nonce"] + "/BENCH.JSON"))
        cancelled["host_cancel_response_seconds"] = latency
        (output / "cancellation.json").write_text(json.dumps(cancelled, indent=2) + "\n")
        if not cancelled["cancelled"] or not cancelled["max_session_roundtrip"]:
            raise ValueError("cancel roundtrip assertion failed")
        leave_app(p)
        # Open the actual installed launcher and close its home screen.
        p.data.clear()
        mark_foreground("/Apps/MK61AI/MK61AI.APP", foreground, output)
        p.send(b'run "/Apps/MK61AI/MK61AI.APP"\r')
        until = time.monotonic() + p.remaining(10)
        while time.monotonic() < until:
            if "RUNTIME=APP" in p.status():
                break
        else:
            raise ValueError("installed launcher did not open")
        leave_app(p)
        report["passed"] = True
        print("cancellation and installed launcher lifecycle PASS", flush=True)
    except BaseException as e:
        failure = e
        report["error"] = type(e).__name__ + ": " + str(e)
    finally:
        try:
            if initial_accepted and own_hardware_started:
                if p is None:
                    usb_identity()
                    p = Serial(time.monotonic() + 90)
                else:
                    p.deadline = time.monotonic() + 90
                report["final"] = cleanup(p, phase, owned, foreground)
                report["temporary_removed"] = True
        except BaseException as e:
            report["cleanup_error"] = type(e).__name__ + ": " + str(e)
            report["passed"] = False
        finally:
            if p:
                p.close()
            report["cdc_closed"] = p is None or p.fd == -1
            (output / "result.json").write_text(json.dumps(report, indent=2) + "\n")
    if failure or not report["passed"]:
        raise RuntimeError(report.get("error", report.get("cleanup_error")))


def recover(phase, output):
    # Used only after the outer supervisor has killed AND reaped its worker.
    # Never flashes/reboots, never restores old data.
    owned = json.loads((output / "owned.json").read_text()) if (output / "owned.json").exists() else []
    allowed = {"/AI/" + phase["nonce"], "/Apps/MK61AI/" + phase["nonce"]}
    if not set(owned) <= allowed:
        raise ValueError("unexpected cleanup ownership record")
    foreground = set(json.loads((output / "foreground.json").read_text())) if (output / "foreground.json").exists() else set()
    if not foreground <= {"/Apps/MK61AI/" + phase["nonce"] + "/AIBENCH.APP", "/Apps/MK61AI/MK61AI.APP"}:
        raise ValueError("unexpected foreground ownership record")
    usb_identity()
    p = Serial(time.monotonic() + 90)
    try:
        final = cleanup(p, phase, owned, foreground)
        (output / "recovery.json").write_text(json.dumps(final, indent=2) + "\n")
    finally:
        p.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase", type=Path, required=True)
    parser.add_argument("--grant", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--execute", action="store_true", required=True)
    parser.add_argument("--worker", action="store_true")
    parser.add_argument("--recover", action="store_true")
    args = parser.parse_args()
    phase = validate(args.phase, args.grant)
    phase["_sha"] = sha(args.phase)
    args.output.mkdir(parents=True, exist_ok=True)
    if args.recover:
        recover(phase, args.output)
    elif args.worker:
        worker(phase, args.output)
    else:
        if (args.output / "supervisor.json").exists():
            raise ValueError("phase already attempted")
        command = [sys.executable, str(Path(__file__).resolve()), "--phase", str(args.phase.resolve()),
                   "--grant", str(args.grant.resolve()), "--output", str(args.output.resolve()), "--execute"]
        with (args.output / "worker.log").open("w") as log:
            process = subprocess.Popen(command + ["--worker"], stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
            record = {"pid": process.pid, "phase_sha256": phase["_sha"], "reaped": False}
            (args.output / "supervisor.json").write_text(json.dumps(record, indent=2) + "\n")
            try:
                code = process.wait(timeout=phase["deadline_seconds"] + 105)
            except BaseException:
                os.killpg(process.pid, signal.SIGKILL)
                code = process.wait(timeout=10)
                record["forced_stop"] = True
                subprocess.run(command + ["--recover"], stdout=log, stderr=subprocess.STDOUT, timeout=100)
            finally:
                if process.poll() is None:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait(timeout=10)
                record.update({"exit_code": process.returncode, "reaped": True})
                (args.output / "supervisor.json").write_text(json.dumps(record, indent=2) + "\n")
        if code:
            raise SystemExit(code)


if __name__ == "__main__":
    main()

"""Verify the frozen evidence and exact source fingerprint without device I/O."""
import hashlib
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))
import clock_protocol
import metrology

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def require(ok, message):
    if not ok:
        raise ValueError(message)

def main():
    manifest = json.loads((HERE / "ARCHIVE.json").read_text())
    for name, value in manifest["files"].items():
        require(sha(HERE / name) == value, "Changed archive file: " + name)
    meta = json.loads((HERE / "DIAGNOSTIC.json").read_text())
    original = Path(meta["image_manifest"]).parents[1]
    def local(path):
        return HERE / Path(path).relative_to(original)
    for name, value in meta["source_files"].items():
        require(sha(ROOT / name) == value, "Tested source changed: " + name)
    firmware = json.loads((HERE / "firmware-003/manifest.json").read_text())
    digest = hashlib.sha256()
    inputs = [ROOT / "tools/firmware/picocalc/build_picocalc.py", ROOT / "dev/lib/seal_picocalc.py"]
    inputs += [p for folder in ("code", "ports/picocalc", "third_party/fatfs", "third_party/core_math")
               for p in (ROOT / folder).rglob("*") if p.is_file() and
               (p.suffix in (".c", ".cpp", ".h", ".hpp", ".S", ".inc", ".ld", ".pio")
                or p.name == "CMakeLists.txt")]
    for path in sorted(inputs):
        digest.update(str(path.relative_to(ROOT)).encode() + b"\0")
        digest.update(path.read_bytes())
    digest.update(b"cosmic-clock-diagnostic=1\0")
    require(digest.hexdigest() == firmware["source_sha256"], "Complete firmware source fingerprint differs")
    ladder = json.loads((HERE / "LADDER-001.json").read_text())
    require([r["mhz"] for r in ladder["rows"]] == [125, *range(130, 251, 10)], "Incomplete ladder")
    modes = windows = probes = 0
    for row in ladder["rows"]:
        path = local(row["receipt"])
        receipt = json.loads(path.read_text())
        require(sha(path) == row["receipt_sha256"], "Changed receipt")
        require(receipt["lease"] == "reserved_ports_closed", "Port not released")
        require(all(s["closed"] and not s["errors"] for s in receipt["cdc_sessions"]), "CDC close error")
        if row["mhz"] == 250:
            require(receipt["status"] == "HOLD" and receipt.get("primary_error") is None and
                    receipt["error"] == "Hold('Fallback reset missed105s deadline')" and
                    receipt["cleanup_native_verified"], "Unexpected historical HOLD")
        else:
            require(receipt["status"] == "PASS", "Failed clock mode")
        if row["mhz"] in (125, 200, 250):
            raw = (path.parent / "game.txt").read_bytes()
            for parsed in (metrology.measurements(raw), metrology.pipeline_details(raw), metrology.sound_details(raw)):
                require(all(receipt["result"][key] == value for key, value in parsed.items()), "Window reparse differs")
            modes += 1
            windows += len(receipt["result"]["windows"])
        for probe in receipt["usb_probes"]:
            raw = (HERE / "usb" / f'{path.parent.name}-{probe["sequence"]}.txt').read_text()
            require(clock_protocol.usb(raw, probe["sequence"], bytes.fromhex(probe["challenge"])) == probe["result"],
                    "USB checksum/data mismatch")
            probes += 1
    timeout = json.loads((HERE / "TIMEOUT-PROBE-001.result/receipt.json").read_text())
    supervisor = json.loads((HERE / "TIMEOUT-PROBE-001.supervisor.json").read_text())
    require(timeout["status"] == "PASS" and timeout["automatic_125_fallback_verified"] and
            104 <= timeout["fallback_observed_seconds"] <= 115, "Independent return unproved")
    require(supervisor["reaped"] and supervisor["exit_code"] == 0 and not supervisor["timed_out"], "Child not reaped")
    for probe in timeout["usb_probes"]:
        raw = (HERE / "usb" / f'TIMEOUT-PROBE-001.result-{probe["sequence"]}.txt').read_text()
        require(clock_protocol.usb(raw, probe["sequence"], bytes.fromhex(probe["challenge"])) == probe["result"],
                "Timeout probe USB data mismatch")
    require((modes, windows, probes) == (3, 30, 45), "Missing complete evidence")
    print("PASS: exact C3F35FAE sources, 14 frequencies, 30 windows, 48 USB transfers and independent 250→125 return")

if __name__ == "__main__":
    main()

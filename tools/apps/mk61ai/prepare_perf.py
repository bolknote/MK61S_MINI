#!/usr/bin/env python3
"""Materialize an AI HIL comparison packet on the host; never opens hardware."""
import argparse
import hashlib
import json
from pathlib import Path
import secrets
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[3]


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def item(path):
    path = Path(path).resolve()
    return dict(path=str(path), bytes=path.stat().st_size, sha256=sha(path))


def materialize(args):
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    firmware = {k: json.loads((d / "manifest.json").read_text()) for k, d in
                (("baseline", args.baseline), ("normal", args.normal), ("oc", args.overclock))}
    firmware_dirs = dict(baseline=args.baseline, normal=args.normal, oc=args.overclock)
    if firmware["normal"].get("ai_overclock_diagnostic") or not firmware["oc"].get("ai_overclock_diagnostic"):
        raise ValueError("normal and diagnostic firmware flags differ from the experiment")
    runtime_sources = sorted([ROOT / "tools/firmware/picocalc/build_picocalc.py", ROOT / "dev/lib/seal_picocalc.py",
        *(p for d in ("code", "ports/picocalc", "third_party/fatfs", "third_party/core_math") for p in (ROOT / d).rglob("*")
          if p.is_file() and (p.suffix in (".c", ".cpp", ".h", ".hpp", ".S", ".inc", ".ld", ".pio") or p.name == "CMakeLists.txt"))])
    digest = hashlib.sha256()
    for path in runtime_sources:
        digest.update(str(path.relative_to(ROOT)).encode() + b"\0");digest.update(path.read_bytes())
    if digest.hexdigest() != firmware["normal"]["source_sha256"]:
        raise ValueError("ordinary image was not built from this exact source")
    digest.update(b"picocalc-ai-overclock=1\0")
    if digest.hexdigest() != firmware["oc"]["source_sha256"]:
        raise ValueError("diagnostic image was not built from this exact source")
    source_files = runtime_sources + [ROOT / p for p in (
        "tests/hil_mk61_ai_perf.py", "tests/hil_mk61_ai.py", "tests/hil_mk61_ai_finish.py",
        "tests/mk61_ai_file_hash_probe.c", "examples/portable-apps/MK61AI/bench.c")]
    source_files += [Path(__file__).resolve(), ROOT / "tools/apps/portable/build_portable_app.py",
                     *(p for p in (ROOT / "sdk/portable").rglob("*") if p.is_file())]
    pins = {str(p.resolve()): sha(p) for p in source_files}
    config = dict(kernel=2, arithmetic=3, cores=2, freeze=1, filter=0, mhz=125,
                  prefill=8, decode=4, repeat=2, stress_ms=0, control=0, constrained=0)
    experiments = [
        ("freeze", dict(kernel=0, cores=1), "full-lut", None),
        ("flash-kernel", dict(kernel=1, cores=1), "full-lut", None),
        ("sram-kernel", dict(cores=1), "full-lut", None),
        ("dual-core", dict(stress_ms=1000), "full-lut", None),
        ("dual-live-screen", dict(freeze=0), "full-lut", None),
        ("sparse-head", dict(filter=1, constrained=1), "full-lut", None),
        ("int8-planes", dict(arithmetic=1), "full-lut", None),
        ("lut-int8", dict(arithmetic=2), "full-lut", None),
        ("int8-nibble", dict(arithmetic=1), "full-nibble", None),
        ("vocab4096", {}, "vocab4096-lut", None),
        ("vocab2048", {}, "vocab2048-lut", None),
        ("escape", dict(prefill=2, decode=2, repeat=1), "full-lut", dict(pass_=1, step=1, key=27)),
        ("pause-key", dict(prefill=2, decode=2, repeat=1), "full-lut", dict(pass_=1, step=1, key=133)),
        ("clock200", dict(mhz=200, control=1, stress_ms=120000), "full-lut", None),
        ("clock250", dict(mhz=250, control=1, stress_ms=120000), "full-lut", None),
        ("clock300", dict(mhz=300, control=1, stress_ms=120000), "full-lut", None),
    ]
    sequence = [];counter = 0
    def phase(action, image, name, previous=None):
        nonlocal counter
        counter += 1
        nonce = "HILV3-20261106-" + secrets.token_hex(6).upper()
        folder = out / f"{counter:02d}-{name}";folder.mkdir()
        m = firmware[image]
        p = dict(schema=3, uid="E6657CD423721C35", port="/dev/cu.usbmodem11301", save_or_restore=False,
                 deadline_seconds=850, action=action, nonce=nonce,
                 new_build=m["build_id"].upper(), new_crc=m["firmware_integrity"]["crc32"].upper(),
                 script_sha256=sha(ROOT / "tests/hil_mk61_ai_perf.py"), helper_sha256=sha(ROOT / "tests/hil_mk61_ai.py"),
                 finish_helper_sha256=sha(ROOT / "tests/hil_mk61_ai_finish.py"), source_pins=dict(pins),
                 payloads={"firmware_manifest": item(firmware_dirs[image] / "manifest.json")})
        if action == "flash":
            for ext in ("uf2", "bin"):
                p["payloads"][ext] = item(firmware_dirs[image] / ("mk61s-picocalc-pico-h." + ext))
            p["payloads"]["picotool"] = item(args.picotool)
            p["old_build"] = firmware[previous]["build_id"].upper() if previous else args.entry_build
            p["old_crc"] = firmware[previous]["firmware_integrity"]["crc32"].upper() if previous else args.entry_crc
        return folder, p
    def seal(folder, p, name):
        destination = folder / "PHASE.json"
        destination.write_text(json.dumps(p, indent=2) + "\n")
        sequence.append(dict(name=name, phase=str(destination), phase_sha256=sha(destination),
                             action=p["action"], requires_separate_root_go=True))
        print(f"prepared {name}: {destination}", flush=True)
    def app_payloads(folder, p, model):
        nonce = p["nonce"];directory = "/AI/" + nonce
        alternate = model != "full-lut"
        path = directory + "/MODEL.MKA" if alternate else "/AI/MODEL.MKA"
        p.update(alternate_model=alternate, expected_usb_reenumerations=0, cancel_at=None)
        package = args.models / model / "MODEL.MKA"
        p["payloads"]["model"] = item(package)
        wrapper = folder / "benchmark.c"
        wrapper.write_text('#define MK61_AI_DIAGNOSTIC_DIRECTORY ' + json.dumps(directory) + '\n#include ' +
                           json.dumps(str(ROOT / "examples/portable-apps/MK61AI/bench.c")) + '\n')
        hash_wrapper = folder / "hash.c"
        hash_wrapper.write_text('#define MK61_AI_HASH_PATH ' + json.dumps(path) + '\n#define MK61_AI_HASH_BYTES ' +
                                str(package.stat().st_size) + 'U\n#include ' +
                                json.dumps(str(ROOT / "tests/mk61_ai_file_hash_probe.c")) + '\n')
        for name, source in (("AIBENCH", wrapper), ("AIHASH", hash_wrapper)):
            subprocess.run([sys.executable, str(ROOT / "tools/apps/portable/build_portable_app.py"),
                            "--target", "picocalc-pico-h", "--shared-runtime", "--name", name,
                            "--source", str(source), "--arm-toolchain-bin", str(args.toolchain),
                            "--output-dir", str(folder / name)], check=True, stdout=subprocess.DEVNULL)
            p["source_pins"][str(source)] = sha(source)
        p["payloads"]["benchmark"] = item(folder / "AIBENCH/AIBENCH.APP")
        p["payloads"]["hashprobe"] = item(folder / "AIHASH/AIHASH.APP")
    folder, p = phase("flash", "baseline", "flash-baseline")
    seal(folder, p, "flash-baseline")
    folder, p = phase("baseline", "baseline", "baseline-B0")
    app_payloads(folder, p, "full-lut");seal(folder, p, "baseline-B0")
    folder, p = phase("flash", "normal", "flash-candidate", "baseline")
    seal(folder, p, "flash-candidate")
    for name, changes, model, cancel in experiments:
        if name == "clock200":
            folder, p = phase("flash", "oc", "flash-oc-diagnostic", "normal")
            seal(folder, p, "flash-oc-diagnostic")
        c = dict(config, **changes)
        folder, p = phase("perf", "normal" if c["mhz"] == 125 else "oc", name)
        app_payloads(folder, p, model)
        p.update(config=c, expected_usb_reenumerations=2 if c["mhz"] != 125 else 0)
        if cancel:
            p["cancel_at"] = dict(pass_=cancel["pass_"], step=cancel["step"], key=cancel["key"])
            p["cancel_at"]["pass"] = p["cancel_at"].pop("pass_")
        cfg = folder / "PERF.CFG"
        cfg.write_text("AIPERF1\n" + "".join(f"{k}={v}\n" for k, v in c.items()))
        p["payloads"]["config"] = item(cfg);seal(folder, p, name)
    folder, p = phase("flash", "normal", "final-normal-125", "oc")
    seal(folder, p, "final-normal-125")
    plan = dict(schema=1, status="HOST_PREPARED_NOT_RUN", physical_io=False,
                first_entry_binding_required=args.entry_build is None or args.entry_crc is None,
                sequence=sequence, policy="Every phase needs its own exact fresh ROOT GO. Stop at first unexpected fault. No old state/RTC saved or restored. Clock phases explicitly disconnect USB twice, use stock voltage and restore 125MHz before SD/return. Final ordinary image is separately flashed after successful diagnostic phases.")
    (out / "PLAN.json").write_text(json.dumps(plan, indent=2) + "\n")
    print(json.dumps({"plan": str(out / "PLAN.json"), "phases": len(sequence), "physical_io": False}))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ("output", "baseline", "normal", "overclock", "models", "picotool", "toolchain"):
        p.add_argument("--" + name, type=Path, required=True)
    p.add_argument("--entry-build", help="Exact build from the later coordinator release; omit for an unexecutable first draft")
    p.add_argument("--entry-crc")
    materialize(p.parse_args())


if __name__ == "__main__": main()

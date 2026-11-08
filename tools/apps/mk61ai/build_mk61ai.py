#!/usr/bin/env python3
"""Build the native PicoCalc launcher and an SD bundle from frozen weights."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tools"))
from firmware.picocalc.build_picocalc import compiler_bin
from export_model import export
from build_m3_linear import build as build_m3_linear


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--weights", type=Path, required=True, help="Frozen MKQ4v1 or MKQBv1 file")
    parser.add_argument("--hf", type=Path, required=True, help="Matching HF directory with tokenizer.json")
    parser.add_argument("--output-dir", type=Path, default=ROOT / ".build/mk61ai/bundle")
    parser.add_argument("--build-dir", type=Path, default=ROOT / ".build/mk61ai")
    parser.add_argument("--toolchain", type=Path)
    parser.add_argument("--sdk", type=Path)
    parser.add_argument("--jobs", type=int, default=4)
    parser.add_argument("--prompt", type=Path, help="Optional UTF-8 prefix; otherwise use firmware default")
    parser.add_argument("--validation", type=Path, help="Matching native validation report to include in the bundle")
    firmware = parser.add_mutually_exclusive_group(required=True)
    firmware.add_argument("--build-firmware", action="store_true")
    firmware.add_argument("--firmware", type=Path, help="Already built matching UF2")
    args = parser.parse_args()
    out = args.output_dir.resolve()
    build = args.build_dir.resolve()
    toolchain = compiler_bin(args.toolchain)
    app_dir, model_dir = out / "sd/Apps/MK61AI", out / "sd/AI"
    app_dir.mkdir(parents=True, exist_ok=True)
    model_dir.mkdir(parents=True, exist_ok=True)
    subprocess.run([sys.executable, str(ROOT / "tools/apps/portable/build_portable_app.py"),
                    "--target", "picocalc-pico-h", "--shared-runtime", "--name", "MK61AI",
                    "--source", str(ROOT / "examples/portable-apps/MK61AI/main.c"),
                    "--handled-magic", "M6", "--arm-toolchain-bin", str(toolchain),
                    "--output-dir", str(build / "app")], check=True)
    shutil.copy2(build / "app/MK61AI.APP", app_dir / "MK61AI.APP")
    subprocess.run([sys.executable, str(ROOT / "tools/apps/portable/build_portable_app.py"),
                    "--target", "picocalc-pico-h", "--shared-runtime", "--name", "AIBENCH",
                    "--source", str(ROOT / "examples/portable-apps/MK61AI/bench.c"),
                    "--arm-toolchain-bin", str(toolchain), "--output-dir", str(build / "benchmark")], check=True)
    shutil.copy2(build / "benchmark/AIBENCH.APP", app_dir / "AIBENCH.APP")
    m3 = build_m3_linear(build / "m3-linear", toolchain)
    shutil.copy2(m3["package"], model_dir / "M3LINE.S3M")
    export(args.weights.resolve(), args.hf.resolve() / "tokenizer.json", model_dir / "MODEL.MKA", "lut")
    prompt_path = model_dir / "PROMPT.TXT"
    if args.prompt:
        prompt = args.prompt.read_bytes()
        prompt.decode("utf-8")
        if len(prompt) >= 1024 or b"\0" in prompt:
            parser.error("Prompt must be UTF-8, shorter than 1024 bytes and contain no NUL")
        prompt_path.write_bytes(prompt)
    elif prompt_path.exists():
        prompt_path.unlink()
    readme = ROOT / "examples/portable-apps/MK61AI/README.md"
    shutil.copy2(readme, out / "README.md")
    uf2 = args.firmware
    if args.build_firmware:
        command = [sys.executable, str(ROOT / "tools/firmware/picocalc/build_picocalc.py"),
                   "--toolchain", str(toolchain), "--build-path", str(build / "native-build"),
                   "--output-dir", str(build / "native"), "--jobs", str(args.jobs)]
        if args.sdk:
            command += ["--sdk", str(args.sdk.resolve())]
        subprocess.run(command, check=True)
        uf2 = build / "native/mk61s-picocalc-pico-h.uf2"
    if uf2:
        shutil.copy2(uf2, out / "mk61s-picocalc-pico-h.uf2")
        metadata = uf2.parent / "manifest.json"
        if metadata.exists():
            shutil.copy2(metadata, out / "firmware.json")
        elif (out / "firmware.json").exists():
            (out / "firmware.json").unlink()
    manifest = {
        "target": "PicoCalc + Pico H (RP2040), 8 MiB PSRAM",
        "ai_service": {"id": 2, "version": 1, "diagnostic_version": 2},
        "model": json.loads((model_dir / "MODEL.json").read_text()),
        "launcher": json.loads((build / "app/MK61AI.json").read_text()),
        "benchmark": json.loads((build / "benchmark/AIBENCH.json").read_text()),
        "arithmetic": "LUT FP32", "kv": "FP32 in PSRAM",
        "optional_m3": m3,
        "hardware_verified": False,
        "files": {},
    }
    validation_path = out / "validation.json"
    if args.validation:
        validation = json.loads(args.validation.read_text())
        if (validation["firmware"]["uf2_sha256"] != hashlib.sha256((out / "mk61s-picocalc-pico-h.uf2").read_bytes()).hexdigest()
                or validation["model"]["sha256"] != manifest["model"]["sha256"]):
            parser.error("Validation report does not match the firmware and model in this bundle")
        shutil.copy2(args.validation, validation_path)
        hardware = validation.get("hardware", {})
        manifest["hardware_verified"] = bool(hardware.get("performed") and hardware.get("result", {}).get("passed"))
        manifest["validation"] = {"file": "validation.json", "schema": validation["schema"]}
    elif validation_path.exists():
        validation_path.unlink()
    for path in sorted(out.rglob("*")):
        if path.is_file() and path.name != "manifest.json":
            data = path.read_bytes()
            manifest["files"][str(path.relative_to(out))] = {
                "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}
    (out / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    archive = out.with_suffix(".zip")
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as z:
        for path in sorted(out.rglob("*")):
            if path.is_file():
                z.write(path, str(path.relative_to(out)))
    print(f"PicoCalc AI bundle: {archive}")


if __name__ == "__main__":
    main()

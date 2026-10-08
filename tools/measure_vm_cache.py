#!/usr/bin/env python3
"""Measure owned VM modules and package feasibility; no firmware/device writes.

Shared pools below are only a size lower bound, NOT an executable package.
This keeps potential package savings separate from the implemented RAM cache.
"""
import argparse
import json
import shutil
import struct
import subprocess
from pathlib import Path

from measure_language_vm import ROOT, corpus
import m8_codec


def run(*command):
    result = subprocess.run([str(x) for x in command], cwd=ROOT, text=True,
                            capture_output=True, check=True)
    return result.stdout


def resources(image):
    if not image[7] & 8:
        return []
    at = struct.unpack_from("<H", image, 30)[0]
    pool = []
    while at < len(image):
        length = struct.unpack_from("<H", image, at)[0]
        assert at + 2 + length <= len(image)
        pool.append(image[at+2:at+2+length])
        at += 2 + length
    assert at == len(image)
    return pool


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=ROOT/"tmp/vm-cache/measure")
    args = parser.parse_args()
    out = args.output_dir.resolve()
    out.mkdir(parents=True, exist_ok=True)
    compiler = shutil.which("clang++") or shutil.which("c++")
    if not compiler:
        raise RuntimeError("host C++ compiler required")
    probe = out/"probe"
    run(compiler, "-std=c++17", "-O2", "-Wall", "-Wextra", "-Werror",
        "-I"+str(ROOT/"code"), ROOT/"tools/language_vm_probe.cpp",
        ROOT/"code/language_bytecode.cpp", ROOT/"code/language_vm.cpp",
        ROOT/"code/zx0_encode.cpp", "-o", probe)
    layout = json.loads(run(probe, "--cache-layout"))
    source_dir = out/"source"
    source_dir.mkdir(exist_ok=True)
    sources = list(corpus(source_dir))
    # An explicit measurement list, never inferred runtime dependencies.
    for path in sorted((ROOT/"programs/games/Turochamp").glob("*.tbi")):
        destination = source_dir/("turochamp-"+path.name)
        destination.write_bytes(m8_codec.encode(path.read_text(encoding="utf-8")))
        sources.append(("basic", destination, str(path.relative_to(ROOT))))
    programs = []
    pools = {}
    for language, source, origin in sources:
        measured = {}
        for mode, option in (("source", "--source-resources"), ("owned", "--owned-resources")):
            image = out/(source.stem+"-"+mode+".bvm")
            measured[mode] = json.loads(run(probe, language, source, image, option))
            if mode == "owned":
                pools[origin] = resources(image.read_bytes())
        programs.append({"language": language, "origin": origin,
                         "source_file": str(source.relative_to(out)), **measured})
    packages = {}
    for name in ("High Noon", "Turochamp"):
        members = [p for p in programs if p["origin"].startswith("programs/games/"+name+"/")]
        strings = set(s for p in members for s in pools[p["origin"]])
        code = sum(p["owned"]["code_bytes"] for p in members)
        separate = sum(p["owned"]["bytecode_bytes"] for p in members)
        shared = code+sum(2+len(s) for s in strings)
        packages[name] = {
            "modules": [p["origin"] for p in members],
            "source_bytes": sum(p["source"]["source_bytes"] for p in members),
            "source_backed_bytes": sum(p["source"]["bytecode_bytes"] for p in members),
            "owned_bytes": separate,
            "aligned_cache_bytes": sum((p["owned"]["bytecode_bytes"]+7)&~7 for p in members),
            "code_and_maps_bytes": code,
            "shared_pool_lower_bound_bytes": shared,
            "shared_pool_maximum_saving_bytes": separate-shared,
            "whole_package_can_fit_payload": shared <= layout["payload_bytes"],
            "note": "Shared-pool lower bound excludes package header, entry table and padding; not a runnable package."
        }
    report = {"head": run("git", "rev-parse", "HEAD").strip(), "cache": layout,
              "program_count": len(programs), "programs": programs, "packages": packages,
              "notes": ["Host compiler/format size only; no device timings or heap high-water.",
                        "All sources are M8, not UTF-8 byte counts.",
                        "Source recipes and owned resources use the same code and numeric ABI.",
                        "No automatic package preload or filesystem cache is implemented."]}
    (out/"report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2)+"\n")
    print(json.dumps({"cache": layout, "program_count": len(programs), "packages": packages},
                     ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

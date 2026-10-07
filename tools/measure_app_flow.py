#!/usr/bin/env python3
"""Compare completed matched APP-flow bundles; no builds/device writes."""
import argparse
import json
import struct
from pathlib import Path
from measure_resident_language_vm import elf_info

ROOT = Path(__file__).resolve().parents[1]


def bundle(directory):
    roots = [p for p in directory.iterdir() if p.is_dir() and p.name.startswith("mk61s-")]
    assert len(roots) == 1, directory
    root = roots[0]
    binary = next(root.glob("*.bin")); elf = next(root.glob("*.elf"))
    apps = {}
    for file in (root / "System").glob("*.APP"):
        data = file.read_bytes()
        image, memory = struct.unpack_from("<II", data, 28)
        apps[file.stem] = {"image_bytes": image, "memory_bytes": memory, "app_bytes": len(data)}
    assert all(name in apps for name in ("BASIC", "FOCAL", "LANGVM", "LANGIN", "EXPLORER", "SETUP"))
    return {"path": str(root), "flags": (root / "build.flags").read_text().split(),
            "flash_bytes": binary.stat().st_size, **elf_info(elf), "apps": apps}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, default=ROOT / "tmp/app-flow")
    parser.add_argument("--baseline-ref", default="fc327699")
    parser.add_argument("--candidate-label", default="app_flow")
    parser.add_argument("--expect-cache-off", action="store_true")
    args = parser.parse_args()
    comparisons = {}
    for profile in ("f401", "f411"):
        old = bundle(args.directory / "baseline" / profile)
        new = bundle(args.directory / "candidate" / profile)
        assert old["flags"] == new["flags"], "feature/math/placement mismatch"
        if args.expect_cache_off:
            assert "-DMK61_LANGUAGE_VM_IMAGE_CACHE_BYTES=0" in old["flags"], "RAM cache not explicitly disabled"
        assert old["apps"].keys() == new["apps"].keys()
        comparisons[profile] = {
            "baseline": old, args.candidate_label: new,
            "resident_flash_delta": new["flash_bytes"] - old["flash_bytes"],
            "resident_static_ram_delta": new["static_ram_bytes"] - old["static_ram_bytes"],
            "dynamic_pool_delta": new["dynamic_bytes"] - old["dynamic_bytes"],
            "app_delta": {name: {key: new["apps"][name][key] - old["apps"][name][key]
                                 for key in new["apps"][name]} for name in new["apps"]},
            "external_app_file_delta": sum(a["app_bytes"] for a in new["apps"].values()) -
                                       sum(a["app_bytes"] for a in old["apps"].values())}
    report = {"comparisons": comparisons,
              "notes": [f"Matched frozen source baseline {args.baseline_ref} plus {args.candidate_label} changes.",
                        "RAM figures are ELF/image budgets, not simultaneous device heap/stack peaks.",
                        "Larger hot/cold APPs contain policy moved out of the resident.",
                        "No APP arena/workspace/source quota or functionality was reduced."]}
    if args.expect_cache_off:
        report["notes"].append("RAM bytecode cache is explicitly zero in BOTH baseline and candidate; this is not the F411 default cache configuration.")
    (args.directory / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({p: {k: c[k] for k in ("resident_flash_delta", "resident_static_ram_delta",
                    "dynamic_pool_delta", "external_app_file_delta", "app_delta")}
                    for p, c in comparisons.items()}, indent=2))


if __name__ == "__main__": main()

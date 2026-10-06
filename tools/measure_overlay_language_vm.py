#!/usr/bin/env python3
"""Measure completed matched overlay-VM bundles and the current program corpus.

Only builds a host bytecode probe; does not build/flash firmware or change C6.
Arena budgets exclude live C heap and C-stack high-water, which require HIL.
"""
import argparse
import json
import re
import shutil
import struct
from pathlib import Path

from measure_language_vm import ROOT, corpus, run
from measure_resident_language_vm import elf_info

VALUES_BYTES, STATE_BYTES, WORKSPACE_BYTES = 3504, 1504, 8192
IMAGE_ROOM = WORKSPACE_BYTES - VALUES_BYTES - STATE_BYTES


def resident_input_frame(elf, objdump, pattern=r"language_vm::\(anonymous namespace\)::read_input"):
    """Own fixed frame from shipping ARM instructions, not a call-graph peak."""
    assembly = run([objdump, "-d", "-C", "--no-show-raw-insn", elf])
    symbol = re.search(r"^[0-9a-f]+ <("+pattern+r"[^\n]+)>:\n",
                       assembly, re.MULTILINE)
    if not symbol: raise ValueError(f"resident read_input symbol missing: {elf}")
    body = assembly[symbol.end():].split("\n\n",1)[0]
    saved = local = 0
    prologue = []
    for line in body.splitlines():
        instruction = re.match(r"\s*[0-9a-f]+:\s+(\S+)\s+(.*)",line)
        if not instruction: continue
        op, operands = instruction.groups(); op = op.split(".",1)[0]
        if op in ("bl", "blx"): break
        if op == "push" or (op == "stmdb" and operands.startswith("sp!")):
            registers = re.search(r"\{([^}]+)\}",operands)
            if not registers or "-" in registers[1]:
                raise ValueError(f"unsupported register-save prologue: {line}")
            saved += 4*len(registers[1].split(",")); prologue.append(line.strip())
        elif op in ("sub", "subw") and operands.startswith("sp,"):
            amount = re.match(r"sp,\s*(?:sp,\s*)?#(\d+)",operands)
            if not amount: raise ValueError(f"unsupported stack prologue: {line}")
            local += int(amount[1]); prologue.append(line.strip())
        elif op == "vpush" or (op in ("add", "mov", "bic") and operands.startswith("sp,")):
            raise ValueError(f"unsupported stack prologue: {line}")
    if not saved or not local: raise ValueError(f"fixed INPUT frame not found: {elf}")
    return {"own_frame_bytes":saved+local, "saved_registers_bytes":saved,
            "local_bytes":local, "function":symbol[1], "prologue":prologue}


def bundle(directory):
    candidates = [p for p in directory.iterdir() if p.is_dir() and p.name.startswith("mk61s-")]
    if len(candidates) != 1:
        raise ValueError(f"expected one completed firmware bundle in {directory}")
    root = candidates[0]
    apps = {}
    for name in ("BASIC", "FOCAL", "LANGVM", "LANGIN"):
        path = root/"System"/(name+".APP")
        if not path.exists(): continue
        data = path.read_bytes()
        assert struct.unpack_from("<H", data, 12)[0] == 6
        image, memory = struct.unpack_from("<II", data, 28)
        apps[name] = {"image_bytes": image, "memory_bytes": memory, "app_bytes": len(data)}
    elf = next(root.glob("*.elf"))
    flags = (root/"build.flags").read_text().split()
    return {"path": str(root), "flash_bytes": next(root.glob("*.bin")).stat().st_size,
            **elf_info(elf), "flags": flags, "apps": apps}


def feature_flags(flags, exceptions=()):
    prefixes=tuple("-D"+name+"=" for name in exceptions)
    defaults={"-DMK61_SHARED_SCREEN_GRID=0","-DMK61_SCREEN_BUFFER_LOAN=0"}
    return [flag for flag in flags if not flag.startswith(prefixes) and flag not in defaults]


def compare(before, after, programs, generation=7):
    # All feature/math/placement flags except the requested VM placement must
    # match. A different board or a stripped baseline is not a saving.
    exceptions=("MK61_OVERLAY_LANGUAGE_VM",)
    if generation>=7: exceptions+=("MK61_SHARED_SCREEN_GRID","MK61_SCREEN_BUFFER_LOAN")
    assert feature_flags(before["flags"],exceptions)==feature_flags(after["flags"],exceptions)
    static = after["static_ram_bytes"] - before["static_ram_bytes"]
    flash = after["flash_bytes"] - before["flash_bytes"]
    hot = after["apps"]["LANGVM"]["memory_bytes"]
    cold = after["apps"]["LANGIN"]["memory_bytes"]
    run_savings = {n: before["apps"][n]["memory_bytes"] - hot - static
                   for n in ("BASIC", "FOCAL")}
    phases = []
    screen_room = 0
    if generation>=7 and "-DMK61_SCREEN_BUFFER_LOAN=1" in after["flags"]:
        screen_room=1344 if "-DMK61_ENABLE_USB_SCREEN=1" in after["flags"] else 192
    for program in programs:
        name = "BASIC" if program["language"] == "basic" else "FOCAL"
        size = program["bytecode_bytes"]
        # Include worst APP alignment and 8-byte lower-arena rounding.
        staging = size if generation >= 5 else VALUES_BYTES+size
        screen_staged = bool(screen_room and size<=screen_room)
        if screen_staged: staging=0
        compile_arena = after["apps"][name]["memory_bytes"] + ((staging+7)&~7) + 31
        retained = size if size > IMAGE_ROOM else 0
        phases.append({"origin": program["origin"], "language": program["language"],
                       "compile_arena_upper_bound": compile_arena,
                       "staging": "screen" if screen_staged else "overlay",
                       "compile_free_before_live_heap": after["dynamic_bytes"] - compile_arena,
                       "retained_bytecode_overlay": retained,
                       "run_ram_savings": run_savings[name] - retained})
    return {"baseline": before, "overlay_vm": after,
            "resident_flash_delta": flash, "resident_static_ram_delta": static,
            "loaded_hot_app_bytes": hot, "loaded_input_app_bytes": cold,
            "screen_staging_capacity":screen_room,
            "run_ram_savings_if_image_fits_workspace": run_savings,
            "input_phase_arena_bytes": {"editing": cold, "evaluation": hot},
            "native_total_delta": flash + sum(x["image_bytes"] for x in after["apps"].values())
                                  - sum(x["image_bytes"] for x in before["apps"].values()),
            "external_app_file_delta": sum(x["app_bytes"] for x in after["apps"].values())
                                      - sum(x["app_bytes"] for x in before["apps"].values()),
            "size_pass_arena_upper_bound": {n: after["apps"][n]["memory_bytes"] + (0 if generation >= 5 else VALUES_BYTES) + 31
                                            for n in ("BASIC", "FOCAL")},
            "corpus_compile_max": {n: max(x["compile_arena_upper_bound"] for x in phases
                                          if x["language"] == n) for n in ("basic", "focal")},
            "program_phases": phases}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output-dir", type=Path, default=ROOT/"tmp/language-vm-screen")
    p.add_argument("--previous-dir", type=Path, default=ROOT/"tmp/language-vm-input-stack")
    p.add_argument("--generation", type=int, choices=(3,4,5,6,7), default=7)
    p.add_argument("--arm-objdump", type=Path,
                   help="optionally measure read_input's own fixed frame from shipping ELF")
    args = p.parse_args(); root = args.output_dir.resolve()
    probe = root/"probe"
    compiler = shutil.which("clang++") or shutil.which("c++")
    if not compiler: raise RuntimeError("host C++ compiler required")
    run([compiler, "-std=c++17", "-O2", "-Wall", "-Wextra", "-Werror",
         "-I"+str(ROOT/"code"), ROOT/"tools/language_vm_probe.cpp",
         ROOT/"code/language_bytecode.cpp", ROOT/"code/language_vm.cpp",
         ROOT/"code/zx0_encode.cpp", "-o", probe])
    programs_dir = root/"corpus"; programs_dir.mkdir(exist_ok=True)
    programs = []
    for language, path, origin in corpus(programs_dir):
        output = path.with_suffix(".bvm")
        measured = json.loads(run([probe, language, path, output]))
        previous = ROOT/"tmp/language-vm/corpus"/output.name
        measured["identical_to_v1"] = (output.read_bytes() == previous.read_bytes()
                                        if previous.exists() else None)
        programs.append({"language": language, "origin": origin, **measured})
    comparisons = {}
    skipped = {}
    for profile in ("classic/core", "f411/classic/local"):
        before, after = root/profile/"baseline", root/profile/"vm"
        # An output directory may exist after a linker failure. It is never
        # a completed/sealed bundle and must not become an invented saving.
        complete=lambda d:d.is_dir() and any(p.is_dir() and p.name.startswith("mk61s-") for p in d.iterdir())
        if complete(before) and complete(after):
            comparisons[profile] = compare(bundle(before), bundle(after), programs, args.generation)
            if args.arm_objdump:
                comparisons[profile]["resident_input_frame"] = resident_input_frame(
                    next(Path(comparisons[profile]["overlay_vm"]["path"]).glob("*.elf")),args.arm_objdump)
                if args.generation>=7:
                    comparisons[profile]["resident_dispatcher_frame"] = resident_input_frame(
                        next(Path(comparisons[profile]["overlay_vm"]["path"]).glob("*.elf")),args.arm_objdump,
                        pattern=r"language_vm::invoke_resident")
            if args.generation >= 4:
                previous = args.previous_dir/profile/"vm"
                if args.generation>=7 and complete(root/profile/"reference-vm"):
                    previous=root/profile/"reference-vm"
                if complete(previous):
                    old = bundle(previous)
                    new = comparisons[profile]["overlay_vm"]
                    if args.generation>=7:
                        assert feature_flags(old["flags"],exceptions=("MK61_SHARED_SCREEN_GRID","MK61_SCREEN_BUFFER_LOAN"))==feature_flags(new["flags"],exceptions=("MK61_SHARED_SCREEN_GRID","MK61_SCREEN_BUFFER_LOAN"))
                    delta_name = f"v{args.generation-1}_delta"
                    comparisons[profile][delta_name] = {
                        "resident_flash_bytes":new["flash_bytes"]-old["flash_bytes"],
                        "resident_static_ram_bytes":new["static_ram_bytes"]-old["static_ram_bytes"],
                        "hot_app_ram_bytes":new["apps"]["LANGVM"]["memory_bytes"]-old["apps"]["LANGVM"]["memory_bytes"],
                        "cold_app_ram_bytes":new["apps"]["LANGIN"]["memory_bytes"]-old["apps"]["LANGIN"]["memory_bytes"],
                        "external_app_file_bytes":sum(x["app_bytes"] for x in new["apps"].values())-sum(x["app_bytes"] for x in old["apps"].values())}
                    if args.arm_objdump:
                        old_frame = resident_input_frame(next(Path(old["path"]).glob("*.elf")),args.arm_objdump)
                        comparisons[profile]["previous_resident_input_frame"] = old_frame
                        comparisons[profile][delta_name]["resident_input_own_frame_bytes"] = (
                            comparisons[profile]["resident_input_frame"]["own_frame_bytes"]-old_frame["own_frame_bytes"])
                        if args.generation>=7:
                            old_dispatcher=resident_input_frame(next(Path(old["path"]).glob("*.elf")),args.arm_objdump,
                                                              pattern=r"language_vm::invoke_resident")
                            comparisons[profile]["previous_resident_dispatcher_frame"]=old_dispatcher
                            comparisons[profile][delta_name]["resident_dispatcher_own_frame_bytes"]=(
                                comparisons[profile]["resident_dispatcher_frame"]["own_frame_bytes"]-old_dispatcher["own_frame_bytes"])
                    if args.generation >= 5:
                        old_report = args.previous_dir/"report.json"
                        if old_report.exists():
                            old_comparison=json.loads(old_report.read_text())["comparisons"][profile]
                            comparisons[profile][delta_name]["corpus_compile_arena_delta"]={
                                n:comparisons[profile]["corpus_compile_max"][n]-old_comparison["corpus_compile_max"][n]
                                for n in ("basic","focal")}
                    if args.generation>=7:
                        old_phases=compare(before=bundle(before),after=old,programs=programs,generation=6)
                        comparisons[profile][delta_name]["corpus_compile_arena_delta"]={
                            n:comparisons[profile]["corpus_compile_max"][n]-old_phases["corpus_compile_max"][n]
                            for n in ("basic","focal")}
                        comparisons[profile]["screen_reference_vm"]=old
        elif args.generation>=7:
            skipped[profile]="No complete matched/sealed bundle; do not infer size savings from a failed link or an absent build."
    arm = {path.stem:json.loads(path.read_text()) for path in root.glob("arm-v*-*.json")}
    result = {"status": "experimental default-off; no persistent cache; no hardware flashing",
              "generation":args.generation,
              "transient_values_backup_bytes":0 if args.generation >= 5 else VALUES_BYTES,
              "input_image_c_stack_bytes":0 if args.generation >= 6 else 256 if args.generation >= 4 else 768,
              "input_image_in_value_stack":args.generation >= 6,
              "values_bytes": VALUES_BYTES, "continuation_bytes": STATE_BYTES,
              "workspace_image_capacity": IMAGE_ROOM, "comparisons": comparisons,
              "skipped_profiles":skipped,
              "programs": programs, "arm_stack_calls":arm,
              "notes": ["Savings include loaded APP and resident static RAM, not C-stack/live-heap high-water.",
                        "INPUT unloads the VM; expression evaluation unloads INPUT, so their APP sizes are not summed.",
                        "v4 uses a 256-byte INPUT image and borrows the main stack tail. Native-call stack traces exclude resident dispatcher/loader and live heap.",
                        "Images larger than the workspace capacity retain an image-sized OVERLAY; subtract it from the RUN savings.",
                        "Exact-size two-phase emission keeps unsaved source in compiler WORKSPACE and does not reopen the editor.",
                        "v5 protects a 3504-byte values tail, forbids snapshots during the foreground partition, and stages only bytecode.",
                        "v6 stores INPUT bytecode in the upper 32 VM stack slots, bounds expression values to the lower 64, and preserves all 96 for program RUN.",
                        "v7 screen staging is conditional on a foreground loan; USB-off only loans the 192-byte page with redraw deferred.",
                        "Current resident uses independently fenced dynamic staging beside an active USB session; these corpus budgets model inactive USB, not the session's simultaneous RAM peak.",
                        "Never compare USB-on screen savings against USB-off firmware: the latter has no spare 1536-byte framebuffer or duplicate grid.",
                        "Inode/cache metadata, device input latency and hardware integration remain separate qualification gates."]}
    if args.generation == 4:
        for profile in ("core", "local"):
            old, new = arm.get("arm-v3-"+profile), arm.get("arm-v4-"+profile)
            if old and new:
                old_peak = old["native_call_stack_peaks"].get("expression",0)
                new_peak = new["native_call_stack_peaks"].get("expression",0)
                result.setdefault("expression_native_stack_delta",{})[profile] = new_peak-old_peak
    (root/"report.json").write_text(json.dumps(result, ensure_ascii=False, indent=2)+"\n")
    print(json.dumps({profile: {k: v[k] for k in (
        "resident_flash_delta", "resident_static_ram_delta", "loaded_hot_app_bytes",
        "run_ram_savings_if_image_fits_workspace", "external_app_file_delta", "corpus_compile_max")}
        for profile, v in comparisons.items()}, indent=2))


if __name__ == "__main__": main()

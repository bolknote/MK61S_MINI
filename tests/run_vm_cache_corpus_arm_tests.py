#!/usr/bin/env python3
"""Compile/verify the measured corpus in real ARM APPs directly into cache RAM.

Storage, loader and cache allocation remain fixtures. Stack numbers include
APP/native services, not native flow dispatcher frames or a live heap peak.
"""
import argparse
import json
import struct
import tempfile
from pathlib import Path

from run_language_vm_arm_tests import package
from run_language_vm_overlay_arm_tests import OverlayMachine
from run_portable_system_arm_tests import Elf, ROOT, run


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--resident-elf", type=Path, required=True)
    parser.add_argument("--system", type=Path, required=True)
    parser.add_argument("--corpus-report", type=Path, required=True)
    parser.add_argument("--report-file", type=Path, required=True)
    args = parser.parse_args()
    corpus = json.loads(args.corpus_report.read_text())
    elf = Elf(args.resident_elf)
    cache = elf.symbol("image_cache")
    # ImageCache stores its aligned byte arena first. Its metadata is not used
    # by this APP ABI test; generation/pin policy has a separate native test.
    payload = corpus["cache"]["payload_bytes"]
    results = []
    with tempfile.TemporaryDirectory(prefix="mk61-cache-corpus-arm-") as directory:
        work = Path(directory)
        reader = work/"reader"
        run(["c++", "-std=c++17", "-O2", "-I"+str(ROOT/"code"),
             ROOT/"tests/portable_app_format_self_test.cpp",
             ROOT/"code/loadable_module_format.cpp", ROOT/"code/zx0.cpp", "-o", reader])
        packages = {kind: package(reader, args.system/name, elf, work, kind) for kind, name in
                    (("tinybasic", "BASIC.APP"), ("focal", "FOCAL.APP"),
                     ("language-input", "LANGIN.APP"))}
        for entry in corpus["programs"]:
            m = OverlayMachine(args.resident_elf, True, 0)
            # Larger real programs need more CPU-hook time than the small
            # ABI probes. This only changes the test watchdog, not firmware.
            m.call_timeout_us=60_000_000
            m.call_instruction_limit=30_000_000
            language = 1 if entry["language"]=="basic" else 2
            source = (args.corpus_report.parent/entry["source_file"]).read_bytes()
            m.files[42] = (3 if language==1 else 2, "RAMCORPUS", source)
            m.partitioned = True
            request, execution, overlay, certificate = [m.input+x for x in (512,640,720,768)]
            variables = m.input+128
            m.load(packages["tinybasic" if language==1 else "focal"])
            m.stage = "sizing"
            m.uc.mem_write(request, bytes(40))
            m.put(request,40,7,0,9728)
            m.uc.mem_write(request+32,b"\x01")
            m.call(0x20A if language==1 else 0x106,42,1 if language==1 else 0,request)
            wire = bytes(m.uc.mem_read(request,40))
            assert wire[16]==0 and wire[30]==1, (entry["origin"],wire.hex(),m.lines)
            length = struct.unpack_from("<H",wire,18)[0]
            assert length==entry["owned"]["bytecode_bytes"] and length+16<=payload
            reads = sum(t[0]=="file_read" for t in m.trace)
            assert reads==1, (entry["origin"], reads)
            m.uc.mem_write(cache,b"\xA5"*(length+16))
            m.put(request+8,cache+8,length)
            m.stage = "emission"
            try:
                assert m.call(0x704,0,0,request)==1
            except AssertionError as error:
                raise AssertionError((entry["origin"],"EMIT",m.stage_peaks,m.trace[-8:])) from error
            assert sum(t[0]=="file_read" for t in m.trace)==reads
            assert bytes(m.uc.mem_read(cache,8))==b"\xA5"*8
            assert bytes(m.uc.mem_read(cache+8+length,8))==b"\xA5"*8
            image = bytes(m.uc.mem_read(cache+8,length))
            assert not image[7]&4 or image[7]&8
            m.load(packages["language-input"])
            m.stage = "verification"
            m.uc.mem_write(m.workspace,bytes(1520))
            m.uc.mem_write(m.workspace+1506,bytes((language,)))
            m.uc.mem_write(execution,bytes(48))
            m.put(execution,48,7,cache+8,length,variables,m.workspace+5112,385 if language==1 else 0)
            m.uc.mem_write(overlay,bytes(24))
            m.put(overlay,24,7,execution,m.workspace,certificate)
            assert m.call(0x705,overlay)==1 and m.uc.mem_read(execution+36,1)[0]==0
            assert bytes(m.uc.mem_read(cache+8,length))==image
            assert sum(t[0]=="file_read" for t in m.trace)==reads
            results.append({"origin":entry["origin"], "image_bytes":length,
                            "source_reads":reads,"source_bytes":len(source),
                            "source_reads_during_emit_or_verify":0,"stack_peaks":m.stage_peaks})
            if len(results)%10==0:
                print(f"ARM corpus: {len(results)}/{len(corpus['programs'])}",flush=True)
    peaks = {}
    for result in results:
        for stage, size in result["stack_peaks"].items():
            peaks[stage] = max(peaks.get(stage,0),size)
    report = {"status":"PASS", "program_count":len(results), "programs":results,
              "stack_peaks":peaks,
              "note":"Real compiler/cold verifier directly targeting cache SRAM; native allocation and storage are fixtures, no device peak/timing claim."}
    args.report_file.parent.mkdir(parents=True,exist_ok=True)
    args.report_file.write_text(json.dumps(report,indent=2)+"\n")
    print(json.dumps({k:report[k] for k in ("status","program_count","stack_peaks","note")},indent=2))


if __name__=="__main__":
    main()

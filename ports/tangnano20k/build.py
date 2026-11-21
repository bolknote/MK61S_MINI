#!/usr/bin/env python3
"""Synthesize the Tang Nano 20K accelerator with OSS CAD Suite."""

import argparse
from decimal import Decimal, localcontext
from pathlib import Path
import re
import shutil
import subprocess

HERE = Path(__file__).resolve().parent


def build(tools, output, clock, phase, hardfloat=None, half_sdram_clock=False, prefill_lanes=4, seed=None,
          sdram_divider=None, dsp_clock=None, sdram_from_dsp=False):
    output.mkdir(parents=True, exist_ok=True)

    def run(tool, args, log):
        with (output / log).open("w") as stream:
            completed = subprocess.run([str(tools / tool), *args], cwd=output,
                                       stdout=stream, stderr=subprocess.STDOUT)
        if completed.returncode:
            print("\n".join((output / log).read_text().splitlines()[-35:]))
            completed.check_returncode()

    rtl = [HERE / file for file in ("uart.v", "link.v", "schedule.v", "sdram.v", "q4_dot.v", "tang_top.v")]
    if dsp_clock:
        rtl += [HERE / "dot_cdc.v"]
    if sdram_from_dsp:
        rtl += [HERE / "sdram_cdc.v"]
    flags = ""
    if hardfloat:
        source = hardfloat / "source"
        include = output / "hardfloat-source"
        if not include.is_symlink():
            include.symlink_to(source, target_is_directory=True)
        if include.resolve() != source.resolve():
            raise ValueError("Use a fresh output folder for a different HardFloat checkout")
        flags = '-DTANG_MODEL -Ihardfloat-source -Ihardfloat-source/RISCV'
        rtl += [source / file for file in (
            "HardFloat_primitives.v", "HardFloat_rawFN.v", "RISCV/HardFloat_specialize.v",
            "isSigNaNRecFN.v", "mulRecFN.v")]
        rtl += [HERE / file for file in ("fp_add.v", "fp_divsqrt.v", "fp32.v", "exp32.v", "attention.v", "matrix_scale.v", "model.v")]
        with localcontext() as context:
            context.prec = 90
            table = [round(Decimal(2) ** (Decimal(i) / 64) * (1 << 55)) for i in range(64)]
        (output / "exp2.hex").write_text("".join(f"{word:015x}\n" for word in table))
    shutil.copyfile(HERE / "schedule.hex", output / "schedule.hex")
    sources = " ".join(f'"{part}"' for part in rtl)
    divider = sdram_divider or (2 if half_sdram_clock else 1)
    run("yosys", ["-Q", "-T", "-p", f'read_verilog -sv {flags} {sources}; chparam -set CLOCK_HZ {clock*1000000} '
        f'-set SDR_PHASE "{phase:04b}" -set SDRAM_DIVIDER {divider} '
        f'-set PREFILL_LANES {prefill_lanes} -set DSP_CLOCK_HZ {(dsp_clock or 0)*1000000} '
        f'-set SDRAM_FROM_DSP {int(sdram_from_dsp)} tang_top; '
        'synth_gowin -family gw2a -top tang_top -json tang.json'], "synth.log")
    routing = ["--json", "tang.json", "--write", "tang-routed.json", "--device",
        "GW2AR-LV18QN88C8/I7", "--vopt", "family=GW2A-18C", "--vopt", f"cst={HERE / 'tang.cst'}",
        "--freq", str(clock), "--report", "timing.json"]
    if seed is None and prefill_lanes == 6:
        seed = 3 if (clock == 90 or (clock == 102 and divider == 3) or
                     (clock, divider, dsp_clock) == (102, 2, 162)) else 2
    if seed is not None:
        routing += ["--seed", str(seed)]
    if dsp_clock:
        sdram_constraint = (
            f'ctx.addClock(ctx.cells["separate_dsp.fast_pll"].ports["CLKOUTD3"].net.name, {dsp_clock/3})\n'
            if sdram_from_dsp else ''
        )
        (output / "clocks.py").write_text(
            f'ctx.addClock(ctx.cells["pll"].ports["CLKOUT"].net.name, {clock})\n'
            f'ctx.addClock(ctx.cells["separate_dsp.fast_pll"].ports["CLKOUT"].net.name, {dsp_clock})\n'
            + sdram_constraint
        )
        routing += ["--pre-pack", "clocks.py"]
    run("nextpnr-himbaechel", routing, "route.log")
    run("gowin_pack", ["-d", "GW2A-18C", "-o", "tang.fs", "tang-routed.json"], "pack.log")
    for line in (output / "route.log").read_text().splitlines():
        if re.search(r"Max frequency|MULT9X9:|MULT18X18:|MULT36X36:|BSRAM:|LUT4:", line):
            print(line)
    print(output / "tang.fs")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tools", type=Path, required=True, help="OSS CAD Suite bin directory")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--clock", type=int, choices=(27, 36, 45, 54, 63, 72, 81, 90, 96, 99, 102, 108), default=36)
    parser.add_argument("--phase", type=int, choices=range(16), default=8)
    memory_clock = parser.add_mutually_exclusive_group()
    memory_clock.add_argument("--half-sdram-clock", action="store_true", help="Run SDRAM at half the fabric clock")
    memory_clock.add_argument("--sdram-divider", type=int, choices=(1, 2, 3))
    memory_clock.add_argument("--sdram-from-dsp", action="store_true",
                              help="Run the batched SDRAM controller at one third of the DSP clock")
    parser.add_argument("--prefill-lanes", type=int, choices=(1, 2, 4, 6), default=4)
    parser.add_argument("--seed", type=int, help="Override the placement seed")
    parser.add_argument("--dsp-clock", type=int, choices=(162, 189, 198, 216, 243, 252, 270))
    parser.add_argument("--hardfloat", type=Path, help="Berkeley HardFloat Release 1 root to include the transformer sequencer")
    args = parser.parse_args()
    if args.sdram_from_dsp and not args.dsp_clock:
        parser.error("--sdram-from-dsp requires --dsp-clock")
    build(args.tools.resolve(), args.output.resolve(), args.clock, args.phase,
          args.hardfloat.resolve() if args.hardfloat else None, args.half_sdram_clock, args.prefill_lanes, args.seed,
          args.sdram_divider, args.dsp_clock, args.sdram_from_dsp)


if __name__ == "__main__":
    main()

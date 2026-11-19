"""Build the 125 MHz frame-2438 probe and verify both modes against the game VM."""
import argparse
from hashlib import sha256
from pathlib import Path
import re
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import build_probe
from edge_results import parse

p = build_probe.phase
once = p.once
DEFINES = ("AW_PAGE_WRITE", "AW_PAGE_PAIR")
# Default mode, alternative mode and the one-byte SD marker for each series.
PROFILES = {"base": (0, 7, "7"), "capacity": (11, 13, "F"),
            "lead": (0, 5, "5"), "rows": (8, 16, "R")}
# 67 consecutive frame numbers and full pixel/palette hashes from the independent live VM run.
REFERENCE = "b9b3820a8dc0d62ba327566cead0dfdc3d9b74e03476db91a1cf59d8e1153fc2"


def check_images(log):
    records = [s for s in log.splitlines() if s.startswith("SCK H ")]
    if len(records) != 67 or sha256(("\n".join(records) + "\n").encode()).hexdigest() != REFERENCE:
        raise ValueError("storm pixel hashes differ from the reference")


def prepare(out, profile):
    _, _, marker = PROFILES[profile]
    timed = profile in ("lead", "rows")
    units = build_probe.sources(out)
    meter_dir = out / "writeback"
    meter_dir.mkdir(exist_ok=True)
    shutil.copyfile(HERE / "visible_meter.h", meter_dir / "meter.h")
    main = once((p.SPI / "main.c").read_text(), '#include "writeback/meter.h"',
                '#include "writeback/meter.h"\n#include "edge.h"')
    main = once(main, "    if (ok) wb_store(offset, size);", "    if (ok) { edge_store(offset, size); wb_store(offset, size); }")
    main = once(main, "    wb_boundary(intro);", "    edge.in_interval = intro == 2438;\n    wb_boundary(intro);")
    main = once(main, "    if (ok && intro == 2438) {", "    if (ok) edge_show(intro);\n    if (ok && intro == 2438) {")
    main = once(main, "        wb_print();", "        edge_print();\n        wb_print();")
    # The physical control had two direct pages, prepared PCM and no optional
    # background cache. Keep precisely that layout in this scene-only probe.
    start = main.index("    if (compact_ready) {\n        if (acquire_direct(&background_cache, 6144))")
    end = main.index("    if (compact_ready && 6 * AW_VIDEO_PAGE_BYTES", start)
    main = main[:start] + main[end:]
    start = main.index("    if (audio_prepared) arena_reserved =")
    end = main.index("    if (!startup_active()) goto done;", start)
    main = main[:start] + """    if (!audio_prepared || !acquire_frames(&paired_frames) || !paired_frames) {
            error = "pcm-and-two-pages";
            goto done;
        }
    """ + main[end:]
    begin = main.index('    const unsigned marker = file_size("AWPGCTL.TAG");')
    end = main.index("\n#else", begin)
    main = main[:begin] + """    wb.mode = 6;
        aw_storm_configure_timing(&storm->tail, hz, spi);
        storm->tail.black_before_rows[0] = 32; // Explicit for the existing probe's row-limit readback.
        if (hz != 125000000u || spi != 24000000u) {
            error = "125-MHz-24-MHz-required";
            goto done;
        }
        EDGE_DEFAULT
        const unsigned marker_size = file_size("AW38CFG.TAG");
        if (marker_size) {
            char marker;
            if (marker_size != 1 || !file_read("AW38CFG.TAG", 0, &marker, 1) || marker != 'EDGE_MARKER') {
                error = "bad-2438-mode";
                goto done;
            }
            edge.batches = EDGE_ACTIVE;
        }""" + main[end:]
    initial = "" if profile == "base" else "edge.batches = 11;"
    alternative = {"base": "edge.batches = 7;", "capacity": "edge.batches = 13;",
                   "lead": "color_clock.bias = 5;", "rows": "color_clock.row_cut = 16;"}[profile]
    if timed:
        main = '#define AW_EDGE_LEAD\n' + main
    if profile == "rows":
        main = '#define AW_EDGE_ROWS\n' + main
        initial += "\n    color_clock.bias = 5;\n    color_clock.row_cut = 8;"
        main = once(main, "edge.batches = EDGE_ACTIVE;\n        }",
                    "edge.batches = EDGE_ACTIVE;\n        }\n"
                    "    for (unsigned i = 0; i < 3; ++i)\n"
                    "        storm->tail.black_before_rows[i] -= color_clock.row_cut;")
    main = main.replace("EDGE_DEFAULT", initial)
    main = main.replace("EDGE_MARKER", marker)
    main = main.replace("edge.batches = EDGE_ACTIVE;", alternative)
    (out / "main.c").write_text(main)
    shutil.copyfile(HERE / "edge.h", out / "edge.h")
    storm_path = out / "display_storm.cpp"
    line = "    if (hidden && !defer_latch && (!lcd->wait(ctx, 0) || !lcd->show(ctx, page)))"
    storm_path.write_text('extern "C" bool edge_prewrite(void);\n' + once(storm_path.read_text(), line,
        """    if (hidden && !defer_latch && following == AW_STORM_FRAMES && s->tail.available &&
            !edge_prewrite()) return s->ready = false;
    """ + line))
    if timed:
        storm = ('extern "C" unsigned edge_lead_bias(void);\n'
                 'extern "C" void edge_mark_color(unsigned, unsigned, unsigned);\n' + storm_path.read_text())
        real_lead = "tail.overlap ? overlap_lead_ms[index] : lead_ms(s, frame, lcd.spi_hz)"
        storm = once(storm, real_lead, "(" + real_lead + ") + edge_lead_bias()")
        storm = once(storm, "lcd.wait(ctx, lead) && select_page(p, page, lcd.select, ctx);",
                     "(edge_mark_color(index, 0, lead), lcd.wait(ctx, lead)) &&\n"
                     "        (edge_mark_color(index, 1, lead), select_page(p, page, lcd.select, ctx));\n"
                     "    edge_mark_color(index, 2, lead);")
        storm_path.write_text(storm)
    video_path = out / "video.c"
    video = "void edge_copy_begin(void);\nvoid edge_copy_end(void);\n" + video_path.read_text()
    video = once(video, "    wb_copy_begin();", "    edge_copy_begin();\n    wb_copy_begin();")
    video_path.write_text(once(video, "    wb_copy_end();", "    wb_copy_end();\n    edge_copy_end();"))
    units = [out / "main.c" if unit.name == "main.c" else unit for unit in units]
    return units


def check_intro(out, units, data, profile):
    mock = once(p.host_mock(), "{profile_mode=true;page_mode=1;}",
                "{profile_mode=true;page_mode=1;reject_background=true;}")
    begin = "    if (op == MK61_SERVICE_MICROS)"
    mock = once(mock, begin, """    if (op == MK61_SERVICE_COMPUTE) {
            if (a == MK61_COMPUTE_PROBE) return MK61_COMPUTE_MAGIC;
            if (a == MK61_COMPUTE_HZ) return 125000000u;
            return 1;
        }
    """ + begin)
    close = "        if (a == MK61_AUDIO_CLOSE) { ended = true; return 1; }"
    mock = once(mock, close, "        if (a == MK61_AUDIO_PREPARE) return 1;\n" + close)
    if profile == "rows":
        accepted = "        ++presents; return 1;"
        mock = once(mock, accepted, """        uint32_t crc = UINT32_MAX;
        for (unsigned i = 0; i < f->pixel_bytes; ++i) {
            crc ^= f->pixels[i];
            for (unsigned b = 0; b < 8; ++b) crc = (crc >> 1) ^ ((0u - (crc & 1u)) & 0xEDB88320u);
        }
        printf("EDGE CRC %08X %u %u\\n", (unsigned)~crc, f->width, f->height);
""" + accepted)
    text_src = (p.GAME / "text.c").read_text()
    lookup = "const char *aw_text(uint16_t id) {"
    (out / "text.c").write_text('#include <stdio.h>\n' + once(text_src, lookup,
        lookup + '\n    fprintf(stderr, "TEXT_ID %u\\n", (unsigned)id);'))
    units = [out / "text.c" if unit.name == "text.c" else unit for unit in units]
    trace = p.compile_host(out, units, out / "main.c", mock, defines=DEFINES)
    trace_run = subprocess.run([trace, data, "profile-pages"], capture_output=True, text=True, check=True)
    check_images(trace_run.stdout)
    ids = {int(i) for i in re.findall(r"^TEXT_ID (\d+)$", trace_run.stderr, re.M)}
    assert ids and all(line.startswith("TEXT_ID ") for line in trace_run.stderr.splitlines())
    # Keep the original records and their order for the fixed intro. An unexpected
    # text ID on the board invalidates the run; a different game remains untouched.
    pattern = r"(?m)^    X\(s\d+, (0x[0-9A-F]+), .*?\)(?: \\)?$"
    seen = {int(i, 16) for i in re.findall(pattern, text_src)}
    assert ids <= seen
    def record(match):
        return match.group() if int(match[1], 16) in ids | {0xffff} else ""
    selected = re.sub(pattern, record, text_src)
    start, end = selected.index("#define AW_STRING_LIST"), selected.index("/* Byte-aligned")
    selected = selected[:start] + "\n".join(row for row in selected[start:end].splitlines() if row) + "\n\n" + selected[end:]
    selected = once(selected, lookup, "void edge_unexpected_text(unsigned id);\n" + lookup)
    selected = once(selected, "if (code == 0xFFFF) return 0;",
        "if (code == 0xFFFF) { edge_unexpected_text(id); return 0; }")
    (out / "text.c").write_text(selected)
    print("Intro text IDs retained:", len(ids), "of", len(seen), flush=True)
    (out / "text-ids.txt").write_text("\n".join(f"0x{i:04X}" for i in sorted(ids)) + "\n")
    app = p.compile_host(out, units, out / "main.c", mock, defines=DEFINES)
    with TemporaryDirectory(dir=out) as tmp:
        fixture = Path(tmp)
        for file in data.iterdir():
            if file.is_file() and file.name.casefold() != "aw38cfg.tag":
                (fixture / file.name).symlink_to(file)
        control, alternative, marker = PROFILES[profile]
        for mode in (control, alternative):
            if mode == alternative:
                (fixture / "AW38CFG.TAG").write_bytes(marker.encode("ascii"))
            log = subprocess.check_output([app, fixture, "profile-pages"], text=True)
            (out / f"mode-{mode}.log").write_text(log)
            check_images(log)
            parse(log, mode, host=True, profile=profile)
            print(f"125-MHz profile, mode {mode}: 67 images and both outside latches verified", flush=True)

    return units


def build_arm(out, units, pioasm, toolchain):
    header = out / "wire.pio.h"
    subprocess.run([pioasm, "-v", "0", "-o", "c-sdk", p.SPI / "wire.pio", header], check=True)
    subprocess.run([sys.executable, p.SPI / "test_pio.py", header], check=True)
    cmd = [sys.executable, p.ROOT / "tools/apps/portable/build_portable_app.py", "--target", "picocalc-pico-h",
           "--shared-runtime", "--name", "AWEDGE", "--arm-toolchain-bin", p.compiler_bin(toolchain),
           "--output-dir", out / "arm", "--include", p.GAME, "--include", p.SPI, "--include", out]
    for name in DEFINES:
        cmd.extend(["--define", name])
    for unit in (p.ROOT / "code/zx0.cpp", p.ROOT / "sdk/portable/rp2040_divide.S", *units):
        cmd.extend(["--source", unit])
    subprocess.run(cmd, check=True)


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--output-dir", required=True, type=Path)
    cli.add_argument("--check-data", required=True, type=Path, help="directory with DOS game data and AWSTORM.BIN")
    modes = cli.add_mutually_exclusive_group()
    modes.add_argument("--capacity", action="store_true", help="compare 11 and 13 writes (default: 0 and 7)")
    modes.add_argument("--lead", action="store_true", help="compare the timer lead at 11 writes")
    modes.add_argument("--rows", action="store_true", help="defer 8 or 16 hidden black rows with a 5 ms lead")
    cli.add_argument("--pioasm", default="pioasm")
    cli.add_argument("--toolchain", type=Path)
    args = cli.parse_args()
    out = args.output_dir.resolve()
    out.mkdir(exist_ok=True, parents=True)
    profile = next((name for name in ("capacity", "lead", "rows") if getattr(args, name)), "base")
    units = prepare(out, profile)
    units = check_intro(out, units, args.check_data.resolve(), profile)
    build_arm(out, units, args.pioasm, args.toolchain)


if __name__ == "__main__":
    main()

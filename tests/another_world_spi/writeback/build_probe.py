"""Measure page writeback on storm frames 2439 and 2440 against the live game VM."""
import argparse
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "phases"))
import build as phase
from decode import parse


def sources(out):
    video = (phase.GAME / "video.c").read_text()
    signature = "bool aw_video_copy(aw_video *v, uint8_t src, uint8_t dst, int16_t scroll)"
    video = phase.once(video, signature + " {", "static " + signature.replace("aw_video_copy", "measured_copy") + " {")
    video += """
void wb_copy_begin(void);
void wb_copy_end(void);
bool aw_video_copy(aw_video *v, uint8_t src, uint8_t dst, int16_t scroll) {
    wb_copy_begin();
    bool ok = measured_copy(v, src, dst, scroll);
    wb_copy_end();
    return ok;
}

"""
    (out / "video.c").write_text(video)
    storm = (phase.GAME / "display_storm.cpp").read_text()
    storm = 'extern "C" void wb_visible_done(unsigned);\n' + storm
    storm = phase.once(storm, "ok = lcd.select(ctx, page) && lcd.wait(ctx, 0);", """ok = lcd.select(ctx, page);
            if (ok) {
                wb_visible_done(index);
                ok = lcd.wait(ctx, 0);
            }""")
    (out / "display_storm.cpp").write_text(storm)
    replacements = {"video.c": out / "video.c", "display_storm.cpp": out / "display_storm.cpp",
                    "main.c": phase.SPI / "main.c"}
    return [replacements.get(name, phase.GAME / name) for name in phase.SOURCES]


def check_host(out, units, data, defines):
    mock = phase.once(phase.host_mock(), "{profile_mode=true;page_mode=1;}",
                      "{profile_mode=true;page_mode=1;reject_background=true;}")
    close = "        if (a == MK61_AUDIO_CLOSE) { ended = true; return 1; }"
    mock = phase.once(mock, close, "        if (a == MK61_AUDIO_PREPARE) return 1;\n" + close)
    pair = "AW_PAGE_PAIR" in defines
    if pair:
        begin = "    if (op == MK61_SERVICE_MICROS)"
        mock = phase.once(mock, begin, """    if (op == MK61_SERVICE_COMPUTE) {
        if (a == MK61_COMPUTE_PROBE) return MK61_COMPUTE_MAGIC;
        if (a == MK61_COMPUTE_HZ) return 125000000u;
        return 1;
    }
""" + begin)
    app = phase.compile_host(out, units, phase.SPI / "main.c", mock, defines=defines)
    hashes = []
    with TemporaryDirectory(dir=out) as folder:
        fixture = Path(folder)
        for file in data.iterdir():
            if file.is_file() and file.name.casefold() != "awpgctl.tag":
                (fixture / file.name).symlink_to(file)
        modes = (("spread", None), ("same", b"2439A"), ("base", b"2440"),
                 ("rounded", b"2439R1"), ("full", b"2439ALL"), ("advance", b"2439ADV8"),
                 ("defer", b"2439LATE8")) if pair else (
            ("early", None), ("control", b"2440"))
        for mode, marker in modes:
            if marker is not None:
                (fixture / "AWPGCTL.TAG").write_bytes(marker)
            log = subprocess.check_output([app, fixture, "profile-pages"], text=True)
            (out / ("host-" + mode + ".txt")).write_text(log)
            result = parse(log, mode, host=True)
            hashes.append([r for r in log.splitlines() if r.startswith("SCK H ")])
            print(mode, result.get("previous", {}).get("early_bytes"), result["page"]["early_bytes"], flush=True)
    if any(series != hashes[0] for series in hashes[1:]):
        raise ValueError("VM fingerprints differ")
    print("67 VM fingerprints and pixel-by-pixel LCD readbacks matched in every mode.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--pioasm", default="pioasm")
    parser.add_argument("--toolchain", type=Path)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--large-windows", action="store_true", help="write only while sending at least 5000 pixels")
    modes.add_argument("--pair", action="store_true", help="keep partial writeback on 2440 and compare policies on 2439")
    parser.add_argument("--check-data", type=Path)
    args = parser.parse_args()
    out = args.output_dir.resolve()
    out.mkdir(parents=True, exist_ok=True)
    units = sources(out)
    header = out / "wire.pio.h"
    subprocess.run([args.pioasm, "-v", "0", "-o", "c-sdk", phase.SPI / "wire.pio", header], check=True)
    subprocess.run([sys.executable, phase.SPI / "test_pio.py", header], check=True)
    defines = ["AW_PAGE_WRITE"]
    if args.large_windows:
        defines.append("AW_WRITE_LARGE_WINDOWS_ONLY")
    if args.pair:
        defines.append("AW_PAGE_PAIR")
    cmd = [sys.executable, phase.ROOT / "tools/apps/portable/build_portable_app.py", "--target", "picocalc-pico-h",
           "--shared-runtime", "--name", "AWPAGE", "--arm-toolchain-bin", phase.compiler_bin(args.toolchain),
           "--output-dir", out / "arm", "--include", phase.GAME, "--include", phase.SPI, "--include", out]
    for name in defines:
        cmd.extend(["--define", name])
    for unit in (phase.ROOT / "code/zx0.cpp", phase.ROOT / "sdk/portable/rp2040_divide.S", *units):
        cmd.extend(["--source", unit])
    subprocess.run(cmd, check=True)
    if args.check_data:
        check_host(out, units, args.check_data.resolve(), defines)


if __name__ == "__main__":
    main()

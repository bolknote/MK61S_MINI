"""Replay the retail APP entry point and check the storm scheduler against the game VM."""
import argparse
import os
from pathlib import Path
import shutil
import subprocess
from tempfile import TemporaryDirectory

from build_edge import check_images, once, p


def check(out, data):
    # The desktop model supplies only hardware services. Observe the actual
    # retail presentation and write callbacks and stop after frame 2453.
    src = '#include <stdio.h>\n#include <assert.h>\n' + (p.GAME / "main.c").read_text()
    marker = "static bool store_write(void *ctx, uint32_t offset, const void *in, uint32_t size) {"
    src = once(src, marker, "static unsigned observed_frame, early_calls, early_bytes;\n"
               "static bool early_active;\n" + marker + "\n    if (early_active) early_bytes += size;")
    marker = "static bool wait_for_storm_125(void *ctx, unsigned lead_ms) {"
    src = once(src, marker, """static bool observed_write(aw_video *v, unsigned batches) {
    assert(observed_frame == 2438 && batches == 11 && v->resident_valid && v->resident_page == 2);
    assert(storm->tail.black_before_rows[0] == 24 && storm->tail.black_before_rows[1] == 48 &&
           storm->tail.black_before_rows[2] == 80);
    ++early_calls;
    early_active = true;
    const bool ok = aw_video_write_displayed(v, batches);
    early_active = false;
    return ok;
}
""" + marker)
    src = once(src, "!aw_video_write_displayed(video, 11)", "!observed_write(video, 11)")
    marker = "static bool wait_for_frame_lead(void *ctx, unsigned lead_ms) {"
    src = once(src, marker, marker + """
    if (storm->tail.active && lead_ms) printf("COLOR WAIT %u %u\\n", observed_frame, lead_ms);
""")
    marker = "        if (shown) return !input.quit && !pump_failed;"
    src = once(src, marker, """        if (intro && shown) {
            if (observed_frame >= 2387) {
                extern void aw_host_check_pixels(const uint8_t *, const uint16_t *, unsigned);
                aw_host_check_pixels(pixels, palette, observed_frame);
                printf("SCK H %u %08X\\n", observed_frame, aw_storm_frame_hash(pixels, palette));
            }
            if (++observed_frame == 2454) {
                assert(early_calls == 1 && early_bytes == 28160);
                input.quit = true;
            }
        }
""" + marker)
    (out / "main.c").write_text(src)
    mock = once(p.host_mock(), "    if (op == MK61_SERVICE_CAPABILITIES)", """
    if (op == MK61_SERVICE_COMPUTE) {
        if (a == MK61_COMPUTE_PROBE) return MK61_COMPUTE_MAGIC;
        if (a == MK61_COMPUTE_HZ) return 125000000u;
        return 1;
    }
    if (op == MK61_SERVICE_CAPABILITIES)""")
    mock = once(mock, "if (a == MK61_AUDIO_CLOSE) { ended = true; return 1; }",
                "if (a == MK61_AUDIO_PREPARE) return 1;\n        if (a == MK61_AUDIO_CLOSE) { ended = true; return 1; }")
    mock = once(mock, 'checked_frames == 67 && strstr(debug_output, "SCK END 0 0")', 'checked_frames == 67')
    mock = once(mock, "{profile_mode=true;page_mode=1;}",
                '{profile_mode=true;page_mode=1;reject_background=getenv("AW_EDGE_NO_BACKGROUND")!=NULL;}')
    shutil.copyfile(p.GAME / "display_storm.cpp", out / "display_storm.cpp")
    units = [p.GAME / name for name in p.SOURCES]
    app = p.compile_host(out, units, out / "main.c", mock, defines=())
    env = dict(os.environ)
    env.pop("AW_EDGE_NO_BACKGROUND", None)
    for background in ("available", "unavailable"):
        if background == "unavailable":
            env["AW_EDGE_NO_BACKGROUND"] = "1"
        result = subprocess.check_output([app, data, "profile-pages"], text=True, env=env)
        check_images(result)
        waits = [line for line in result.splitlines() if line.startswith("COLOR WAIT ")]
        if waits != ["COLOR WAIT 2439 30", "COLOR WAIT 2440 34", "COLOR WAIT 2441 29"]:
            raise ValueError(f"unexpected color frame clocks: {waits}")
        print(f"Retail APP with background {background}: 67 images, 28160 early bytes and three color deadlines.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("data", type=Path)
    parser.add_argument("--cache", type=Path, help="use a freshly generated AWSTORM.BIN")
    args = parser.parse_args()
    with TemporaryDirectory() as tmp:
        out, data = Path(tmp), args.data.resolve()
        if args.cache:
            fixture = out / "game"
            fixture.mkdir()
            for entry in data.iterdir():
                if entry.is_file() and entry.name.casefold() != "awstorm.bin":
                    (fixture / entry.name).symlink_to(entry)
            (fixture / "AWSTORM.BIN").symlink_to(args.cache.resolve())
            data = fixture
        check(out, data)

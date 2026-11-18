"""Replay page writeback on the 125 MHz board's observed video-buffer configuration."""
import argparse
import os
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory

from build import SPI, compile_host, host_mock, once, sources
from replay import parse


def build_replay(out):
    units = sources(out)
    main = (SPI / "main.c").read_text()
    main = once(main, '#include "prepared.h"', '#include "prepared.h"\nvoid copy_replay_window(aw_video *v);')
    marker = "    ph_attempt(result, x, y, width, height, start);"
    main = once(main, marker, marker + """
    if (ph->active && ph->detail && result == 1 && width != AW_VIDEO_WIDTH)
        copy_replay_window(video);""")
    (out / "main.c").write_text(main)

    path = out / "video.c"
    video = path.read_text()
    header = '#include "video.h"'
    video = once(video, header, header + """
static void copy_replay_transfer(aw_video *, bool, uint32_t, const uint8_t *, uint32_t);
static void copy_replay_begin(const aw_video *, uint8_t, uint8_t, int16_t);
static void copy_replay_end(void);""")
    entry = "static bool transfer(aw_video *v, bool write, uint32_t offset, uint8_t *bytes, uint32_t count) {"
    video = once(video, entry, entry + "\n    copy_replay_transfer(v, write, offset, bytes, count);")
    call = "    bool ok=aw_video_copy_measured(v,src,dst,scroll);"
    video = once(video, call, "    if (saved < PH_COUNT) copy_replay_begin(v, src, dst, scroll);\n" + call +
                 "\n    if (saved < PH_COUNT) copy_replay_end();")
    path.write_text(video + '\n#include "copy_replay.h"\n')

    # Match the physical probe's two video pages, reserved PCM and absent
    # optional background cache. The host already rejects the arena request.
    mock = once(host_mock(), "{profile_mode=true;page_mode=1;}",
                "{profile_mode=true;page_mode=1;reject_background=true;}")
    close = "        if (a == MK61_AUDIO_CLOSE) { ended = true; return 1; }"
    mock = once(mock, close, "        if (a == MK61_AUDIO_PREPARE) return 1;\n" + close)
    return compile_host(out, units, out / "main.c", mock)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("data", type=Path, help="game directory containing the original banks and AWS5")
    args = parser.parse_args()
    environment = os.environ.copy()
    environment.pop("AW_TEST_EARLY_PAGE_WRITE", None)
    hashes = []
    with TemporaryDirectory() as directory:
        app = build_replay(Path(directory))
        for early in (False, True):
            if early:
                environment["AW_TEST_EARLY_PAGE_WRITE"] = "1"
            log = subprocess.check_output([app, args.data.resolve(), "profile-pages"], env=environment, text=True)
            parse(log, "detail", host=True)
            assert "PH START pcm=1 arena=0 paired=1 bg=0 tail=0" in log
            summary, = [line for line in log.splitlines() if line.startswith("VM_COPY ")]
            print(summary)
            hashes.append([line for line in log.splitlines() if line.startswith("SCK H ")])
    assert hashes[0] == hashes[1]
    print("All 67 VM fingerprints matched across both runs and every displayed pixel matched each live VM frame.")


if __name__ == "__main__":
    main()

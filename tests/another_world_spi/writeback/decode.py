"""Decode and validate the page-writeback A/B probe's serial output."""
from pathlib import Path
import re
import sys


def rows(log, name):
    prefix = "WB " + name + " "
    return [line[len(prefix):].split() for line in log.splitlines() if line.startswith(prefix)]


def check(ok, label):
    if not ok:
        raise ValueError(label)


def parse(log, mode, host=False):
    check("SCK FIRST 2350 4FC268F0" in log and "SCK END 0 0" in log and "SCK FAIL" not in log, "scene or PCM")
    pair = rows(log, "PAIR")
    pair_modes = {"base": (0, 0, 0, 0), "same": (1, 5000, 0, 3), "spread": (2, 2000, 0, 8),
                  "rounded": (3, 1500, 1000, 11), "full": (4, 1000, 1400, 13),
                  "advance": (5, 1000, 1400, 13), "defer": (6, 1000, 1400, 13)}
    check(mode in (pair_modes if pair else ("early", "control")), "unknown mode")
    (settings,) = rows(log, "MODE")
    early, cpu, spi, overlap, pcm, paired, bg, tail = map(int, settings)
    expected_mode = pair_modes[mode][0] if pair else int(mode == "early")
    check(early == expected_mode and spi == 24000000 and overlap == 0 and pcm == paired == 1, "clock or buffers")
    if host:
        check([int(x) for x in re.findall(r"^SCK H (\d+) [0-9A-F]{8}$", log, re.M)] == list(range(2387, 2454)),
              "67-frame readback")
    else:
        check(cpu == 125000000 and "APP_FLOW_RESULT=0" in log, "CPU or app exit")
        (cal,) = rows(log, "CAL")
        microseconds, edges, selected = map(int, cal)
        check(edges == 82008 and 0 < selected * 2 / 125 < microseconds, "calibration")
    (counts,) = rows(log, "PAGE")
    names = ("displayed", "copies", "early_writes", "early_bytes", "copy_writes", "copy_bytes",
             "other_bytes", "early_us", "copy_us", "windows", "accepted")
    page = dict(zip(names, map(int, counts), strict=True))
    check(page["displayed"] == 2 and page["copies"] == 1 and page["windows"] == 7, "VM or visible windows")
    threshold = rows(log, "MIN_PIXELS")
    check(threshold in ([], [["5000"]]), "unknown writeback policy")
    early_bytes = 17920 if pair else (17920 if threshold else 32000) if early else 0
    early_writes = 7 if pair else (7 if threshold else 13) if early else 0
    check(page["early_bytes"] == early_bytes and page["copy_bytes"] == 32000 - early_bytes and
          page["early_writes"] == early_writes and page["other_bytes"] == 0, "page writeback")
    (lcd,) = rows(log, "LCD")
    frames = {int(f): int(us) for f, us in rows(log, "F")}
    check(list(frames) == list(range(2387, 2454)) and min(frames.values()) > 0, "scheduler series")
    wire = {}
    for f, us, edges, ticks in rows(log, "W"):
        f, us, edges, ticks = map(int, (f, us, edges, ticks))
        low = ticks * 2 / 125
        check(host or (0 < edges / 24 <= low + 5 and low <= us + 5 and abs(frames[f] - us) < 15), "wire timing")
        wire[f] = dict(wall_us=us, edges=edges, cs_high_us=round(us - low, 3), selected_us=round(low, 3))
    check(list(wire) == list(range(2438, 2443)), "five wire intervals")
    visible = {int(f): (int(offset), int(dt)) for f, offset, dt in rows(log, "V")}
    check(list(visible) == [2439, 2440, 2441], "visible frame fences")
    for f, (offset, dt) in visible.items():
        check(0 < offset <= frames[f], "visible fence outside scheduler interval")
        if f > 2439:
            check(dt == frames[f - 1] - visible[f - 1][0] + offset, "fence time does not close")
    result = dict(mode=mode, page=page, frames=frames, wire=wire, visible=visible, rgb_bytes=int(lcd[0]),
                  geometry=lcd[1], background_bytes=bg + tail, min_pixels=5000 if threshold or pair else 0)
    if pair:
        _, min_pixels, round_pixels, batches = pair_modes[mode]
        check(pair == [[str(min_pixels), "5000"]] and cpu == 125000000 and bg + tail == 0, "pair settings")
        rounding = rows(log, "ROUND")
        check(rounding == [[str(round_pixels), "0"]] or (not rounding and not round_pixels), "rounding policy")
        saved = min(32000, batches * 2560)
        (counts,) = rows(log, "PREVIOUS")
        previous = dict(zip(names, map(int, counts), strict=True))
        check(previous["displayed"] == 1 and previous["windows"] == 7 and previous["accepted"] == 8 and
              previous["copies"] == 1 and previous["early_writes"] == batches and previous["other_bytes"] == 0 and
              previous["early_bytes"] == saved and previous["copy_bytes"] == 32000 - saved,
              "page 1 writeback")
        black_rows = rows(log, "BLACK_ROWS")
        limits = {"advance": [40, 64, 96], "defer": [32, 56, 88]}.get(mode, [32, 64, 96])
        if black_rows or mode in ("advance", "defer"):
            check(black_rows == [list(map(str, limits))], "hidden row limits")
        # FNV over all eight accepted windows. The last window is the hidden strip.
        prev_lcd = {"advance": ["61216", "13C64C38"], "defer": ["61216", "1BC658A0"]}.get(mode, ["66336", "1BC65898"])
        geometry = "47781440" if mode == "defer" else "7F786CA8"
        check(rows(log, "PREVLCD") == [prev_lcd] and lcd == ["77920", geometry], "LCD geometry")
        copies = {int(f): (int(start), int(end)) for f, start, end in rows(log, "COPY")}
        for f, details in ((2439, previous), (2440, page)):
            start, end = copies[f]
            check(visible[f][0] <= start <= end <= frames[f] and end - start == details["copy_us"], "copy interval")
        (latch,) = rows(log, "LATCH")
        count, at = map(int, latch)
        check(count == 1 and 0 < at <= frames[2438], "previous frame latch")
        black = rows(log, "BLACK")
        if black:
            (black_latch,) = black
            black_count, black_at = map(int, black_latch)
            check(black_count == 1 and 0 < black_at <= frames[2442], "black latch")
        sight = {}
        for f, us, edges, ticks in rows(log, "VW"):
            f, us, edges, ticks = map(int, (f, us, edges, ticks))
            if f == 2439:
                expected = frames[2438] - at + visible[2439][0]
            elif f == 2442 and black:
                expected = frames[2441] - visible[2441][0] + black_at
            else:
                expected = visible[f][1]
            check(us == expected and (host or 0 < edges / 24 <= ticks * 2 / 125 + 5 <= us + 10), "visible wire time")
            sight[f] = dict(us=us, edges=edges, cs_high_us=round(us - ticks * 2 / 125, 3))
        check(list(sight) == list(range(2439, 2443 if black else 2442)), "visible wire series")
        result.update(previous=previous, copies=copies, visible_wire=sight, previous_min_pixels=min_pixels)
    return result


if __name__ == "__main__":
    for name in sys.argv[1:]:
        path = Path(name)
        result = parse(path.read_text(), path.stem.split("-")[-1])
        print(path.name, result["frames"][2440], result["page"], result["visible"])

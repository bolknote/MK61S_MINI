"""Verify the four probe transcripts and export the measured frame intervals."""

import argparse
import csv
import math
from pathlib import Path

ARCHIVE = Path(__file__).resolve().parents[2] / "doc/measurements/picocalc-another-world-spi-20261118"


def records(text, tag):
    prefix = tag + " "
    return [line[len(prefix):].split() for line in text.splitlines() if line.startswith(prefix)]


def require(condition, detail):
    if not condition:
        raise ValueError(detail)


def check_run(text):
    require(records(text, "SCK FIRST") == [["2350", "4FC268F0"]], "wrong first frame")
    require(records(text, "SCK END") == [["0", "0"]] and "APP_FLOW_RESULT=0" in text, "incomplete run or PCM gap")


def check_scope(text, run):
    check_run(text)
    (clock,) = records(text, "SCK CLOCK")
    sys_hz, spi_hz, overlap = map(int, clock)
    require((sys_hz, spi_hz, overlap) == (125_000_000, 24_000_000, 0), "unexpected clock profile")
    (spi,) = records(text, "SCK SPI")
    cr0, cr1, prescaler, dmacr = (int(v, 16) for v in spi)
    require(cr1 & 2 and dmacr & 3 == 3 and (cr0 & 0xF0) == 0, "unexpected SPI mode or DMA enable")
    require(48_000_000 == spi_hz * prescaler * (1 + ((cr0 >> 8) & 255)), "unexpected SPI divider")
    channels = set()
    for _, ctrl, source, dest in records(text, "SCK DMA"):
        value = int(ctrl, 16)
        if (value >> 2) & 3 == 1:
            channels.add(((value >> 15) & 63, (value >> 4) & 3, int(source, 16), int(dest, 16)))
    dr = 0x40040008
    require(any(d == 18 and inc == 1 and dst == dr for d, inc, _, dst in channels), "missing 16-bit SPI1 TX")
    require(any(d == 19 and inc == 0 and src == dr for d, inc, src, _ in channels), "missing 16-bit SPI1 RX")

    leading = {int(row[0]): row[1:] for row in records(text, "SCK W")}
    trailing = {int(row[0]): row[1:] for row in records(text, "SCK V")}
    calibrated = []
    for row in records(text, "SCK C"):
        index, rate, wall, edges, selected, _, blind = map(int, row)
        require(edges == 5120 * 16 + 88, f"control {index}: wrong number of clocks")
        wire_us = edges * 1e6 / rate
        cs_us = selected * 2e6 / sys_hz
        require(wire_us <= cs_us + 1 <= wall + 3 and blind <= 12, f"control {index}: invalid timing")
        bits, count, *first = leading[index]
        width = int(bits)
        require(width in (1, 4) and count == "8", f"control {index}: incomplete sample")
        mask = (1 << width) - 1
        samples = [(int(w, 16) >> k) & mask for w in first + trailing[index] for k in range(32 - width, -1, -width)]
        require(not any(v & 8 for v in samples), f"control {index}: CS released inside burst")
        rising = [i for i in range(1, len(samples)) if samples[i] & 1 and not samples[i - 1] & 1]
        periods = [b - a for a, b in zip(rising, rising[1:])]
        target = sys_hz / rate
        regular = [n for n in periods if math.floor(target) <= n <= math.ceil(target)]
        require(regular and abs(sys_hz * len(regular) / sum(regular) / rate - 1) < 0.045,
                f"control {index}: sampled SCK disagrees with requested rate")
        calibrated.append((index, rate))
    require(calibrated == list(enumerate([12_000_000] + [spi_hz] * 3)), "missing calibration")

    frames = []
    for row in records(text, "SCK F"):
        frame, wall, edges, selected, gaps, blind, payload, rects = map(int, row)
        cs_us = selected * 2e6 / sys_hz
        wire_us = edges * 1e6 / spi_hz
        require(wall > 0 and wire_us <= cs_us + 4 and cs_us <= wall + 5 and blind <= 15,
                f"frame {frame}: invalid timing")
        frames.append(dict(run=run, frame=frame, wall_us=wall, edges=edges, selected_us=round(cs_us, 3),
                           wire_us=round(wire_us, 3), inselect_idle_us=round(cs_us - wire_us, 3),
                           outside_us=round(wall - cs_us, 3), gaps=gaps, blind_us=blind,
                           submitted_bytes=payload, accepted=rects))
    require([r["frame"] for r in frames] == list(range(2387, 2454)), "incomplete frame range")
    return frames


def check_feed(text):
    check_run(text)
    require(records(text, "FEED CLOCK") == [["125000000", "24000000"]], "unexpected DMA probe clock")
    frames = []
    for row in records(text, "FEED F"):
        frame, wall, samples, selected, running, hits, stops, aligned, nulls, minimum, _, _ = map(int, row)
        require(samples >= selected >= running >= hits >= stops >= 0, f"frame {frame}: bad sample counters")
        require(0 <= aligned <= stops and 0 <= nulls <= stops and 0 <= minimum < wall,
                f"frame {frame}: invalid stop observations")
        frames.append(frame)
        if frame == 2440:
            print(f"2440: {stops} DMA stops sampled, {aligned} at strip boundaries, {nulls} null sources, "
                  f"at least {minimum} us")
    require(frames == list(range(2438, 2443)), "incomplete DMA probe")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", nargs="?", type=Path, default=ARCHIVE)
    parser.add_argument("--csv", type=Path, help="write the decoded PIO frames")
    args = parser.parse_args()
    frames = []
    for i in (1, 2):
        frames.extend(check_scope((args.directory / f"scope-{i}.txt").read_text(), i))
        check_feed((args.directory / f"feed-{i}.txt").read_text())
    if args.csv:
        with args.csv.open("w", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=list(frames[0]), lineterminator="\n")
            writer.writeheader()
            writer.writerows(frames)
    print(f"Verified {len(frames)} PIO intervals and both DMA traces")


if __name__ == "__main__":
    main()

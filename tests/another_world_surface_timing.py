"""Check the pool-exit frame cadence in a 125 MHz PicoCalc diagnostic trace."""

import argparse
import re
from pathlib import Path


def delta_us(end, start):
    return ((end - start + 2**31) % 2**32) - 2**31


def check_surface_timing(trace):
    rows = {}
    for frame, target, end, digest, wire, hz in re.findall(
        r"^AWQ f=(\d+) t=(\d+) r=\d+ e=(\d+) h=([0-9A-F]{8}) w=(\d+) hz=(\d+) show=0\b", trace, re.M
    ):
        frame = int(frame)
        if int(hz) != 125_000_000 or frame in rows:
            raise ValueError(f"unexpected clock or duplicate record at frame {frame}")
        rows[frame] = (int(target), int(end), digest, int(wire))
    if not all(n in rows for n in range(4, 69)):
        raise ValueError("missing frame records in the pool-exit trace")
    for n, expected in ((63, "4C7C0D52"), (64, "F627725B"), (65, "FC840C77")):
        if rows[n][2] != expected:
            raise ValueError(f"pixel or palette mismatch at frame {n}")
    if rows[5][3] != rows[4][3] or rows[64][3] - rows[63][3] != 128_000:
        raise ValueError("unexpected LCD transfer at pool entry or exit")
    intervals = []
    for n in range(6, 69):
        target, end = rows[n][:2]
        prev_target, prev_end = rows[n - 1][:2]
        period = delta_us(end, prev_end)
        if delta_us(target, prev_target) != 80_000 or abs(period - 80_000) > 2_000 or abs(delta_us(end, target)) > 2_000:
            raise ValueError(f"frame {n}: period {period} us, deadline error {delta_us(end, target)} us")
        intervals.append(period)
    strips = [(int(n), int(us)) for n, us in re.findall(r"^AWSTRIP f=(\d+) us=(\d+)\b", trace, re.M)]
    if len({n for n, _ in strips}) != 10 or len(strips) != 10 or any(n >= 64 or not 0 < us <= 18_000 for n, us in strips):
        raise ValueError("the ten 20-row strips must finish within their idle windows before frame 64")
    audio = re.findall(r"^AWQ END mode=1 count=69 audio=(\d+),(\d+)\b", trace, re.M)
    if len(audio) != 1 or audio[0][0] != audio[0][1]:
        raise ValueError("incomplete run or audio underrun")
    return intervals


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("trace", type=Path)
    args = parser.parse_args()
    try:
        intervals = check_surface_timing(args.trace.read_text())
    except ValueError as exc:
        parser.exit(1, f"{args.trace}: {exc}\n")
    print(f"63/63 intervals in {min(intervals)}..{max(intervals)} us; frame 64: {intervals[64 - 6]} us")

"""Validate frame-2438 probe records and emit CSV from saved board logs."""
import argparse
import csv
from pathlib import Path
import re
import sys
from zlib import crc32


BASE_HISTORY = ("2CCDE6E9,A99403A6,7B559160,537BB536,05FB3BDE,01F3134B,01F3134B,6B3CCE6A,"
                "712A5FA9,CF90A213,787BE0D8,53A69C87,226F6A81,C1A7CE55,4BF64D67,9E00937D").split(",")


def expected_history(cut=0):
    if not cut:
        return BASE_HISTORY
    black40 = f"{crc32(bytes(160 * 40)):08X}"
    if cut == 8:
        return BASE_HISTORY[:7] + [black40] + BASE_HISTORY[8:]
    return BASE_HISTORY[1:7] + [black40, f"{crc32(bytes(160 * 8)):08X}"] + BASE_HISTORY[8:]


def parse(raw, mode, host=False, profile="base"):
    batches = 11 if profile in ("lead", "rows") else mode
    cut = mode if profile == "rows" else 0
    lead_bias = mode if profile == "lead" else 5 if profile == "rows" else None
    if ("SCK FIRST 2350 4FC268F0" not in raw or "SCK END 0 0" not in raw or "SCK FAIL" in raw
            or "EDGE unexpected" in raw or "WB MODE 6 125000000 24000000 0 1 1 0 0" not in raw):
        raise ValueError("scene, CPU, SPI, audio or frame buffers")
    if host:
        hashes = re.findall(r"^SCK H (\d+) [0-9A-F]{8}$", raw, re.M)
        if list(map(int, hashes)) != list(range(2387, 2454)):
            raise ValueError("missing host image checks")
    else:
        cal = re.findall(r"^WB CAL (\d+) (\d+) (\d+)\r?$", raw, re.M)
        if len(cal) != 1 or int(cal[0][1]) != 82008 or not 0 < int(cal[0][2]) * 2 / 125 <= int(cal[0][0]) + 5:
            raise ValueError("PIO clock calibration")
        memory = {"lead": 39704, "rows": 39772}.get(profile, 39400)
        if not re.search(rf"^APP_RESULT=0 CRC=[0-9A-F]{{8}} MEMORY={memory}\r?$", raw, re.M) or not re.search(
                r"^APP_FLOW_RESULT=0\r?$", raw, re.M):
            raise ValueError("APP did not finish")

    def metrics(key, count):
        found = re.findall(r"^EDGE " + key + r" ((?:-?\d+ ?)+)\r?$", raw, re.M)
        if len(found) != 1:
            raise ValueError("missing or duplicate " + key)
        values = list(map(int, found[0].split()))
        if len(values) != count:
            raise ValueError("bad arity for " + key)
        return values

    if batches not in (0, 7, 11, 13) or cut not in (0, 8, 16):
        raise ValueError("unknown early-write or hidden-row schedule")
    actual, calls, copies, early, late = metrics("BYTES", 5)
    expected = [batches, 1, 1, min(batches * 2560, 32000), max(32000 - batches * 2560, 0)]
    if [actual, calls, copies, early, late] != expected:
        raise ValueError("unexpected page 2 writes")
    leading, trailing, first, last = metrics("OUTER", 4)
    if (leading, trailing) != (1, 1) or not all(0 < t < 2000000 for t in (first, last)):
        raise ValueError("outside latches")
    if metrics("MID", 7) != [1, 1, 1, 1, 1, 32000, 17920]:
        raise ValueError("middle latches or overlapping page writes")
    wire = [[int(x) for x in row] for row in re.findall(r"^WB VW (\d+) (\d+) (\d+) (\d+)\r?$", raw, re.M)]
    if [w[0] for w in wire] != list(range(2439, 2443)):
        raise ValueError("four middle periods")
    if not host and any(not (0 < edges / 24 <= active * 2 / 125 + 5 <= wall + 10)
                        for _, wall, edges, active in wire):
        raise ValueError("clock edges or CS duration")
    periods = [first, *(w[1] for w in wire), last]
    slack0, slack1, early_us, copy_us = metrics("TIME", 4)
    waits = []
    if lead_bias is not None:
        if lead_bias not in (0, 5) or metrics("BIAS", 1) != [lead_bias]:
            raise ValueError("wrong color schedule")
        waits = [[int(n) for n in row] for row in re.findall(
            r"^EDGE W (\d+) (\d+) (-?\d+) (\d+) (\d+)\r?$", raw, re.M)]
        if ([w[0] for w in waits] != list(range(2439, 2442))
                or [w[1] - lead_bias for w in waits] != [25, 29, 24] or any(max(w[3:]) > 70000 for w in waits)):
            raise ValueError("color timer or LCD selection")
    if cut:
        if metrics("CUT", 1) != [cut]:
            raise ValueError("wrong hidden row schedule")
        if host and re.findall(r"^EDGE CRC ([0-9A-F]{8}) \d+ \d+$", raw, re.M)[-16:] != expected_history(cut):
            raise ValueError("host LCD rectangle history")
    if not host:
        history = re.search(r"^LCD_COLOR_CRCS=([A-F0-9,]+)$", raw, re.M)
        if not history or history[1].split(",") != expected_history(cut):
            raise ValueError("board LCD rectangle history")
    return dict(batches=batches, early_bytes=early, eviction_bytes=late, periods_us=periods, waits=waits,
                slack_before_ms=slack0, slack_after_ms=slack1, early_us=early_us, eviction_us=copy_us,
                cs_high_us=wire[0][1] - wire[0][3] * 2 / 125,
                target_hits=[38000 <= t <= 42000 for t in periods],
                sequence_us=metrics("SEQUENCE", 1)[0])


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("directory", type=Path, help="contains one subdirectory with six board logs per series")
    args = cli.parse_args()
    rows = []
    for series, order in (("base", (0, 7, 7, 0, 0, 7)), ("capacity", (11, 13, 13, 11, 11, 13)),
                          ("lead", (0, 5, 5, 0, 0, 5)), ("rows", (8, 16, 16, 8, 8, 16))):
        for run, mode in enumerate(order, 1):
            path = args.directory / series / f"{run}-{mode}.txt"
            bias = mode if series == "lead" else 5 if series == "rows" else 0
            data = parse(path.read_text(), mode, profile=series)
            periods = data["periods_us"]
            waits = [value for row in data["waits"] for value in row[1:]]
            rows.append([series, run, data["batches"], bias, mode if series == "rows" else 0,
                         data["early_bytes"], data["eviction_bytes"],
                         data["early_us"], data["eviction_us"], data["slack_before_ms"],
                         data["slack_after_ms"], *periods, sum(data["target_hits"]),
                         round(data["cs_high_us"], 1), data["sequence_us"], *(waits or [""] * 12)])
    writer = csv.writer(sys.stdout, lineterminator="\n")
    writer.writerow(["series", "run", "batches", "extra_color_lead_ms", "hidden_rows_deferred",
                     "early_bytes", "eviction_bytes", "early_us",
                     "eviction_copy_us", "slack_before_ms", "slack_after_ms",
                     *(f"f{n}_to_{n+1}_us" for n in range(2437, 2443)), "within_38_42_ms",
                     "cs_high_to_2439_us", "clip_67_frames_us",
                     *(f"f{n}_{key}" for n in range(2439, 2442)
                       for key in ("lead_ms", "time_to_deadline_ms", "timer_wait_us", "page_select_us"))])
    writer.writerows(rows)


if __name__ == "__main__":
    main()

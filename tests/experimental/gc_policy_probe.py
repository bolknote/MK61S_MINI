#!/usr/bin/env python3
"""Deterministic packed-log placement experiment, not a C9 flash driver.

Compare 32-sector window selection with live-byte summaries, two append heads,
and two prepared erased sectors. Record bytes include payload/name/header/F9CH;
catalog/WAL, staging, block chains and flash timing are deliberately excluded.
`foreground_erases` is an erase-latency proxy, not a latency measurement.
"""

import csv
import random
import sys
from dataclasses import dataclass, field


@dataclass
class Sector:
    used: int = 16
    records: list = field(default_factory=list)
    erased: bool = True
    erases: int = 0


class PackedLog:
    def __init__(self, sectors, policy, pool):
        self.sectors = [Sector() for _ in range(sectors)]
        self.policy, self.pool_limit = policy, pool
        self.heads = [0, 1] if policy == "hot-cold" else [0]
        self.reserve = sectors - 1
        self.pool = []
        self.current = {}
        self.cursor = len(self.heads)
        self.program = self.copied = self.scanned = self.foreground = 0
        self.gc_count = 0
        for head in self.heads:
            self.initialize(head)

    def initialize(self, i):
        sector = self.sectors[i]
        if not sector.erased:
            sector.erases += 1
            self.foreground += 1
        sector.used = 16
        sector.records.clear()
        sector.erased = False
        self.program += 16

    def live(self, i):
        return [(key, generation, length) for key, generation, length
                in self.sectors[i].records
                if self.current.get(key) == (i, generation, length)]

    def exclude(self):
        return set(self.heads + [self.reserve] + self.pool)

    def reclaim(self, need):
        count = len(self.sectors)
        allowed = [i for offset in range(count)
                   if (i := (self.cursor + offset) % count) not in self.exclude()]
        # A dead sector is returned before copying live data, matching C9.
        for position, i in enumerate(allowed):
            if self.policy in ("window", "hot-cold") and position % 32 == 0:
                self.scanned += len(self.current)
            if not self.live(i):
                self.initialize(i)
                self.cursor = (i + 1) % count
                return i
        if self.policy in ("window", "hot-cold"):
            victim = None
            for offset in range(0, count, 32):
                indices = [(self.cursor + k) % count
                           for k in range(offset, min(offset + 32, count))]
                self.scanned += len(self.current)
                candidates = [(sum(r[2] for r in self.live(i)), i)
                              for i in indices if i not in self.exclude()]
                candidates = [item for item in candidates if item[0] + need <= 4080]
                if candidates:
                    victim = min(candidates)[1]
                    break
        else:
            # Hypothetical RAM summaries avoid repeated inode scans.
            candidates = [(sum(r[2] for r in self.live(i)), i) for i in allowed]
            candidates = [item for item in candidates if item[0] + need <= 4080]
            victim = min(candidates)[1] if candidates else None
        if victim is None:
            raise RuntimeError("no COW/GC progress space")
        dest = self.reserve
        self.initialize(dest)
        for key, generation, length in self.live(victim):
            self.sectors[dest].records.append((key, generation, length))
            self.sectors[dest].used += length
            self.current[key] = (dest, generation, length)
            self.copied += length
            self.program += length
        old = self.sectors[victim]
        old.erases += 1
        self.foreground += 1
        old.used, old.records, old.erased = 16, [], True
        self.reserve = victim
        self.cursor = (victim + 1) % count
        self.gc_count += 1
        return dest

    def prepare_pool(self):
        # Preparation only erases dead sectors; never copies live records.
        for offset in range(len(self.sectors)):
            if len(self.pool) >= self.pool_limit:
                break
            i = (self.cursor + offset) % len(self.sectors)
            if i in self.exclude() or self.live(i):
                continue
            before = self.foreground
            self.initialize(i)
            self.foreground = before
            self.pool.append(i)

    def put(self, key, payload, cold=False):
        length = (16 + 8 + payload + 18 + 1) & ~1
        assert 0 < length <= 4080
        lane = int(cold and len(self.heads) == 2)
        i = self.heads[lane]
        if self.sectors[i].used + length > 4096:
            i = self.pool.pop(0) if self.pool else self.reclaim(length)
            self.heads[lane] = i
        generation = self.current.get(key, (0, 0, 0))[1] + 1
        self.sectors[i].records.append((key, generation, length))
        self.sectors[i].used += length
        self.current[key] = (i, generation, length)
        self.program += length
        self.prepare_pool()

    def validate(self):
        for key, (i, generation, length) in self.current.items():
            assert (key, generation, length) in self.sectors[i].records
            assert not self.sectors[i].erased
        assert self.sectors[self.reserve].erased
        assert not (set(self.heads) & set(self.pool))
        assert all(s.used <= 4096 for s in self.sectors)


def run(sectors, workload, policy, pool):
    log = PackedLog(sectors, policy, pool)
    rng = random.Random(0xC9F12)
    # Scale live bytes to ~60%; sector tails increase occupied sectors.
    hot_count = 64 if sectors < 100 else 2048
    cold_count = int((sectors * 4080 * .60 - hot_count * 138) / 1498)
    for i in range(max(1, cold_count)):
        log.put(("cold", i), 1456, True)
    for i in range(hot_count):
        log.put(("hot", i), 96)
    for step in range(5000):
        if workload == "mixed" and step % 16 == 0:
            log.put(("cold", rng.randrange(max(1, cold_count))), 1456, True)
        else:
            key = rng.randrange(hot_count)
            log.put(("hot", key), rng.choice((64, 96, 160)))
        if step % 127 == 0:
            log.validate()
    log.validate()
    erases = [s.erases for s in log.sectors]
    summary_bytes = sectors * 2 if policy == "summary-greedy" else 0
    return [sectors, workload, policy, pool, len(log.current), log.program,
            log.copied, sum(erases), max(erases), sum(e != 0 for e in erases),
            log.foreground, log.scanned, summary_bytes]


def main():
    writer = csv.writer(sys.stdout, lineterminator="\n")
    writer.writerow(["data_sectors", "workload", "policy", "pool", "objects",
                     "program_bytes", "copied_bytes", "erases", "peak_erases",
                     "touched_sectors", "foreground_erases", "scan_references",
                     "summary_ram_bytes"])
    for sectors in (79, 3870):
        for workload in ("hot", "mixed"):
            for policy, pool in (("window", 0), ("summary-greedy", 0),
                                 ("hot-cold", 0), ("window", 2)):
                writer.writerow(run(sectors, workload, policy, pool))


if __name__ == "__main__":
    main()

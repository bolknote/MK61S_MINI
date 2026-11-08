# PicoCalc AI performance at270 MHz

Two RP2040 cores, INT8 activations, Q4 model MKA-AA8246E1-2093896,
8192 tokens, DMA prefetch, frozen display during compute. Each candidate
pass uses2 prefill and2 decode tokens. The archived control is1.114016 s/token;
no control was rerun. Candidate passes measured1.0719955 and1.0720915 s/token
(3.77% and3.76% less time). Tokens and all-row checksums match the archive.

Text rendering sends only8-pixel strips intersecting changed text rows,
reuses glyph/color layout across scanlines, and avoids quadratic glyph
measurement while writing a bounded line. Compute-time input/service polling
runs at an8 ms cadence; loading and normal UI polling remain immediate.
Detailed presentation and nested service counters distinguish LCD traffic
from arithmetic. The diagnostic has a candidate-only archived-reference mode.
The optional M3 backend is not enabled in these measurements.

The controller lost the final USB prompt. The completed on-device report was
retrieved after confirming stock125 MHz and no active runtime. Its load time
5132064 us matches this run's captured AI_LOAD marker, establishing freshness.
The receipt records recovery and final closed CDC/MSC/lease state. Firmware
19222E8E/6806A4A1 was written with verification and remains installed.

Validation: full PicoCalc HOST tests with the real model and ASan/UBSan;
exact colored-pixel checks, unchanged-line zero traffic, neighboring-row
preservation, palette splitting, archived references, Esc and pause/resume;
ARMv6-M firmware build and two physical candidate passes at270 MHz.
These are short-context decode measurements, not a long-context throughput claim.

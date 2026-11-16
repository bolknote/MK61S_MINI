# RP2040 exp coefficient placement A/B, 2026-11-16

The Pico H ran at 125 MHz. A was the installed `4D133820 / 78AA379D` image.
B was `9E5007FE / E45F1DAC`, built from `657157905be22ab43047386375b9dcc6794ed7a1`
with a one-line linker change. A's firmware source was identical to that
revision. B moved the table from `0x10191280` to `0x101927C0`.

The 11,760 coefficient bytes were identical. Comparing the sealed binaries
outside the two table ranges found a single table pointer update at
`0x1017720C` and the build ID and integrity CRC words. The APP and all
benchmark inputs were identical. The ARM instruction counts matched in all
27 groups. An additional B run checked 100,196 `exp` results against MPFR
without a mismatch. The address was selected from an offline model of the
XIP accesses. The actual timing and cache counters came from the Pico H.
[RP2040 datasheet](https://datasheets.raspberrypi.com/rp2040/rp2040-datasheet.pdf)

| Broad `exp` group | A, µs/call | B, µs/call | B change | A misses/call | B misses/call |
| --- | ---: | ---: | ---: | ---: | ---: |
| 512 inputs in [−8, 8] | 5.932 | 5.892 | −0.67% | 0.809 | 0.834 |
| 512 inputs in [−700, 700] | 5.888 | 5.940 | +0.88% | 0.745 | 0.736 |

Each image ran the same 27 groups in sequence. Each group used twelve timed
batches with alternating order against the factory v3 ROM, giving six
paired estimates after calibration. Both wide groups had overlapping A/B
ranges. The absolute median differences across the 13 previously slow
`exp` cases were at most 0.017 µs. All 5,020 returned values matched MPFR, and
both images beat ROM in all six estimates of every group. The project keeps
the A placement. Full data are in the [27-group CSV](m0-exp-layout-20261116.csv).

The first window stopped before CDC opened because the host's `lsof` call
stalled on an SMB volume. The renewed window used exact device-node process
lookups through Darwin and completed in 276 seconds. B was programmed once
and verified against a full Flash readback. Both temporary benchmark
directories were removed. The final state was CALCULATOR / CLOSED / NONE with
`BOOTS=1` and `CRASH=NONE`. CDC and its lock were released with B installed.
The sealed manifest and raw receipts are in `.build/m0-exp-layout-20261116/`.

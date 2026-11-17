# RP2040 pow fallback on physical PicoCalc, 2026-11-17

The production Pico H image `181E9BEA` (CRC `453B35A3`, 1,805,072 bytes)
was built from clean main commit `9521e757f955ee1844d55610e7d478ee8b648e93`.
Its source SHA-256 is
`d9acd05e83f878b3e2412315110e728c1d6aa7fcadf874f8951e817626a450dc`.
The BIN SHA-256 is
`0677362408dbc93b8d317c23b74884e386bf44125f41a8c82b484dd15de120ca`.
The device ran at 125 MHz throughout the measurement.

The temporary POWWDT APP called the linked production functions for
the 512-bit, 1,024-bit, exact integer and 4,096-bit stages, even when an
earlier stage had already decided. The last two stages received the
adjacent pair selected before the test. Each case was compared bit for
bit with directed MPFR 4.2.2. The largest subnormal base paired with
`y = -((2^53-1)/2^116)` drives the 4,096-bit stage through 169 full-width
products and 52 multiplications by a four-word factor. The positive
exponent variant omits the final full-width multiplication.

| Input or workload | 512-bit, µs | 1,024-bit, µs | Exact, µs | 4,096-bit, µs | Forced chain, µs | Watchdog gap, µs |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Exact tie, 3^34 | 494 | 515 | 436 | 49,956 | 51,401 | 51,412 |
| Maximum products, negative exponent | 91,925 | 581,758 | 30 | 1,619,942 | 2,293,655 | 2,293,703 |
| Published near-midpoint pair | 42,444 | 273,706 | 19 | 1,566,847 | 1,883,016 | 1,883,024 |
| Longer fixed-point exponential work | 157,561 | 976,312 | 8,656 | 67,661 | 1,210,190 | 1,210,196 |
| Maximum products, positive exponent | 89,493 | 581,565 | 22 | 1,608,467 | 2,279,547 | 2,279,550 |
| Maximum products, negative exponent, repeat 1 | 89,486 | 581,521 | 23 | 1,619,930 | 2,290,960 | 2,290,964 |
| Maximum products, negative exponent, repeat 2 | 89,476 | 581,524 | 25 | 1,619,919 | 2,290,944 | 2,290,946 |

All seven cases matched MPFR. The stage timings use the RP2040 timer
counter. The gap uses the microsecond timestamps recorded by production
`feed_watchdog()` immediately before its hardware reloads. The reload
counter did not advance inside any timed chain and advanced once
after each chain. The longest observed gap left 5,706,297 µs of the
configured 8,000,000 µs timeout. The native watchdog reported a maximum
of 2,293 ms after truncation to milliseconds and no watchdog reset.
These are observed maxima for this cohort, which includes the maximum
multiplication count. The numerical certificate covers when the directed
intervals are sufficient to round. The final `trap` still covers an
undecided interval. [Rounding certificate](m0-pow-power-bounds-20261117.md)

The predecessor and installed image each matched a complete physical Flash
readback. The single Flash write ended below the settings region. The test
left `181E9BEA` installed, with native `CALCULATOR/CLOSED/NONE`, `BOOTS=1`
since the planned Flash reboot, `CRASH=NONE`, no settings writes, preserved
calculator data, temporary files removed and CDC closed.

## Reproduce the APP and check the saved report

The [fixture](../../tests/fixtures/m0_pow_watchdog_benchmark.c) takes its
function and data addresses from the verified production ELF. The
generated APP SHA-256 is
`9003b99dcb4c4456f3559fb28a7db4902e2d473305608506436a7aa2d32d3b75`.
The raw report SHA-256 is
`7696ceae4f78bca15a464c763a4aa8399994602d0f73ee7069cdc50368ff18fc`.
Use the matching ELF/BIN/UF2 package, Pico SDK 2.2.0, ARM GCC 14.2.1
and host MPFR. The commands below run entirely on the host.
[Raw report](m0-pow-watchdog-20261117.bin)

```sh
python3 tests/m0_pow_watchdog_benchmark.py prepare \
  --production "$firmware_dir" --output "$new_benchmark_dir"
python3 tests/m0_pow_watchdog_benchmark.py verify \
  --benchmark "$new_benchmark_dir/benchmark.json" \
  --result doc/measurements/m0-pow-watchdog-20261117.bin
```

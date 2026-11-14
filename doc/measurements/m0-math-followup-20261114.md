# RP2040 math follow-up: exp, cos and the exact pow fallback

The paired Pico H images use platform commit `61eb4b84b`, Pico SDK 2.2.0
(`a1438dff1d38bd9c65dbd693f0e5db4b9ae91779`) and ARM GCC 14.2.1. Control
`1A45D32D` has the previous math. The first candidate `7E99254E` used
35,280 bytes of `exp` coefficients; `EC8493C6` compressed them to 5,880
bytes. The current candidate `04503D73` stores 11,760 bytes at `0x10191280`
to keep the working set small while doing less work on each call. All four
images span 1,793,244 bytes of Flash and reserve 120,552 bytes of static RAM.
The table is generated from exact rational Taylor bounds and contains no
benchmark inputs. Twenty generic M0+/Cortex-M4 math objects built in five
modes were byte-identical between the control and the compact candidate.

## Host results

| Workload from the November 6 measurement | Inputs | Control instructions/call | Compact candidate | Current candidate | Factory ROM v3 |
| --- | ---: | ---: | ---: | ---: | ---: |
| Slow `exp` cases, range | 13 | 1,145–1,174 | 565–579 | 521–532 | 589–692 |
| `exp`, broad sampling around ±8 | 512 | 522.09 | 572.64 | 525.15 | 637.55 |
| `exp`, broad sampling around ±700 | 512 | 519.01 | 572.12 | 524.52 | 634.16 |
| `cos`, broad cohort with correct reference results | 96 | 1,141.03 | 1,095.68 | 1,095.68 | 1,345.81 |

These are executed Thumb instructions in Unicorn. Flash waits, cache behavior
and physical elapsed time were measured separately. In a larger 1,606-input ARM
comparison for `sin` and `cos`, the candidate used fewer instructions for
1,346 inputs and tied the control on 260. Both owned versions agreed with
directed MPFR on every input. The separate argument-reduction check compares
the ARM routine against an exact rational enclosure of π/2 over 20,161
calls. On each tested candidate, directed MPFR found zero wrong results in
519,503 public calls: 100,196 `exp`, 106,304 each `cos`/`sin`/`tan`, and
100,395 `pow`.

The `exp` kernel reduces the input to a signed Q69 residual and expands it
around the nearest multiple of `2^-21`. The current table stores the even
terms after the square and the full odd terms starting at the cube. It
reconstructs the slope from those values. Its rational error bound is
below 31 Q69 units before normalization (below 62 after doubling). An interval that
reaches a rounding midpoint goes to the existing Q94 refinement. Results
near the subnormal or overflow limits can use CORE-MATH directly.

The last exact `pow` stage now covers 912 signed exponents in place of 224.
Its domain is nonzero `y = p/q` in lowest terms with `53*|p| + 54*q <= 6912`.
The bound ensures that both exact integer powers fit, including their product
for negative `y`; it also covers the zero/subnormal and max/overflow
midpoints. Directed MPFR agreed with 21,071 hinted host calls over 4,822
pairs, covering all 912 exponents, and 95 direct ARM calls. The maximum stack
use observed in the direct ARM test was 3,700 bytes. The public function still
uses its existing earlier passes. If the 1,024-bit interval and the exact
stage both fail to decide, the final trap remains. The broader exact integer
comparison [prototype](../../research/m0-pow-boundary-20261023/README.md)
has no usable worst-case time bound for the RP2040 watchdog; finite MPFR
tests cannot establish totality for the remaining exponents. The published
[CORE-MATH worst-case search](https://core-math.gitlabpages.inria.fr/worst.html)
also does not cover the full `pow` domain.

One explicit bound illustrates the resource gap. For `x` and a positive
rounding midpoint `m`, put `Λ = p*ln(x) - q*ln(m)`. After the existing
tiny/huge exponent rules, `|p| < 2^63` and `q <= 2^117`. If the two rational
bases are multiplicatively independent, invert either base when necessary
to make both larger than one. When the terms then add, there is no small
cancellation: for a binary64 input or a binary64 midpoint distinct from
one, the nonzero log has magnitude at least `2^-55`. When they
subtract, [Laurent's Corollary 2](https://www.impan.pl/shop/en/publication/transaction/download/product/82485)
applies with `D=1`, `log(A1)=log(A2)=746`, `m=30` in its parameter table
and normalized coefficient sum below `2^118`. It gives
`|Λ| >= exp(-17.9*83^2*746^2)`. Dividing by `q` still gives a log gap
greater than `2^-100000000000`. For dependent bases, write both as integer
powers of one positive rational using the primitive vector of their prime
valuations. Up to inversion the primitive base is `A*2^e` with odd
`A < 2^54` (or it is `2`). If it lies in `(1/2, 2)` and differs from one,
its numerator and denominator differ by at least one and are at most
`2^54`; this bounds the absolute log from below by `2^-54`. Thus a nonzero
log gap in the dependent case is at least `2^-171` after dividing by `q`.
A base equal to one reduces to the other log, or an exact tie.
The independent-base bound is far too weak to certify the available
1,024-bit stage. It does not predict an actual need for that many bits.

## Measuring the factory ROM on PicoCalc

Raspberry Pi's [RP2040 B2 boot ROM](https://github.com/raspberrypi/pico-bootrom-rp2040)
already contains double `exp`, `cos`, and `sin`. `pow` is not an entry in
that ROM table. The pinned Pico H ROM bytes give the correct results for all
1,255 inputs in 27 groups selected from the
[November 6 recording](m0-exp-q70-20261106/README.txt). This is a comparison
cohort, not a claim that raw ROM routines round correctly for all inputs.
The timing APP calls the verified ROM v3 table entries; the production image
is copied byte for byte, with zero bytes of Qfplib placed in Flash. For
compatibility the timing wire and decoder still label the reference field
`qfplib`; the manifest identifies its source as `RP2040_factory_BootROM_v3`.

The local `.build/m0-math-20261114/` evidence contains `rom-paired-baseline`,
`rom-paired-candidate`, `rom-compact` and `rom-balanced`, their manifests,
instruction counts, inputs and ARM APP protocol results. To rebuild a pack
with a qualification Python environment (Unicorn and MPFR):

```sh
python3 dev/tools/certify_m0_exp_center.py --json /tmp/m0-exp-certificate.json
python3 dev/tools/certify_m0_pow_exact_small.py --json /tmp/m0-pow-certificate.json
python3 tests/build_m0_rom_math_compare.py --production "$firmware_dir" \
    --bootrom "$captured_bootrom" \
    --records doc/measurements/m0-exp-q70-20261106/records.jsonl.gz \
    --output "$new_timing_dir"
python3 tests/m0_math_compare_app_self_test.py --benchmark "$new_timing_dir" \
    --bootrom "$captured_bootrom" --output "$host_result_dir" \
    --kinds 1 --cache-counters --bounded-warmup
```

On the physical Pico H at 125 MHz, the control and three candidates ran all
27 groups per image. Both implementations matched MPFR for every input in
each image (10,040 results across 108 groups). Each estimate uses 12 calibrated
batches, balanced by alternating the order of the two implementations.

| Workload | Control, µs/call | First, µs/call | Compact, µs/call | Current, µs/call | Factory ROM v3, µs/call (current session) |
| --- | ---: | ---: | ---: | ---: | ---: |
| 13 former slow `exp` cases | 11.763–12.067 | 5.386–5.469 | 5.912–6.001 | 5.376–5.481 | 6.056–6.880 |
| Broad `cos`, 96 inputs | 13.320 | 12.804 | 12.809 | 12.821 | 12.945 |
| Broad `exp` near ±8, 512 inputs | 5.469 | 7.150 | 6.223 | 6.056 | 6.448 |
| Broad `exp` near ±700, 512 inputs | 5.397 | 6.953 | 6.251 | 6.065 | 6.421 |

All six paired differences for each of the 13 difficult `exp` inputs favored
the first candidate over ROM. For broad `cos` the differences were −0.188 to
−0.096 µs/call. The first candidate was faster than ROM in 25 of 27 groups. The
two broad `exp` groups regressed because XIP misses increased from about
0.25/0.22 to 2.53/2.25 per call, respectively. The compact candidate reduced
this to 0.55/0.48 and was faster than ROM in both broad `exp` groups. It
also remained faster in all 13 former slow `exp` groups and in broad `cos`,
with all six paired differences favoring it on those workloads. It won
23 of 27 groups; four short `exp` groups (`12`–`15`) were 0.234–0.298 µs/call
slower than ROM. The smaller table incurs computation to reconstruct the
coefficients on every call. `04503D73` removed these four losses and was
faster than the factory ROM in all 27 groups, with all six paired differences
below zero in every group. The two broad `exp` groups still take longer than
the control implementation had taken, although each is now faster than ROM.

The repository follow-up after the last physical session also handles
nonzero `|y| < 2^-64` for positive finite `x` in the cold `pow` path.
`|ln(x)| < 745` puts the exact result strictly inside the rounding cell
of one; NaN, infinity, zero and negative bases keep the existing handling.
On the 196-input historical tiny-exponent corpus the change cut mean ARM
instructions from 41,236 to 145, with all results unchanged. The 778 `pow`
inputs in the November 6 timing set returned the same bits and executed
the same number of instructions. This `pow` adjustment was measured in
Unicorn and is newer than the on-device `04503D73` image. The integrated
image `5A1968E1` (platform `97f781acd`) also passed 200,591 `pow`/`exp`
checks and had the same instruction profile in the 27 ROM timing groups.
The physical results above refer to the exact images listed in the table.

See the [current physical results](m0-math-rom-final-20261114.csv), the
[first candidate](m0-math-rom-20261114.csv) and the
[compact candidate](m0-math-rom-compact-20261114.csv), each alongside the
same control. Raw v5 reports and Flash readbacks are in
`.build/m0-math-20261114/pico-window-001/`, `pico-window-002/` and
`pico-window-003/`. The latest handoff left `04503D73` on the board at 125 MHz
with its programmed bytes verified by readback. The operator removed its
temporary SD files and released the CDC lock before each handoff.

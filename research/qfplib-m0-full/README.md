# Compact Qfplib-M0-full fork experiment

This is an independently built, GPL-2.0-only fork of Mark Owen's
Qfplib-M0-full. It is **not linked into the calculator firmware**. Cortex-M4
sources and build options are untouched.

`upstream/` preserves the original source and header from commit
`ec814ad1f17934ac777f9e042efacfae5b15210d` of the
[Qfplib mirror](https://github.com/mysterywolf/Qfplib-M0-full).
`src/` contains the modified assembly. Source hashes and changes are recorded
in `UPSTREAM.json`; the build verifies both source hashes.

## First changes

Only `qfp_dln` changes its numerical implementation:

* Signed zero returns negative infinity; negative nonzero values return a quiet
  NaN; positive infinity is preserved and input NaNs are quieted.
* Positive subnormals are normalized exactly into the original logarithm kernel.
* The 32nd greedy iteration is omitted. Its rounded increment and logarithm table
  entry are both exactly `2^30` in Q62, so their contributions cancel in `y+x-1`.
* A small integer polynomial replaces the inaccurate cancellation near one.
  For `x = 1 + N*2^-53`, with `-65535 <= N <= 65534` and even positive `N`, it
  computes `t-t*t/2`, with the strictly positive higher-order remainder in
  the magnitude represented by a sticky bit. The final pack is binary64 RNE.

`prove_ln.py` bounds every possible initial Q62 mantissa through the greedy
iterations using exact integers, proves the remainder bound with rationals,
and checks the integer construction for every encoding in the small kernel.
`tests/qfplib_m0_fork_self_test.py` independently executes the ARM assembly and
compares all **98,303** near-one inputs against directed MPFR bounds.

## Measured result

These are executed ARM instruction counts under Unicorn, **not physical RP2040
times or cycle counts**. Production flash/cache effects still require hardware.

| Input to `ln` | Original | Fork |
| --- | ---: | ---: |
| `1` | 683 | 11 |
| `1 + 2^-52` | 745 | 99 |
| `2` | 711 | 699 |
| `100` | 775 | 757 |

The full library's code and constants occupy **5,948 bytes**, versus the
original **5,780 bytes**: **+168 bytes**, with **no additional lookup table**.
Both use zero static RAM; maximum observed stack use over this suite is 68
bytes. This is an observed bound, not a separate static stack proof.

All 98,303 near-one results are correctly rounded; the original differs from
RNE on 98,301 of these inputs. On 5,153 positive subnormal logarithms, incorrect
results decrease from 5,153 to 18; the remaining differences are one ULP.
Other tested normal outputs outside the new kernel are unchanged.

Detailed hashes, cases, failures and instruction samples are in
[`doc/measurements/qfplib-m0-fork-20261020.json`](../../doc/measurements/qfplib-m0-fork-20261020.json).

## Reproduce

From the repository root, using Python with `unicorn` and a host MPFR library:

```sh
python3 research/qfplib-m0-full/build.py \
  --toolchain /absolute/path/to/arm-none-eabi/bin \
  --output-dir .build/qfplib-m0-fork
python3 research/qfplib-m0-full/prove_ln.py \
  --json .build/qfplib-m0-fork/proof.json
python3 tests/qfplib_m0_fork_self_test.py \
  --build .build/qfplib-m0-fork \
  --json .build/qfplib-m0-fork/result.json
```

The standalone ELF contains the Qfplib assembly only, without libgcc or project
math. The test harness checks saved registers, stack restoration and bounded
stack writes on every call. A `PASS_RESEARCH_GATES` result applies to this
experiment's explicit checks; it does not certify the whole library.

## Remaining work and integration

Scientific functions outside the exact small `ln` kernel still fail universal
correct rounding; their relative error can grow near zeros. Other entry points
still retain upstream NaN flushing, subnormal flushing and range restrictions.
`asin`, `acos`, `log10`, `pow` and `fma` have no native Qfplib entry points.
Thus this fork is not a complete replacement for the current math runtime.

The copyright notices grant GPL version 2 only, without an "or later" option.
The project's root `LICENSE` is GPLv3. Distributed combined firmware needs a
compatible licensing arrangement; the
[GNU compatibility explanation](https://www.gnu.org/licenses/gpl-faq.en.html#v2v3Compatibility)
describes the distinction. Upstream's README offers alternative licensing
enquiries. This experiment preserves the notices and carries its own
`LICENSE.GPL-2.0`; it does not change the project's license.

## Interval-certified ln experiment (2026-10-21)

The optional `--near-ln` build adds the separate entry `qfp_dln_checked`.
The default fork and its 5,948-byte executable are unchanged. The new entry
keeps Qfplib's greedy reduction, unrolls 18 steps, and compensates their rounded
shifts in Q82. For `|x-1| <= 2^-11`, a relative integer polynomial instead
calculates a normalized logarithm with error below one unit at its variable
precision. An interval check accepts only unambiguous RNE results; other cases
invoke Q117 and then Q245 integer refinements.

The full optional library occupies **11,996 bytes**, including **1,272 bytes**
of added constant tables (472 for the fast calculation, 800 shared by both
refinements). It uses no libgcc, floating point arithmetic in the added C,
static writable storage, or heap. Maximum observed stack use is **532 bytes**.

The current V9 ARM executable passes **57,698** MPFR-directed RNE cases,
52,637 direct Q82 interval checks, and 23,581 relative-seed interval checks.
Both integer seeds must match independent exact integer models. Other checks
cover 11,026 synthetic packing intervals, 10,049 wide integer products, saved
registers, stack restoration, and both refinements. A separate run passes all
**134,944** entries of the saved CORE-MATH logarithm hard-case file; four
entries actually invoke Q245. These finite corpora do not prove universal
termination of the final refinement.

Full-call ARM instruction means, including any refinements:

| Corpus | Original | V9 checked |
| --- | ---: | ---: |
| Normal inputs across exponents | 799.25 | 629.48 |
| Ordinary inputs in `[0.5, 2]` | 777.63 | 611.85 |
| Original tiny near-one kernel | 713.67 | 101.33 |
| Wider near-one inputs | 743.61 | 606.28 |
| Decimal powers | 800.10 | 624.65 |
| Random near-one inputs | 760.72 | 648.14 |

**V9 physical timing passes all six groups.** On the RP2040 B2 at 125 MHz,
both libraries execute from the same isolated flash reference. Accepted
0.8.12/BE246AF2 resident code and RAM initializers retain their original layout.
The harness uses identical vectors, nine alternating paired batches, typed
calibration and at least one second of warmup; interrupts remain enabled.

| Corpus | Original, microseconds | V9 checked, microseconds |
| --- | ---: | ---: |
| Normal inputs across exponents | 7.343 | 6.534 |
| Ordinary inputs in `[0.5, 2]` | 7.162 | 6.331 |
| Original tiny near-one kernel | 6.555 | 1.216 |
| Wider near-one inputs | 6.847 | 6.369 |
| Decimal powers | 7.351 | 6.485 |
| Random near-one inputs | 7.000 | 6.847 |

Every V9 result in these streams matches RNE. The two V6 near-one slowdowns
are closed for these measured streams. This does not establish a worst-case
latency bound: rare inputs can invoke the longer refinements. The transaction
restored accepted firmware, calculator values, program address, settings and
elapsed RTC, then closed the serial port.

`prove_compensated_ln.py` derives the Q82 bound with exact rationals;
`prove_near66_ln.py` bounds the relative polynomial and its integer rounding.
`prove_checked_ln.py` supplies the shared Q117/Q245 refinement bound; its
legacy Q62 fast bound applies only to `--checked-ln`. Certification includes
the closer rounding midpoint below a power of two. The finite Q245 limit
still has an explicit undecided trap; **all-input totality is unproved**.
The public entry handles `ln(1)` exactly before refinement. This experiment
does not replace the firmware runtime or repair other Qfplib functions.

See [`doc/measurements/qfplib-ln-fast-20261021.json`](../../doc/measurements/qfplib-ln-fast-20261021.json)
for current qualifications, source identities, historical physical results,
and limits. The earlier Q62 experiment is retained in
[`doc/measurements/qfplib-ln-checked-20261021.json`](../../doc/measurements/qfplib-ln-checked-20261021.json).
To reproduce, append `--near-ln` to the build command above, then run:

```sh
python3 research/qfplib-m0-full/generate_ln_constants.py --check \
  --json .build/qfplib-m0-fork/constants.json
python3 research/qfplib-m0-full/prove_checked_ln.py \
  --json .build/qfplib-m0-fork/checked-proof.json
python3 research/qfplib-m0-full/generate_ln_compensated.py --check \
  --json .build/qfplib-m0-fork/compensated-constants.json
python3 research/qfplib-m0-full/prove_compensated_ln.py \
  --json .build/qfplib-m0-fork/compensated-proof.json
python3 research/qfplib-m0-full/prove_near66_ln.py \
  --json .build/qfplib-m0-fork/near-proof.json
python3 tests/qfplib_m0_ln_checked_self_test.py \
  --build .build/qfplib-m0-fork --samples 10000 \
  --json .build/qfplib-m0-fork/checked-result.json
python3 tools/profile_qfplib_ln_checked.py \
  --build .build/qfplib-m0-fork \
  --qualification .build/qfplib-m0-fork/checked-result.json \
  --json .build/qfplib-m0-fork/checked-profile.json
```

# RP2040 pow midpoint comparison in log space, 2026-11-17

The probe compares `y * ln(abs(x))` with `ln(m)` where `m` is the exact
midpoint between adjacent binary64 encodings `L` and `L+1`. Its output
selects the side of a **supplied** boundary for round-to-nearest-even. It
uses outward-rounded fixed-point intervals at 512 and 1,024 bits. If the
intervals overlap, it returns undecided. The existing exact dyadic check
handles ties. The midpoint construction preserves all 54 bits, including
the zero-to-minimum-subnormal and maximum-finite-to-infinity boundaries.
[Test-only patch](../../research/m0-math-probes-20261117/pow-log-midpoint.patch)

For each logarithm the normalized significand gives an atanh argument
below 1/3. If `u = 2^-P`, the upper rounded square is less than 1/8.
Each successive odd power therefore takes its upper bound in units of
`u` from `k` to at most `ceil(k/8)`. The tail test terminates within
`ceil(P/3)` iterations per logarithm, giving 171 or 342. At 1,024 bits
the two series together use at most 1,372 fixed-point products, including
the two directed square calculations per series. The comparison multiplies
by the 53-bit exponent significand and applies the remaining power of two
as a directed right shift to one side, keeping both intermediates in range. [Existing interval certificate](../../dev/tools/certify_m0_pow_interval.py)

MPFR 4.2.2 agreed on all 25,055 midpoint-side checks at both precisions.
These cover the two adjacent boundaries around each of 261 archived
difficult results, 24,522 checks near computed boundaries, and 11 special
cases. A separate check of three exact midpoint inputs confirmed
tie-to-even in the host and ARM implementations, covering an even lower
neighbor, an even upper neighbor and zero. Neither precision returned an
undecided answer in the tested corpus.
[Archived inputs](../../research/m0-pow-checked-20261022/hard-pow-inputs.json)

The ARM benchmark ran the two linked Pico H ELFs with captured factory
BootROM v3 in Unicorn. At each precision it compared a call to the
direct midpoint test with a call to the current interval evaluator on
10 cases, including the subnormal and overflow boundaries. The current
evaluator returns a rounded encoding. The probe returns one boundary
decision. The stack measurement starts at the callee entry and excludes
the reference evaluator's caller-owned output word. Instruction counts
and stack depths are observed values from those calls. Wall time and
watchdog margin on PicoCalc remain unmeasured for this prototype.

| Precision | Max instructions, midpoint test | Max instructions, full interval | Max stack, midpoint test | Max stack, full interval |
| --- | ---: | ---: | ---: | ---: |
| 512 bits | 13,785,722 | 13,660,759 | 2,376 B | 2,656 B |
| 1,024 bits | 90,627,218 | 85,049,758 | 4,232 B | 4,832 B |

The 1,024-bit probe reached 90.63 million instructions at the subnormal/normal boundary. The current evaluator used 51.76 million on that input. The maxima in the table are selected independently for each column.
[Per-case ARM results](m0-pow-log-midpoint-20261117.csv)

The second logarithm adds work on some inputs, especially when the
normalized base and midpoint are both near 2. In the current evaluator
that case needs a single logarithm and the two exponential endpoints
have very small reduced arguments. The probe can cost less when those
endpoints require more terms. The method also needs a proven bracket or
an independent way to locate the rounding cell. The production rescue's
candidate output from the 1,024-bit stage supplies a hint.

The remaining proof obligation is to show that the intervals separate
for every finite binary64 input outside the exact cases. The available
logarithm-separation bound is still too large for the Pico H budget. The probe is
recorded for research and the production rescue continues to trap if
the existing directed and exact stages cannot prove rounding.
[Production rescue](../../code/native_eabi_m0_cr.cpp#L95),
[Prior analysis](m0-math-20261116.md#exact-pow-rounding)

The source snapshot for the builds is
`93cd91991770c91376401d2e12876b7639f2d43a`. Raw test outputs and ELF
hashes are in `.build/m0-math-probes-20261116/pow/`.

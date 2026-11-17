# ARMv6-M pow interval cutoff and the remaining midpoint case, 2026-11-17

The fixed-point fallback encloses `abs(y * ln(abs(x)))`. Before the
change, an enclosure straddling the internal cutoff of 800 could report
an undecided result. Its directed width after scaling is below one.
If the upper endpoint reaches 800, the exact magnitude therefore exceeds
799. This exceeds both the RNE overflow cutoff and the magnitude of the
zero-to-minimum-subnormal cutoff, so the sign of `y * ln(abs(x))` determines
the rounded result. The same check applies before a left shift, where the
cutoff is scaled by an exact power of two. [Rational certificate](../../dev/tools/certify_m0_pow_interval.py)

The certificate also bounds the reduced interval inside
`(-0.346784, 0.346784)`. The exponential enclosure before restoring the
power-of-two scale lies inside `(1/2, 2)`. Consecutive RNE midpoints there
are separated by at least `2^-54` after accounting for the shared scale,
including the subnormal and overflow cells. The certified interval width
is smaller, so an undecided valid enclosure contains only one midpoint.
The existing integer check handles actual equality with that midpoint.
For an exponent `p/2^k` in lowest terms, exact equality requires a
perfect `2^k`-th root of the input's odd coefficient and a compatible
power-of-two scale. An odd coefficient greater than one is at least
three, and `3^64 > 2^53`, so `k <= 5`. A midpoint has at most 54
coefficient bits, and `3^35 > 2^54` bounds the numerator for a
nontrivial positive power. Powers of two reduce to exact exponent
arithmetic. Negative powers with a nontrivial odd coefficient have an
odd denominator and cannot equal a dyadic midpoint.

The host test compared 1,033 pairs at each of 512 and 1,024 bits against
directed MPFR 4.2.2. This includes 90 added probes around the internal cutoff
and the two binary64 extremes. The linked Pico H ARM test with factory
BootROM v3 compared 32 pairs per precision, including 18 near the cutoff.
Every result agreed with MPFR. Maximum observed callee stack use was
2,728 and 4,968 bytes at the two precisions. An additional ARM build
forced the 1,024-bit rescue on 19 cases and matched MPFR on each.
[Host test](../../tests/m0_pow_interval_host_self_test.py),
[ARM test](../../tests/m0_pow_interval_arm_self_test.py)

The final rescue can still reach `trap` if the value differs from the one
midpoint and the intervals and bounded exact stage cannot certify its side.
Removing the trap requires an all-input separation bound usable within the
device's memory and watchdog budget, or a different exact comparison with
proved resource limits. The existing explicit separation estimate for
independent logs is far too weak for a 1,024-bit enclosure. CORE-MATH's
published search covers selected exponent domains. The host and ARM
samples establish correctness for the sampled decisions.
[Earlier separation analysis](m0-math-followup-20261114.md#host-results),
[CORE-MATH search coverage](https://core-math.gitlabpages.inria.fr/worst.html),
[Production rescue](../../code/native_eabi_m0_cr.cpp#L95)

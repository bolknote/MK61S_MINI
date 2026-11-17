# RP2040 pow rounding by bounded power products, 2026-11-17

After the directed 512-bit and 1,024-bit passes, the midpoint step
uses the adjacent encodings from the final enclosure. The existing
bounded exact comparison runs first. The new RP2040 stage applies
when that comparison has no answer. For positive exponent `p/q` it
compares `abs(x)^p` with `m^q`, where `m` is the exact midpoint. For
negative exponent it compares their product with one and reverses the
side. Zero, subnormal and overflow boundaries share the existing midpoint
decoder. The result sign is restored by the existing rescue entry point.

The power products use a 4,096-bit normalized lower significand and a
signed 128-bit scale. Each multiplication rounds downward. With
`N` factors, expanding the expression tree gives at most `N-1` local
rounding losses. Each relative loss is strictly below `2^(1-P)` for
significand precision `P`. Bernoulli's inequality and
`1/(1-z) <= 1+2*z` for `z <= 1/2` bound the upper significand by the
lower significand plus `4*(N-1)` units. An exact result needs zero
allowance. This construction proves the decision whenever the endpoints
identify the side. Equal exact endpoints use the parity of the lower
encoding for RNE.

After the existing tiny and huge exponent rules, `q <= 2^116`.
The combined exponentiation work takes at most 169 full-width products
and 11,128,832 16-bit multiply-accumulates, including the multiplications
by the original four-word factor. The relative interval width is below
`2^-3976`. The tested Pico H build used 119,896 bytes of static RAM and
a 1,805,072-byte Flash image.
[Rational certificate](../../dev/tools/certify_m0_pow_power_bounds.py)

| Check | Result |
| --- | --- |
| Native normalized multiply and upper-bound packing | 3,000 products and 1,000 bounds matched exact integers |
| Native directed MPFR side checks | 2,362 at 256 bits and 346 at 4,096 bits, all correct |
| Narrow test at 128 bits | 15 undecided results in 2,362 checks, zero incorrect decisions |
| Linked Pico H comparator with factory BootROM in Unicorn | Seven cases matched MPFR, including both tie parities |
| Input reaching the full-product bound | 146,215,403 guest instructions, 2,300 bytes of callee stack |
| Forced ARM rescue | 19/19 correct, each entered the new stage, 5,944 bytes of stack at the worst observed point |
| Existing exact stage with a forced interval hint | 19/19 correct |
| Public ARM pow numerical regression | 20,395 results matched directed MPFR |
| Committed exp inputs in ARM emulation | All 22 groups matched the earlier instruction counts, and the two broad modeled XIP miss rates matched |

The input with the largest exercised workload uses the largest subnormal
base and a negative exponent with 53 numerator bits and denominator
`2^116`. It exercises 169 full-width products and 52 four-word products.
The benchmark reports guest instructions and stack usage. PicoCalc elapsed
time for this new stage remains unmeasured.

The final trap remains for an undecided enclosure. The explicit separation
estimate available for independent logarithms is much weaker than the
working precision, and the published exhaustive searches cover selected
exponents. Removing the trap still needs a stronger uniform bound or
a total exact method that fits the device.
[Prior separation analysis](m0-math-followup-20261114.md#host-results),
[CORE-MATH coverage](https://core-math.gitlabpages.inria.fr/worst.html)

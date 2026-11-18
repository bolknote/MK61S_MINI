The binary64 CORE-MATH functions provide the correctly rounded fallback for
the Cortex-M0 software runtime. Every source file retains its MIT notice.
`provenance.json` pins both the original and adapted bytes. Reproduce with:

```
python3 dev/tools/vendor_m0_core_math.py --source /path/to/core-math-binary64 --check
```

The snapshot is the September 16, 2026 upstream revision, published in the
cross-platform binary64 repository linked by the official CORE-MATH project.
The vendored files retain their original coefficients. The port replaces
unsupported compiler `__int128` with the project's tested two-limb arithmetic,
reorders C designated initializers without changing field values/layout, and
adjusts two C goto scopes for GNU C++. The wrapper supplies exact software FMA,
sqrt, and integer rounding. It fixes the environment to RNE, matching the
project's arithmetic contract; it does not implement errno or floating flags.

The port checks both sides of the approximation-error band in the 128-bit
and 256-bit pow stages. Near the zero/minimum-subnormal midpoint, the
128-bit approximation can defer to the 256-bit stage. The final guard
invokes the owned 512/1024-bit directed integer refinement in
`code/native_eabi_m0_pow_interval.inc`. RP2040 can continue with directed
power products and exact integer comparison. Other ARMv6-M configurations
trap when the 1024-bit refinement is undecided. The practical uniform
latency of the RP2040 chain remains unproved.
[Boundary regression](../../tests/m0_pow_round_guard_host_self_test.py)

Official project: https://core-math.gitlabpages.inria.fr/

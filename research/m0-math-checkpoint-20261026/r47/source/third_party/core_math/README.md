The binary64 CORE-MATH functions provide the correctly rounded fallback for
the Cortex-M0 software runtime. Every source file retains its MIT notice.
`provenance.json` pins both the original and adapted bytes. Reproduce with:

```
python3 tools/vendor_m0_core_math.py --source /path/to/core-math-binary64 --check
```

The snapshot is the September 16, 2026 upstream revision, published in the
cross-platform binary64 repository linked by the official CORE-MATH project.
The vendored files retain their original coefficients and algorithms. The port replaces
unsupported compiler `__int128` with the project's tested two-limb arithmetic,
reorders C designated initializers without changing field values/layout, and
adjusts two C goto scopes for GNU C++. The wrapper supplies exact software FMA,
sqrt, and integer rounding. It fixes the environment to RNE, matching the
project's arithmetic contract; it does not implement errno or floating flags.

The upstream pow implementation includes a final guard against a previously
unknown worst case after its 256-bit pass. The wrapper sends that guard to the
owned 512/1024-bit directed integer refinement in
`code/native_eabi_m0_pow_interval.inc`. Its exact dyadic boundary check and
closed rounding intervals preserve RNE; its ln2 constant is generated from
exact rational bounds. Original diagnostics/exit are not linked into firmware.
An undecided 1024-bit interval still traps: increasing a fixed precision does
not establish all-input totality. This limitation must remain visible in
qualification reports.

Official project: https://core-math.gitlabpages.inria.fr/

The RP2040 port shares the unmodified pow integer tail in
`pow/pow_accurate_body.inc`. A checked internal entry can skip phase_1 after
an undecided Q94 enclosure. The normal special/FP entry still reaches the
same integer body. Both integer rounding tests, exact boundary detection,
and the owned rescue remain unchanged. `provenance.json` also pins the
original adapted pow file and the generated include; the vendor tool
reproduces both from the same pinned upstream bytes. Other ARMv6-M builds
expand the original body in place; Cortex-M4 does not compile this unit.

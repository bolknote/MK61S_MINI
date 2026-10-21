# RP2040 placement and literal-free float widening (V74)

This is a qualified private prototype. The patch has not been applied to
production math or installed on PicoCalc. Physical timing is still required.

`placement-and-f2d.patch` contains the complete five-file difference from the
committed V71 math (`45d320db78b63a7703c5154662613a64c61e6af9`). It applies to
the current math files without including another chat's platform changes:

```sh
git apply --check research/m0-f2d-no-literal-20261021/placement-and-f2d.patch
```

The V73 part fixes the flash locations of tangent refinement, float widening
and double square root. V72's three measured regressions had unchanged ARM
instruction counts and increased XIP misses. Fixed locations are a candidate
for reducing cache conflicts; their timing benefit remains unverified.

The V74 part removes the normal `__aeabi_f2d` literal read on RP2040. The old
path loads `0x38000000`. The replacement constructs `0x38000000` for a positive
input and `0xb8000000` for a negative input with shifts and an add, then adds
the exponent and significand. It retains 13 normal-path instructions and
saves two instructions before the unchanged slow helper for special inputs.
Generic M0 and M4 retain their existing code.

Qualification used accepted A7483AE6's frozen platform plus the committed
V71 math and this patch. No new coefficient table or main RAM is introduced.
Allocated flash is 6 bytes smaller than V73 and 6 bytes larger than V72;
the firmware image extent is unchanged.

- 44,816 ARM float-widening cases: exact integer-derived binary64 results,
  both signs and every exponent encoding, normal significand boundaries,
  subnormals, infinities and quieted NaNs. The 44,453 normal cases execute
  13 instructions and perform zero flash data reads, versus one in V73.
- 265,409 MPFR RNE checks across the twelve real-valued functions: zero errors.
- All 114 comparison groups / 116 chunks / 23,091 cases: unchanged owned
  instruction counts; 112 groups use fewer instructions than Qfplib and
  two use the same count. These are instruction counts, not device timings.
- M4 soft/hard-float and generic M0 allocated bytes remain identical.
- Diagnostic boot CRC, production code placement, APP ABI, UF2 bounds and
  the negative layout test pass.

The additional transaction test executes the prepared restoration function
with simulated USB and a simulated laptop sleep. RTC elapsed time now uses
UTC wall time, and a failed install still saves its transcript. It does not
claim a physical restore.

The source identities and artifact hashes are recorded in
`doc/measurements/m0-f2d-no-literal-v74-20261021.json`. The three V72 speed
gaps still need a complete physical comparison on the accepted platform at
the time of the math window. General `pow` totality also remains open outside
the exact stage's supported exponents; the undecided trap is still present.

The subsequent V75 experiment includes six tangent support helpers and a
different sqrt location. Its linked traces reduce the remaining modeled
conflicts; see `research/m0-trig-support-20261021/README.md`. Neither experiment
has physical speed measurements yet.

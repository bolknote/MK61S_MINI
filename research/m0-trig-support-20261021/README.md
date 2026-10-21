# RP2040 trig support placement (V75)

This private prototype extends V74's literal-free float widening and stable
math locations. Production math has not been changed and no math image has
been installed on PicoCalc. Physical timings remain pending.

`placement-and-f2d.patch` contains the complete six-file difference from
committed V71 math (`45d320db78b63a7703c5154662613a64c61e6af9`):

```sh
git apply --check research/m0-trig-support-20261021/placement-and-f2d.patch
```

The V74 cache probe showed that moving tangent refinement alone left
conflicts in its midpoint comparison, quotient, leading-zero and product
helpers. V75 fixes the locations of six unchanged helper bodies. It also
moves the existing double-sqrt block to avoid conflicts between its table
and division code on the composed exact-exponent `pow` stream. No formulas
or coefficient tables are added or changed by V75.

The selected locations were screened under four explicit model assumptions:
LRU/FIFO replacement, each with whole-line/per-word filling. The models
use exact ARM instruction/data traces, two warm corpus passes and a third
measured pass. They omit the other core, IRQ traffic and caller prefetch;
their miss counts are neither measured XIP counters nor device timings.
The newly linked ELF reproduced the screened counts on all nine checked
groups (2,956 exact-result cases):

| Stream | V72 modeled misses/call | V75 modeled misses/call |
| --- | ---: | ---: |
| `tan small_medium_remainder`, LRU word fill | 19.984375 | 5.1953125 |
| `pow composed_exact_exponents`, LRU word fill | 0.1796875 | 0 |

All four model variants give zero additional misses on the six standalone
sqrt chunks; all four agree on the direction of the tangent improvement.
This supports the next hardware experiment and does not prove speed parity.

Offline qualification of production build `7479d772`:

- 265,409 MPFR RNE checks over twelve real-valued functions: zero errors.
- 44,816 ARM widening inputs: exact results, ABI preserved, 13 normal-path
  instructions and no normal-path flash data read.
- All 114 groups / 116 chunks / 23,091 cases: unchanged owned instruction
  counts; 112 groups use fewer instructions than Qfplib and two tie.
- M4 soft/hard-float and generic M0 allocated code/data remain identical.
- Diagnostic CRC, production placement, reference link, APP ABI, UF2 bounds,
  exact-pow checks and negative layout checks pass.
- No new tables or main RAM. Allocated flash grows by 140 bytes over V74,
  or 146 bytes over V72; the image extent stays unchanged.

The prepared transaction uses UTC wall elapsed time for RTC restoration and
has a simulated disconnect/sleep test. Its restore image is still A7483AE6:
it must be rebased if the accepted platform changes. After the platform and
short memcmp windows, use the then-current accepted frozen source and restore
image, requalify, and measure the complete matrix.

Hashes, source identity, linked-address checks and qualification results are
recorded in `doc/measurements/m0-trig-support-v75-20261021.json`. The earlier
three V72 physical timing gaps remain unverified as fixed. General `pow`
totality outside the exact stage's 224 exponent values remains open, and the
undecided trap is retained.

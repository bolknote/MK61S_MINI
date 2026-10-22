# Exact short-significand integer powers (V81)

This private RP2040 prototype handles positive integer powers 3 through 8
without approximation when the stripped odd coefficient's power fits in
64 bits. It computes that integer power exactly, then performs one final
binary64 ties-to-even rounding. The existing public negative-base path
applies the sign. No table, allocation or global RAM is added.

The one-file `exact-short-integer.patch` applies over V79 and also passes
`git apply --check` against current ROOT math. It has not been applied to
production or flashed. Qualification uses the V77 arena, unaccepted 7AEA
platform and frozen flash-memory candidate.

| Example | V79 instructions | V81 instructions |
| --- | ---: | ---: |
| `52.5^8` | 53,545 | 591 |
| `51.5^8` | 53,479 | 591 |
| `0x1.bb4p-7 ^ 5` | 54,655 | 496 |

These are actual emulated instructions with the captured ROM and linked
memory implementation. They are not measured device cycles.

Qualification passes:

- 27,647 exact integer-oracle cases, including every normal exponent field,
  coefficient width transitions, midpoint ties, subnormals and overflow;
  3,456 public calls also check negative-base parity.
- All 5,717 entries of the saved million-case corpus which may enter the
  new exact acceptance domain. The full million-case result is for V79;
  this extracted subset is explicitly identified and hashed.
- 265,409 actual ARM / directed MPFR RNE cases over twelve functions.
- The original 114-group matrix retains 112 fewer and two equal instruction
  counts. All per-case counts replay identically after the Unicorn counter fix.
- M4 soft/hard-float and generic M0 allocated code/data identity.
- All 274 ordinary math inputs retain their addresses; constants are
  unchanged. Main static RAM remains 198,856 bytes and heap 30,520 bytes.
  The existing 4 KiB scratch reservation is unchanged. Allocated flash
  increases by 280 bytes; image extent is unchanged. No libgcc member links.

The range/rounding argument is source-pinned by
`tools/certify_m0_pow_short.py`. It proves that every accepted partial
product fits 64 bits and that normalization/sticky shifts preserve the
single final rounding. This is an algebraic argument with ARM qualification,
not machine-checked verification of every instruction.

The broader difficult-pow gaps remain: moderate-base mean instructions drop
from 25,597.273 to 23,545.547, still above Qfplib's 1,535.453. The other two
difficult streams also remain slower. The isolated cache models introduce
1–4 additional modeled misses per 128-call pass of the simple-exponent
pow stream; other checked streams are unchanged. Physical timing is required.

Results and source identities are in
`doc/measurements/m0-pow-short-v81-20261022.json`. Production promotion,
the complete expanded hardware comparison, and general pow totality remain
unfinished. No fallback accuracy guard has been weakened.

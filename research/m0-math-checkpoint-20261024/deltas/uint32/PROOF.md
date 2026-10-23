# uint32 conversion: full bit-domain argument

The new leaf retains the existing project's unsigned32 behavior. Normal
finite in-range conversions truncate toward zero, as this EABI entry already
does; this is distinct from RNE for floating arithmetic. Outside the ordinary
C conversion range the project returns 0 for negative inputs and NaN, and
UINT32_MAX for positive overflow/infinity. No new language guarantee is implied.

Let s, E and F be the binary64 sign, exponent field, and 52-bit fraction.

1. A set sign bit returns zero before modifying any fraction. This includes
   negative zero, finite inputs, infinity and either NaN class, as before.
2. For nonnegative inputs E<1023, the value is less than one, including every
   subnormal and zero. Subtracting 1023 from E fits signed32 and the negative
   branch returns zero.
3. For e=E-1023 in 0..31 the significand is the 53-bit integer
   N=2^52+F and the answer is `floor(N/2^(52-e))`. After removing E from
   the high word and setting the hidden bit, write N=H*2^32+L.
   If e≤20, the answer is `H>>(20-e)`; the low word cannot contribute.
   Otherwise e is21..31, and the answer is
   `(H<<(e-20)) | (L>>(52-e))`.
   The two pieces occupy disjoint bits and fit uint32. All register shifts
   are in range and the result is exactly truncation, with no rounding tail.
4. For e in32..1023 a nonnegative finite input is at least2^32. Return max.
   For e=1024 the exponent field is all ones. Right shifting e by10 is zero
   for every preceding large finite exponent and one only in this case.
   `(high<<12)|low` is zero exactly when F=0. Infinity returns max and every
   NaN payload returns zero, preserving the earlier policy.

These cases partition all 2^64 raw input encodings. The existing public
argument/result layout is R0:R1 input and uint32 result in R0. R0-R3 and flags
are volatile. The leaf does not touch SP, nonvolatile registers, memory stores,
SIO, IRQ state, helpers, heap or global RAM; the only load is its bias literal.

The argument is source-level mathematics, not a mechanically checked ARM
proof. The executed diagnostic body matches the full public assembly body
byte for byte. Targeted finite ARM/integer/MPFR results and compiler-object
isolation are separate evidence. No universal Qfplib speed theorem, physical
cycle measurement, or full production integration is claimed.

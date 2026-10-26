# Exact modular remainder-sign certificate

This changes only the private positive-one-numerator reciprocal. Its divisor
guard, quotient approximation, initial rounding, fallback classes and final
IEEE pack are inherited without relaxing rounding. The old complete product
is retained whenever the certificate is inconclusive.

At the correction point let B be R4, u be R2 and v be R0, all uint32.
The old sign test uses H = B - hi32(u*v) - (lo32(u*v) != 0), modulo 2^32.
Set d = hi16(u)*hi16(v). Expanding the product into four 16-bit limbs shows
0 <= hi32(u*v)-d <= hi16(u)+hi16(v) <= 131070. Including the borrow gives
E = hi32(u*v)-d+(lo32(u*v)!=0) in [0,131071]. Therefore H = A-E modulo
2^32, where A=B-d modulo 2^32.

We certify a sign only if (A & 0x7fffffff) >= 131072. If A is nonnegative,
then H is strictly positive. If A is negative, H remains negative without
crossing INT32_MIN. In every other case the original complete product and
signed sign test run. This includes H=0; parent tie behavior is unchanged.
The proof holds for every uint32 B/u/v, without an approximation error
assumption about the reciprocal or any restriction on the numerator.

The two Thumb shifts LSRS R6,R4,#17; LSLS R6,#18 make Z indicate the
uncertain band and C contain A's sign. BEQ selects the full computation;
BCS selects the negative result; the positive result falls through.
The full path first adds d back to R4, restoring the exact modular B.
R0/R1 (the midpoint), R12 and SP remain intact. Flags after the sign decision
are dead: positive rounding starts with ADDS before ADCS, and the downward
pack starts with shifts.

The additional removed shift of R4 by 16 is private to numerator +1.
The dividend's raw low word is zero; it remains unchanged through the two
initial products. The existing yL assignment LSLS R4,R0,#5 consequently
sets R4 to zero. The signed correction product does not overwrite R4,
and either normalization branch keeps it zero. Its removed shift has no
live carry consumer before SUBS. This specialization is not applied to a
generic division entry.

The bare unit uses exactly the production macro and compares all returned
signs with the complete 64-bit integer product. Its 100,800 test cases
include both signed discontinuities and all 16 incoming NZCV combinations.
Binary64/public qualification separately checks MPFR rounding, every actual
certificate decision, identical live joins, PCS, stack and SIO state.
An inconclusive certificate can increase cost; those cases are retained.
Counts are executed instructions, not physical device cycles.

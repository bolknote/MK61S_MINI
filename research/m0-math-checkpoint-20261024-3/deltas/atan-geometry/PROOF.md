# Residual repair across atan reduction geometries

The inherited71-bit residue and six-bit division code is byte-identical
to the independently reviewed residual component. Only the gate in
`atan_fast` changes. The selector, reciprocal, first polynomial, tables,
all other allocated sections and fallback remain unchanged.

Every fast input lies between1/64 and64 in magnitude. Inverted geometry
has `D=(s<<6)+(index<<(52-e)) >= 2^58`. Non-inverted exponent-6 halves
the exceptional65-bit denominator and loses less than1/2 Q70 unit; its
numerator halving is exact. Other non-inverted exponents do not halve.
The pinned global ratio proof gives quotient error below30.500008,
hence below33 for the unchanged residue helper. Its truncated divisor
is at least2^20 even at D=2^58.

The ordinary atan table contributes at most1/2 Q70. Inverted geometry
also subtracts the rounded pi/2 table value, giving at most1 Q70.
Inversion and denominator halving are mutually exclusive. Thus the sum
of table and halving errors is at most1 Q70 in every geometry.

Using the inherited exact polynomial bound, quotient truncation below
`1+34/2^20`, and the derivative term
`33*(hcap+33/2^70)^2`, the total is strictly below:

- 5.959510 Q70 for `h<=2^62+2^40`: radius6;
- 6.001914 Q70 for `h<=floor(2^70/250)`: radius7.

`certificate.json` stores exact Fractions for both bounds. Repair starts
within54 Q70 of a binary64 midpoint. Its correction has magnitude at
most33 and half-quantum is at least1024, so the original quantum, binade
and retained significand stay unchanged. Only the rounding tail changes.
A midpoint distance at least the respective radius is safe because the
bounds are strict. Otherwise the original fallback is used.

`helper-proof.json` rechecks denominators starting at2^58 against exact
unbounded residuals/division and both SIO states. `qualification.json`
measures every one of79,096 state cases, including all original parent
inputs and new direct/inverted h-cap neighborhoods. No functional-only
row is omitted from speed analysis. Seventeen raw speed deficits remain;
the test proves the reported improvements, not complete atan performance.

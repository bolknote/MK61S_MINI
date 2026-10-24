Private RP2040 exp: exact tiny-input rounding without iterative refinement.

The new code is selected only by MK61_M0_RP2040_EABI. Its caller first
handles every magnitude <=2^-54 (including both zeros) and all large
special inputs exactly as the accepted parent. The new path is reached
precisely for 2^-54 < |x| < 2^-38. Other input classes retain the accepted
algorithm. No claim here changes the parent's general-exp totality scope.

Write |x|=M*2^(e-52), with integer 2^52<=M<2^53 and -54<=e<=-39.
All outputs lie close to 1, so the binary64 grid is h=2^-52 for positive
x and h=2^-53 for negative x. Put s=-e-negative. The magnitude of the
linear displacement, in output units, is M/2^s. Its integer part is
retained; its fractional midpoint is M0=(2*retained+1)*2^(s-1).
The split high-word test in exp_tiny_rne computes this exact quotient
and fraction, with shift=s-32 in [6,22].

Let C=(exp(x)-1-x)/2^(e-52), the strictly positive correction in input
ulp units. Taylor's theorem with the absolute exponential series gives
0<C<M^2*2^(e-53)/(1-2^-38)<2^14/(1-2^-38)<16385.
Therefore a midpoint can be crossed only when the linear displacement
is within 16384 input ulps on the affected side. Positive x approaches
the midpoint from below; negative x approaches it from above. The code's
low-word guards recognize exactly those distances d=1,...,16384. Exact
linear midpoints d=0 have C>0 and their direction is handled directly.
All other linear cells cannot cross a midpoint.

For a guarded midpoint, set z=2*retained+1. At M0 its quadratic
correction is C0=z^2/2^(e+55+2*negative). The denominator shift q is
in [1,18]. Every z is odd and z<=65535, so the product fits uint32 and
the distance from C0 to any integer is at least 2^-18. These statements
are mechanically checked for every possible linear midpoint in proof.py.

Replacing M0 by M0+/-d changes the quadratic correction by at most
2^14*(2^54+2^14)*2^-92. The cubic and higher remainder in input ulps
is below 2^-23/(6*(1-2^-38)). Their sum is strictly below 2^-22,
and thus strictly below the minimum integer distance 2^-18. It follows
that floor(C)=floor(C0) throughout every guarded cell, for either sign.
There is no equality C=d. For positive x, the upper result is selected
iff d<=floor(C0). For negative x, the larger magnitude displacement is
selected iff d>floor(C0). These are exactly the two new comparisons.

The returned raw integer is 0x3ff0000000000000 plus the rounded
positive displacement or minus the rounded negative displacement. Both
grids are binary64 normal throughout this domain, without carry into a
different spacing. The proof establishes the exact RNE returned value
for the complete domain, not merely a polynomial's approximate error.
IEEE status flags are outside the existing returned-value contract.

proof.py enumerates all midpoint cells, checks the exact rational
separation and 32-bit product/shift bounds, and prepares both integer
transition neighbors for actual ARM/MPFR execution in every cell. The
full-source candidate is tested through its public mk61_m0_exp ABI;
no host model substitutes for the emulated function. Existing accepted
48763-input exp qualification is preserved and rechecked separately,
including every prior slow input and both SIO states. Wrong Qfplib
returns and their costs remain in the acquisition records. Independent
review, full-firmware integration and physical-cycle acceptance remain
separate gates.

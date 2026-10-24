# Private main-ln coefficient enclosure

This child changes the RP2040 main packing gates and carries the already
computed fourth and fifth powers to a cold coefficient check. The existing
argument helpers, polynomial terms, tables, near-Q77 path and fallback remain
unchanged. The parent is the frozen ln2-sign child, not an exploratory trial.

Let S=2^70 and h denote the computed nonnegative argument divided by S.
The true argument is H=delta*2^29/(den*S), den=2049+2*index. Both h and H
are below 1/(d-1) whenever den>=d, for d=2049,2081,3585. This follows from
H<=1/den and the accepted argument error A=106497/16384 Q70 units.

The square error lies in(-1-2^-16,1]. The accepted cube helper gives absolute
error C=35/64+h*(1+2^-16). Write t=floor(h*S/2^27). The unchanged fourth
power is floor(floor(cube/64)*t/2^37). Its error relative to S*h^4 is in
(-F4minus,F4plus), where

    F4minus=1+63*h+(S*h^3+C)/2^43+h*C
    F4plus=h*C.

The 63 is an integer truncation of cube/64. It is multiplied by h, without
an additional factor64. The subsequent fifth power floor(fourth*t/2^43)
has lower magnitude bound 1+h*F4minus+(S*h^4+F4plus)/2^43 and upper bound
h*F4plus. Both omitted products and each final floor are included.

Nearest /3 has error at most1/3. Ceil(z/2)-z/2 is0 or1/2. The fourth and
fifth coefficient remainders are retained exactly:

    r4=fourth-4*floor((fourth+2)/4) in{-2,-1,0,1}
    r5=fifth-5*floor((fifth+2)/5) in{-2,-1,0,1,2}.

The multiply by52429 followed by>>18 is exact nearest /5 for every possible
fifth value; certify.py checks all65536 enclosing integer values and overflow.
The known coefficient error is r4/4-r5/5 on positive offsets, r4/4+r5/5
on negative offsets. Its representation bias20/20 uses only signed32 values.

After removing this coefficient bias and the exact linear h error, the
remaining bounds, including centre rounding and the omitted fifth-degree
Taylor remainder, are:

| Minimum den | Positive lower magnitude | Positive upper | Negative lower magnitude | Negative upper |
|---|---:|---:|---:|---:|
|2049|2.219134|4.448604|2.019031|4.648708|
|2081|2.219080|4.211244|2.018978|4.411346|
|3585|2.217628|1.865569|2.017571|2.065626|

These decimals are explanatory upward approximations. propagation.py and
certificate.json contain the exact rational values. The emitted constants
are larger: lower9/4 or17/8, and the three upper bands use9/2 or19/4,
17/4 or9/2, and2 or17/8. Their factor40 is the common denominator with
the known coefficient bias.

The fifth-degree Taylor polynomial exceeds the true logarithm for either
offset sign. Its remaining error is positive, at most S*hmax^6/(6*(1-hmax)).
Removing the exact linear argument error leaves nonlinear magnitude at most
A*hmax/(1-hmax). The signed residue r=(delta<<29)-h_integer*den is exact
from its low32 bits because |r|<32768. Orientation v is negative exactly
when the input offset and output magnitude signs differ. Linear magnitude
error is therefore -v*r/den. Negative output signs also negate the known
coefficient bias and swap the remaining upper/lower bounds.

The accepted Q70 ln2 constant has error in(-1/2,0). Its magnitude contribution
is in(-n/2,0) for either exponent sign. The exact n is recovered from the old
ceil(n/2) argument and the original input exponent parity. All2046 normal
exponents are checked. This avoids unnecessarily replacing an odd n/2 by
ceil(n/2) in the new gate.

For a point above a midpoint, the new integer predicate proves that its
maximum error is strictly below the distance to that midpoint. For a point
below, it proves the minimum error strictly exceeds the negative distance.
The strict rational bounds permit integer equality in the predicate. An
exact midpoint still declines to the existing refinement. All intermediate
signed expressions are below2^28 in magnitude. The inherited output-width
and neighboring-midpoint separation argument remains valid.

The cheaper preliminary gates have separate one-sided bounds: exact k=0
has lower radius4 and upper6/7 for negative/positive offsets; raw k=0 has
residual-aware lower3/4 and upper6. Positive endpoints in indices0..31 with
offset_high10>=1022 have a Taylor omission large enough to improve the
lower radius to1. The exact rational lower remainder and domain checks are
included in certify.py. These gates use no coefficient metadata.

The bare unit compiles literal copies of both packing functions and the new
coefficient helper. It checks accepted and declined predicates, equality,
both output/offset signs, all coefficient remainders, band edges, all normal
exponent magnitudes, exact midpoint declines, binary64 parity and binade
carries. Rational RNE is checked at both enclosure endpoints for accepted
pack points. Only the unit ELF and a read-only input fixture are loaded;
there is no firmware, ROM or SIO access. Public MPFR testing, isolation,
whole-object/ELF rebuilding and measured regressions are recorded separately.

This is a private component proof. It does not assert universal speed,
whole-library correctness, independent review, integration or hardware GO.

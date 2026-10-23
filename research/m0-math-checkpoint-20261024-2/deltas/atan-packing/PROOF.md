# atan: directional enclosures and bounded-domain packing

The argument geometry, reciprocal, products, polynomial coefficients,
angle table and original refinement/CORE-MATH fallback are unchanged.
Only RP2040's fast-path enclosure and integer output packing change.

## Reciprocal direction

Let normalized d be in [2^63,2^64), r be the existing corrected32-bit
estimate, S=r*2^32, and R=2^126/d. The inherited rational certificate gives
|S-R|<c*2^32, c<2, and r<=2^31. Write epsilon=d*r-2^94. The last correction
in the unchanged source is

    C = floor(floor(abs(epsilon)/2^32)*r/2^30).

Its exact counterpart is X=abs(epsilon)*r/2^62, so0<=X-C<r/2^30+1<=3.
There is no wrapped multiplication: floor(abs(epsilon)/2^32)<c*2^32,
therefore its product with r is<c*2^63<2^64.

The exact Newton step T=2*S-d*S*S/2^126 satisfies

    T-R = -d*(S-R)^2/2^126 <= 0.

For positive epsilon the source subtracts C, giving T+(X-C), whose
overshoot above R is strictly<3. For negative epsilon it adds C, giving
T-(X-C)<=R. Both branches have strict lower error>-(4*c*c+3), the parent's
existing bound. Thus the reciprocal error is asymmetric: (-B,3), with
B=12.000003668... from the exact rational certificate.

For normalized numerator n, the quotient-product error is consequently

    -(6.5+B*n/2^62) < h-H < 6.5+3*n/2^62.

The6.5 is the unchanged bounded product's error. atan is increasing and
1-Lipschitz, so these directional errors propagate without enlargement.
The unchanged polynomial's rounding, truncated operands, omitted series,
table rounding and optional denominator halving are added with the same
exact-rational formulas as the parent certificate.

## Regions

`certificate.json` evaluates the formulas with exact fractions. The two
radii below are for positive correction before geometry/inversion swaps:

| Region | Down from q, Q73 | Up from q, Q73 |
|---|---:|---:|
|Whole original reduced domain|282|426|
|h<=2^-8 in real units|144|288|
|Non-inverted e=-5..-1, h<=47/8192, normalized n<49*2^56|121|176|
|Same non-inverted domain, normalized n<2^59|91|100|

Every actual error is **strictly** smaller than its radius. The tiny n
condition implies h<2^60+33<2^62 in Q70 units, so its small-h bound applies.
The non-inverted rows use one rounded atan table value (<=1/2 Q70 error)
and have no optional denominator truncation. All65 existing table rows
are separately checked using directed256-bit MPFR bounds.

For e=-5..-1, the exact denominator satisfies

    2^(58-e) <= d < 2^(59-e),  clz64(d)=e+5.

This follows from s<2^53 and index<=2^(e+7). Geometry gives normalized
n<2^63 without wrap. For k=e+5 in0..4, the8-bit high-word test

    (uint32_t(numerator>>32)>>(24-k)) <49

is exactly normalized n<49*2^56. The tiny condition is equivalently
`(numerator_high>>(27-k))==0`. No low-word comparison or CLZ is needed.
The normalized numerator is2^69*abs(x-index/64), so these are full regions,
not checks for particular inputs.

The correction's sign and the optional pi/2 inversion determine whether
the two radii swap. The final sign of the original argument is applied
only after rounding the positive magnitude.

## Specialized packing

For non-inverted reduced input, source exponent e is-6..0 and the output
center's exponent is e or e-1. The alternating-series bound atan(x)>=
x-x^3/3>=2*x/3 puts it well above2^(e-1); x's binary64 grid puts it at
least one input ULP below2^(e+1). Both margins dwarf64 Q70 units.
For inverted input, atan(x) is in(atan(1),atan(64)), strictly between2/3
and2-1/64. Its two possible output exponents are-1 and0.

Use base exponent0 when inverted, otherwise e. Comparing q.high with
`1<<(base+6)` selects the correct center binade. The shift is11..18.
Word shifts recover the exact53-bit significand; adding its biased
exponent and one rounding increment handles carry into the next binade.

The cheap symmetric enclosure admits most inputs immediately. Only a
near-midpoint center evaluates the tighter directional/region bounds.
Let distance be the integer Q70 distance to the neighboring midpoint.
Accept when8*distance>=the relevant Q73 radius; equality is safe because
the certified error is strictly smaller. Exact-center midpoint cases
always decline. The opposite midpoint is at least1024 Q70 units away,
far beyond every radius; changes of binade inside the interval are also
far inside the power-of-two result's rounding cell. Thus admitted
intervals have one binary64 RNE answer. Otherwise the old refinement
and CORE-MATH paths remain available.

## Executed scope

The full public translation unit is compiled normally. The rebuilt parent
matches all259,764 allocated bytes of the original frozen build object.
The candidate component is linked from that full public object, with the
same pinned resident helper and captured-ROM bindings as its control.
Every profiled control call must retain the resident result/count exactly.
This is an offline component fixture, not a self-contained firmware.

Generic M0 and M4 preprocessor branches keep their previous code. No new
table, global RAM, arithmetic approximation, libgcc dependency, firmware
version, canonical edit or hardware access is involved. Finite numerical
and instruction tests support the change; they do not prove all-input
cycle speed or whole-library completion.

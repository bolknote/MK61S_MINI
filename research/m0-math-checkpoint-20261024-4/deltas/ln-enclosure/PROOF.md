# Strict RP ln enclosures and the negative outer half-cell

The exact RP residual is floor(delta*2^29/den)+1, so its Q70 error is at
most1. The inherited pure propagation used6.50006103515625 for the generic
retained reciprocal product. Changing only that argument bound in the
same exact Fraction calculation gives

    main error <=7.897372764676165... <8.

The unchanged near-one interval calculation already gives

    near error <=3.6850118973626564... <4.

Both exact fractions and the propagation-function fingerprint are in
certificate.json/prospective.json. No polynomial, reciprocal, table or
primitive changes. The old additional ceil(abs(k)/2) from the ln2 table
is retained for normal inputs. The subnormal converter is exact for
N<2^52, so the same base bound applies with n1023..1074; its ceil(n/2)
allowance is also retained. The inherited generic M0 path keeps16/8.

The former packer declined midpoint distance<=radius. This child treats
the proven integer radius as strict: actual error is below radius, so
integer distance>=radius is safe. The existing unsigned closed-window
test is used with guard=radius-1. All call radii are positive. Within
the relevant domains radius<=half-quantum: near ln has half>=4, the
general kernel excludes the small interval around1, and subnormal ln
uses half2^26. Algebraically, tail-(half-guard)<=2*guard is equivalent to
abs(tail-half)<radius. certify.py checks24,612 boundary configurations.
Exact midpoint still declines. Packing and rounding themselves are old.

The former near dispatcher also admitted negative n128, whose omitted
65-bit table row caused an immediate refinement. In the negative
geometry, n=floor(((1-x)*2^62+2^48)/2^49). Thus n128 begins at
x=16129/16384. The RP dispatcher now admits x strictly above this
dyadic boundary, encoding the inclusive lower endpoint as its next
binary64. The excluded half-cell uses the existing general normal-input
kernel, where abs(ln(x)) is sufficiently large for the old packing.
The defensive n128 check remains. Generic M0 retains its old selector.

Only ln_near_interval, public ln, and ln_special change; every allocated
section keeps its size. log10_special, all other functions, all tables,
dependencies and the entire ratio ASM object match. Generic M0 and both
M4 compile controls match. Public CPP/ASM objects and the entire ELF
independently recompile/relink byte-exactly. The retained ratio helper
and its table closure are identical to the accepted parent; that parent's
155,608 bare ARM checks are inherited rather than counted as fresh calls.

The fresh corpus retains every prior input, adds all near-one centers,
half-cells and selector boundaries, and profiles all39,318 state cases.
Every own answer passes fresh directed MPFR. All29,814 retained parent
instruction counts reproduce. Raw incorrect Qfplib answers, remaining
speed deficits and +1-instruction parent regressions are retained.
This is private component evidence, not whole-library or hardware GO.

# Near-ln directional rounding from exact division remainders

This private child changes only the RP2040 near-interval body. The
previous near polynomial, retained-product kernel and 256-row table are
unchanged. The saved prototype in checkpoint d0b9cbd6c is immutable; this
child qualifies that same runtime source in a new directory.

For center c=den/8192, den8065..8320, and the original Q62 dyadic
distance delta<=2^48, the exact Q70 reduced argument is

    H=(delta*2^21)/den.

The unchanged product54 yields integer h with |h-H| less than
69/128+2^-22, not merely69/128. Its exact signed error is -r/den with
r=delta*2^21-h*den. The bound gives |r|<4486; the source obtains that
signed integer from its low32 bits without wide multiplication/division.
Every existing reciprocal and Q70 log center is independently rechecked
using exact rational reciprocal rounding and log-series intervals.

The three polynomial rounding remainders are exact:

    r2=z-2*ceil(z/2) in{-1,0}
    r3=cube-3*nearest(cube/3) in{-1,0,1}
    r4=fourth-4*floor((fourth+2)/4) in{-2,-1,0,1}.

The existing multiply-by0xAAAAAAAB gives floor(cube/3): cube<2^29
leaves the reciprocal's positive error below1/48, so no quotient can
cross its next integer. The source's bias12 is exactly

    -4*r3-s*(6*r2+3*r4), s=+1 for odd+even, -1 for odd-even.

The unchanged square/cube/fourth propagation supplies their non-integer
errors. Replace the old symmetric h error by its exact -r/den term;
the remaining derivative error is bounded by argument*nh/(1-nh), with
nh=1/16000. The omitted fifth-and-higher term is positive in the exact
log correction for either sign, so it only enlarges the lower error
bound. Including the center-table error<=1/2 gives strict bases

    U=1.4207551029470529... <3/2,
    L=1.6459491589440776... <7/4.

Let B=bias12/12-r/den and q be the integer magnitude assembled by the
old code. When the correction is added, q-trueMagnitude lies in
[B-L,B+U]; when subtracted, it lies in[-B-U,-B+L]. For integer midpoint
distance d1..3, an upper-side test therefore accepts when

    den*(12*d-bias12)+12*r >=18*den,

and the lower-side test accepts when

    den*(12*d+bias12)-12*r >=21*den.

The class is upper precisely when (tail>half)==add. Strict rational
bounds protect equality in these integer comparisons. Distance>=4
retains the parent's strict near bound. For delta0 only the center
table error remains; distance>=1 is safe. Exact midpoint0 always
declines, so the prototype cannot guess a tie or blindly return its
approximation. Packing after acceptance is the original RNE packing.

All cold signed expressions have magnitude<486472; cube/third casts,
remainders and den fit int32. Half-quantum>=4 and pack shifts3..12 are
valid in the nonzero near domain. The half4 outputs lie far above their
lower binade edge because n>=1 implies |x-1|>=1/16384 and
|ln(x)|>=u-u^2/2. Later lower-neighbor half-gaps are at least4, exceeding
the strict error. The existing carry/sign/normalization behavior is kept.

certify.py binds the source and exact Fraction propagation, checks all
256 rows and207360 discrete gate extrema. The exact inline packer is
also compiled as a bare unit with the original clz helpers:16896 actual
ARM calls cover both SIO states, both signs/add directions, exact centers,
midpoints, binade carries and all denominators. Its accepted results
match11554 rational RNE interval endpoints; all PCS/SP/bounded-write
checks pass and there are no SIO accesses. This unit does not map any
firmware or ROM and does not replace full public qualification.

Only.text.ln_near_interval changes,912->1160 bytes. All other allocated
sections, tables, undefined dependencies and the ratio ASM object match.
Generic M0 and guarded M4 compile controls match. Public CPP/ASM objects
and the entire ELF independently rebuild byte-exactly. Public ln still
uses the pinned V164 helper/CORE-MATH image and captured support ROM;
no new ROM mathematics is introduced. An unrelated generator error from
forming negative raw neighbors of +0 is retained in trials; it was fixed
before the successful full qualification, without changing math source.

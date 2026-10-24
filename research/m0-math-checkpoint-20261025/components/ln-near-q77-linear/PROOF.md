# Certified Q77 near logarithm

This private RP2040 child changes only the near-one normal logarithm.
Generic M0, M4, main/subnormal logarithms, log10 and the original shared
tables retain their source and allocated object bytes. The normal entry
selects the new near function under the existing domain predicate.
Existing near-one cancellation handling for n=0 is retained.

For n>=1, index is1..256 and den=8064+index is8065..8320. The exact
center distance delta is at most2^48; H=delta*2^28/den is the true Q77
argument. H/2^77<=1/16130. The error analysis uses hbound=1/16000 for
both true and approximate reduced arguments; their gap safely exceeds
all argument-rounding errors.

The existing184B product54 kernel and unchanged Q62 reciprocals produce
Q70 h0 with error<69/128+2^-22. Shift7 gives an initial Q77 error
A0=69+2^-15. Its exact signed remainder r0=(delta<<28)-h*den is below
2^20, recovered through defined uint32 modular arithmetic. For each
used denominator, T=4096-floor(den/4) approximates2^24/den within3/4.
Indeed, with d=den-8192, the exact reciprocal is
2048-d/4+d^2/(4den); certify.py verifies all256 rational cases.
One32bit multiply and half-up shift approximates |r0|/den. Correcting
h by its signed result gives argument error
9030828227/17179869184=0.525663387205<0.526 Q77. This internal argument
need not be RNE; its exact residual and final enclosure certify output
RNE. All products fit uint32 and the corrected residual is below2^13.

Let S=2^77, t=high32(h), a=low32(h). The square is
floor(t*t/2^13)+floor(t*a/2^44)+1. The omitted a*a/S is below2^-13,
so its absolute error from h*h/S is below1+2^-13.

The cube needs six small products rather than a full128bit product.
Write z=B*2^18+b. For the Q27 numerator start with exact t*B, add
floor(a/2^16)*floor(B/2^16) and
floor(t/2^16)*floor(b/4), then round after shifting27. These represent
the leading terms of a*B/2^59 and t*b/2^45 in h*z/S. The omitted
parts are positive and total less than
(131072+65537+1)/2^27<1/512 Q77, including a*b/S. Thus cube error
is below1/2+1/512+hbound*square_error.

cube<9*2^32. Its exact nearest integer division by3 uses the existing
base2^32 quotient identity, with high-word quotient (hi*171)>>9 exact
for hi0..8. Since2^32=3*0x55555555+1, high/low residues and the final
carry recover the full64bit quotient/remainder. The final remainder
decides nearest division by3; there is no half tie.

For the fourth power use floor(z/2^19), its exact square, and a rounded
shift39. The error includes the full one-unit truncation of this floor.
For the fifth power, a single32bit product of floor(t/2^16) and
floor(fourth/64), followed by a rounded shift23, approximates h*fourth/S.
Its discarded terms total<1/64+2^-22<1/32. Operand bounds ensure the
32bit product and rounding addition cannot overflow. The fifth value
is below145; ((fifth+2)*205)>>10 is exactly nearest division by5 over
the entire admitted range, verified for the broader0..255 range.

Keep exact coefficient remainders r2=-z mod2 in{-1,0},
r3=cube-3*third in{-1,0,1}, r4=fourth-4*quarter in{-2,-1,0,1},
r5=fifth-5*fifth_term in{-2,-1,0,1,2}. Their combined bias60 is
5*(-4*r3 +/- (6*r2+3*r4))-12*r5, with the even sign selected by
subtract. Its absolute value is at most104. The polynomial now includes
the fifth term; the remaining series is bounded by S*hbound^6/(6*(1-hbound)).

Center error, nonlinear argument amplification and all product errors
leave symmetric base B=1.401214032242<3/2. The exact correction-error
center is bias60/60-residue/den; negate it when the correction is
subtracted from the stored magnitude. Generic complete error, including
argument and coefficient biases, is3.660210752781<4 Q77. The packer
therefore accepts distance>=4. At smaller nonzero distances its exact
integer inequalities use radius3/2 with denominator60. Exact midpoints
decline. At a table center, the sole error is its rounded constant,
at most1/2, so any nonzero integer distance is safe.

For h<=2^38 the linear term alone suffices. The true argument is at most
(2^38+argument_bound)/S; the omitted nonlinear series is below0.251Q77.
Together with center error its remaining base is0.750000000001411,
strictly inside the same3/2 gate. The exact residue remains available;
the coefficient bias stays zero. This avoids unnecessary polynomial work
near centers, including all28 regressions found in the rejected full
nonlinear Q77 trial. Tests cover all255 used centers on both sides and
both sides of this precision threshold.

The old256rows retain their exact Q62 reciprocals and Q70 logs for other
users. New signed-byte corrections store Q77log-128*Q70log, each-64..64:
only256 new readonly bytes. Rational100term logarithm-series intervals
certify every old/new row and reciprocal. All256 initializations are
checked to avoid low64 carry/borrow, so the high center word is the old
Q70 word shifted right57. Full magnitude updates track later carries
and borrows. Output widths63..72 imply midpoint half-gaps>=512; even
lower binade half-cells256 exceed the strict error4. Integer shifts,
signed gate products and unsigned sums are bounded in certify.py.

Actual-source bare pack execution covers10752configurations/21504ARM
calls with16394 rational RNE endpoint checks, all denominators, signs,
coefficient/residual extrema and binades. Bare arithmetic executes80120
calls:4096argument pairs,5892product configurations and8300exact integer
thirds. It loads only unit code, a2KiB test reciprocal fixture and the
actual184B product54 capsule. Every executed PC stays in those exact
function extents; capsule entry SP is8aligned. No full firmware/ROM or
SIO access. PCS/SP/bounded writes and both SIO states pass throughout.

Public59022inputs/118044all-profiled states/472176ARM use fresh MPFR4.2.2,
raw parent NaN policy, caller SIO/PCS/SP/bounded writes on every call.
All97998 frozen parent counts reproduce directly. All114766 cold-parent
counts from the rejected full trial reproduce as a separate cross-check;
that trial's candidate is not used as the parent. Its zero-call generator
error and rejected numerical/performance runs are not qualified counts.
Qualified total573800ARM; capsule entries are nested, not added again.

Parent58expanded raw correct-Qfplib deficits become4raw/8states:
54fixed,0new. All42old near deficits and12new-control deficits are fixed.
The original10ln cases are all no-slower; four general-kernel inputs
remain. All wrong-reference outcomes and47110parent cost regressions
remain recorded. Ordinary near cases often cost88..102more instructions
while remaining no-slower than correct Qfplib. This is instruction
profiling, not physical cycles or a whole-input speed guarantee.

Only old near code1160B is replaced by1356B and256readonly bytes:
object+452B, linked+448B after alignment reuse. Public max stack640same;
bare core60B and pack48B are distinct scoped observations. No new global
RAM or libgcc; whole public CPP/ASM/ELF and both unit ELF rebuilds are
byte-exact. Existing table/object bytes match, while linked addresses
and literals relocate. Generic-M0/M4 compile controls are identical;
this is not a whole-platform firmware build.

Independent review, canonical integration, physical cycles/acceptance,
the remaining general ln cases, other operations, general pow totality
and the original whole goal remain open. No Git/device/shipping action.

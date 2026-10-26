# Scope and inherited premises

This review accepts only the frozen main-raw split child of the accepted
small-low-limb component. The parent control ELF is exactly that accepted
component. The near/special/subnormal functions, exact quotient helper,
fallback, center tables and polynomial operations are inherited without
semantic change. Later IEEE cold-entry, Q77, and ln2-sign children are not
covered by this verdict. No entire-library, shipping, timing, or hardware
qualification follows.

# Argument and directed error

For a positive normal main input, index is 0..1023, den=2049+2*index,
delta=abs(offset-2^41) in 0..2^41. All 1024 reciprocal rows in the actual
linked ELF equal floor(2^75/den)&~63. If P=delta*R/2^46 and
H=delta*2^29/den, 0<=H-P<2.

The accepted nine-product routine omits limb pairs 00/01/10, whose sum
is below 2^49+2^32. Its Q46 entry performs half-up rounding and adds the
mandatory bias 4. This recenters the omitted interval [0,8+2^-14), giving
|h-P|<4.5+2^-14 and |h-H|<A=106497/16384. The bias cannot be omitted from
this derivation. Every relevant quotient and intermediate remains within
the inherited operation domains.

The unchanged polynomial's source bounds give total generic Q70 error
13.400120688467078. Removing just the signed linear argument term leaves
B=6.900059653310828<7. In particular the nonlinear argument amplification
A*hmax/(1-hmax) remains in B; this is not an assertion that argument
uncertainty has disappeared from the nonlinear terms. Center rounding,
square/cube/fourth/fifth integer-operation error and the sixth-order tail
are included. Adding k*ln2 contributes less than ceil(abs(k)/2), denoted e.

The exact integer r=delta*2^29-h*den has |r|<A*4095<32768. Therefore the
source's modulo-2^32 subtraction and actual ARM signed conversion recover
it exactly. For magnitude M and true magnitude T,
M-T=-v*r/den+epsilon, |epsilon|<B+e, where v is negative exactly when
input-offset sign differs from logarithm sign. The code's unsigned low-word
negation reconstructs delta*2^29 for either offset orientation.

# Gate proof and binades

If integer midpoint distance d>=16+e, generic error A+B+e<16+e suffices.
The unsigned guard selects exactly the complementary distances d<=15+e.
At d=0 it always falls back to unchanged ln_refine(original x).

Above a midpoint, den*(d-7-e)+v*r>=0 implies
d-(-v*r/den+B+e)>=7-B>0. Below a midpoint the analogous predicate with
-v*r gives d+(-v*r/den-B-e)>=7-B>0. Thus equality in the integer predicate
is safe, including when the strict interval endpoints approach it. This
is an algebraic proof for every admitted residual, not an inference from
sampled residuals. Uncertain intervals decline. The signed integer
expression has absolute value below 2^22; no signed overflow is needed.

Outside the inherited near-one domain, |ln(x)|>1/128. The quantized
magnitude has width 64..80 and shift 11..27; all source shifts are valid.
For the upper endpoint, exp(.7)>2 from five positive Taylor terms, hence
|ln(x)|<1024*.7. Even the maximum error cannot raise width above 80.
At a power-of-two result the lower rounding half-cell is half the usual
one. Width 64 implies k is -1 or 0, so e<=1 and radius<=17<512. At widths
65..80 the smaller half-cell is at least 1024>528. The retained-bit
addition handles a binade carry; signed outputs use the same positive
magnitude argument. Exact center, signed midpoint, just-before-carry and
binade-start controls were also executed from the exact inline source.

# Dispatch and isolation

Modulo 2^32, delta_low is +/-input_low; the interval [-64,64] is invariant
under negation. Thus the public raw dispatch excludes exactly the accepted
small-low-limb family. READY and family inputs retain the old arithmetic
body. The new raw branch is taken only on positive-normal main inputs
with DIRTY set. Bare trace and public trace verify the branch selection;
raw main does not call the exact quotient helper. The only changed
allocated object sections are the 28-byte dispatch expansion and the
1356-byte raw function. Other code, tables, BSS and imports are identical;
linked literals/table addresses may relocate.

Complete private CPP+ASM objects and the entire ELF, plus the bare pack
unit, were independently rebuilt byte for byte. All 39 external symbol
bindings were checked against the actual resident, including the actual
__wrap_memcpy/__wrap_memset aliases. Generic M0 allocated controls are
equal. M4 objects have zero allocated bytes because this TU is excluded;
that fact is not whole-M4 firmware or math qualification.

# Numerical and performance limits

Own bounded controls comprise 750 public ARM calls (125 raw inputs in
READY/DIRTY, candidate/accepted-parent/Qfplib) with fresh MPFR 4.2.2,
and 448 bare pack calls with 288 exact Fraction RNE interval endpoints.
They include all 24 fixed raw deficits and all 49 remaining raw deficits,
historical ln inputs, signed family boundaries, IEEE/subnormal controls,
equality/decline/binade/carry cases. Every call checks PCS, SP, bounded
writes and SIO state; bare pack makes zero SIO accesses. This is not an
exhaustive public-input execution claim. The new gate itself is justified
algebraically over its domain, and uncertain inputs retain old fallback.

The author full corpus was not reexecuted. Its saved counts and retained
parent rows were independently recounted: 24 deficits fixed, zero newly
slower correct-Qfplib inputs, 49 raw deficits remain. 32,670 parent states
cost 4 more instructions and 12,096 cost 8 more. Code grows 1384 bytes;
there is no overall no-regression or whole-ln speed GO. Own stack maxima
were 528 public and 56 bare-pack bytes; the author's wider 640-byte public
maximum is retained as author evidence, not a fresh independent sweep.

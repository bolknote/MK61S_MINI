The new helper is entered only for normal input binades e=-32 through -12.
The one-file source delta inserts that dispatch after the unchanged tiny path;
all other inputs, IEEE policy, tables and exact refinement are inherited only
through the exact accepted directed-parent binding.

For B=2^16, a<2^48 and b<2^58, the high kernel retains the six digit products
with i+j>=3. The omitted positive integer is at most
(B-1)^2(1+2B+3B^2). Together with its half-up rounding this is strictly within
the claimed eta=7/2+2^-15 high-word error. The first col4 add omits ADC safely:
the preceding rounded col3 sum is below 2^18 and a1*b3<2^26. All later carries
are explicit. The nine-term middle kernel omits only columns0/1, bounded by
(B-1)^2(1+2B); its floor therefore has directed error strictly between -3 and0.

The square leaf forms floor(X^2/2^32) exactly from a0^2, a0*a1, a1^2,
a0*a2, a1*a2, a2^2. In the low two columns, the carry from a0^2+2*a0*a1*B
is floor(a0^2/B^2+2*a0*a1/B). Each subsequent doubled cross product explicitly
retains its high carry. X<2^48 makes the full retained word below2^64.
The final right shift is6..26, so the result is exactly floor(X^2/2^shift).
Actual Thumb bytes are separately checked against these integer identities.

Let r=|x|, rho=2^-11, L=2^(68-e), M the exact 53-bit significand, and
C=L(exp(sigma*r)-1-sigma*r), where sigma is the sign of the input.
The implementation keeps M exactly and evaluates the positive nonlinear
correction in Q16 input-ulp units. Its x64 is exactly floor(r*2^64).
Nearest Q48 coefficients, the high-product bound and truncating x64 give a
strict Horner error below4 Q48 units, independently recomputed in proof.py.
Every coefficient is positive and below2^48; x64 and Z are below2^58, and the
tail is below2^35. Thus the stated integer-kernel domains hold at every call.

Z=floor(floor(M/32)^2/2^(26-e)). Dropping five significand bits contributes
less than extra+1 correction units, using M^2-(32 floor(M/32))^2<2^59.
The additional floor-square, half-square, middle-product and Taylor errors
sum to strictly less than27. The Horner contribution is below4(h+1), where
h=floor(Z/2^48). The fifth term is included in Horner at e=-12; at -13/-14,
all32 coarse significand intervals are checked with exact rational endpoints.
For smaller binades the omitted fifth term is bounded by69,5,1 units.
Consequently |C_approx-C|<4h+32+extra+fifth_error, exactly the source guard.
The greatest possible source E is5148, strictly below8192.

The coarse /15 is exact across its full reachable u<=242294 domain, not merely
the sampled values: u=65536h+l implies u/15=4369h+(h+l)/15. Here h<=3,
v=h+l<=65538. floor(v*4369/65536) underestimates floor(v/15) by at most one;
the residual>=15 correction repairs it. All intermediate products fit uint32.

The source constructs N=M*2^16 +/- C_approx exactly as a96-bit integer.
Its output grid U=2^(16-e-negative) covers shifts27..48. The three packing
branches implement the same full-width quotient and modular veto
((N+U/2+E) mod U)<=2E. For shifts below32, reduction modulo a power dividing
2^32 preserves wrapping correctness. At32 the carry is explicit; above32 the
high remainder and low carry reconstruct the full modulus. Since2E<U,
every accepted strict interval (N-E,N+E) lies inside a single rounding cell.
No admitted result can be a tie; integer half-up then gives binary64 RNE.
Declined cases retain the exact parent's refinement. Negative-output spacing
is half the positive-output spacing around one, as represented by the sign
term in the shift. Observed stack peaks and instruction counts are separate
measurements and do not establish universal physical bounds.

The unchanged shared77 product's R12 output remains outside scalar C ABI.
The fresh private linked ELF guard must close its actual16-byte Flash veneer,
producer, zero-byte marker, two post-call stores and88-instruction live range.
That private result cannot qualify a future integrated ELF: integration must
install/adapt and rerun the guard on fresh actual disassembly and compiler
flags. This review gives no integrated, hardware, whole507, main or release GO.

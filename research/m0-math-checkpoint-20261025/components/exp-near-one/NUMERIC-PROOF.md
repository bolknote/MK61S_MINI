Private RP2040 exp near one: source-bound RNE enclosure

The unchanged public entry admits this helper only for -32<=e<=-12,
where |x|=M*2^(e-52), 2^52<=M<2^53. The exact linear M is retained.
Everything outside this interval, including IEEE entry policy and the
existing tiny helper, stays with the accepted directed-product parent.
The source and linked object are bound in certificate.json/build.json.

Let r=|x|, rho=2^-11, K=2^48, L=2^(68-e), and sigma=+1/-1 for
positive/negative input. The positive nonlinear correction is

    C = L*(exp(sigma*r)-1-sigma*r).

The output increment from one, in these Q16 input-ulp units, is
M*2^16+C for positive input, or M*2^16-C for negative input.

Integer kernels

The two product kernels take a<2^48,b<2^58. Split each into base-2^16
digits. The high64 kernel retains exactly the six products with i+j>=3
and rounds retained/2^64 half upwards. The omitted integer is strictly
less than 3*2^64+2^49, hence its absolute real error is strictly below
7/2+2^-15. The bit48 kernel retains nine products with i+j>=2 and floors
retained/2^48; its directed error is in (-3,0]. There is no overflow at
the initial column4 addition: a1*b3<2^26 and the preceding accumulator
is below2^18. All remaining carries are explicit ADCS.

The six-MULS square kernel takes X<2^48,38<=shift<=58 and returns
floor(X^2/2^shift) exactly. It constructs floor(X^2/2^32) using
a0^2,a0*a1,a1^2,a0*a2,a1*a2,a2^2. Each doubled cross term includes its
high carry. The final right shift is6..26, with no C shift ambiguity.
The literal units check exact values, active PCs, R4-R11, SP, stack writes
and all16 incoming NZCV variants. They execute the actual public bytes.

Polynomial

u=floor(r*2^64)/2^64 differs from r by less than2^-64. Horner evaluation
of H_sigma(r)=r/6+sigma*r^2/24+r^3/120 uses nearest Q48 constants and the
high64 product. With eta=7/2+2^-15 the absolute Q48 error is bounded by

    eta+rho*(1/2+eta+rho*(1/2+eta+rho/2))
       +(1/6+rho/12+rho^2/40)/65536 <4.

All intermediate coefficients remain positive; they are respectively
below2^44,2^46, and2^35. This proves every assembly operand contract.
The shorter two-stage Horner evaluation has a smaller error bound.

Define Z=floor(floor(M/32)^2/2^(26-e)). This approximates L*r^2 and
is strictly below2^58. The extra square error from dropping five M bits
contributes less than extra+1 to C, where extra=2^(e+22) for e>=-22,
and zero otherwise. Indeed M^2-(32*floor(M/32))^2<2^59 and
(1/2+rho/6+rho^2/24+rho^3/120)*2^(e+23)<extra+1.

For e=-12 the third Horner stage includes the fifth exponential term.
For e=-13/-14 the fifth term is added separately. With c=floor(M/2^47),
32<=c<=63, its approximation is floor(c^5/(15*2^(s+8))),s=-4e-48.
Its interval error is strictly less than floor(21174/2^s)+2 because
(64^5-63^5)/3840<21174. The exact division uses
65536=15*4369+1; its low reciprocal can be short by at most one, corrected
by a residual comparison. All possible intermediates are also exhausted
on the host, separately from ARM execution counts. For e<=-15 the
omitted fifth term is below69,5,1 Q16 units for e=-15,-16,<=-17.

The sixth and later exponential terms contribute at most

    2^14/(720*(1-rho/7)).

Together, half-square rounding, bit48 product error, fractional square
loss and this tail contribute less than

    4+rho/6+rho^2/24+rho^3/120+2^14/(720*(1-rho/7)) <27.

Writing h=floor(Z/2^48), the Horner product error is less than4*(h+1).
Adding the extra truncated-square and fifth-term bounds therefore gives
the strict source guard

    |C_approx-C| < E = 4*h+32+extra+fifth_error.

All products, additions and error bounds fit their source types. E<8192.
No unsigned subtraction can underflow within the coefficient/correction
evaluation. The source explicitly splits variable shifts into32-bit
ranges, with separate zero and32 cases. No compiler archive is linked.

Final rounding

The output grid in Q16 input ulps is U=2^(16-e-negative),27..48 bits.
The code constructs the exact96-bit integer N=M*2^16+sigma*C_approx,
then adds U/2. It declines exactly when

    ((N+U/2+E) mod U)<=2*E.

Otherwise the complete strict interval (N-E,N+E) lies in one rounding
cell. Accepted results cannot be exact ties, so floor((N+U/2)/U) is the
binary64 RNE displacement. Addition/subtraction from the bit pattern of
one is valid because positive results lie in[1,2), negative-input results
in(1/2,1), with the corresponding two different grid spacings. The literal
pack unit covers all21 binades, both signs, every packing branch, carry
edges, and admission boundaries against independent unbounded integers.
Declined inputs use unchanged exp_refine(x,0), including its exact fallback.

Integration limits

The shared77-instruction product is byte-identical to the accepted parent.
Its extra R12 result remains a private producer/consumer contract. The
builder automatically runs the guard against fresh actual disassembly,
the real16-byte tail veneer, the producer-to-marker window and the
marker-to-consumer live range. Integration must install/adapt and rerun
this guard for its actual linked release object. This packet grants no
canonical, integration, hardware, physical-cycle or release approval.

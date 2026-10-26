Exact binary64 exp rounding through logarithmic midpoint thresholds.

The public caller retains its accepted treatment of all |x|<=2^-54,
large inputs, infinities and NaNs. Only the RP2040 selection changes.
The expanded helper domain is 2^-54<|x|<2^-32. Write |x|=M*v,
v=2^(e-52), 2^52<=M<2^53, -54<=e<=-33. The output spacing is
h=2^-52 for positive x and h=2^-53 for negative x. Let N=negative,
s=-e-N in [32,54], and r=floor(M/2^s). The linear midpoint occurs
at M0=z*2^(s-1), z=2*r+1, with output displacement u=z*2^(-53-N).
Its exact input threshold is log(1+u) or log(1-u). These logarithms
are analytical tools in the proof; no runtime logarithm is called.

Define the positive correction D, in input ulps, by
 D+=(u-log(1+u))/v,  D-=(-log(1-u)-u)/v.
For every relevant midpoint 0<u<=2^-32, 0<D<2^20/(1-2^-32)<1048577.
Also 1048577<2^(s-1). Thus only the affected side within1048576input
ulps of the one linear midpoint can change rounding. Exact linear
midpoints need no products: D>0 makes positive x choose the upper
result and negative x choose the smaller magnitude displacement.

Put q=e+55+2N, A=z^2/2^q=K+t/2^q. The square has at most44bits,
q is1..24 and t is an odd integer, hence nonzero. On the same fraction
grid as t, the cubic magnitude is B=z^3/(3*2^(52+N)). The remaining
positive-log series E+ satisfies 0<E+<z^4/2^(107+2N); the negative-log
series E- satisfies 0<E-<z^4/(2^(107+2N)*(1-u)). Consequently
 D+=K+(t-B+E+)/2^q,  D-=K+(t+B+E-)/2^q.

Every possible positive midpoint has odd z<2^21, and every negative
midpoint has odd z<2^22. proof.py checks all3145728such odd classes
using integer inequalities, independently of any MPFR approximation.
Let L=3*2^(52+N), R=z^3 mod L, so0<R<L. The checks are exactly
 positive: R*2^(55+N)>3*z^4;
 negative: (L-R)*2^(55+N)*(2^(53+N)-z)>3*z^4*2^(53+N).
They show E+<fraction(B) and E-<1-fraction(B), respectively. Therefore
floor(B-E+)=floor(B+E-)=b=floor(B). There is strict separation from
every relevant integer, so neither corrected D is integral. Since b
is smaller than2^q (B/2^q<=2^-11/3<1), the complete exact formulas are
 floor(D+)=K-(t<=b),  floor(D-)=K+(t+b>=2^q).
The source uses precisely these formulas, with unsigned overflow
excluded by the positive D and bounded K. The inequalities cover the
whole finite odd class range, rather than a sampled real interval.

The runtime square and cube use the accepted exact wide32 primitive.
For square=L0+H0*2^32, cubeLow=L0*z and cubeHigh=H0*z+(cubeLow>>32).
The latter fits34bits; cube fits66bits. Then
 floor(z^3/2^(52+N))=(cubeHigh>>20)>>N <65536,
 b=floor(floor(z^3/2^(52+N))/3).
The multiplication by43691 followed by>>17 gives exact division by3
for all65536possible inputs, checked mechanically. All remaining
shifts are32-bit with counts1..31 or fixed64-bit shifts; no compiler
runtime division or variable64-bit-shift helper is needed. For z<65536,
z^2 fits32bits and b=0, so one uint32MUL gives floor(D) directly.

For s>32, the source splits M into its21-bit high word and32-bit low
word. It computes r and the high remainder exactly. On the positive
side a close lower approach has highTail+1==half and d=0-low32; on
the negative side a close upper approach has highTail==half and
d=low32. For s=32 (only the negative e=-33 class) r=high32, the half
bit is0x80000000 in low32, and unsigned subtraction rejects the
unaffected side by wrapping well above1048576. These tests cover
every relevant guarded distance without an undefined shift by32.

For positive x=M0-d, exp(x) lies above its output midpoint iff d<D+,
equivalently d<=floor(D+). For negative |x|=M0+d, the larger magnitude
displacement is chosen iff d>D-, equivalently d>floor(D-). These are
the exact source predicates. The returned raw word is1's binary64
encoding plus or minus r+up, on the constant normal output grid.
Inputs outside the guards cannot cross a midpoint because D<1048577.
This establishes returned-value RNE on the full selected tiny domain.
IEEE exception-status flags remain outside the existing contract.

The exhaustive odd-class proof is not3million emulated calls. All
earlier qualified163675inputs are preserved and freshly checked with
the new public ARM exp body; new sampled midpoint transitions, guard
edges, dense domain boundaries and raw controls get fresh ARM/MPFR
checks too. Sampling and inherited measurements are recorded separately.
Every incorrect Qfplib value and cost remains in the raw acquisition.
Independent review, integration and physical-cycle acceptance are open.

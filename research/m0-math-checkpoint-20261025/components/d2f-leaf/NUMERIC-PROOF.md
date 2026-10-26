This is the author's source proof of binary64 to binary32 returned-value
RNE, including gradual underflow, both zero signs, overflow, infinities
and quieting/payload truncation of NaNs. It is not independent acceptance,
physical-cycle acceptance or integration of the complete math library.

Let E be the binary64 exponent field, F its20 high fraction bits and L
the low32 bits; H=(E<<20)+F is the magnitude of the input's high word.
Input sign remains in the original R1 until final packing. Every finite
normal binary64 mantissa is m=2^52+(F<<32)+L.

The first LSL by2 drops sign and puts E's bit10 in carry. Lower and upper
exponent halves have separate range tests; no complete exponent extraction
is needed in the normal, zero, overflow or nonfinite paths.

For E<1024, SUB L-1 sets C exactly when L!=0. The following literal load
preserves C; SBC computes g=4*(H-(873<<20))-[L==0]. Borrow occurs exactly
for inputs at or below2^-150, the midpoint between zero and minimum
binary32 subnormal. The exact midpoint rounds to even zero. Hence a
signed-zero return here is exact, including every binary64 subnormal.

After this test, H's unit stride becomes4 while borrow is0 or1.
Consequently g>=(24<<22)-1 iff E>=897, regardless of F and L. The
remaining lower-half inputs have E873..896 and go to the subnormal path.
For E>=1024, shifted R2 is4*(((E-1024)<<20)+F); comparison against
127<<22 distinguishes normal binary32 E<=1150 from overflow/nonfinite.
The interval checks in proof.json certify every exponent and borrow state.

For E897..1150, binary32's exponent is E-896. Its retained significand
uses F and L>>29; discarded bits are L modulo2^29. LSR29 yields guard;
L<<4 is zero iff the28 lower sticky bits are zero. Thus the ordinary
branches implement exactly round-to-nearest, ties-to-even. A retained
low word can become8, correctly carrying into the high fraction/exponent.

Packing uses the original high word shifted3 plus a signed2^30 bias.
For E897..1023, arithmetic R1>>30 is0 or-2, so adding1 gives+1 or-1.
For E1024..1150, arithmetic R1>>30 is already+1 or-1. Multiplication by
2^30 gives the required sign and exponent correction. All additions are
modulo2^32. The resulting positive magnitude is
`((E-896)<<23)+(F<<3)+rounded(L/2^29)`. It ranges through signed infinity
when the maximum finite binary32 boundary rounds upward.

On an exact midpoint, parity of the retained significand is L's bit29.
Adding high_word<<3 does not change parity. The tie block therefore shifts
the partially packed value by1 to set C, and its final ADC adds both the
signed exponent bias and the parity increment. This is the same RNE rule
without a separate increment instruction. Packing/tie algebra is checked
for every normal exponent, both signs, carry head classes and retained
low value0..8; guard/sticky/parity classes are enumerated separately.

Every finite E>=1151 overflows to signed infinity. Adding2^22 to the
upper-half shifted word carries exactly when E==2047. The residual word
then equals F<<2, at most22 bits. OR with L tests whether the entire
fraction is zero while leaving L's top3 retained payload bits unchanged.
If zero, R1>>23 followed by LSL23 gives signed binary32 infinity. For NaN,
the payload is (F<<3)|(L>>29), sign/infinity bits come from R1>>23, and
the existing2^22 literal forces the quiet bit. This exactly preserves the
old narrow() return-bit policy, including low-payload signalling NaNs.

For E873..896, the exact binary32 subnormal integer is RNE(m/2^n), where
n=926-E is30..53. The shortcut g==(24<<22)-4 and L>>29==7 recognizes
exactly `m>=2^53-2^29`; its RNE result is minimum normal, including its
even tie. Sign and exponent of that result follow directly from
`((R1>>23)-111)<<23`.

Otherwise form T=floor(m/2^21) in32 bits and retain the exact low21-bit
sticky information. Put s=n-21=905-E, so9<=s<=32. The quotient is T>>s;
guard is T's bit(s-1). For guard1, shifting T left(33-s) removes guard
and all retained bits while retaining precisely the lower sticky bits.
OR with the original low21 bits decides whether the tail is an exact tie.
On a tie, the quotient's parity determines the increment. ARMv6-M's
register LSR by32 returns zero and T's bit31 as carry, which also handles
the smallest nonzero binary32 midpoint correctly. The rounded integer
may become2^23; OR of the preserved sign still gives minimum normal.

The complete pinned Qfplib-correct input partition follows directly from
qfp_double2float in qfplib-linked.S:

- E<873, or E873 with zero fraction: signed zero.
- E896 with fraction>=2^52-2^29: minimum normal.
- E897..1150: its ordinary RNE normal conversion.
- E1151..2046: finite overflow to infinity.
- E2047 with zero fraction: infinity.

Other E873..896 inputs are flushed incorrectly, and every NaN becomes
infinity in Qfplib. These incorrect outputs and their instruction costs
remain in the raw qualification; they are not included as valid speed
references. The source partition predicts the independently compared
reference-correct flag of every freshly executed input; no nominal-domain
filter is used.

The code contains no loop or indirect data-dependent call. For every
correct-reference class, the branch predicates reduce to the exponent
half, guard/sticky and parity cases listed below. Thus the instruction
counts do not depend on any unenumerated mantissa bit. The actual Cortex-M0
execution counts of every qualification row match this complete path table:

| Class | Candidate | Qfplib |
|---|---:|---:|
| Zero, including exact minimum-subnormal half |9|9|
| Subnormal range rounding to minimum normal |19|20|
| Lower normal, no increment |19|20|
| Lower normal, guard+sticky round up |22|22|
| Lower normal, tie even / odd |22|23 /24|
| Upper normal, no increment |14|20|
| Upper normal, guard+sticky round up |17|22|
| Upper normal, tie even / odd |17|23 /24|
| Finite overflow / infinity |13|13|

The function uses R0-R3/R12 only, never changes SP, reads no SIO/ROM and
uses no global RAM, external function, table or libgcc. Its literals are
part of its256-byte section. Full intended ASM emits exactly that tested
section; all other RP sections and relocations match the accepted parent.
Generic M0 and M4 selected ASM is byte/relocation-identical. Compared with
the old parent, lower normal ordinary paths increase by1 instruction;
all110782 observed such state rows are retained and remain no slower than
correct Qfplib. A full repaired-platform relink and hardware cycles remain
separate acceptance steps.

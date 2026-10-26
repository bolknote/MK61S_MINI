Author's whole-binary32-domain widening proof and complete instruction
partition against correct Qfplib. Independent review, integrated firmware
and physical-cycle acceptance remain separate steps.

Write the binary32 input as sign s, exponent E and23-bit fraction F.
Every finite binary32 value, including subnormals, is exactly representable
in binary64; no discarded bit or rounding approximation is permitted here.

LSL R2,R0,1 removes sign, sets Z iff the entire magnitude is zero and puts
the original sign in C. The zero branch preserves C. Thus the next BCS
selects a negative normal/special branch without another sign operation.
For either signed zero, R0 is only its sign bit; copying it into R1 and
clearing R0 returns exactly the binary64 sign/high/low words.

On the positive path, LSR23 produces E; SUB1 gives E-1. On the negative
path, ASR23 produces E-256; ADD255 gives the same E-1. Unsigned compare
against253 accepts exactly E1..254. On a positive normal input,
`high=(R0>>3)+0x38000000`. On a negative normal input,
`high=ASR(R0,3)+0xc8000000` modulo2^32. ASR extends sign into the top
three bits; the second bias produces the required bit31 sign and the same
exponent increase896. In both cases low_word=R0<<29. Together these are
exactly `sign | ((E+896)<<52) | (F<<29)`. All23 fraction bits survive.

Special paths shift R0 by9 into R2, removing sign and exponent. If R2 is
zero, input zero has already been handled, so the input is infinity. The
known-sign infinity constant and zero low word are exact.

For nonzero R2, the preserved E-1 register is either-1 (subnormal) or254
(NaN). NaN packing uses sign, R2>>12=F>>3, infinity+quiet constant
0x7ff80000 and low_word=R0<<29. This preserves every original fraction
bit and sign and forces the quiet bit. It matches the old extend() raw
return policy even for low-payload signalling NaNs.

For subnormal F!=0, let k=bit_length(F), in1..23. Initially R2=F<<9.
The16/8/4/2/1 conditional shifts put the leading bit at31. Each branch
depends only on whether the current leading bit lies below its boundary;
no significant bit is shifted off. Thus the total shift is23-k, the
normalized integer is N=F<<(32-k), and the decremented exponent register
is895-(23-k)=k+872. Adding N>>11 includes its hidden1 and increments
the encoded exponent to k+873. The low word N<<21 preserves its remainder.
The resulting53-bit significand is F<<(53-k), at exponent k+873, giving
exactly F*2^-149. Both signs are preserved. The23 possible shift paths and
packing identities are certified in proof.json; the source argument covers
every mantissa of each width, beyond the finite checks.

The pinned qfp_float2double implementation returns the exact result for
every normal input, both signed zeros and infinities. It flushes every
nonzero subnormal to zero and turns NaNs into infinity. The qualification
retains those incorrect outputs and their counts. The following complete
correct-reference path table follows directly from the branch predicates;
normal sign selection changes the block, but not its instruction count:

| Correct-reference class | New code | Qfplib |
|---|---:|---:|
| Either signed zero |5|8|
| Any normal input, either sign |12|13|
| Either infinity |12|12|

The actual ARM execution of every qualified input/state matches the source
correctness partition and these counts. The incorrect-reference NaN and
subnormal rows are preserved separately. No nominal-domain filter is used.

The function uses only R0-R3, never changes SP, performs no global or SIO
write and has no ROM/table/libgcc/external call. It is172 bytes including
literals. The full intended ASM emits exactly the tested body. Only the RP
f2d section changes: all d2f256-byte leaf bytes, other RP sections and
semantic relocations remain exact. Generic M0 and M4 selected ASM remains
byte/relocation-identical; CPP is unchanged. All observed candidate calls
are strictly faster than the old parent, with no retained cost increase.

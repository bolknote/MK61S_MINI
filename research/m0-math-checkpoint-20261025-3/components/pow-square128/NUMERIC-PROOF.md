# Exact replacement of the existing 128-bit square transform

The object is `{uint64 high, low; int32 exponent; uint32 radius}` (24 bytes).
All statements below describe the actual old machine-code transform, including
its wrap at 32, 64 and 128 bits; they do not infer a different radius from an
older C++ experiment. In particular the old nonzero-low radius increment is 16.

Let H and L denote its two 64-bit fields. Let C be the unchanged old 94-byte
`pow_integer128_approx_high64(L,H)` when L is nonzero, and zero otherwise.
The old and new kernels both form P = H² + 2C modulo 2^128. They form
E = 2*radius + (L != 0 ? 16 : bool(radius)) modulo 2^32 and double the exponent.
If bit127(P) is set they increment the doubled exponent; otherwise they shift
P and E left once. They store the same complete four fields. No interval bound,
domain gate, approximation table, fallback or final RNE packing changes.

For the new exact 32-bit square use radix B=2^16 and x=a+bB, 0<=a,b<B.
Then x²=a²+2abB+b²B². The low word is a²+(ab<<17) modulo 2^32; the high word
is b²+(ab>>15)+the carry from that low-word addition. Each of a², ab, b² fits
32 bits. `LSLS`/`LSRS`, `ADDS` then `ADCS` implement precisely this identity.

For the 32-by-32 cross product, write x=a+bB, y=c+dB. Set p=ac,
t=bc+(p>>16), v=ad+(t mod B). Each intermediate is at most B²-B,
so no unsigned32 addition overflows. The low word is (p mod B)+(v mod B)B;
the high word is bd+(t>>16)+(v>>16). This is the standard radix expansion
of xy, with all carries explicitly included.

For H=u+v*2^32, its exact square is u²+2uv*2^32+v²*2^64. The two square32
macros compute u² and v², and the cross schedule computes uv. Two carry chains
add uv at bit32 into the four-word result. The same unchanged helper C is
then added twice through all four words, reproducing the old modular transform.

For L=0, `CMP radius,#1` leaves carry equal to bool(radius), including values
with the sign bit set. `ADCS radius,radius` therefore computes the exact old
unsigned radius rule. For L!=0 the explicit +16 rule is unchanged. The four
word left shift uses `LSLS` followed by three `ADCS word,word`; the propagated
carry is precisely the preceding word's old top bit. The sign test of the top
word is exactly the old bit127 test. These identities hold for arbitrary input
field bit patterns, not just the normalized values sampled by public `pow`.

The unit images contain only the actual linked kernel and actual 94-byte helper,
without firmware, ROM or arithmetic mocks. All 24 output bytes, ordinary PCS,
SP/PC and write bounds are checked against the old kernel and the integer model
on 18,210 tests / 36,420 actual ARM calls, including all16 NZCV values and noisy
volatile registers. Static traversal of the linked code has the same four cost
classes as those actual runs: 129→94, 195→154, 182→149 and 116→89 instructions.
Kernel frames shrink 48→40 bytes; including the unchanged helper, 68→60 bytes.

The two retained assembly callers treat the function as void, overwrite R0
before use and set their own flags. R4–R11, SP and the return PC remain subject
to ordinary PCS. There is no additional private return value in R12 here.
The separate table-product R12 contract is untouched and still requires the
previously specified guards in any future merged release image.

The old 310-byte slot is retained at the same address, with 78 bytes of unused
padding after the 232-byte new function. The full RP2040 source objects differ
only in that section and its own relocations/symbol size. Generic M0 and M4
soft/hard selected assembly objects compare equal. The isolated replacement
does not relink or reorder other resident code or GNU veneers.

Public validation freshly executes the complete inherited 116,468-pair union in
both SIO states and requires exact old raw return bits and exact instruction
delta equal to the sum of actual kernel-call deltas. Fresh independent controls
also execute parent, layout control, candidate and all three Qfplib compositions
and validate actual binary64 inputs with directed MPFR. Incorrect Qfplib outputs
and their costs are retained. These checks preserve the existing accuracy;
general `pow` totality and overall library speed remain separate unfinished work.

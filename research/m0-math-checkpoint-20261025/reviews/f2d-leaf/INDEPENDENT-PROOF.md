# Independent RP f2d component proof and limits

This review accepts the exact private 172-byte `__aeabi_f2d` leaf for its
returned bits, public AAPCS entry and Cortex-M0 instruction paths. It does
not accept a complete firmware, hardware cycles or the whole math library.
No exception-flag behavior is claimed. Original507 remains 418/507.

## Exhaustive returned-value argument

For raw32 input X, write sign S, exponent E and fraction F. Every finite
binary32 value is exactly representable by binary64. The independent
oracle decodes an integer N times 2^power and places its leading bit and
remaining bits directly into binary64. It calls neither the author's
normalizer nor host float32 widening. Even the smallest binary32 subnormal
is a normal binary64 value, so no output underflow, overflow or rounding
decision exists for finite inputs.

The actual LSL by one sets Z precisely for either zero, and C to input sign.
BEQ preserves these flags. The zero path copies X (only its sign bit) into
the result high word and clears the low word. For nonzero inputs, BCS then
selects the sign path without a new flag-changing instruction.

The positive path computes (X>>23)-1=E-1. The negative path uses signed
ASR23 followed by ADD255, also E-1. Unsigned comparison with 253 accepts
exactly E1..254. Positive high-word packing is (X>>3)+0x38000000.
Negative packing is ASR(X,3)+0xc8000000 modulo 2^32. Both give
S32|((E+896)<<20)|(F>>3). The low word X<<29 retains the other three
fraction bits. This is the exact binary64 representation
S64|((E+896)<<52)|(F<<29). The packing identities are affine in F>>3;
their coefficients and sign/exponent biases hold for every high fraction,
with all eight low-bit cases independently checked. Carry endpoints do
not create an overlapping or dropped bit.

In special paths, X<<9 removes sign and exponent, leaving F<<9. A zero
fraction must be infinity because zero has already returned. Known sign
constants 0x7ff00000/0xfff00000 plus zero low word return the exact infinity.
For nonzero fractions, the preserved E-1 is -1 for subnormals and 254 for
NaNs. NaN packing gives S64|0x7ff0000000000000|(F<<29)|(1<<51). Every
payload bit and sign is preserved and quiet is forced, matching the
accepted parent's `extend` policy for quiet and signalling NaNs, including
the lowest possible signalling payload. MPFR category checks do not stand
in for this exact raw policy.

For subnormal F!=0, put k=bit_length(F), 1<=k<=23. Initially V=F<<9 has
leading-bit position k+8. The conditional 16/8/4/2/1 shifts normalize its
leading bit to position31. Each condition compares a fixed shift of V with
zero or tests its top bit, so it depends only on k, not on the lower bits.
The complete width interval [2^(k-1),2^k-1] is propagated through each
branch in proof.py. Its two endpoints always choose the same branch; no
chosen shift drops a significant bit, and the resulting interval stays
within 32 bits. This proves the behavior for every mantissa of each width.

The total shift is 23-k, the final V=F<<(32-k), and the decremented bias is
895-(23-k)=k+872. Packing high=S32+(bias<<20)+(V>>11), low=V<<21 modulo2^32
adds V's hidden leading bit to the bias, yielding encoded exponent k+873.
The remaining significand is F<<(53-k), with every original bit retained.
Its exact value is F*2^-149 as required. The proof covers all 23 width
intervals and both signs. Own actual ARM runs exercise every one of their
46 sign-specific paths, with lower-bit controls as well as endpoints.

These paths cover every raw32 input. The disjoint class cardinalities in
proof.json sum exactly to 2^32: two zeros, all normal inputs, two infinities,
all NaNs and all nonzero subnormals. This is a reviewed source proof with
mechanical integer certificates and actual-code correspondence; it is not
an SMT/formal-verifier theorem claim.

## Complete ISA comparison

The pinned Qfplib source and actual linked qfp_float2double are exact on all
normal inputs, both zeros and both infinities. E0 returns signed zero for
every fraction, so nonzero subnormals are incorrect. E255 returns infinity
for every fraction, so every NaN is incorrect. There are no additional
correct-reference classes or mantissa-dependent predicates.

| Correct reference class | Candidate | Qfplib |
|---|---:|---:|
| Signed zero |5|8|
| Any normal, either sign |12|13|
| Either infinity |12|12|

The function's actual decoded paths contain these exact instruction counts,
including return. Thus all correct-Qfplib input classes are no slower in
instruction count. This does not claim physical-cycle dominance. All raw
incorrect-reference inputs remain in the evidence: NaN costs19 versus12;
nonzero subnormal width k costs30+2*popcount(23-k), namely30..38, versus8
for Qfplib's incorrect flush. In both the sealed author's corpus and own
bounded corpus, every candidate state is strictly faster than the native
parent. That native comparison is an observed claim, not an additional
all-input physical-time theorem.

The normalizer has no loop or indirect call. Width predicates exhaust the
data-dependent subnormal paths. Actual traces retain all 53 leaf paths:
46 sign/width subnormal paths, two normal, two infinity, two NaN and one
zero path. Qfplib has three actual paths. All observed costs match the
independent source-derived model.

## Exact source and execution binding

The complete 61-file frozen packet and 424 lineage pins were verified.
Its parent-review-at-seal record remains pending/false. The later accepted
d2f receipt 500e2c5b and all 27 pins (receipt plus 26 references) were
verified additively; no historical acceptance state was rewritten.

Current control RP allocations and semantic relocations exactly match the
accepted d2f parent object. Actual resident parent f2d bytes match except
its resolved BL; independent Thumb BL decoding targets the real old C
`extend` helper. Both sides use their public ABI entries directly. The new
entry is 0x10164001; no interposition veneer is inserted.

The standalone source, new include, intended-source object, standalone ELF
and intended-source ELF emit the exact same172-byte body. Eleven own-output
rebuilds reproduce the selected objects/ELFs byte for byte. Only RP f2d
changes:34→172 bytes, +138 selected ASM. Accepted d2f256B and all other RP
allocated bytes/semantic relocations are identical. Generic M0 selected
ASM is identical; M4 selected ASM is empty and identical. No complete M4
firmware was built. No CPP source is changed by this component's patch.
Whole firmware size and possible old C-helper GC savings remain unmeasured.

Own instruction hooks constrain every new leaf instruction to its actual
Thumb16 body, excluding alignment padding and literals; SP stays fixed
at every instruction. All data reads are the six in-section literals.
There are no writes, stack accesses, SIO, ROM, external functions, mocks,
tables or global RAM accesses. Both SIO states preserve all28 bytes.
Only the parent runs real pinned ROM initializers, excluded from qualified
calls. The standalone candidate does not load firmware or ROM.

## Evidence accounting

Own fresh evidence is3366 inputs,26928 ARM calls across four machines and
two SIO states, and3366 direct MPFR conversions. MPFR finite inputs are
constructed with set_ui/mul_2si/neg from their integer lattice values,
avoiding host float32 widening; all are exact at128-bit precision. NaNs
enter MPFR for category checks, while payload/sign/quiet are verified
against the independent bit oracle and raw native-parent outputs.

The author's132959 oracle evaluations comprise124373 actual directed MPFR
input conversions and8586 pre-MPFR NaN category shortcuts. The additive
postseal accounting is correct; frozen result/HANDOFF MPFR labels must be
read with that precision. Author-qualified797754 ARM calls and265918
states are inherited evidence for this independent review. All sealed rows
were reconciled against the own exact decoder and full path model without
re-executing the broad corpus. All9122 old raw inputs are present with
identical old-parent bits. The256 old samples reproduce, with249 correct
references and their single deficit closed. Four expanded raw deficits,
both zeros and both infinities, are also closed and executed freshly here.
The separate41490 smoke calls are excluded from qualified totals.

Reproduce in this directory using the configured Python venv, running
binding.py, proof.py and arm.py. They write only this independent directory.
Unicorn JIT requires host execution outside the restricted sandbox. No
script accesses devices, USB, Flash, leases, canonical sources, Git or
release state. Full integrated math, hardware/physical cycles and release
remain separate acceptance steps.

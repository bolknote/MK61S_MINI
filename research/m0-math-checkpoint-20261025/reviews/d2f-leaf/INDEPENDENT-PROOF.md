# Independent RP d2f component reasoning

This review applies to the exact 256-byte `__aeabi_d2f` body in the sealed
candidate, its complete-source object, and the independently rebuilt ELFs.
It is a returned-value/AAPCS and instruction-path review on HOST Cortex-M0
execution. It does not certify hardware cycles, a linked firmware, or the
complete private math library. The unchanged original507 ledger stays 418.

## Complete returned-value partition

Write the input as sign S, binary64 exponent field E, 52-bit fraction F,
high word H and low word L. For E>0, its positive value is
M*2^(E-1075), with M=2^52+F. `model.exact` independently rounds this integer
times a power of two directly onto binary32's normal or subnormal lattice.
It does not call the author's `integer_cast` or use its normalization code.

The actual initial LSL by 2 discards sign, moves exponent bit10 into C,
and separates E<1024 from E>=1024. In the lower half, SUBS L-1 followed
by a flag-preserving LDR makes SBC compute
g=4*(magnitude_high-(873<<20))-[L==0]. The unsigned borrow branch is taken
precisely for magnitudes at or below 2^-150, including its exact tie.
Every such value correctly returns its original zero sign. This includes
all binary64 subnormals. Monotonic high-fraction intervals, checked at both
endpoints for every exponent and borrow state, prove that the next threshold
(24<<22)-1 selects exactly E>=897. The remaining range is E873..896.

In the upper half, the shifted value equals
4*(((E-1024)<<20)+high_fraction), so comparison with 127<<22 selects
exactly E>=1151. All finite inputs in that class overflow to signed infinity.
Adding 2^22 carries if and only if E==2047. Its residue is high_fraction<<2;
OR with L distinguishes zero fraction from NaN without altering L's top
three payload bits. Infinity packing is exact. NaN packing yields
S|0x7f800000|(F>>29)|0x00400000. Thus quiet/signalling payloads and signs
match the accepted parent's `narrow` policy exactly, including payloads
whose retained fraction would otherwise be zero. MPFR NaN category checks
are separate from this exact payload policy.

For E897..1150, the lattice needs the top 24 significand bits and discards
L modulo 2^29. LSR29 leaves the retained low three bits and guard bit28 in
C. LSL4 is zero exactly when the lower 28 sticky bits are zero. The branches
therefore implement nearest-even: no guard means truncate, guard+sticky
increments, and an exact half increments only odd retained values. The tie
ADC occurs after the high word has been added; that addition is a multiple
of eight and cannot change parity.

Packing uses signed(H)>>30, plus one only for the lower exponent half.
That factor is +1 for positive and -1 for negative inputs in both halves.
Consequently modular 32-bit addition gives
S|((E-896)<<23)+(high_fraction<<3)+rounded(L/2^29).
The expression is affine in high_fraction. Its coefficient and exponent
bias identity establish every high fraction, while retained values 0..8
cover fraction carries. A carry at E1150 yields signed infinity, including
the even tie at the finite-overflow boundary.

For E873..896, binary32's subnormal lattice requires RNE(M/2^n),
n=926-E, so 30<=n<=53. The fast minimum-normal condition is exactly
E896 and M>=2^53-2^29. Its lowest value is the half between maximum
subnormal and minimum normal; the even minimum normal is correct.
The subtraction of one when L==0 does not lose any member of this class,
because every member has L>=7*2^29 and hence L!=0. Its sign packing gives
S|0x00800000.

The full subnormal path builds T=floor(M/2^21) and separately represents
the low21 bits by L<<11. Set s=n-21=905-E, 9<=s<=32. The actual register
LSR returns Q=T>>s and G=T.bit(s-1). The zero-guard branch rounds down.
For guard one, T<<(33-s) modulo 2^32 retains exactly bits below the guard;
OR with L<<11 is zero if and only if the complete remainder below guard
is zero. A nonzero remainder increments Q; an exact half adds Q's parity.
ARMv6-M's register LSR by 32 specifically returns Q=0 and C=T.bit31,
so the smallest nonzero subnormal case has no undefined host shift.
The rounded Q may reach 2^23, which packs minimum normal correctly.
`proof.py` checks the bit identity across all 24 shifts, guard/parity and
zero/nonzero sticky equivalence classes. The identity is independent of
the values of other bits. Own actual ARM tests include every shift and
actual half cells with adjacent raw64 values.

These branches are exhaustive over all finite numbers, signed zeros,
infinities and NaNs. The source contains no loop, indirect call, external
call or data-dependent memory address.

## Complete valid Qfplib comparison

The pinned source and actual linked `qfp_double2float` first compute E-896.
For negative results it flushes to signed zero. For zero it admits only
the all-one high fraction and L>>29==7 shortcut to minimum normal. For
1..254 it applies the same normal nearest-even rule. For >=255 it returns
infinity, including all NaNs. Therefore its output is correct precisely on:

- E<873, plus E873 with F=0;
- E896 with F>=2^52-2^29;
- every E897..1150 input;
- every finite E1151..2046 input;
- E2047 with F=0.

The remaining subnormal-range inputs and every NaN are incorrect references.
They remain in all raw data and raw cost records. The full disjoint raw64
partition, including these incorrect classes, has exact cardinalities in
`proof.json` that sum to 2^64. No nominal input-domain filter is applied.

Counting actual decoded branch paths gives the following number of Thumb
instructions, including the return. All 12 valid-reference classes are
covered by the own actual ARM runs, with exact path traces retained.

| Correct-reference class | Candidate | Qfplib |
|---|---:|---:|
| Zero, including 2^-150 half |9|9|
| Subnormal range rounding to minimum normal |19|20|
| Lower normal, guard0 |19|20|
| Lower normal, guard1+sticky |22|22|
| Lower normal, exact half even/odd |22|23/24|
| Upper normal, guard0 |14|20|
| Upper normal, guard1+sticky |17|22|
| Upper normal, exact half even/odd |17|23/24|
| Finite overflow or infinity |13|13|

There are no omitted mantissa-dependent predicates on these paths. This
establishes the all-input instruction dominance claim for correct Qfplib
answers. It does not establish physical-cycle dominance. Wrong-reference
NaNs cost 19 versus 13, and full subnormal paths cost 32/35/39/42 versus
9/13/16. These costs are retained explicitly. Against the accepted native
parent, the lower normal paths take one additional instruction; the sealed
corpus has 110782 such states and the own corpus also reproduces them.

## Provenance, execution and count limits

All 60 frozen artifacts, 362 lineage pins, and the accepted rsqrt receipt
with its 22 direct references were reverified. The accepted parent RP
object exactly matches the new control object. The actual resident parent
entry has the same 68-byte body except its resolved BL; independent BL
decoding targets the real old C `narrow` helper. New candidate and intended
source call the public ABI entry directly at 0x10163001. No synthetic
wrapper is inserted on either side of the comparison.

The standalone source, new include, full intended-source object and both
private ELFs emit the same 256-byte leaf, with no relocations or undefined
symbols. Eleven own-output rebuilds reproduce all selected objects/ELFs.
Only the RP `.text.__aeabi_d2f` allocation changes by +188 bytes; all other
RP bytes and semantic relocations match. Generic M0 selected ASM matches;
M4 selected ASM is empty and unchanged. A complete M4 firmware was not built.
The full firmware was not relinked, so old C slowpath GC savings and overall
firmware size remain unmeasured.

Own ARM hooks constrain every leaf instruction to the real Thumb16 body,
check SP at every instruction, and permit only six in-section literal
reads. They observe no writes, stack, SIO, ROM, mocks or firmware calls.
Both divider states preserve all 28 bytes. Parent-only BootROM lookup
initializers execute real pinned ROM and are excluded from qualified calls.

Author broad data are inherited evidence for this independent review:
1391904 fresh-to-author ARM calls and 231984 oracle evaluations. The author's
`DirectMPFR.float` deliberately returns a canonical NaN before entering MPFR;
therefore the latter number includes NaN category shortcuts, which are
itemized separately in `proof.json`. It must not be described as that many
actual MPFR input conversions. The own review uses direct MPFR even for
its NaN category controls, while exact NaN payload/sign/quiet are checked
with the independent integer policy and raw equality against the parent.
The author's separate 11004 smoke calls are not added to qualified totals.

Reproduce the review from this directory with the configured Python venv:
`binding.py`, `proof.py`, and `arm.py`, in that order. They write only this
independent report directory and its own rebuild directory. Unicorn JIT
requires host execution outside the restricted sandbox; no script accesses
USB, hardware, leases, canonical sources, Git or release state.

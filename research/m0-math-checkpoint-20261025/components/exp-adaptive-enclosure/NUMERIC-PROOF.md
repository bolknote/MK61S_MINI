RP2040 normal exp: magnitude-sensitive first-pass enclosure and a cheaper
ABI-equivalent shared rounded product. Independent review pending.

Let A be the accepted512-entry Q62 table's integer value and r the exact
reduced argument. Let D be the Q64 polynomial displacement already used
by the public caller. The accepted complete reduction/polynomial proof
gives |exp(r)-1-D/2^64|<E/2^64, E<275/64 (certificate.json records the
exact previous E, about4.287008). This includes input and split-step
reduction, every polynomial truncation, coefficient error and Taylor tail.
We re-evaluate that rational certificate and both tables' RNE roots.

The rounded product P(A,|D|) has absolute error <=1/2+2^-15 integer
Q62 units. The new product changes only its argument-save prologue and
the base of its stack argument loads. Its entire arithmetic body stays
byte-identical. Thus this same error bound and every previous output
remain valid. All formulae below are selected only when error==4: the
caller has not doubled q for normalization. Endpoints and error6 retain
the accepted fallback/endpoint algorithms unchanged.

If q=A+/-P is the current integer Q62 result, A<2^63 and |D| is below
the unchanged maximum polynomial displacement. certify.py proves
maximum_correction<23*2^48. Hence A<q+23*2^48 and, writing
H=floor(q/2^48), A/2^64<(H+24)/65536. This is an input-sensitive
upper bound, rather than replacing A/2^64 by1/2 for every table row.

Let T94 be the existing correctly rounded Q94 table value, and let
delta32=T94-(A<<32), represented by the row's signed low32bits. Its
true table bias is B=delta32/2^32 plus an uncertainty below2^-33.
All512rows are rechecked by exact512th-power midpoint inequalities.
The true scaled exponential V satisfies
 |V-q-B| < E*A/2^64+C,
 C=(1/2+2^-15)+(h/(2*(1-h)))+2^-33/(1-h), h=1/1400.
The second term is the cross term B*(exp(r)-1), and the last term is
the Q94 uncertainty multiplied by exp(r). The prior reduction proof
certifies |r|<h. All three terms together are <129/256.

The source therefore computes
 top=H+24;
 bound=ceil(275*top/16384)+129,
 so bound/256 is a strict upper bound on the remaining error E*A/2^64+C.
For the source's integer head range, the multiplication and addition
fit uint32; all casts and shifts are exact. The signed ASR24 produces
bias=floor(delta32/2^24). For tail>512, distance*256+bias is a lower
bound on256*(distance+B). For tail<512, distance*256-bias-1 is a lower
bound on256*(distance-B). If this margin is greater than bound, the
entire true interval lies strictly on the same side of the midpoint as
q. The unchanged integer normal pack then returns the exact binary64 RNE
value. Undecided cells keep the original correctly rounded refinement.

The new predicate applies only to distance2or3. Distance0and1 cannot be
admitted by this conservative global residual bound and keep the old
path. The accepted distance3bias predicate runs first and is retained
verbatim; every previously certified fast numerical decision remains.
No nominal-domain filter is used for performance comparisons. This is
an enclosure improvement for all qualifying normal cells, not a list
of special-case input numbers. IEEE status flags are outside the existing
returned-value contract.

Shared product ABI proof: the old frame is PUSH{r4-r7,lr}, SUBsp20,
then four STRs for r0..r3 atsp0..12. The new frame is PUSH{r0-r7,lr},
SUBsp4, with the argument-base register set tosp+4. Both frames are40B;
r4-r7/LR have exactly the same saved positions sp20..36. Relative to
the selected argument base, every16-bit argument load sees the same
input bits. The unchanged arithmetic starts after MOVSr6,#0. The added
ADDbase,#4 may alter incoming flags; the first ADCS in the body is
preceded by an ADDS that establishes its carry, so no incoming flag can
affect a result. Every later carry dependency and instruction is unchanged.
The epilogue is unchanged, restoring r4-r7, SP and the return PC exactly.
R0..R3 and condition flags are caller-clobbered under the existing PCS.
The fixed straight-line active path is84->81instructions for every raw
argument pair. The active body is168->162B;6outside-function NOP bytes
retain the original168B RAM slot, preserving every following symbol and
all other allocated/relocation bytes. These padding bytes never execute.
Stack alignment at entry/calls/return and stack40 are unchanged. No SIO,
new global RAM, tables, allocation, ROM or external runtime calls are added.

The literal gate expression is separately compiled and run on all head
bins with signed-bias admission boundaries, both sides and both distances;
each accepted unit case is checked against the exact rational interval.
Bare old/new products test PCS, stack, all raw-bit argument corners and
valid63x54exact-integer references, plus universal fixed instruction cost.
The full public exp corpus is separately checked against directed MPFR,
with inherited old comparison rows explicitly separated from fresh calls.
Independent review, integration and actual device cycles remain open.

# Independent private RP exp log-midpoint component acceptance

The reviewed object is the frozen private component in
`../m0-exp-tiny-log-midpoint-20261024`, based directly on the accepted
exp-radius component (`ac32571a…`). This is a HOST component review of the
returned binary64 result and emulated Thumb instruction counts. It does
not accept a complete firmware, physical timing, hardware integration,
canonical source promotion, or a release. Exceptions/status flags remain
outside the existing returned-value contract.

## Exact midpoint threshold

Let N be the input sign, |x|=M v, v=2^(e−52), 2^52≤M<2^53. The selected
domain is 2^-54<|x|<2^-32, so −54≤e≤−33. The normal output spacing near
1 is h=2^-52 for positive inputs and 2^-53 below 1. With s=−e−N,
32≤s≤54, the integer quotient r=floor(M/2^s) identifies the linear
output interval. Its midpoint occurs at M0=z 2^(s−1), z=2r+1 odd,
and the midpoint displacement is u=z 2^(−53−N).

The exact input threshold is log(1+u) for positive inputs and
−log(1−u) for negative magnitudes. Define the strictly positive
input-ulp corrections

    D+ = (u − log(1+u))/v,
    D− = (−log(1−u) − u)/v.

Since u≤2^-32, each is less than 2^20/(1−2^-32)<1048577. The guard
G=1048576 covers every integer distance that can change rounding.
G+1<2^(s−1), so only the affected side of one linear midpoint matters.
At an exact linear midpoint D>0 determines the direction without a
product: positive rounds upward, negative takes the smaller magnitude
displacement. This is not an exact exp tie.

Set q=e+55+2N and z²/2^q=K+t/2^q. Here q is 1..24 and t is odd and
nonzero. On the same fractional grid put B=z³/(3 2^(52+N)). The log
series gives

    D+ = K + (t − B + E+)/2^q,
    D− = K + (t + B + E−)/2^q,
    0<E+<z^4/2^(107+2N),
    0<E−<z^4/[2^(107+2N)(1−u)].

These estimates follow directly from the alternating positive-log
series and a geometric bound on the all-positive negative-log tail.
They concern the input threshold, not a Taylor approximation evaluated
at a rounded input. That distinction is necessary at the 154 cells
where a quadratic-only input shortcut returns the wrong last bit.

## Exhaustive strict separation, using integers

`proof.py` independently checks all odd z<2^21 for positive inputs and
z<2^22 for negative inputs: 1,048,576+2,097,152=3,145,728 classes. It
uses uncancelled rational cross-products derived from the bounds above.
Writing L=3 2^(52+N), R=z³ mod L, EDen=2^(107+2N), UDen=2^(53+N), it
checks

    positive: R EDen > z^4 L,
    negative: (L−R) EDen (UDen−z) > z^4 L UDen.

R is nonzero because z is odd. The minimum separation ratios are

    positive, z=1949039:
      245473233535229586948751360 / 43291573601129817537712323
    negative, z=3172801:
      407618261714956886577864364 / 101337768092322586979731201.

Both are strictly greater than 1. Thus E+<frac(B), while
E−<1−frac(B). With b=floor(B), B−E+ and B+E− both have integer part
b and a strictly nonzero fractional part. Also b<2^q. Consequently

    floor(D+) = K − [t≤b],
    floor(D−) = K + [t+b≥2^q].

Each D is strictly between consecutive integers; the weak comparisons
in these formulas do not introduce a rounding tie. For positive
M=M0−d the upper output wins exactly when d≤floor(D+); for negative
M=M0+d the larger magnitude displacement wins exactly when
d>floor(D−). These are the actual source predicates.

The canonical exponent for each odd class is z.bit_length()−54−N.
Positive z=1 also occurs at the upper edge of the preceding e=−54
binade. This additional occurrence has q=1 and floor(D)=0 and is
checked separately. There are 3,145,729 midpoint occurrences but
3,145,728 odd classes. No claim of millions of fresh ARM calls follows
from the integer certificate.

The independently recomputed changed-class list exactly equals the
frozen 154-element list. Its sign/exponent counts are positive
−36:1, −35:2, −34:8, −33:47, and negative −35:1, −34:12, −33:83.
Every one has both threshold-transition inputs checked on the actual
linked public function and separately compiled helper. At one of these
two inputs per cell the quadratic-only shortcut is wrong by 1 ULP.

## Source arithmetic and complete word predicates

The square has at most 44 bits and cube at most 66 bits. The accepted,
unchanged `wide32` primitive computes exact 32×32 products using
16×16 partial products. Its t and v carry intermediates fit uint32;
this review retains that already accepted primitive rather than
claiming to requalify every raw 32×32 input. The new source combines
the products exactly:

    square = low + high 2^32,
    cubeLow = low z,
    cubeHigh = high z + (cubeLow>>32) = floor(z³/2^32).

All 3,145,728 classes are checked against bigint for these bounds,
split shifts, threshold result and reciprocal truncations. cubeHigh
fits 34 bits (observed exact maximum 17179856896). The runtime scaled
quotient floor(z³/2^(52+N)) is at most 8191. Its exact /3 follows from
`(a*43691)>>17`; proof.py also checks every one of the 65,536 inputs
of the author's looser uint16 bound, and excludes uint32 multiply
overflow. The quotient identity floor(floor(A)/3)=floor(A/3) applies.
For z<65536, z² fits uint32 and b=0; the single-MUL fast path is exact.
All variable shift counts are valid: q=1..24 and 32−q=8..31.
The computed threshold ranges from 0 to 1048575. t+b fits uint32.
The nonzero-cubic positive subtraction cannot underflow: D+>0 and the
strict formula above rule that out; the exhaustive class check agrees.

For s>32, high-word shift=s−32 is 1..22. Positive near-midpoint input
has highTail+1==half and low32>2^32−G−1, so distance=2^32−low32 is
exactly 1..G. Negative near-midpoint input has highTail==half and
1≤low32≤G, so distance=low32. All other remainder configurations are
on the unaffected side or more than G input ulps away.

s=32 occurs only for negative e=−33. The source takes r=high32 and
the midpoint half-bit 0x80000000 in low32. For low32<half unsigned
subtraction wraps to at least 2^31 and fails the guard. At exact half,
distance=0 also fails the guard and keeps the correct direction.
The four half/wrap/guard boundaries are independently exercised for
several high-word mantissas. There is no shift by 32. Returning one's
raw encoding ±(r+up) stays within the appropriate normal binade near
1, with no output overflow, underflow or signed-zero ambiguity.

## Independent oracle and actual machine code

The independent second numerical oracle encloses exp(x) by the exact
rational degree-five Taylor polynomial with error
|x|^6/[720(1−|x|)]. Both bounds round to the same binary64 bit pattern
for 1,321 selected inputs. This does not reuse the author's log-floor
oracle. Directed MPFR independently agrees on these inputs.

The successful fresh bounded run contains 1,376 unique public inputs,
including 1,314 selected tiny inputs, all original 16 exp cases, IEEE
header controls, old/new domain endpoints, all 154 cubic-changing
classes and ordinary remaining/layout controls. Four actual public
machines are called in READY and DIRTY states: newly rebuilt child,
newly rebuilt control, accepted radius parent and pinned Qfplib.
The first three use the pinned resident firmware and captured real
boot ROM; no ROM intrinsic mock is installed. The same input is then
run against the source-exact isolated helper in both states.

Qualified own totals are 11,008 public +2,628 bare =13,636 ARM calls;
1,374 actual directed MPFR inputs +2 pre-MPFR sNaN shortcuts =1,376
oracle evaluations. The two sNaN shortcuts must not be called MPFR
conversions. All child outputs equal raw parent bits, and rebuilt
control costs equal accepted parent costs. Ordinary paths outside the
new range have exact parent costs. This bounded test supports the
source proof; it is not an exhaustive raw binary64 execution test.

The helper is exactly 472 bytes in current source object, full overlay,
and a separately compiled ELF containing only that section. Executed
PCs stay in its code (first 452 bytes), reads use only the five local
literal words or its stack, and writes stay in its 56-byte stack frame.
There are no firmware, ROM, external helper, SIO or global data calls
in the isolated execution. Actual allocated SP depth is distinguished
from the smaller subset of stack bytes touched on some paths. One
initial reviewer harness attempt confused these measures; its five
ARM calls and one MPFR conversion are explicitly excluded from the
qualified totals and recorded in execution.json. It exposed no
candidate numerical or state error.

Full public tiny execution stays within the 1,276-byte public entry
and helper, calls the helper once, accesses no SIO, and has stack
depth at most 96+56=152 bytes. DIRTY's full 28 bytes are preserved;
READY is never left DIRTY. The new finite observed child peak is 376
bytes; the own controls reach 744 in the parent. Neither peak is a
universal stack theorem. Static core frame remains 96, helper grows
20→56.

## Instruction and layout conclusions

The actual helper disassembly is an acyclic CFG without calls. A
conservative traversal ignoring predicate feasibility gives a maximum
169 instructions. The unchanged public entry control structure has
34 or 37 instructions outside the helper, so the full selected tiny
path is at most 206. Own actual paths exercise 12 helper and 15 public
paths; observed public costs are 83..200, including every cost class
in the broad author data.

Pinned Qfplib's finite tiny path unconditionally executes its loop
with r7=1..32. Its shorter branch needs 11 Thumb instructions per
iteration, establishing ≥352 instructions before all prefix/finish
work. Every own tiny call also verifies these 32 iterations and its
smallest measured cost is 466. Therefore the new tiny path is faster
in ISA instructions throughout its domain whenever comparing outputs
is meaningful, without relying on a nominal-domain filter. This is
not a physical-cycle statement and does not accept Qfplib's wrong
outputs. Their costs remain in the data.

Only two CPP sections differ: helper 196→472 bytes and core
5012→5012 with a single cutoff immediate byte at offset 3916,
38→32. All other core bytes and semantic relocations are exact.
All other allocated CPP sections/relocations and all RP ASM
allocations/relocations match the accepted parent; d2f256 and f2d172
remain exact. Generic M0 CPP remains exact, M4 soft/hard selected CPP
is empty/equal, and unchanged ASM sources retain inherited accepted
generic/M4 evidence. No whole M4 image was built.

Twelve own complete object/ELF rebuilds are byte-exact; the additional
standalone helper object/link also binds the entire 472-byte helper.
There is no new interposition veneer, table, global RAM, libgcc or
helper dependency. Source-selected code increases 276 bytes; the
explicit private Flash PT_LOAD increases 280 including alignment.
Unchanged product RAM is 168 bytes at 0x20038ee4 with the same resident
wrapper binding. These sizes concern the private overlay, not whole
firmware or eventual linker-GC savings.

## Broad evidence, inherited data and remaining work

evidence.py streams every sealed row without replaying the broad ARM
corpus. It verifies all 856,462 states for 428,231 unique inputs,
both-state coverage, input binary binding, exact old bits/costs and
every retained regression object. Every new-domain row agrees with
the independent word and bigint threshold models. All 616 mandatory
cubic-transition states are in the actual broad acquisition.

Author fresh qualification is 856,462 child +529,112 new Qfplib
+1,028 parent remaining-audit =1,386,602 ARM calls. The earlier
327,350 state rows' parent/Qfplib measurements are inherited, not
freshly acquired. Author directed MPFR is 428,229 actual conversions
+2 sNaN shortcuts. Author final probe 24,898, superseded trial
24,854 and diagnostic 2 ARM calls are excluded. Reusing four parent
measurements from the excluded final probe is explicitly disclosed;
the other 310 known remaining-state parent costs come from the old
corpus, and 1,028 receive the fresh remaining audit.

On the same old 163,675-input corpus, exp raw losses fall 669→155:
514 fixed. The older 48,763-input corpus remains at 154 losses.
The expanded corpus has 671 losses: 155 old +514 new dense endpoint
controls at/outside 2^-32 +2 new ordinary controls. All already lose
in the parent; there are zero new raw speed losses. The two ordinary
inputs are 407BED9F64CDD660 and 4081358A5B33F3E0. Wrong Qfplib rows
remain: 385,334 states; correct comparisons are 469,786 faster and
1,342 slower states, with no equal. No Qfplib correctness/domain
filter hides the remaining rows.

There are 239,986 known state costs higher than the parent, by
6,7,8,11,18,23,27 or 33 instructions. They are all retained and remain
faster than Qfplib. It would be false to call every native input
faster than its parent. The two original exp hard cases remain
2268 vs649 and 2248 vs622 in both states. The author's separately
pinned refinement profile (546/558 instructions before refinement)
is diagnostic evidence, not an additional own ARM qualification.

The original 507-case separate component union stays 418 accepted
(412 strict, 6 equal), with 89 remaining: pow51/exp2/sin22/cos14.
Conversion components are separate and this is not one integrated
math binary. Expanded exp671, pow7904, ln5, sin22/cos14, FMA,
remaining conversion/totality work, whole-math regression, platform
integration, physical cycles, hardware qualification and release
remain open. This component review alone grants none of those GO's.

Reproduce with the pinned Python environment and toolchain using
binding.py, proof.py, arm.py (HOST Unicorn JIT requires executable
memory), then evidence.py and finalize.py. Each writes only this
independent review directory. Producer, accepted ancestors, primary
sources, Git, canonical state and hardware remain unchanged.

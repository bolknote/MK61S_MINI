# Independent private RP adaptive exp enclosure review

The frozen component is m0-exp-adaptive-enclosure-20261024, based directly
on the accepted log-midpoint receipt bdaba8cf…. Its 143 artifacts, 741
lineage pins, and 48 referenced parent files plus the parent receipt were
read and checked. This review is HOST-only. It accepts the private source
component and specified returned-value/ABI behavior, not a complete math
binary, firmware, physical timing, hardware integration or release.

## New enclosure, independently derived

The original table value A is an integer in Q62. The existing full
reduction and polynomial guarantee bounds the exact reduced exponential
by

    |exp(r) − 1 − D/2^64| < E/2^64,
    E = 16002083185666403208005253442412405258030774305560488006981254418822166648269455792397475483696979759
        /3732692613936344822560249276504192336042393930314220012699100441572677279188030925483797647877734400
      < 275/64.

proof.py recalculates the rational reduction, coefficient quantization,
truncation and Taylor-tail terms without executing the author's certify
script. The unchanged source coefficients give the same exact E. A
separate 160-term artanh series interval for ln2 recertifies the split
step, reciprocal, segment bound and reduction index. This retains the
accepted base fixed-point arithmetic proof; it is not a fresh formal
verification of the entire compiler or all old integer primitives.

The actual linked Q62 and Q94 tables are read from the rebuilt ELF.
For each of all 512 rows, exact 512th-power integer inequalities put the
true root strictly between both adjacent rounding midpoints. The tables
therefore have their claimed RNE values. Let T94 be the Q94 entry and

    B = (T94 − (A<<32))/2^32.

The difference is exactly the signed low32 word used by the source;
this equality, its range (−1/2,1/2), and the table bytes are checked for
every row. The true table bias differs from B by less than 2^-33.
This recertification matters: using an arbitrary signed low word would
not justify the asymmetric gate.

Let q=A±P(A,|D|), before any doubling, where P is the accepted rounded
shared product. Its absolute error is at most 1/2+2^-15 Q62 units on the
unchanged A<2^63, |D|<2^54 domain. The independently recomputed maximum
|D| bound is below 2^54. The remaining true scaled exponential V obeys

    |V − q − B| < E A/2^64 + C,
    C = (1/2+2^-15) + h/[2(1−h)] + 2^-33/(1−h),
    h = 1/1400,
    C = 751665119407/1502164811776 <129/256.

The first residual term is product rounding; the second bounds
B(exp(r)−1); the third covers the Q94 uncertainty times exp(r).
The accepted reduction domain gives |r|<h. This derives an enclosure
of the true value, not a sampled approximation to the returned value.

The same polynomial bound gives maximum product correction
<23*2^48. Hence

    A < q +23*2^48 < (floor(q/2^48)+24)*2^48.

For H=floor(q/2^48), the source uses

    bound = ceil(275(H+24)/16384)+129.

Thus bound/256 is a strict upper bound for E A/2^64+C. error==4 implies
q was not doubled; otherwise error becomes6 and the new predicate cannot
run. Here q≥2^62, and the looser q<2^63+2^53+1 bound gives
16384≤H≤32800. Every one of the 16,417 head bins is checked rationally.
Multiplication, rounding addition, unsigned shifts and casts fit their
32-bit types over this entire range.

For distance d from the midpoint, let b8=floor(256B), implemented by
the actual Thumb ASR24 of signed delta32. If q is above the midpoint,

    margin =256d+b8 ≤256(d+B).

If q is below it,

    margin =256d−b8−1 ≤256(d−B).

Both follow for every signed32 delta32, including negative values and
its lowest/highest 24-bit fractions. A strict margin>bound therefore
places the full true interval on the same side of its midpoint as q.
The unchanged normal pack returns the exact binary64 RNE value. Strict
separation excludes tie/parity ambiguities. No finite input list is
used by this decision.

The outer guard permits only distances0..3 for error4; the new branch
requires distance≥2, so it handles only2 and3. Distances0/1 keep
refinement. The accepted distance3 bias predicate is retained verbatim
and runs before the new check. Its worst gap3−11/32=85/32 is also
independently verified larger than E/2+C. The actual largest table
row plus its worst correction remains strictly below2^63, so the
looser head bound does not imply an actual normalization overflow. error6, nonnormal endpoints, huge input,
NaN, infinity, tiny-domain handling and fallback algorithms retain their
accepted numerical logic. The two table-index expressions use the same
signed segment index, and the actual public hook checks that the loaded
bias belongs to the A used in that call. Status flags are outside the
existing returned-value contract.

## Actual source and code binding

The patch has exactly two source changes: the normal exp gate and the
product-save prologue. All control sources equal the accepted parent.
The only changed CPP allocation is the exp core, 5012→5064 bytes. Its
preexisting refinement prefix3736 and separate tiny472 helper are exact.
All other allocated CPP bytes and semantic relocations are exact. All
RP ASM outside the retained168-byte product slot has exact bytes,
semantic relocations and symbol addresses. d2f256/f2d172 remain exact.
Generic M0 and M4 soft/hard selected CPP and ASM are independently
rebuilt and compared; no whole M4 image is claimed.

Twenty-three own complete object/ELF rebuilds are byte-exact, including
the actual full CPP/ASM translations, generic controls, public overlays,
literal-gate unit and both bare product units. The actual source gate
fragment is present verbatim in unit.cpp; the full public ELF is checked
separately and exercised through its real public alias, not through an
interposition veneer. The existing RAM address0x20038ee4 and resident
Flash wrapper binding are unchanged. Private Flash grows48 bytes
including alignment; selected CPP grows52, selected ASM allocation0.
There is no new table or global RAM. These are private-overlay figures,
not full firmware size or eventual linker-GC savings.

## Shared product: universal raw-bit and PCS equivalence

The old prologue pushes r4-r7/LR and allocates20 more bytes, writing
r0-r3 at finalSP+0..12. The new prologue pushes r0-r7/LR and allocates4
more bytes, selecting argumentBase=finalSP+4. Both allocate40 bytes and
save r4-r7/LR at identical finalSP+20..36 positions. Relative to the
argument base, every halfword input load sees identical bits. The common
arithmetic suffix has no argument-memory writes, external calls or
branches. Its 148 bytes, including the epilogue, are exact.

The changed prologue sets different condition flags, but the first
common carry-consuming ADCS follows a common ADDS that overwrites C.
No result depends on incoming flags. All subsequent arithmetic and
carry dependencies coincide. Restored registers, SP and return PC
coincide; r0-r3 and flags are caller-clobbered under PCS. This proves
raw output/ABI equivalence for all raw64 input pairs, including those
outside the numerical63×54 contract. Numerical correctness outside that
contract is not claimed.

Active code is168→162 bytes and fixed instruction count84→81 for every
raw pair. Six NOP bytes remain outside function size, retaining the
168-byte RAM slot and following addresses. Own PC hooks exclude this
padding. Frame size stays40; lowest memory write changes40→36 because
the new bottom alignment word is unused. Frame depth and write watermark
are distinct measurements. Physical PUSH/STR timing is not derived from
the ISA count.

Own new tests use627 raw/carry pairs,338 valid exact-integer references,
both SIO states and512 additional old/new calls covering all16 incoming
NZCV combinations. All raw returns, preserved registers and SP match;
costs are always84/81. Argument reads and writes stay in the40-byte
frame, with no ROM, firmware, mocks, SIO or outside memory dependency.

A separate own public replay of all189 relevant original jobs
(153pow,22sin,14cos) takes1134 ARM calls and189 direct MPFR references.
Every shared product argument pair is identical in parent and child
and is within the63×54 contract. Every caller saves exactly3 instructions
per product call. Pow has66 product calls across both states and46
improved state costs; sin/cos have none on these jobs. Residual counts
stay pow51/sin22/cos14. Other old pow paths cannot worsen under the
proved value/ABI equivalence and constant instruction reduction. This
is a component-context statement, not an integrated math qualification.

## Bounded new gate and full public checks

The own literal gate run takes8308 ARM calls on4154 distinct adversarial
cases, with both SIO states. Cases include head extrema, ceil boundaries,
every actual table bias and both sides of exact signed-bias admission
cutoffs. All four instruction paths are exercised (30..33 instructions),
with16-byte stack, only own literals/stack, no ROM/firmware/mock/SIO.
There are5284 accepted state cases and no unsafe admissions against the
independent rational enclosure. The author's595004 gate sweep is pinned
and reconciled, but is not rerun or relabeled as own fresh execution.

Own full public testing uses994 unique exp inputs in both states on
four machines: child rebuilt ELF, rebuilt control, accepted parent and
Qfplib. This is7952 ARM calls and992 actual directed MPFR references
plus2 pre-MPFR sNaN shortcuts. Separately128 directed MPFR log preimages
generate new input controls; these generations are not exp validation
references. Controls cover all29 fixed inputs, all56 prior hot-margin
inputs, all100 known parent-increase inputs, the original16 exp cases,
new small/normal/endpoint midpoint preimages, IEEE/tiny boundaries and
same-input deep stack cases.

Hooks on the real inlined public gate bind132 events: actual q, table
bias, distance, integer bound and signed margin exactly match the source
formula. All58 admissions satisfy the strict true-value enclosure using
the actual A, rather than only its head bound. Both admit and decline
paths execute. All returned child bits equal parent; rebuilt control
costs equal the accepted parent. Every DIRTY context preserves all28
bytes and READY is never left DIRTY. Static core stack remains96;
focused parent and child both reach744 on the same new deep cases.
Those peaks do not prove a universal math-stack bound.

The qualified own total is20414 ARM calls and1181 actual directed MPFR
references, plus2 sNaN shortcuts. An initial complete numerical bounded
run ended on an incorrect reviewer assertion requiring every fixed input
to be strictly faster. One fixed expanded input instead equals Qfplib.
That initial19280 ARM/992 MPFR run, its2 shortcuts and128 log generations
are explicitly excluded from qualified totals. The corrected final run
repeats the controls. No candidate numerical, ABI or state defect caused
this exclusion.

## Counts, retained regressions and the component ledger

All880014 sealed exp state rows for440007 inputs are independently
streamed and reconciled. The earlier428231 inputs preserve raw returned
bits in both states. Their856462 parent/Qfplib state measurements are
inherited, not fresh. Author fresh counts are

    880014 child exp +23552 new Qfplib +2762 parent remaining audit
    +736324 bare gate/product +1134 original other callers
    +10081 expanded pow losing-state calls =1653867 ARM calls.

Actual directed MPFR validation is440005 exp +189 other callers=440194,
plus2 sNaN shortcuts. The1536 log generations are separate. Final probe
32208, margin336, stack640, initial failed unit736324 and rejected
layouts are excluded. R1/R2 are rejected trials, not accepted ancestors.

On the same428231-input exp corpus,671 losses become642:29 fixed,
comprising28 strictly faster and1 equal. The equal input is
C0861FF4680382C9,607=607 in both states. The older48763 corpus falls
154→126. The new440007 corpus has2023 losses:642 old plus1381 new
preexisting controls (1353 small actual-midpoint preimages,15 uniform,
13 normal/endpoint preimages). All2023 losses have bound parent costs:
1284 old state measurements and2762 fresh audit calls. No new raw
speed loss occurs on these measured corpora. Different-size corpus
counts must not be subtracted.

Wrong-Qfplib outputs and costs remain:390568 states. Correct comparisons
are485398 faster,4046 slower and2 equal states. All200 known parent
cost increases are retained:126 at+2 and74 at+29 instructions. Of these,
44 already lose to correct Qfplib,70 have wrong Qfplib and86 are no
slower than correct Qfplib. It would be false to claim every affected
exp input becomes faster. Global numerical safety follows the enclosure
proof; performance comparisons outside measured corpora are not a new
all-binary64 speed theorem.

The expanded pow replay keeps every10085 prior losing reference variant
and makes10081 distinct fresh x/y/SIO candidate calls. All old expected
bits, reference costs and original row fields are inherited exactly;
new results match and costs equal parent−3*actual product calls. All7904
pairs still lose. There is no fresh111912-pair acquisition or new MPFR
claim for this replay. Every original189 caller row is also reconciled
against the own fresh run.

The original negative hard exp input C041265824E2113C changes2248→599
versus Qfplib622; the positive4085F424184F6DC5 remains2264 versus649
(parent2268). Own fresh ARM/MPFR covers both states. Only this one new
strict fix extends the accepted separate original507 component union:
419 no slower =413 strict +6 equal;88 remain(pow51/exp1/sin22/cos14).
The expanded equal case is outside that original delta and must not
increment the original equal ledger.

Expanded exp2023/pow7904, ln5, remaining trig/conversions/FMA,
general pow/exp totality, whole-math regression, platform integration,
physical cycles, hardware acceptance and release remain open. This
receipt grants only the private adaptive enclosure/shared-product
component. Producer, frozen ancestors, primary source, Git, canonical
state and devices are unchanged.

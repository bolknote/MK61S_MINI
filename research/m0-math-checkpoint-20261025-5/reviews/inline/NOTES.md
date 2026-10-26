# PRIVATE inline seed and exact tiny-overflow component

Supplier0be351d5, actual parent numerator-one3341f37f / independentf9945c0c.
The later parent ROOT78a3c26a is additive; the child's frozen soft/LUT stamps
are unchanged. This is a separate private component review. All94 local and
2281 external pins pass; twelve own source/object/ELF/unit rebuilds are byte
exact. The inline macro and table are shared literally by unit/production.
Their50-byte code differs only at the decoded ADR relocation; all256 table
bytes agree. The old312-byte standalone seed is absent from the candidate.
All four186-byte RNE suffixes remain identical.

For positive subnormal d=k*2^-1074, the reciprocal is2^1074/k. Binary64 RNE
overflows at H=2^1024-2^970. With T=2^50, T*H=2^1074-2^1020 is below the
boundary numerator, while (T+1)*H exceeds it by
2^1024-2^1020-2^970>0. Monotonicity proves all integer1<=k<=T overflow and
all larger subnormal magnitudes do not satisfy this fast predicate. No
integer lies at the tie. Signed zero is handled by its IEEE division rule,
not the inequality. The sign-stripped high-word/low-word ARM comparison is
exactly k<=T, and output bits are signed infinity. Other classes keep the
old fallback with raw operands; no rounded threshold or precision change.

The macro maps quotient to R6, D17 to R1, temporary to R4, residual to R7.
The exact full65536-domain proof retains the prior error[-1,3], signed fold,
wrapped-product residual and Euclidean invariant. At most three decrements
or one increment suffice. R0/R1/R2/R3/R5/R12/SP are unchanged during the
macro; there is one aligned table LDRH and no write, stack operation or C ABI
call. Production SP is its own entrySP-20, not the outer Machine SP. The
old control's leaf BL remains8-aligned. R1/R7 differences die before fresh
definitions, and R4 is overwritten by the exact first-product replacement.
After the second product, all live registers/flags and28 saved bytes agree.
READY still has its nine independent ALUs between divisor issue and read.

Own qualification is4314 CPU-only Thumb calls:778 paired bare-unit calls
on389 tests,3368 scalar calls on421 flag-jobs/46 distinct denominators, and
168 public calls on14 pairs. There are54 directed MPFR invocations and6
sNaN policy shortcuts; scalar expected values are cached per denominator.
Signed T±2, zero/min/max-subnormal and all16 NZCV patterns, every remaining
denominator, IEEE classes and all three slowdown classes are covered.
The unit's20-byte wrapper is not production stack/performance evidence.

Production has150 fresh inline live-context checks, including two nested
pow contexts where own entrySP differs from outer Machine SP.304 complete
after-second-product state/frame28 comparisons and150 actual READY latency
checks pass.846 private entries restore their original return frame, and
all four public return sites are observed. The strict public pair, a distinct
new reference-state equality and the one-up inline saving5 were reproduced.
Wrong Qfplib outputs/costs and positive parent deltas remain. No own call
failed, was partial or was discarded.

Full saved public raw:120980 pairs/241960 states/279522 reference variants,
including77106 wrong references. Loss pairs11372 to11371, one strict pair
fix,754 faster states(377 READY,377 DIRTY),2-7 instructions saved, no public
increases/wrong/new losses.778 parent path replays include24 unchanged
powers-of-two controls; they are not778 speedups. All10254 fresh controls
match. The separate new reference equality is not the strict pair fix.
Original153 remains119 strict/34 slower; reviewed507 remains422.

The expanded scalar corpus is20994 jobs/41988 states. Its immediate parent
has7422 correct-Qfplib losses, not the old smaller corpus's216. Candidate
has32370 faster,5 equal and13 slower; all9600 wrong references remain.
There are9664 parent cost increases:3168 states +8,352 +2,6144 +11. All are
retained, including wrong-reference cases. Own bounded tests reproduce
64 +8,26 +2 and128 +11 cases. No new correct-Qfplib deficit in these saved
or bounded sets implies neither universal parent-speed improvement nor
universal reciprocal superiority. The five equal scalar states stay equal.

Author615606 fresh calls are separate from own4314.143392 bare calls include
old/new wrapper tests, without a wrapper speed/stack claim. The zero-call
symbol failure and318 complete plus2 partial nested-SP trace failures/
23 MPFR evaluations are preserved and excluded. Parent campaigns are not
fresh. All24 author rebuilds are separate from the twelve own rebuilds.

Allocation1060 to1072 bytes(+12); no new mathematical table values, RAM or
libgcc. Current free-Flash layout is below2MiB. Saved full peak2284 and
author controls2148/scalar176 remain unchanged; the changed-parent subset
is not a complete comparator. Own selected public968/scalar176 peaks agree
in all three images. No physical cycles or universal stack benefit is
claimed. The hidden entry still requires positive numeratorone in R0:R1,
denominator R2:R3; it is not generic division or a one-argument C ABI.

Near-one remains a sibling. Source merge/relink, actual integrated shared
R12, loader/layout/stack checks, the old168-byte exp overlay's14-byte table
hazard, remaining scalar deficits, other needed math, general pow totality,
physical cycles and hardware/release remain open. No device, USB, Flash,
network, Git or canonical/product edits were used by this review.

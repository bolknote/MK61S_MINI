# Private inline seed and exact tiny overflow: author qualification complete

Contract remains exact positive numerator1, denominator any binary64. The
actual sole root caller and its positive-one loads are unchanged. This is
not a general ddiv/C ABI replacement. Parent numerator-one has independent
TECH_GO; the new component still needs separate review. Parent receipts
available at seal are pinned without widening their scope.

For subnormal magnitude k*2^-1074, exact endpoint products prove reciprocal
RNE overflow for every integer0<=k<=2^50. The new cold path returns signed
infinity; all other special inputs retain the original IEEE fallback. The
threshold and both neighbours are checked under both signs and all16 flags,
with random subnormals and all denominator exponent/sign classes. The exact
seed is inlined in R4/R6/R7/R1, retaining R0/R2/R3/R5/R12/SP. Complete65536
domain plus all16 table-edge flags passes71696 unit tests /143392 actual
old+new ARM calls. The wrapper's20B stack/speed is not production evidence.
Production inline SP is exactly its own entrySP-20 and makes no C ABI call.
The new macro and unit share the same source/table. Old312B standalone seed
is not allocated. The256B table and four186B RNE suffixes are unchanged.
Hardware retains nine independent ALU operations before SIO quotient read;
all seven DIRTY SIO words are preserved without writes.

Same120980 pairs /241960 states:11372->11371 raw loss pairs, one new strict
fix,0newloss/0wrong/0public parent increases.754 states (377 READY,377 DIRTY)
save2-7 instructions. All754 changed paths have fresh parent replays; the
778 parent-call counter also includes24 unchanged powers-of-two controls.
All10254 fresh controls match full records, all actual public costs match
the exact model. Every279522 reference-state variant, including77106 wrong
Qfplib outputs/costs, is retained without a nominal-domain filter.

Expanded scalar1/x corpus:20994 pairs /41988 states, correct-Qfplib losses
7422->13, no new Qfplib losses;32370 faster,5equal,13slower. All9600 wrong
reference variants remain. There are9664 scalar parent cost increases:
3168 states +8,352 +2,6144 +11 instructions, from cold fallback checks;
these are explicit and none creates a new loss against correct Qfplib.
This is not a universal reciprocal or whole-library speed claim.

615606 fresh qualified ARM calls:241960 full candidates,778 parent paths,
61524 fresh public controls/references,167952 scalar calls and143392 bare
context calls.26011 directed MPFR inputs plus110 sNaN policy shortcuts.
The first driver symbol lookup failed before scalar/MPFR calls. Initial
nested public trace runs stopped on an absolute rather than relative stack
assertion after318 completed calls, two partial aborts and23 MPFR calls;
these are preserved/excluded. Kernel/scalar results were already correct.
Parent qualification and old seed campaigns are inherited, not fresh.
Twenty-four full source/object/ELF rebuilds are byte-exact.

Private code1060->1072B (+12B), no new table values/global RAM/libgcc. Default
M0/M4 controls and six new disabled objects remain empty. Full observed stack
2284B, fresh controls2148B each, scalar176B each unchanged. The parent path
subset is not a full comparator; no universal stack bound is claimed.
Original153 stays119strict/34slower, author separate507437 and reviewed422.

Remaining work includes13 scalar states, other needed operations, general
pow totality, source merge/relink and actual integrated R12/loader/layout
guards, the14B old-overlay hazard, physical cycles and release. No canonical,
M4, Git, device, USB or Flash change, and no integration/hardware/main/release
GO. Historical producers must not run inside frozen packets. Goal is active.

Independent private bounded seed correction
==========================================

Actual parent is Zero98ef/independent8c97, accepted for correctness only.
Later Zero ROOT4ee4 is additive; the child frozen stamp is unchanged. The
private entry is positive numerator1 with raw R0=0, packed R1=3ff00000 and any
binary64 denominator. The inline seed newly requires R0=0. It preserves that
value but cannot inherit a generic old seed contract accepting arbitrary R0.

The unchanged128-entry256B table and exact uint32/ASR sequence were independently
evaluated for every D=65536..131071. Error k=estimate-floor((2^32-1)/D) has
histogram{-1:140,0:5167,1:35252,2:23815,3:1162}. For negative residual, exact
R=r-kD with0<=r<D is signed-safe. First decrement and ADD D exit on BPL exactly
for k=1. At k=2 the next ADD wraps unsigned and sets carry1; at k=3 it leaves
negative residual and carry0. Immediate SBC q,R0 subtracts0/1 under R0=0,
yielding the exact same quotient. Error3 alone leaves R7=r-D modulo2^32.
There is no promise of an exact remainder from this private seed.

The emitted macro is56B versus50B, shared by unit/production except decoded ADR
addresses. Its inputs and all declared live registers/SP are preserved. ADDS
q,1 cannot overflow for q in[32768,65535]; following LSRS restores identical
NZCV and u0. Static inspection finds no R7 reference from seed done to the
second product; its first occurrence there is LSRS R7,R2,16, an overwrite.
Under the actual Zero scratch mapping, full R0-R7/R12/SP/NZCV/frame28 states
then coincide after the product, residual, R3 certificate and pack. The actual
positive-one root caller and guarded software prefix supply R0=0 throughout.

Own qualification is2908 actual Thumb calls:480 paired bare calls (15D/all16
flags),2176 scalar calls (272flag jobs/47D),252 nested public calls (21pairs,
all3 actual Qfplib compositions).62 actual MPFR evaluations and6 explicit
sNaN policy shortcuts are separate. All5 errors/all16flags, BPL exit and
fresh ADD carry feeding SBC are checked. There are255 post-ADD1/LSR contexts,
58 allowed R7 changes before dead overwrite,514 full after-second/residual
joins,368 complete certificate contexts,255 inline own-entry-SP/READY9ALU
checks,566 original20B frame entry/POP checks and22 actual root returns.
Eleven inline contexts are nested in pow. Both old expanded losses149/147
vs146 become146/144vs146 in actual bounded execution. No numerical check
failed or was discarded. Twelve own whole rebuild outputs are byte-exact.

Saved evidence was recounted without a2M/3M ARM campaign. Every65536 unit row
has all16 NZCV costs and exact quotient/R7 values bound to the independent
integer model:1048576 tests/2097152 author ARM calls,18592 cases save3
instructions and the rest have equal counts. Saved residuals use signed
integers while our model uses uint32; modulo normalization is explicit.

The complete public120980pairs/241960states/279522reference variants retain
77106 wrong outputs/costs.11369 loss pairs remain;10states save3instructions.
All778 fresh parent replays include768 unchanged controls;10254 fresh public
rows match the full raw corpus. Original153 remains120strict/33slower.
The same scalar20994cases/41988states retain9600 wrong references and remain
32387faster/1equal/0slower. The separate two-pattern all-D expanded scan has
131072inputs/262144states,262132faster/12equal/0slower, with correct Qfplib
outputs throughout that finite scan. It covers two mantissa patterns per D,
not every binary64 denominator or universal performance.

Ancestry is retained. All32 Certificate regressions remain above Inline:
26×+6 and6×+5. Both already-losing states are actually reproduced:
READY Inline1697/Certificate1705/Zero1703/Bound31703 and DIRTY
Inline1706/Certificate1714/Zero1712/Bound31712, versus Qfplib1526/1547/1584.
The earlier correction and performance-adoption-false verdict remain binding.
Reviewed507 remains422; author438 is not promoted.

Instruction nonincrease is not cycle nonregression. Error1 reverses a taken
versus untaken branch in35252D (564032 saved flag cases); branch, Flash/cache
and pipeline costs have not been measured. Keep the old loop control for a
future physical comparison. Correctness receipt does not authorize adoption,
claim global speed parity, or provide a physical timing result.

Author3355798 qualified ARM calls and157083 MPFR evaluations are additive,
overlapping campaigns, not a unique-input union. Partition is2097152+241960+
778+61524+167952+786432, with110 sNaN shortcuts separate. The rejected author
trace has14184 completed ARM,1106MPFR and76sNaN,0partial, all excluded. Its
parent/control comparison incorrectly applied the old/new R7 rule; the exact
fix only supplies False for that unchanged pair, leaving default-True old/new
semantics byte-for-source equivalent. Only the terminal public-control run
was repeated; full/expanded evidence is not counted twice. No producer
command was executed in place. Two own HOST-only failures are retained: the
signed/uint32 saved-residual comparison and a closure metadata keyword syntax
error; both executed zero ARM/MPFR and did not alter supplier evidence.

Allocation1100->1108B(+8), same256B table, no new RAM/libgcc/external calls.
DefaultM0/M4 selected objects and6 disabled objects are unchanged/empty.
Author full2284/public2148/same-scalar176/expanded-normal28 stacks are separate
corpora. Own scalar176/public968 are equal across parent/control/new; no
universal stack bound follows. Source merge/relink, actual integrated shared
R12/consumer/veneer/loader/layout guards and the old168B-overlay14B hazard
remain mandatory. Near-one exp is a separate sibling. General pow totality,
other math, physical timing, hardware, adoption, main and release are outside.
No further micro-optimization is part of this review. Devices/USB/Flash,
network, installs, Git, canonical state and product source were untouched.

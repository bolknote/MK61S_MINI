Independent known-zero private reciprocal component
=================================================

The parent is Certificate9911, accepted for correctness with its explicit
performance tradeoff; Inline0be is the earlier ancestor. Near-one exp is a
separate sibling. Later Certificate ROOTaa392 is bound additively. Supplier
and historical seals are unchanged.

The second unsigned product starts from equal R0=R4=0, established by the
actual positive-one caller and first product. Every emitted instruction of
the complete36B multiplication is exactly the R0/R4 register permutation,
including its carry branch. R0 was otherwise unused by that product. The
new R0 scratch is the old R4 scratch; new R4 stays zero. All other registers,
NZCV and the complete frame agree under that permutation.

Next, R1 is a dead product temporary, overwritten by LDR xH, MUL a0, ADD R3,
then overwritten again by the original shift from R3 before its next read.
This replaces R4's xH temporary while keeping R4 zero. The unchanged SUBS
R0,R4,R2 kills the scratch R0 and all incoming flags. Every register R0-R7,
R12, SP, NZCV and the28B frame rejoins exactly after the y residual. Removing
the zero doubling changes no value; its NZC are replaced by the next LSRS
before any consumer, and it never changed V.

The shared sign certificate only renames its scratch from R6 to R3. Every
scratch read follows its own write. Its accepted whole-uint32 E=[0,131071]
proof, both inclusive discontinuity bands and full multiplication/borrow
fallback apply unchanged. R3 is dead on decisive exits and overwritten before
its first full-product read. The emitted12B nonbranch prefix is the same in
the shared unit and both production paths. This shared macro preserves
arbitrary R6 on decisive exits, independently of private R6=0.

The existing MOVS R6,0 before quotient rounding still executes. Decisive
certificate paths retain that zero, so ADDS low / ADCS high can use R6.
ADDS defines carry before ADCS. The old zero write to R2 is dead: the down
shift defines R2 before ORR and packing defines it again. A full-positive
fallback explicitly clears R6 after the product before joining ADCS; a
full-negative fallback does not need R6. At pack only dead R3/R6 differ.
All live values, flags and stack bytes agree, and saved R4-R7 are restored.
There is no claim of an unchanged186B suffix and no generic division/C ABI.

Own qualification:3904 bare-unit Thumb calls,128 additional direct decisive
target checks (both signs, all16NZCV, R6=0/1/80000000/FFFFFFFF),1776 scalar
calls (222flag jobs/57D) and216 nested public calls (18pairs against3 actual
Qfplib compositions), total6024. There are69 actual MPFR evaluations and6
explicit sNaN policy shortcuts. All8 fast/full, up/down and cross-carry
classes execute. Checks include408 complete product states under permutation,
408 full residual joins,382 complete pre-certificate/zeroR6 joins,134 full
base restorations,202 positive ADC zero checks,202 inline own-entry-SP/READY
9ALU checks,460 original-frame entry/POP checks and16 real root returns.
Eight inline contexts are nested in pow; SP is its own entry SP minus20.
The single own HOST syntax preflight is retained with zero ARM/MPFR. No
numerical attempt failed or was discarded. Twelve own rebuilds are byte-exact.

All three saved raw corpora were independently recounted without repeating
the campaigns. Public120980pairs/241960states/279522reference variants retain
77106 wrong Qfplib variants. Loss pairs remain11369;754 states save2-3
instructions, and no state increases against the immediate Certificate parent.
One reference equality becomes faster without a new pair-level fix. Original
153 remains120strict/33slower; reviewed507 remains422, not author438.

The same scalar20994cases/41988states retain9600 wrong reference variants.
Its correct-Qfplib results become32387faster/1equal/0slower. This is finite:
the separate expanded scan contains65536seed D with2 normal mantissa patterns,
131072inputs/262144states, all actual D observed. Results are262131faster,
11equal and2slower, with all Qfplib outputs correct in that scan. Both remaining
DIRTY denominators are actually reproduced:3FF0CEE65125761B is149vs146 and
3FF10E0E8502C07D is147vs146. The old same-corpus149vs146 case becomes146equal.
No universal reciprocal speed conclusion follows from zero losses in one set.

Ancestry remains binding. Against the same Inline rows all32 Certificate
regressions still exist:26 are now+6 and6 are+5. Both already-losing correct
Qfplib cases are reproduced:READY Inline1697/Certificate1705/Zero1703 and
DIRTY Inline1706/Certificate1714/Zero1712, versus Qfplib1526/1547/1584.
Certificate's additive correction5cd5994f remains binding; zero increases
against Certificate does not erase those regressions or give adoption GO.

Author1460246 fresh ARM calls and157083 MPFR evaluations are additive across
overlapping campaigns, not a unique-input union:241960+778+61524+167952+
201600+786432, with110 separate sNaN shortcuts. Copied parent campaigns are
not fresh. Observed full2284/control2148/same-scalar176 and expanded-normal
28 stack figures refer to different corpora. Own scalar176/public968 match
parent/control/new; neither gives a universal stack bound or physical cycles.

Allocation1108->1100B(-8), unchanged256B table/seed, no added RAM, libgcc or
external call. DefaultM0/M4 selected objects and6 disabled objects remain
unchanged/empty. Before integration: source merge/relink with near-one and
fresh actual integrated shared-R12/consumer/veneer/loader/layout guards. The
old168B overlay still overlaps14 bytes of the newer table-product entry.
General pow totality, other math, physical timing, hardware, performance
adoption, main/release and the author's next high-loop study remain outside.
No device, USB, port, Flash, network, Git, canonical or product source access.

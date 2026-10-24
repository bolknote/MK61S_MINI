# Independent private RP dyadic-product component review

This review concerns the frozen m0-exp-dyadic-product-20261024 source and
function overlays. It grants no integrated firmware, hardware, physical
cycle, main/canonical promotion or release acceptance. All 130 frozen
artifacts and887 lineage pins are checked at entry and again at the end.
The newly accepted adaptive parent receipt83b3d4a9… and54 referenced
files are verified separately.

The child recorded its source-parent independent review as pending at
seal. That fact is preserved in result.json, certificate.json, HANDOFF
and WORK-SCOPE. The later adaptive GO is added in a separate
parent-GO-after-seal.json receipt. No frozen metadata is rewritten to
suggest the acceptance was available earlier. The accepted source
parent is byte-exact to the control objects and ELF in this child.

## Universal index0 identity

The sole C++ change replaces the shared product only when index==0.
The actual linked Q62 table is byte-identical to the accepted adaptive
table and its first row is exactly A=2^62. In 16-bit limbs this is
[0,0,0,2^14]. Every omitted partial product with i+j<2 has a zero A
limb, so the parent retained product is the exact full integer product
in this case. Consequently, for every valid b,

    floor((A*b+2^63)/2^64)
      = floor(2^62*(b+2)/2^64)
      = floor((b+2)/4).

The existing integer-product convention rounds its halfway cases up.
This is exactly preserved; it must not be mislabeled a new RNE rule
for this intermediate product. The enclosing/refinement algorithm still
produces the RNE binary64 result.

proof.py independently recomputes the unchanged coefficient,
quantization and Taylor bound that limits |delta|. It gives the exact
same rational maximum as the sealed certificate, and maximum+2<2^54.
Thus unsigned abs(delta), addition2 and the constant shift cannot wrap
on any input reaching the branch. The identity in fact holds throughout
the entire b<2^54 product domain; controls near its maximum intentionally
exercise more than the public caller's smaller certified maximum.

The complete parent/new CPP source comparison is exactly the one
expression replacement. The product domain, error radii, adaptive gate,
index calculation, normal pack, endpoint logic, refinement, tiny helper,
NaN, zero and infinity policy are identical. Hence the accepted
all-normal enclosure and older fallback proofs carry forward without
any weaker numerical condition. The current table's index0 value and
all copied source dependencies are bound to the tested objects.

## Shared leaf: raw value, carry and PCS proof

Let entry SP be S. Both versions begin with PUSH{r0-r7,lr}, writing the
same36 bytes at S−36..S−1. The parent then allocated an unused4-byte
word, used argumentBase=SP+4, and later added20 before POP. The child
omits that allocation and base adjustment: its SP and argument base
both equal S−36. Each argument halfword load has exactly the same
absolute address and input bits. Saved r4-r7/LR occupy the same
S−20..S−1 positions.

The next144 arithmetic bytes, through MOVr1,r6, are byte-identical.
No arithmetic instruction refers to SP; all argument reads use the
unchanged absolute base. The removed ADD could change initial flags,
but the first common carry-consuming ADCS follows a common ADDS which
sets C. All later dependencies are identical. This proves identical
raw return values for every raw64 argument pair, even outside the
numerically valid63×54 domain. Numerical correctness outside that
domain is not claimed.

At exit the new ADDsp16 and old ADDsp20 both produce S−20. The identical
final POP restores the same r4-r7, SP=S and return PC. Other preserved
registers remain untouched. Caller-clobbered registers/condition flags
need not match under PCS. Active bytes are162→158 and the straight-line
count is81→79 for every raw pair. Ten NOP bytes outside the function
retain the168-byte slot and following addresses; PC hooks verify they
never execute.

Frame depth changes40→36; both versions actually write36 bytes. These
are different measurements and are reported separately. SP is always
word-aligned and is8-byte aligned at entry and return. For the child's
active arithmetic it is normally4 modulo8. This meets the universal
and public-interface constraints respectively in the official
[AAPCS32 2025Q4](https://github.com/ARM-software/abi-aa/blob/2025Q4/aapcs32/aapcs32.rst),
sections6.2.1.1 and6.2.1.2. The leaf contains no BL, BLX, other call or
outside data access while that frame is active. This is not a test of
interrupt delivery, exception stacking or physical cycle timing on a
device; those remain hardware/integration obligations.

## Source, objects and actual instruction paths

Twenty-three independent complete object/ELF rebuilds are byte-exact,
including RP, generic M0, M4 soft/hard selected CPP and ASM, both public
overlays, bare product units and literal dyadic unit. The CPP core grows
5064→5088 bytes; the3736-byte refinement prefix and tiny472 helper
remain exact. Prefix semantic relocations are separately checked. All
other allocated CPP bytes/semantic relocations are unchanged.

Within full RP ASM, only the retained168-byte RAM product slot changes.
The144 arithmetic bytes and POP are exact, and all bytes, semantic
relocations and symbol addresses outside the slot are unchanged.
d2f256 and f2d172 remain exact. Product.o, the bare product ELF, full
ASM object slot and public RAM overlay contain the same168 bytes.
The existing0x20038ee4 address and resident Flash wrapper are retained;
the public exp alias is the real direct entry, without a new veneer.
Selected generic M0/M4 controls remain equal, but no whole M4 image or
repaired-platform firmware is built.

Selected CPP and private Flash both grow24 bytes; allocated ASM/RAM
slot sizes do not change. No new table, global RAM, ROM arithmetic,
libgcc or external dependency is introduced. Whole firmware size and
linker-GC effects are unmeasured.

Own literal controls use668 independent displacement values at powers
of2, all4 residue classes, half ties, lowword carry edges and both
certified/full-product maxima. Both SIO states plus128 calls covering
all16 NZCV states give1464 actual ARM calls, each9 instructions,
zero stack/data-memory accesses. Results equal the independent full
128-bit integer product oracle.

The raw old/new leaf comparison uses1145 pairs,916 valid exact-integer
oracles and both SIO states, plus512 calls for16 NZCV variants. These
5092 calls have identical raw results, preserved registers and return
SP. Counts are always81/79. Per-instruction PC/SP checks prove the
40/36 frame depths, word alignment and public8 alignment, with no
padding execution or data access beyond the shared36-byte write/read
region. The old intermediate4-byte alignment slot is never read.

Own full public exp controls use841 unique inputs and four machines in
both SIO states: rebuilt child, rebuilt control, accepted adaptive
parent and Qfplib. This gives6728 ARM calls,839 actual directed MPFR
references and2 pre-MPFR sNaN shortcuts. It includes all547 newly fixed
same-corpus inputs, original16 exp inputs, former hot-margin controls,
stratified parent increases, independently generated index0/neighboring
segment controls, ordinary inputs and IEEE/tiny boundaries. These are
bounded targeted controls, not a repeated broad old sweep.

Hooks on the actual inlined selection bind1636 events, including1106
index0 events. At the real comparison they read index,A and displacement;
index0 always has A=2^62, and the computed shift matches the exact
product. It makes no shared-kernel call. Every other selected index
calls the leaf once. Entry/internal/return SP rules hold on real full
public execution too. Every child raw result matches parent, and rebuilt
control costs equal accepted parent. DIRTY's full28 bytes are preserved;
READY is never left DIRTY.

A separate own original-other-caller run takes1134 ARM calls and189
MPFR references on153pow/22sin/14cos inputs. Raw values and every
shared argument pair match; all costs are parent−2*actual product calls.
All product arguments satisfy the existing63×54 bound. Pow has66 calls
across both states; sin/cos have none on these original inputs. This
replay independently binds the three new pow ties, not just aggregate
producer counts.

Qualified own totals are14418 ARM calls and1028 actual directed MPFR
validation inputs plus2 sNaN shortcuts. There is no own log-generation
count pooled into these references and no excluded failed numerical
run. Real resident boot-ROM initialization is used for public calls,
with no intrinsic mocks, and initialization is excluded from totals.
Own focused public peak is376, whereas the author broad corpus reaches
744; neither observed peak is a universal full-math stack theorem.

## Streamed evidence and exact ledgers

The full913500 state rows for456750 exp inputs are streamed without
rerunning the broad acquisition. Both-state coverage, input-binary hash,
old raw bits, old reference costs, all retained increases and all
remaining parent costs are reconciled. The old880014 state rows supply
inherited parent/Qfplib measurements, not fresh executions.

Producer qualified fresh ARM counts are

    913500 child +33486 new Qfplib +130 parent remaining audit
    +141320 bare product +70094 literal dyadic +1134 other callers
    +10081 pow losing states =1169745.

Actual directed MPFR validation is456748 exp +189 other callers=456937,
plus2 sNaN shortcuts. The8404 log-preimage generations are separate.
Probe40494, margin336 and initial failed touched-byte-counter unit run
141320 are excluded. Bare unit evidence is pinned and reconciled, not
misrepresented as our own fresh sweep.

On the same440007 exp inputs,2023 losses fall to1476:547 fixed,
542 strict and5 equal. The older48763 inputs fall126→96. The expanded
456750 corpus has1541 losses:1476 old +65 new controls, all already
losing in the parent. The latter comprise40 dyadic/adjacent midpoint,
13 dyadic interior and12 uniform inputs. Every1541 loss has a parent
cost:2952 old state rows and130 fresh audit calls. No new measured raw
speed loss appears; different-size corpus counts must not be subtracted.

Correct-Qfplib comparisons are517720 faster,3082 slower and10 equal
states. All392688 wrong-reference outputs/costs remain, with no nominal
domain filter. All13222 known parent increases are retained, each+2:
200 already lose to correct Qfplib,11950 have wrong Qfplib and1072 are
still no slower. The remaining original positive hard exp visibly
regresses2264→2266 versus649; it is not hidden by the many dyadic wins.
The prior negative hard case remains accepted,599→596 versus622.

Expanded pow replays10085 old reference variants with10081 distinct
fresh candidate state calls. Every inherited expected value, Qfplib
cost and ancestor row is reconciled, including the earlier adaptive
fresh-candidate fields. New costs are parent−2*actual product calls.
Pairs fall7904→7901, exactly the three newly equal original pairs.
Expected bits and references are inherited; this is not a fresh111912
pair acquisition or MPFR run. Other old nonlosses cannot become slower
under the universal raw-value/ABI equivalence and constant cost reduction.

The three freshly verified original pow ties are:

    (3FEFFFFFFFFFFF2B,40BA76B89D3E311A):1346→1344=Q1344
    (3FF000000000004F,40EAAD0A6A243E3E):1322→1320=Q1320
    (3FF000000000017C,4055D6591BBBC2B4):1313→1311=Q1311.

They add3 equal and0 strict to the accepted adaptive original507 ledger.
The result is422 no slower =413 strict +9 equal, with85 remaining:
pow48/exp1/sin22/cos14. Original exp remains15 strict/1 loss, and
unaffected other302 entries retain296 strict/6 equal by unchanged code
and prior accepted evidence. This remains a separate-component union,
not one integrated binary.

Expanded exp1541/pow7901, ln5, remaining conversion/FMA and totality
obligations, whole-math regression, repaired-platform integration,
interrupt behavior, physical cycles, hardware qualification, canonical
promotion and release remain open. No producer/frozen/primary source,
Git, device, USB, Flash, lease or release state is changed by this review.

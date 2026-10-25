# Independent PRIVATE root reciprocal component review

The supplier is frozen `13dc7f81…`, actual parent Boundary128 `61c98b93…`,
accepted independently as `6c1a375b…` and by ROOT `260cb67e…`. Near-one remains
a separate sibling. This receipt qualifies the finite private component,
not a complete firmware, main, hardware, physical cycles or release.

Exactly one root reciprocal BL is rebound to a hidden guarded BSD-kernel
clone. All other resident ddiv call sites retain the original function.
Reversing the clone's symbol/section scaffolding reproduces the existing
source kernel. The candidate differs from the control by the DIRTY branch
target and a 12-byte bridge; the READY instruction sequence is unchanged.
Eight own full source/object/ELF rebuilds are byte exact. All 81 local and
1814 external pins were verified. Default M0/M4 selected objects remain
equal and all 12 added disabled objects are empty.

The continuation is not a scalar C ABI. It receives the raw packed operands,
R6=Ea-Eb+1021 in the guarded unsigned range [0,2043], and the existing 20-byte
R4-R7/LR saved frame. Normal guards exclude exponent zero and 2047; the
dyadic cases and original IEEE fallback precede the changed DIRTY transfer.
At that transfer R0-R3 and R6 are intact. The continuation unpacks the same
normal words, constructs the same R12 sign/exponent tag, and saves five
temporary words. Its seed BL is therefore 8-byte aligned. POP restores the
four operand words; the extra R7 slot is alignment space, not a new ABI.

For D=(hidden|fractionHigh20)>>4 the domain is exactly [65536,131071]. The
leaf starts from prefix=131071, Q=1, R=131071-D, so 0<=R<D. Each of the next
15 one bits produces T=2R+1, appends bit=(T>=D), and subtracts D when selected.
The invariant prefix=Q*D+R persists. CMP sets the quotient carry; the selected
SUBS cannot borrow and keeps it set; ADCS appends the bit. Incoming flags
cannot affect it. T<2^18, Q<=65535 and q+1<=65536, so no unsigned32 overflow
occurs. At exit Q=floor(FFFFFFFF/D), and (Q+1)>>1 is exactly the previous
hardware seed, not a new approximation or rounding rule. The independent
HOST integer check covers all 65536 D values; it is not an ARM/MPFR or public
qualification count. Actual bounded leaf execution separately verifies
288 cases, including all 16 NZCV values at each of 16 edge divisors, noisy
R0/R3/R12, PCS/SP/PC and no data-memory/stack access.

At the common join R0-R6, R12, SP and the complete original saved frame match
READY hardware. R7 is dead until a long-product macro overwrites it. The
first common ASRS establishes carry and the first ADDS establishes all
flags before a conditional branch. The 282-byte NR/remainder/RNE tail is
byte-identical in control hardware, candidate hardware and both software
copies. The initial quotient and all live state agree, so the existing
normal-result RNE mechanism is preserved. All other IEEE guards/fallbacks
retain their old bits, including quiet NaNs; precision is not relaxed.

Own CPU-only execution in Unicorn consists of 1280 qualified ARM calls:
288 seed, 248 direct calls on 31 input pairs, and 744 public calls on 62
pairs. There are 89 directed MPFR inputs and four separate sNaN policy
shortcuts. The direct/public paths enter the real guarded function, never
the continuation as a C function. Their 64 DIRTY join comparisons verify
the guarded R6, raw operands, 20-byte frame, R12, SP, seed alignment and
flags after the first common ADDS against READY hardware. The DIRTY path
reads only CSR, writes no divider register and preserves all seven SIO
words. All 48 saved strict public fixes were independently executed in
both SIO states against all numerically correct real Qfplib compositions.
Wrong Qfplib results and costs are retained. READY costs are unchanged.

The complete saved raw stream was recounted against the accepted parent:
120980 pairs, 241960 states, 279522 reference variants, including 77106 wrong
Qfplib variants. Loss pairs fall 11434 to 11386; all 48 fixes are strict,
377 DIRTY states save 311-380 instructions, and there are no new losses,
wrong outputs or increases. The current comparator is
parent_reciprocal_instructions. Earlier boundary/midpoint traces carried
through the raw rows are historical metadata, not fresh traces claimed by
this review. All 10254 new public control rows match the full records.
Original153 stays 119 strict and 34 slower. Reviewed507 stays 422; the
author's separate 437 union is not promoted or called an integrated image.

Author evidence remains separate: 842693 fresh ARM calls, 6761 MPFR inputs,
184 sNaN shortcuts and 65536 integer/dyadic normal-division oracle inputs.
The direct test has 67354 jobs, not an asserted unique-pair corpus. Its 3636
saved subset rows retain all 936 reported wrong Qfplib variants. Per-divisor
timing rows for the exhaustive seed part were not retained, so this review
makes no per-divisor Qfplib speed claim from that portion. Prior seed66288,
pilot1836/153 MPFR, inherited references/oracles and failed-import preflight0
remain excluded. There were no failed own preflights or discarded own calls.

The diagnostic allocation is 1050 bytes, including a clone and the existing
32 bytes of dyadic constants. There are no new table values, writable RAM
or libgcc dependencies. It occupies free Flash below 2 MiB in the current
private layout. Full-corpus observed peak stays 2284; author fresh controls
stay 2148; the changed-path parent388 is a subset, not a comparator for the
whole corpus. Own selected public peak is 968 in all three images, and the
own direct set peaks at 176 because it also includes fallback cases. No
universal stack improvement or physical cycle result is claimed.

Future source merge/relink must keep the continuation private, bind it to
its exact guards/frame, and check actual integrated R12 consumers, veneers,
loader order, memory/stack/layout and the final linked target. The old
168-byte exp overlay still overlaps 14 bytes of the new table entry and
cannot be mechanically layered onto the new bank. No combined near-one
image, general pow totality or main/hardware/release gate is qualified.
No devices, USB, Flash, network, Git or canonical/product edits were used.

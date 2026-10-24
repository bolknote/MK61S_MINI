The private RP2040 reciprocal-root pow component is frozen for independent review.

Original pow deficits82 ->51; all31 new fixes are strict in READY and DIRTY.
The original507 separate-component author union is418=412strict+6equal;89
remain(pow51/exp2/sin22/cos14). The accepted prior independent union is387.
These are separate-component results, not one integrated firmware.

On the same63795-input corpus:8078 ->5912 expanded deficits,0new. The
additional52215-input all-cell/rounding corpus has1992 remaining deficits.
The deduplicated111912-pair/223824-state union has42790 parent deficits
and7904 candidate deficits,0new and0 parent-cost increases. All remaining
correct-reference losses and all wrong-reference returns/costs are retained.
No nominal domain filter is applied. pow has no native Qfplib routine:
the pinned comparator follows each original stream; targeted rsqrt uses
qfp_composed_pow_exact(sqrt then divide).

Fresh final public calls443784 ARM/116373 MPFR4.2.2;0wrong. Prior baseline
rows are pinned/inherited and not added. The149484 earlier bare quotient
calls bind through exact actual-module identity to the final unit and
inline runtime; they were not repeated after symbol/guard-only changes.
Trials and the syntax-error launcher are excluded from qualified totals.

Normal original paths298..309 vs old385..386 READY/552..642 DIRTY and
Qfplib307..368. Old hard input5B27CF4AC334ECB8 is304 vs old822/1067 and
Qfplib341. These are instructions in Cortex-M0 Unicorn, not physical cycles.

The two-MUL reciprocal from the existing512 rsqrt seeds yields an exact
uint32 quotient after at most2 remainder corrections. The integer Newton
point is bit-identical to the old pipeline. Exact rational bounds give
seed error<25/8, point error down<15.649/up<3. Only tails[497,514] use the
original exact161-bit boundary. Full proof is RATIONAL-PROOF.md; all512
seed inequalities/reciprocals and exact fractions are in certificate.json.

Extra code776 bytes; no new table, global RAM or libgcc. Static helper
frame64; targeted observed196 ->172, full public stack2236 unchanged.
Targeted candidate executes0 SIO reads/writes in both contexts. Full
intended CPP/ASM emits the tested code; ten complete object/ELF rebuilds
are byte exact. All existing CPP allocated bytes and semantic relocations
match the parent; the new boundary export is storage-free. Only the RP
ASM dispatch section changes. Generic M0 and M4 soft/hard selected CPP/ASM
bytes and relocations match; no whole-M4 firmware was built.

Source patch accepted-pow-to-rsqrt.patch targets the exact accepted parent
source, using an include in the existing ASM TU; no build-list addition.
candidate/ contains the full intended CPP/ASM and includes. whole-source.elf
is a private function overlay, not a bootable/released firmware image.

Open:7904 expanded speed inputs(1992 additional sampled boundary paths),
general pow1024-bit undecided trap/totality, new independent review, combined
repaired-platform integration/regression and device cycles/acceptance. No
canonical/Git/device/Flash/network/release change; the full goal remains open.

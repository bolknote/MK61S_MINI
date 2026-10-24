Private RP2040 double-to-float leaf, frozen for independent review.

All231984 inputs are freshly profiled in READY/DIRTY on candidate, parent
and native Qfplib:1391904 ARM calls,231984 directed MPFR4.2.2 references,
and exact integer RNE every input.0wrong; all raw results match parent,
including NaN sign/payload/quieting. The11004 preliminary probe calls are
excluded. All2048 exponent fields, both signs,20320 generated actual normal
midpoints and1292 subnormal midpoints, all prior28423 raw acquisition
records, payload controls and65536 additional uniform raw bits are included.
Generated midpoint counts are not disjoint corpus sizes.

Observed comparable raw losses103496 ->0; all old512 sample counts/results
reproduce, with426/510 comparable losses ->0. No nominal-domain filter.
All incorrect Qfplib outputs and costs remain in qualification.json.
NUMERIC-PROOF.md gives the author's whole-input RNE proof and a complete
source-derived Qfplib-correct input/instruction partition. proof.json checks
all observed correctness flags and counts against that partition. This is
pending independent mathematical/code acceptance, not a physical-cycle GO.

Instruction paths: zero9 vs Qfplib9; overflow/Inf13 vs13; subnormal-to-normal
19 vs20; lower normal19/22/tie22 vs20/22/tie23..24; upper normal14/17/tie17
vs20/22/tie23..24. Incorrect-reference NaN and other subnormal costs are
also retained. Compared with the old parent,110782 lower-normal state rows
increase by1 instruction; all remain <=correct Qfplib and are preserved
verbatim in retained-parent-regressions.json.

The whole function is256 bytes, previously68 (+188 selected ASM bytes).
No stack, external call, new table/global RAM/libgcc, firmware/ROM/mocks or
SIO access in the candidate. Overall linked firmware size is unmeasured;
possible GC of the old C slow path is not counted. Direct ABI tests use
the newly linked function entry, with no artificial interposition veneer.

Only native_eabi_m0_convert.inc and the new native_eabi_m0_d2f.inc change
relative to the accepted rsqrt parent. Full native_eabi_m0.S and CPP remain
unchanged. Full intended ASM emits the exact256 tested bytes; all other RP
allocated sections and semantic relocations match. Generic M0 and M4
soft/hard selected ASM bytes/relocations match. Four complete object/ELF
rebuilds are byte exact. The source patch requires no build-list changes.

The parent rsqrt90181e2e independent receipt and all22 direct refs were
verified. Original507 reviewed union418 remains unchanged; d2f cold losses
are additional conversion cases. Other open work includes f2d's sampled
loss, FMA acceptance, pow7904 expanded/general1024-bit totality, exp395/ln5,
sin22/cos14 original, combined repaired-platform integration/regression,
hardware cycles and device acceptance. No canonical/Git/device/Flash/release
change and no hardware lease; no whole-math or whole-goal GO.

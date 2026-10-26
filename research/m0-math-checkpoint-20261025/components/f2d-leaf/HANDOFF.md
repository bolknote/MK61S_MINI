Private RP2040 float-to-double leaf, frozen for independent review.

132959 unique inputs, every case profiled READY/DIRTY on candidate, parent
and native Qfplib:797754 fresh ARM calls,132959 directed MPFR4.2.2 and
exact integer widening references.0wrong, every raw result bit matches
parent including NaN sign/payload/quieting. The41490 smoke probe calls are
not added. All256 exponent fields/both signs, all23 subnormal widths with
dense heads/tails and random values, every prior9122 raw record, normal
payload split classes, NaN controls and65536 extra uniform words included.

Normal12 instructions vs old13 / Qfplib13. Either zero5 vs old28 / Qfplib8.
Infinity12 vs Qfplib12. All old256 sample costs/results reproduce and the
one deficit among249 correct references is fixed. Expanded parent4 raw
losses (both zeros and infinities) ->0,0new. Every observed candidate
state is strictly faster than parent; no parent cost increase. Incorrect
reference NaN and subnormal returns/costs remain in qualification.json.
No nominal-domain filter. NUMERIC-PROOF.md gives the author's whole-domain
exact widening proof and complete correct-Qfplib instruction partition.
This is pending independent review, not physical-cycle acceptance.

New function172 bytes vs old ASM34 (+138 selected ASM bytes),0stack,
tables/global RAM/libgcc/external calls/SIO/ROM/mocks. Overall linked size
and GC removal of the old C slow helper are not measured or counted.
Full intended ASM emits exact tested172B; only RP f2d section changes.
The complete d2f256B leaf and every other RP allocated section/semantic
relocation are unchanged. Generic M0/M4 selected ASM bytes/relocations
match; full native_eabi_m0.S and CPP source unchanged. Four complete
object/ELF rebuilds byte exact. Tests use direct new private link address,
no artificial interposition veneer. No build-list addition required.

Qualified parent is .build/m0-d2f-leaf-20261024, pinned unchanged. Its
independent-review availability at seal is recorded separately; do not
infer acceptance from its use as a qualified source parent. Independent
review, combined repaired-platform integration/regression, device/physical
cycles and release remain open. Original507 union418 unchanged; FMA and
pow/exp/ln/sin/cos open work unchanged. No canonical/Git/device/Flash/lease
or release change; no whole-math or whole-goal GO.

# A short IEEE entry for ln

Private RP2040-only child of raw-main-split-family. Replace only the
positive-normal/classification entry, retaining every existing numerical
body, reciprocal, table, error enclosure and fallback in exact source.

The naked leaf starts with low-word==0. If high<<1 is zero, input is
exactly +/-0 and setting high to0xfff00000 returns negative infinity.
Otherwise high==0x7ff00000 returns positive infinity unchanged. For all
other inputs let field=high>>20, the12bit sign/exponent. The subsequent
test ((field+1)>>11)==0 and field!=0 holds exactly for field1..2046,
the positive normals. They tail branch to the unchanged normal source.
All other inputs tail branch to unchanged mk61_m0_ln_special with the
original R0/R1 bits. NaN payload/sign/quiet policy and subnormal handling
therefore remain exact parent behavior. No entry path touches SIO or SP.

The exact naked source fragment is compiled with tagged leaf targets,
not firmware or ROM. Fresh131072ARM calls cover65536raw inputs, all4096
sign/exponent fields, zero/nonzero high fraction/low word and quiet/full
payload classes, both SIO states. Forwarding preserves all64input bits;
PCS/SP/bounded writes and SIO pass. The total observed tagged-unit stack
is16B from the synthetic targets; this is not a public-stack claim.
Actual early-return costs are6instructions for either zero and8 for+Inf.

The outline hides the old caller range fact from GCC. The otherwise
unchanged raw body gains lsls#1/lsrs#21 in place of lsrs#20, explicitly
masking the sign from k. On routed positive normals these are equivalent.
verify-raw-mask.py compares all normalized instructions, literal words
and relocation types/target names: this one added instruction plus an
alignment NOP is the entire raw-object difference, +4B.

Full public qualification retains/recounts all97536parent state cases
and adds IEEE bit-class controls. Fresh48999inputs/97998states are fully
profiled against pinned resident, Qfplib and parent:0wrongMPFR4.2.2,
identical raw outputs/NaN policy, caller SIO/PCS/SP/bounded writes pass.
Both correct and wrong Qfplib outputs and every parent regression remain
in the packet. This is instruction count, not physical cycles. Total
qualified ARM calls391992public+131072bare=523064; parent pack-unit calls
are inherited evidence and are not added again.

Correct-Qfplib losses49raw→46raw/92states, exactly3IEEE raw inputs fixed,
0new. Historical ln improves6/10fixed4open→9/10fixed1open. Overall original
goal producer candidates become301/507 no-slower(295faster6equal), while
independent-review completion remains298/507 until new deltas are reviewed.
Public max stack640same, code+16B. The exact parent polynomial/table source
and other allocated object sections/dependencies match; only naked entry,
outlined normal function and the accounted raw mask differ. Generic-M0/M4
allocated compile controls match; no whole-platform firmware claim.
Whole private CPP/ASM/ELF rebuild byte-exact. Linked addresses relocate.

No canonical source, Git, USB/Flash, numeric release, production integration,
device lease or hardware action. Independent review of both new deltas,
remaining ln/other operations, general pow totality, integration and physical
acceptance remain open under the original goal.

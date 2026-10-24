The RP2040 table-only pow product component is frozen for independent review.

Original pow153:48->35 deficits; all13 new fixes are strict in READY/DIRTY.
The same111912-pair corpus improves7901->7888. The expanded116468-pair
union improves10866->10853,0wrong/0new losses. The additional2965 measured
loss pairs were already slow in the parent. Keep all three Qfplib
compositions, their wrong outputs/costs and all8024 +2 instruction states.

Exact table rowzero uses10 instructions instead of77; other table calls
use79. Other users retain the old77-instruction/154-byte general entry,
including its extra R12 fraction. The real Flash wrapper executes5.
CPP allocated bytes and tables are identical; only3 call relocations
change. ASM allocation adds32B (16RAM including2 alignment +16Flash),
without new tables/global RAM/libgcc. Scratch stays4080B. Static frames
are identical. On the new corpus parent/control/candidate peak2284B;
old2236B was a smaller corpus, not evidence of an increased frame.

314546qualified fresh ARM calls:223824 old candidate +58332 new public
+32390 bare. New validation uses4785 actual directed MPFR inputs +76sNaN
shortcuts. Old MPFR/R/C77/Qfplib rows are inherited, not newly executed.
The3096pilot calls and failed early launcher are excluded. All512 roots,
all16NZCV, PCS/SP/PC and bounded writes are checked. All20 complete
objects/ELFs rebuild byte exactly. See NUMERIC-PROOF/source-proof and
VALIDATION-NOTES for source binding, padding and full reference accounting.

The private diagnostic image relocates existing code/readonly constants
(control58256/candidate58272B). This is not additional algorithmic table
storage or a measured integrated-firmware GC delta. Public entries and
all3 changed call-site sections remain at original addresses. Actual GNU
veneers and real ROM memory/CLZ routines execute; no arithmetic mocks.

Original507 author union436=430strict+6equal;71remain(pow35/sin22/cos14).
Reviewed507 remains422 by ROOT's explicit rule. This is not a combined
library or firmware result. Independent component review, general pow
totality, remaining speed paths, integration, physical cycles and hardware
acceptance remain open. M4/defaultM0 selected CPP/ASM controls are equal;
a complete M4 firmware was not rebuilt. No device or canonical/Git edit.

Integration must merge the source deltas and relink. Loading an old
168-byte product overlay after this new bank would overwrite the new
entry with its old padding. The eventual actual integrated exp image
must rerun its required R12 call/capture/live-range guard.

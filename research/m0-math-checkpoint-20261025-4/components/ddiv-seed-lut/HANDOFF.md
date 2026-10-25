# Author exact seed comparison; not public arithmetic qualification

All65536 divisors and additional table-boundary inputs under all16 NZCV
values pass on ARM for all four variants.77840 tests per variant,389200
actual calls total including one old control. The selected floor128 seed
uses256B constants plus56B code and executes20-27 instructions, replacing
194B unrolled code taking82-97. R1,R12,callee-saved/SP/PC preserved; no
stack or memory writes. Selected control+candidate qualification is155680
calls;233520 calls to the other three variants are experimental and are
not added to the selected child component. Full per-case instruction
records and all compared variant sources are retained.

The integer study has32 configurations, each exhaustively checked over
65536 divisors, but its initial selected128-ceil-inner is exploratory.
selection.json is the final decision. It uses the complete-domain worst
latency, then mean and allocation. A preliminary sample-only selection
chose32 bins because all variants predict the same nine current pow fixes;
selection-corpus-only.json and select-corpus-only.py preserve that discarded
criterion. No numerical ARM evidence was changed or rerun for this decision.
Public pow results in selection.json are predictions, not qualification.
The actual linked caller is separately qualified in
.build/m0-pow-reciprocal-lut-20261025. No global divider, integration,
hardware, M4, main or release acceptance is implied. This frozen directory
must not be used to execute historical producers in place.

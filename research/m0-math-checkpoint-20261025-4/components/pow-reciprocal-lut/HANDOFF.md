# Exact small-table seed caller: author qualification complete

Same120980 pairs/241960states:11386->11377 loss pairs,9 new strict Qfplib
fixes,0wrong/0newloss/0parentcostincreases.377 DIRTY public states save59-73
instructions; READY costs unchanged. All377 changed paths were also freshly
parent-replayed. All10254 fresh controls match the full records. Every public
cost delta equals the measured bare seed delta, with no timing model for the
caller. All279522 reference-state variants, including77106 wrong Qfplib
outputs and costs, are retained without a nominal-domain filter.

Only the194B seed suffix changes, to56B instructions plus256B own integer
constants. It takes20-27 instructions instead of82-97. Total private code
allocation1050->1168B (+118B). All other allocated bytes/addresses, hardware
and software setup, common282B RNE tail, root BL, scratch4080 and other ddiv
callers are unchanged. The linked312B blob matches the tested bare image.
No new global RAM or libgcc dependencies. There are new mathematical table
values, explicitly256B. R3 is newly clobbered inside the private seed, but
the caller saves/restores it; R1/R12, PCS, SP/PC and SIO7words are preserved.

The own finite integer proof checks every65536<=D<=131071: the approximate
quotient differs from floor((2^32-1)/D) by[-1,3]; its exact signed residual
fits32 bits even across product wrap. At most3 downward or1 upward correction
restores the Euclidean invariant. No binary64 approximation bound changes.
The selected bare campaign has77840tests/155680 old+selected ARM calls with
all16 NZCV around table boundaries.233520 calls to the other three variants
are exploratory, excluded from selected qualification. Final selection uses
complete-domain worst latency, not the current public-corpus fit. A discarded
sample-only selection and the initial model choice remain in the frozen seed
comparison packet with explicit historical scope.

Total476133 fresh qualified ARM calls:155680 selectedbare,241960 full
candidate,377 changed parents,61524 fresh public controls/references and
16592 direct operator calls.6761 directed MPFR inputs plus184 sNaN policy
shortcuts;256 fresh exact dyadic operator inputs, plus the bare65536-divisor
integer model. Failed direct calibration24ARM/3MPFR is separately preserved
and excluded: the inherited test selected the original resident parent
symbol instead of its newer private alias. All raw direct Qfplib rows are
retained, including936 wrong variants. No fresh original153 pilot was run;
its score is recounted from the full records. Parent qualification/pilot and
original66288 seed calls are not added as fresh.18 exact source rebuilds pass.

Full observed stack remains2284B; fresh controls2148B each. The changed-path
parent388B is a subset, not a full comparison. Original153 stays119strict/
34slower; author separate507 remains437 and reviewed422. Parent reciprocal
now has independent TECH_GO211cf956. This new seed caller still needs its
own independent review. A ROOT parent receipt, when already present at seal,
is pinned in result.json; no parent or child acceptance is widened here.

This remains a private pow reciprocal component, not a global ddiv or C ABI
replacement. Production merge/relink and actual integrated R12/loader/layout
guards, the old168B-overlay/14B-table-entry hazard, general pow totality,
other needed math, physical cycles and release remain open. No M4/canonical/
Git/device/USB/Flash change or hardware/main/release GO. Historical producers
must never be executed inside these frozen directories. Goal stays active.

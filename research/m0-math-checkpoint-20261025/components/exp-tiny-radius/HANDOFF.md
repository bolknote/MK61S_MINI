Private RP2040 exp tiny-cell rounding component, independent review pending.

Only the RP tiny domain 2^-54<abs(x)<2^-38 changes numerically. Exact
integer midpoint geometry replaces the old uncertain Taylor-cell fallback.
For M0=(2*r+1)*2^(s-1), the quadratic correction is odd_square/2^q,
q1..18. Its integer-distance is >=2^-18; the combined input displacement
and cubic-tail error is <2^-22. Thus its exact floor decides all near
midpoints with one uint32 multiply. Other cells have a strict16385input-ulp
margin. Full author proof is in NUMERIC-PROOF.md/proof.py:49153midpoint
cells,442299model controls, and both actual result-transition neighbors
prepared/executed through the full public exp ABI for every cell.

163675unique inputs/327350states, 558134fresh qualified ARM calls =
327350final candidate +229824new Qfplib +960parent audit.
163673actual directedMPFR4.2.2 conversions +2preMPFRsNaN shortcuts.
Old97526parent/Qfp rows are pinned inherited measurements, not new calls.
Final10446smoke calls and rejected inline trial are excluded.0wrong,
all old48763 returned bits identical. All incorrect Qfp outputs/costs
retained in qualification-records.jsonl.gz; no nominal-domain filter.

On the exact same old48763 corpus,395raw speed losses->154:241fixed.
The larger163675 corpus has669remaining =154old+514new dense endpoint
controls at2^-38+1new ordinary input. Every669loss is proven preexisting
by old/fresh parent measurements (remaining-parent-audit.json);0new raw
regressions. These different-size corpus counts must not be subtracted.
All tiny-domain correct-Qfp paths are faster; observed public74..96ISA
instructions. BC90000000000001:17117->96 vsQfp527. Original16exp still
has2hardcases, unchanged2268vs649 /2248vs622. Original507union418,
residual89 unchanged. Remaining669 are retained in qualification.json.

New196B helper, core5144->5012B, net+64selected CPP bytes. No new tables,
globalRAM/libgcc/ROM or external helper calls. Static core88->96stack,
new helper20; overall observed max376 vs accepted parent736 on the same
old corpus (eliminated tiny refinement), not a universal max guarantee.
All13234known state cost increases vs parent retained; they remain faster
than Qfp. The rejected inline layout made one new ordinary speed loss;
the final outlined layout fixes it. No numerical failure in either trial.

Every other full CPP allocated section/semantic relocation unchanged;
full ASM allocated bytes/relocations including d2f/f2d equal the accepted
f2d parent. Generic M0/M4soft/hard selected CPP byte exact; ASM source
unchanged, inherited generic controls apply. Six complete CPP/ASM
object/ELF rebuilds byte exact. Exact196B helper bytes bound to the full
intended-source linked function; no relocations/external calls. Explicit
PHDRS load only reserved Flash and the accepted168B RAM product, without
ELF headers/padding overwriting resident neighbors. Direct public ABI,
no artificial interposition veneer. No build-list change: one CPP patch.

Accepted f2d review 7561feddf77fd13a7760b930414e68f997898526abaed866c909d39a7efcaeb2 read and all
28receipt/direct refs verified before seal. Source
lineage is composite accepted rsqrt CPP plus accepted d2f/f2d ASM, not
an integrated repaired-platform firmware. Whole firmware/GC size not
claimed. No canonical/Git/USB/device/Flash/lease/EA9/release changes.
Independent review, expanded speed work, generalpow totality, combined
math regression, platform integration and actual physical cycles remain
open. No all-math, production or whole-goal GO.

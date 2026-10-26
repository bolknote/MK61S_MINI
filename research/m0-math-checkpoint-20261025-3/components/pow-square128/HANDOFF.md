# Exact M0+ square128 component: author qualification complete, review pending

Candidate ELF SHA256 `6325d6e1d2d619028f9cb7d156c688ead1795331513941207e9c3de2c1214898`. Parent table-product
FROZEN `dd0ec3663009cd390c710611e57ccc23d18c733201911471feae6e52e58e7d1c` is independently accepted;
its ROOT receipt is `09b8c7326b37b67e106ff517cc594dc02d09fa0643ed96dee47c48af747f6d4d`.
That acceptance is not a review of this new kernel.

The one changed function reproduces all24 old output bytes and error rules.
Four instruction classes:129→94,116→89,195→154,182→149. Kernel stack48→40;
with unchanged helper68→60. Function310→232B, old310B slot retained with padding.
No new table, global RAM, libgcc or ROM-math dependency. Other resident code,
addresses and veneers remain unchanged. GenericM0/M4soft/M4hard selected
assembly controls are equal; no production M4 build or modification is claimed.

The complete old116468-pair corpus /232936states is freshly reexecuted:
all parent raw results identical, exact expected cost reduction, no increases,
losses10853→10850. Fresh5127-pair independent controls use parent/control/
candidate and all3Qfplib compositions, 61524 actual ARM calls,5051 directedMPFR
inputs plus76sNaN shortcuts. All existing public RNE enclosures are unchanged.
Qualification totals330880 fresh ARM calls including36420 bare unit calls;
pilot918 and earlier route70 excluded. Inherited oracle/reference calls are
not fresh. All16NZCV, noisy volatile registers, PCS/SP/PC and bounded writes
are verified in the unit campaign; public SIO READY/DIRTY is checked every call.

Expanded union:120980pairs/241960states/
279522reference-state variants, same-corpus losses
11449→11434,15 fixes,0 new.
The expansion adds596 measured preexisting loss pairs; do not compare counts
across different corpora. All77106wrong Qfplib
variants remain, with strict quiet-NaN classification and no nominal filtering.
Original153 pow deficits35→34, one additional strict fix. Author separate507
union437=431strict+6equal,70remain(pow34/sin22/cos14); reviewed507 stays422.

Thirteen full source objects/ELFs rebuilt byte exact at original paths. Unlike
the larger parent table packet, this one-slot replacement does not change
linker veneer placement. The public old-corpus observed stack peak remains2284;
fresh controls have the same parent/control/candidate2148 peak.

The earlier committed checkpoint correctly recorded this kernel as unfinished
at that time. This later packet supersedes its qualification status only.
Independent review, remaining speed paths, general-pow totality, source merge
with the separately accepted near-one exp sibling, actual merged R12/loader/
layout guards, physical cycles and release remain open. The destructive old
168B table overlay remains forbidden. No canonical source, Git, USB, device,
Flash, hardware lease or release was changed. Overall goal incomplete.


## Independent seal reissue

Authoritative packet: `.build/m0-pow-square128-r2-20261025`.
The first producer directory remains unchanged. Its first seal accidentally
pinned an empty stdout log before the producer appended its closing summary.
Only that log pin failed; all sources, binaries, raw numerical evidence,
proofs and results matched. `REJECTED-SEAL-001.json` preserves that invalid
historical seal and `SEAL-REISSUE.json` describes the failure explicitly.
This second packet is a byte copy with a separately issued valid seal;
all330880 qualified ARM calls and5051 MPFR validations were executed in the
original producer directory and are not claimed as new calls from copying.
Historical rebuild commands retain that original frozen source path and must
not be executed there. No original frozen file was repaired in place.

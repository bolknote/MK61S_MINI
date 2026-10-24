Private RP2040 exact dyadic exp product and79-instruction shared leaf.
Source parent .build/m0-exp-adaptive-enclosure-20261024 is frozen de974c59;
its independent review and this child's review remain pending. The accepted
log-midpoint ancestor bdaba8cf receipt is pinned unchanged. No hardware GO.

Row0 has A=2^62 exactly, all omitted terms zero: the old rounded product is
(|delta|+2)>>2 for every valid displacement. The re-evaluated source bound
proves |delta|+2<2^54. No error radius, gate, endpoint, refinement or IEEE
policy changes. NUMERIC-PROOF.md/certificate.json bind the full source.
70094 literal ARM unit cases use exact128-bit integer product references.

The shared leaf removes SUBsp4/ADDr3,4; argument base and saved registers
retain identical absolute addresses.144 arithmetic bytes and finalPOP are
identical; epilogue ADDsp20->16 restores the same SP and registers. All raw
returns/ABI equivalent.81->79 fixed instructions, active162->158B, allocated
168B slot unchanged with10 nonexecuted outside NOP bytes. Frame40->36B;
actual bytes touched remain36. Word alignment always/public8 alignment at
entry/return; no calls while frame active.70660 old/new raw pair units,
36781 valid exact integer products,0wrong. See validation notes for initial
failed legacy touched-byte counter run, excluded from qualified counts.

Public exp456750 inputs/913500states,0wrong.913500fresh candidate+33486fresh
Qfplib+130parent-audit ARM calls; old880014 parent/reference rows inherited.
456748 actual directedMPFR exp inputs+2sNaN shortcuts.8404 MPFR log-preimage
generations are separate, not validation exp references. Every old440007
raw return identical. Same440007 losses2023->1476:547fixed, all1094states
bound in same-corpus-fixed547.json. Same older48763:126->96. Expanded456750
union1541=1476old+65new measured preexisting losses(53dyadic/12uniform), all
parent-bound,0new losses. All392688wrong-Qfplibstate outputs/costs retained,
no nominal-domain filter. Do not subtract counts from different corpus sizes.
Examples: +2^-32:520->439vsQfp471; -2^-32:542->461vs520. Prior fixed hard
negative599->596vs622; remaining original positive2264->2266vs649.13222
parent state costs+2 retained:200already losing,11950wrongQfp,1072still no
slower than correctQfp. Not a universal per-input parent speed improvement.

Other callers189 originalpow/sin/cos jobs:1134freshARM,189actualMPFR inputs,
raw values/argument traces identical andminus2per actual shared-product call.
Three originalpow gaps become ties:1346->1344vs1344,1322->1320vs1320,
1313->1311vs1311. Pow original51->48, sin22/cos14 unchanged. All prior10085
expandedpow losing reference-state variants replayed by10081distinct fresh
candidate calls:7904->7901pairs,0new,0wrong. Full111912pair references/costs
inherited; no fresh full acquisition/MPFR claim. Nonlosses cannot regress by
the universal monotone callee proof. Pow replay observed1208 stack, original
callers968; no universal fullmath stack bound claimed.

Fresh qualified ARM total1169745=946986mainexp+130parentaudit+141320bare
product+70094literal shift+1134othercallers+10081powlossreplay. Actual directed
MPFR validation456937=456748exp+189callers, plus2sNaN shortcuts. Probe40494,
margin336 and failed initial bare141320 calls excluded; logs and notes pinned.

CPP core5064->5088B(+24), private Flashload16336->16360(+24), RAM code slot
168 same, no new tables/globalRAM/libgcc/ROMmath. Staticcore96same; observed
full publicexp stack744. All3736refine bytes/tiny472helper unchanged. All
other CPP allocated bytes/semantic relocs and all RP ASM bytes/relocs/symbol
addresses outside product slot identical. GenericM0/M4soft/hard selectedCPP
and ASM equal.11 completeobject/ELF rebuilds byte-exact. Actual fullsource
slot==unit==publicoverlay at20038ee4, Flashwrapper and directpublicABI kept.
Two-file patch; no build-list change or wholeM4/platform firmware build.

Author separateoriginal507 union422(413strict9equal),85remain:pow48/exp1/
sin22/cos14. Independently reviewed418 unchanged pending both new reviews.
Expandedexp1541/pow7901/ln5, FMA review, generalpow/exp totality, combined
integration/regression, physicalcycles and release remain open. No canonical,
Git, USB, device, Flash, lease, EA9 or release mutations; goal remains active.

Private RP2040 adaptive exp enclosure and81-instruction shared product.
Independent review pending. Accepted source parent is frozen log-midpoint
5dfdd55…; independent receiptbdaba8cf9bbe58c8e36dafe9b8f904eb8428fdd42db0abb070b5f4a42e472554 read and48direct
refs verified (49including receipt). Prior frozen packets are unchanged.

Normal error4 cells use the actual Q62 table magnitude instead of a
global1/2 upper multiplier. A<(floor(q/2^48)+24)*2^48, reduction/polynomial
delta<275/64, and all remaining product/table/cross errors<129/256.
Signed Q94 bias and a strict integer margin certify distance2/3 cells;
the old distance3 predicate remains intact. NUMERIC-PROOF.md and
certificate.json prove the source-bound enclosure for the full qualifying
normal domain.595004literal actualARM gate cases:0unsafe; all512existing
Q62/Q94table roots recertified. No new table or approximated return mode.

The shared product uses PUSHr0-r7,LR/SUBsp4/baseSP+4 in place of separate
argument stores. Its148-byte arithmetic suffix is byte-identical; all
argument bits, saved registers,SP/return and values are preserved by the
PCS proof. Active body168->162B,84->81fixed instructions for every raw
input.6outside-function NOPbytes retain the168B RAM slot and all following
addresses; they never execute. Frame40same, bytes touched40->36 because
the new4-byte alignment word is unused.70660bare old/new raw pairs,
36781valid63x54integer references,0wrong, constant84/81costs. No external
calls, ROM, globalRAM, new tables or SIO added.

440007public exp inputs/880014states:880014newcandidate+23552newQfp+
2762parentaudit.440005actualdirectedMPFR+2sNaNshortcuts.856462old
parent/Qfp measurements inherited/notnew. New input generation includes
1536directedMPFRlog preimages, not validation exp references.0wrong;
everyold428231rawbit identical. All390568wrong-Qfpstate outputs/costs
retained, no nominal-domain filter. Same428231corpus671->642losses,
29fixed (same older48763:154->126). New440007corpus2023=642old+
1381new controls, every2023loss already lost in parent:0new losses.
Do not subtract counts from different corpus sizes. Every fixed29input
has both states bound in same-corpus-fixed29.json. Originalhardnegative
C041265824E2113C:2248->599vsQfp622. Positive4085F424184F6DC5remains
2264vs649 (parent2268). Originalexp16now1loss instead2.

Product-only callers189originalpow/sin/cosjobs:1134freshARM/189actual
directedMPFR; all argument traces/rawresults identical and every call
saves3instructions. Originalremainingpow51/sin22/cos14 unchanged. All
7904old expandedpowlosses replayed:10081fresh candidate states across
10085reference variants, inherited expectedbits/Qfpcosts,0wrong,7904
remain. Unchanged states cannot regress by monotone callee proof; this
is not a full111912-pair fresh acquisition or newMPFR run. Sin/cos had
no calls to this shared kernel on these original jobs.

Qualified freshARM total1653867=903566mainexp+2762parentaudit+736324
bareunits+1134othercallers+10081powlossreplay. ActualdirectedMPFRvalidation
440194=440005exp+189othercallers, plus2sNaNshortcuts. Final32208probe,
336marginprobe,640stack repeats and rejected/failed trials excluded.
The first numerical unit run completed then failed a deepest-write
versusSPframe accounting assertion; final clean repeat measures both
directly. Logs/VALIDATION-NOTES.json records exclusions. The two earlier
CPP layouts had31new hot-path losses and are rejected, not parents.
Final oldmargin56 and completeoldcorpus pass with0new losses. All200
remaining parent state cost increases(+2/+29) retained;44were already
slower than correctQfp,70have wrongQfp,86remain no slower.

CPP core5012->5064B(+52), existing refine3736B/tiny472B unchanged.
ASM allocatedsize unchanged by retainedslot; privateFlashload+48incl
alignment, fullfirmware/GC size unmeasured. Staticcoreframe96same.
New corpus observed744stack; focused same-input deep parent/child are
both744, not a regression from the old376peak on a smaller corpus.
This is not a universal fullmath stack bound. All other fullCPPsections/
relocations and allRPASMbytes/relocations/symboladdresses outside the
168Bproductslot identical. GenericM0/M4soft/hard selectedCPP+ASM exact.
11completeCPP/ASM/unitobject+ELFrebuildsbyteexact. Actual fullsource
productslot==unit==publicRAM overlay; original20038ee4address/Flash
wrapper and directpublicABI preserved, no artificial veneer. Two-file
patch, no buildlistchange. No wholeM4/repaired-platform firmware build.

New author separateoriginal507union419(413strict6equal),remaining88:
pow51/exp1/sin22/cos14; reviewed418unchanged until this child is accepted.
Expandedexp2023/pow7904/ln5,FMA,generalpow/exp totality,combined math
regression,integration,physicalcycles and release remain open. No
canonical/Git/USB/device/Flash/lease/EA9/release mutations or whole-goalGO.

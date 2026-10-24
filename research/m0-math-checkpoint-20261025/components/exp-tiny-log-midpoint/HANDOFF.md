Private RP2040 exp exact log-midpoint component; independent review pending.

Qualified parent .build/m0-exp-tiny-radius-20261024 is frozen unchanged.
Parent independent-review availability at seal is recorded separately:
{"independent_review_available_at_seal": true, "path": ".build/m0-exp-tiny-radius-independent-20261024/FINAL-REVIEW.json", "sha256": "ac32571a4dd0a31d806f94b6c9c85222ed34278d218115c726d4cb0c11ca4a9d", "status": "GO_PRIVATE_RP_EXP_TINY_RADIUS_COMPONENT_ONLY", "receipt_and_direct_refs_verified": 38}. Do not infer accepted status just from using
its qualified source. Its accepted f2d ancestor and complete lineage are
pinned. This is a function overlay, not a combined or bootable firmware.

Fast domain expands64fold:2^-54<abs(x)<2^-32. Exact input rounding
thresholds are log(1+u)/log(1-u), evaluated symbolically by integer floor
identities, not by runtime logarithms. A=odd²/2^q; the exact cubic floor
and exhaustively certified log-tail separation determine floor(D).
All3145728odd classes have strict rational certificates, all65536/3
reciprocal inputs are exact. This is not3million emulated inputs. The154
cells where the cubic changes a threshold all have both transitions in
the actual public ARM/MPFR corpus:308inputs/616states, including154
actual results that would be wrong with the quadratic-only shortcut.
For odd<65536 one uint32MUL suffices; others use exact44bit square/
66bit cube via accepted wide32, no runtime division or external calls.
NUMERIC-PROOF.md/proof.json give the full author tiny-domain RNE proof.

428231inputs/856462fullyprofiledstates: 1386602fresh qualified ARM =
856462finalcandidate+529112newQfp+1028freshparentremainingaudit.
428229actualdirectedMPFR4.2.2+2preMPFRsNaNshortcuts. All327350previous
parent/Qfprows pinned/inherited, not newly executed.24898finalprobe,
24854supersededtrial and2diagnosticARM calls excluded.0wrong, rawbits
match parent on allold163675inputs. WrongQfp385334state outputs/costs
retained in qualification-records.jsonl.gz. No nominal-domain filter.

Same163675corpus:669->155rawlosses,514fixed. Older48763corpus remains
154. New428231corpus has671=155old+514newdense2^-32endpointneighbors
+2newordinarycontrols; all671losses have old/freshparent costs bound
and all preexisted,0new losses. Counts across different corpus sizes
must not be subtracted. All remaining rows are in qualification.json;
remaining-parent-audit.json binds every new remaining loss. Observed
tinypublic83..200ISA,0losses to numerically correctQfp.3D90000000000000:
520->88vsQfp466;negative counterpart542->84vs528. Original exp2hard
cases remain2268/2248vs649/622. Diagnostic shows546/558instructions
before entering refinement, so their next repair needs a cheap middle
decision or an earlier algorithm; no new algorithm claimed here.

Helper196->472B, net+276selectedCPPbytes, privateFlashload+280including
alignment; fullfirmware/GC size not measured. Core5012B unchangedsize;
only byte3916changes38->32 in ADDSr6,#cutoff. All other core bytes and
relocations match, so ordinary instruction paths outside the expanded
domain are unchanged. All239986knownparentcostincreases retained and
all still fasterQfp. Staticcore96same, helper20->56stack; fullobserved
max376same. No new tables/globalRAM/libgcc/ROM/externalhelpercalls.

All other fullCPPallocatedsections/semanticrelocations unchanged.
FullRPASM including d2f/f2d exactparent. GenericM0/M4soft/hard selected
CPPbytes/relocations exact; ASM source unchanged and inherited controls
apply.6completeCPP/ASMobject+ELFrebuildsbyteexact. Full472Bhelper source
and linked body bound exactly; no helperrelocations. ExplicitPHDRS and
directpublicABI, no artificialveneer. One CPPpatch, no buildlistchange.

Original507separateunion418/residual89 unchanged. Expandedexp671,
pow7904/ln5/sin22/cos14/FMA/generalpowtotality, wholemathregression,
repairedplatform integration, physicalcycles and release remain open.
No canonical/Git/USB/device/Flash/lease/EA9/release mutation. No whole
M4 or integratedfirmware build, productionGO or whole-goalGO.

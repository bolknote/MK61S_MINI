# Private DIRTY reciprocal continuation: author qualification complete

The same 120980-pair / 241960-state corpus now has 11386 loss pairs versus
11434 previously:48 new strict fixes, zero new losses, wrong results or
parent cost increases.377 DIRTY public states save311–380 instructions.
READY costs and all actual parent return bits remain unchanged. All377
changed paths were also freshly replayed on the accepted boundary parent.
All279522 reference-state variants remain, including77106 wrong Qfplib
outputs and costs; every numerically correct reference is compared.

The private root reciprocal BL selects a guarded BSD-derived ddiv clone.
Only its DIRTY branch changes, to a software continuation. The exact seed17
reproduces the hardware integer quotient. Its194B body matches the earlier
exhaustive seed. The282B Newton/remainder/RNE tail is byte-identical in the
hardware and software bodies. Direct tests matched R0..R6,R12,SP and the
20B saved frame in66624 software/hardware joins, including every17-bit
seed divisor. Seed BL SP is8-aligned and all7 DIRTY SIO words are preserved
without any divider write. This continuation is private and requires the
guarded raw operands,R6 and existing20B frame; it is not a standalone ABI.

Fresh qualification comprises842693 actual ARM calls:241960 full candidates,
377 changed-path parents,61524 fresh public MPFR/control/reference calls,
and538832 direct unit/calibration calls. There are6761 directed MPFR inputs
plus184 sNaN policy shortcuts and65536 exact integer/dyadic oracle inputs.
The1836-call/153-MPFR pilot, failed import preflight0, inherited66288 seed
calls and old references/oracles are excluded. The direct proof retains
all936 wrong Qfplib variants; no per-divisor Qfplib speed claim is made for
the exhaustive unit portion whose timing rows were not retained. All public
reference outputs/costs are retained. All10254 fresh public controls match
the full records exactly. Twenty-six source/object/ELF rebuilds are exact.

The diagnostic division section adds1050B, including duplicated existing
32B dyadic constants and a hardware-body clone. There are no new mathematical
table values, global RAM or libgcc dependencies. It is a private pow-caller
experiment: all other ddiv callers remain at the original resident function.
Default M0/M4 selected controls are equal;12 new disabled objects are empty.
Full-corpus observed stack remains2284B; fresh parent/control/candidate
controls are2148B each. The changed-path parent388B is a subset, not a
comparison against the full candidate. No universal stack bound is claimed.

The original153 pow score remains119 strict /34 slower. Author separate507
remains437 no-slower(431 strict,6equal); reviewed separate507 stays422.
This is not one integrated executable or a universal speed claim. The parent
is now independently accepted by ROOT260cb67e. This new component still
requires independent review. Production source merge/relink, actual integrated
R12 consumer and loader/layout guards, the old168B-overlay/14B-table-entry
hazard, general pow totality, other needed math, physical cycles and release
remain open. No hardware/main/release GO, device access or Git change.

Numerical/relational argument:NUMERIC-PROOF.md. Source and disabled controls:
source-proof.json. Raw recount:summary.json. Historical scripts must never
be executed in this frozen directory. FROZEN.json binds this packet and its
source-lineage-pins.json. Overall goal remains active.

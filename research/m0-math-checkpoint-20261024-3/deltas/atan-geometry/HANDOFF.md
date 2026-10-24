# atan geometry extension: six fewer deficits, seventeen observed open

Private RP2040-only child of the immutable independently reviewed
71-bit residual component. This extends its rounding repair to the
exponent-6 denominator-halving geometry, inverted geometry, and a small
outer h region using exact6/7-unit enclosures. No new table, global RAM,
libgcc dependency, firmware or platform change.

The fresh full run profiles **every input**:39,548 unique raw inputs,
79,096 READY/DIRTY state cases and316,384 actual ARM calls. All own and
parent answers pass MPFR4.2.2, with exact parent NaN sign/payload policy.
The retained32,124 parent instruction counts reproduce exactly. The
helper adds30,412 actual ARM calls over denominators from2^58.

Six raw inputs now beat correct Qfplib: one newly measured lower-binade
case plus five of the previous eleven deficits. Their DIRTY costs are
1696-1715 instructions, down from3753 or roughly22,000. The earlier four
hard inputs retain their wins at1728/1753 DIRTY versus1783-1791 Qfplib.
Both signs/states and all raw incorrect Qfplib answers are retained.

Profiling the entire expanded corpus exposes additional preexisting
deficits: the parent has23 and this candidate17 raw inputs slower than
correct Qfplib (34 state rows). There are zero new Qfplib deficits versus
the parent. These include ordinary refinement routes as well as CORE;
do not check only CORE calls or report six remaining inputs from the old
subset. `remaining-slower.json` contains the complete current list.

Against its parent,28 state cases improve,78,922 are equal and146 get
slower. The additions are1,3,4,7 instructions or189/195 when a new repair
attempt declines. Four raw inputs now execute more instructions than
V164; two have correct Qfplib answers and remain on the open list. These
regressions and all raw outputs are kept in `regressions.json`.
Observed peak stack remains888 bytes, equal to the immediate parent.
These are executed instructions, not physical cycle measurements.

Only `.text.atan_fast` changes,1780 versus1748 bytes: net+32 bytes over
the residual parent (+476 versus the packing-only parent). The cold
helper, all other allocated sections, all tables, dependency lists and
resident bindings match. Generic M0/M4 allocated compile controls pass.
An independent public recompile/relink reproduces the entire diagnostic
ELF byte-for-byte. No whole firmware or M4 rebuild is claimed.

Source SHA256 `b8a45df5715c7fbf3e7c5a6d29cd7f063daf8695c7f9324cd4a4647ffb682f7b`.
ELF SHA256 `5cea0e75f3d4a7b29af31c3af6d6315b0e0d569bb7c5a3ca5125bf341cfdecc7`.
Full object SHA256 `a68a1ad91a4ec5931b2ff8ee16afc7982604b414bffb4651077997f9f99dd569`.
`geometry-only.patch`, `PROOF.md`, `certificate.json`, `qualification.json`,
`helper-proof.json`, `isolation.json`, `public-body-proof.json` and
`input-pins.json` bind source, bounds and actual execution.

Independent review of this child is not claimed. Hold it immutable for
inspection. Next polynomial work is separate in
`.build/m0-atan-polynomial-analysis-20261024`: an experimental radius3
model and isolated ARM helper, not an integrated runtime improvement.
Canonical/Git/USB/Flash are untouched. Whole math performance/accuracy,
general pow totality, repaired-base integration and hardware acceptance
remain open.

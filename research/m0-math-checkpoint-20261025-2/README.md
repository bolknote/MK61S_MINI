# M0+ mathematical runtime: sixth intermediate checkpoint

This checkpoint continues `589290345b701153d966f776f6826f332601eb4b`.
It saves the completed table-only `pow` product component, its independent
review, and the unfinished exact 128-bit square replacement. These are
private diagnostic candidates, not an integrated production runtime.

| Saved work | Result and limits |
|---|---|
| Table-only `pow` product | Original 153-point matrix: 48 → 35 remaining deficits, thirteen strict fixes. The same expanded 116,468-pair corpus: 10,866 → 10,853 loss pairs, zero new losses or wrong results. Independent private-component TECH_GO received. |
| Exact 128-bit square | 18,210 unit tests, 36,420 actual ARM calls: all 24 output bytes match the old kernel and integer model. The four measured paths save 27–41 instructions per call; peak kernel plus helper stack falls from 68 to 60 bytes. |
| Public `pow` square pilot | 153 pairs, both SIO states: 918 actual ARM calls and 153 oracle evaluations, zero wrong results or new losses. Original deficits 35 → 34 in this pilot only. Full qualification is prepared but has **not run**; this does not promote the accepted result. |
| Route study | Seventy diagnostic ARM calls on the 35 remaining original pairs. Reordering the root path alone would worsen many inputs; no such change is included. |

The table component preserves all 252,450 reference-state variants,
including 60,686 numerically incorrect Qfplib outputs and their costs.
Comparisons use every numerically correct reference without a nominal
input-domain filter. The broader corpus includes 2,965 newly measured
preexisting loss pairs; counts from different corpora are not subtracted.
The component has 314,546 qualified fresh ARM calls and 4,785 actual
directed MPFR validations plus 76 sNaN policy shortcuts. Reviewer runs
are separate: 1,966 ARM calls and 51 directed MPFR validations plus two
sNaN shortcuts. Historical producer wording saying review pending is
preserved; the later receipt supersedes it only within its stated scope.

The specialized table entry takes ten instructions for its literal dyadic
root and 79 otherwise; the old general entry remains 77 instructions.
All 8,024 state cases with a two-instruction parent cost increase remain
in the records. The change adds 32 allocated assembly bytes while retaining
the 4,080-byte scratch reservation, tables, and public RNE enclosures.

The new square function is 232 bytes, compared with 310 previously, and
pads its existing slot back to 310 bytes to preserve all other addresses.
The original approximate helper and error-radius rules are unchanged.
Default M0 and M4 soft/hard assembly controls compare equal; table-product
controls also cover the selected C++ objects. These checks do not replace
a complete integrated firmware build. Measurements count executed Thumb
instructions, not physical device cycles.

The accepted author's separate union of the historical 507 inputs remains
436 resolved (430 faster, six equal), with 71 remaining: `pow` 35, `sin` 22,
`cos` 14. The square pilot is excluded from that count. The separately
recorded reviewed union remains 422. These are separate component results,
not one executable or a universal speed guarantee.

## Saved material and boundaries

`components/pow-exp-table-product/` contains the immutable author packet;
`reviews/pow-exp-table-product/` contains the later sealed independent
review. The actual source parent is the directed-product component
e6ce/CPP575da330. The accepted near-one `exp` candidate is a separate
sibling and requires a source merge and relink.

An older 168-byte product overlay would overwrite fourteen bytes of the
new table entry. Integration must merge sources and rerun the actual ELF
loader and R12 retained-fraction consumer guards. The current `pow` ELF
has no retained `exp` consumer, so its review does not qualify that caller.

The previous checkpoint omitted the qualified focused `pow` reciprocal-root
report named `probe.json`. Its filename did not mean it was an unqualified
pilot. This checkpoint preserves the lossless correction at
`components/pow-exp-table-product/lineage/qualified-R-focused.json.gz`,
including the 150 additional qualified reference-state variants. Earlier
checkpoints and frozen packets are unchanged.

`work-in-progress/pow-square128/` includes exact control/candidate sources,
the kernel patch, unit and pilot evidence, and the prepared full corpus
and runner. Its `CHECKPOINT-STATUS.json` explicitly records that full
qualification and independent review are pending. `analysis/` preserves
the route study. `status/` is a historical point-in-time ledger; the
explicit checkpoint status takes precedence over stale historical keys.

Binary objects, ELF images, firmware and ROM images are omitted; their
hashes and source rebuild recipes are retained. Large JSON uses deterministic
lossless gzip. `provenance.json` maps each saved artifact to its original
bytes. Historical producer scripts retain their paths and must not be
executed inside the archive.

General `pow` totality, remaining speed paths, full square qualification,
combined integration, physical measurements and release acceptance remain
open. No canonical runtime, device, Flash or M4 production code is changed.
The overall goal is not complete.

## Verification

```sh
python3 research/m0-math-checkpoint-20261025-2/verify.py
python3 research/m0-math-checkpoint-20261025-2/verify.py --check-local
python3 research/m0-math-checkpoint-20261025-2/verify.py \
  --build-output .build/m0-math-checkpoint-r6-replay \
  --toolchain /path/to/arm-none-eabi/bin
```

The verifier checks the previous archive chain, hashes, lossless encoding,
source and review bindings, complete saved table-product accounting, the
unit/pilot accounting, and the prepared corpus. Optional rebuilding uses
only archived sources in a fresh private directory and compares allocated
bytes, symbols and semantic relocations for 31 outputs: eighteen full-source
table-product objects and thirteen square objects/ELFs. Debug path bytes
are excluded. Embedded absolute input paths in historical linker scripts
are remapped to that directory, as are command-line paths. Archive
verification and rebuilding execute no ARM or MPFR
campaign and access no device.

Two table-product ELFs are excluded from that portable byte-exact rebuild
claim. The first replay found absolute input-object paths inside linker
section selectors; these are now remapped. A second replay exposed
path-dependent GNU veneer ordering: regular symbol addresses and section
sizes match, but several veneer addresses, branch encodings and allocated
section hashes differ. The original accepted ELF hashes and fingerprints,
author's twenty original-path rebuilds, and independent review are retained
without calling the relocated ELFs byte-identical. This is a checkpoint
replay limitation, not a new numerical qualification or integration approval.

# M0+ mathematical runtime: fourth intermediate checkpoint

This preserves the next offline research results after `54ec8d6f9`.
The three completed diagnostic components and their independent review
receipts are saved alongside the unfinished next `ln` prototype.

| Component | Qualified result | Independent review |
|---|---|---|
| `atan` small-h lower gate | 58,188 unique inputs / 116,376 profiled READY/DIRTY cases; zero own errors. All 107,542 cases with correct Qfplib answers are faster (107,539) or equal (3). | Narrow component GO |
| Exact busy-divider log quotient | 38,902 bare numerator/denominator pairs and 29,814 public state cases; zero errors. Removes 8,283 DIRTY state deficits; `ln(2)` costs 612 instructions versus Qfplib 711. | Narrow component GO |
| Strict `ln` enclosures and negative n128 dispatch | 19,659 unique inputs / 39,318 public state cases; zero errors. Resolves five of ten historical `ln` deficits and 105 expanded raw deficits. | Narrow component GO |

`atan` has 465,504 public ARM calls plus 75,298 bare helper calls. The last
two observed raw speed deficits now equal Qfplib. The change adds 60 code
bytes over its directional/ninth parent, keeps observed peak stack at
912 bytes, and has 132 parent regressions of 1-7 instructions; all remain
in the evidence. The directional/ninth parent's later independent review
is also saved, without rewriting the preceding checkpoint.

The exact log quotient has 155,608 bare helper calls and 119,256 public
ARM calls. It reuses an existing reciprocal table and retained-product
kernel, with an exact remainder correction. Linked component growth is
160 bytes; READY instruction counts remain identical to its parent.

The strict-enclosure child has 157,272 fresh public ARM calls. Its parent
helper evidence is inherited through identical linked code and addresses;
those calls are not counted again. There are still **34 raw inputs / 65
state cases** slower than correct Qfplib. Against the quotient parent,
18,664 cases improve, 1,662 are equal and 18,992 add one instruction.
Allocated code/data size is unchanged; textual source is changed.
Observed stack is 568 bytes for both components on the expanded corpus.
The current strict-enclosure `ln(2)` DIRTY cost is 613 instructions.

All three retain generic M0 and M4 allocated compile controls, existing
tables/global RAM and undefined dependency sets. M4 controls concern the
guarded translation unit, not a complete M4 firmware rebuild. Counts are
executed ARM instructions, not physical cycles. Saved qualification
retains incorrect Qfplib outputs, all losses and all regressions.

The original 507-input historical matrix remains unchanged. Separate
reviewed candidates now resolve 297 historical deficits (292 strictly
faster, five equal). The remaining 210 are `pow`153, `exp`16, `ln`5,
`sin`22 and `cos`14. Expanded corpora overlap and must not be added to this
count. These are separate components, not an integrated library result.
General `pow` totality, other slow paths, integration and hardware
acceptance remain open.

## Unfinished work

`work-in-progress/ln-near-rounding/` is an exact snapshot of a newly built
prototype. It has **no public qualification, isolation proof or speed
claim**. Its build producer inherited a parent status string; that string
does not qualify this child. Its ELF hash is pinned only for reproducible
continuation. It is excluded from all completed counts above.

The preceding directional study modeled 28 observed near-`ln` losses:
13 pass the plain gate and 15 pass the residual-aware gate. That is a
prospective model, not the prototype's runtime result. Two declined
approximate outputs are wrong, so they must retain refinement. The study
script's `69/128` residual assertion is only checked on its selected
inputs; the universal bound needs the additional `2^-22` term. A runtime
certificate and full qualification remain necessary before using the
prototype. No new table was added.

## Contents and verification

- `deltas/`: completed component sources, patches, producers and evidence.
- `reviews/`: four independent receipts and their supporting records.
- `study/` and `work-in-progress/`: explicitly unfinished continuation.
- `status/`: the progress ledger, including historical entries.
- `provenance.json`: original paths, byte hashes and lossless gzip mapping.

The original component HANDOFF files predate their later reviews. Their
"review not claimed" statements remain historical; the receipts in this
checkpoint establish the current narrow review status. Frozen originals
are preserved byte for byte. Large JSON reports use deterministic gzip.
Binary objects, firmware, ROM images and device backups are omitted.
Historical producer scripts keep private paths; use the verifier below
instead of executing producers inside the archive.

```sh
python3 research/m0-math-checkpoint-20261024-4/verify.py
python3 research/m0-math-checkpoint-20261024-4/verify.py --check-local
python3 research/m0-math-checkpoint-20261024-4/verify.py \
  --build-output .build/m0-math-checkpoint-r4-replay \
  --toolchain /path/to/arm-none-eabi/bin --replay-oracles
```

The verifier checks all preceding archives, saved bytes, review pins,
source/build binding and qualification accounting. Optional rebuilding
reproduces all four public diagnostic ELF/object hashes, including the
unqualified prototype, and the isolated ninth-term and product units.
Optional MPFR replay checks every recorded public output against fresh
references. It does not execute public ARM functions, Qfplib or firmware.
Generated files go to a new private directory; no device is accessed.

# M0+ mathematical runtime: fifth intermediate checkpoint

This saves the offline mathematical work completed after checkpoint
`d0b9cbd6c`. It preserves nineteen component snapshots, their sources,
patches, numerical proofs, complete qualification records, and nineteen
independent component reviews. These are separate diagnostic components;
they have not been integrated into one shipping library.

| Latest component | Saved result | Review |
|---|---|---|
| `ln` quarter/fifth enclosure, after the near-one and quotient repairs | 88,589 inputs, zero wrong results; all ten original deficits resolved; five expanded inputs remain slower | Component GO with documented code, stack and instruction costs |
| `pow` exact square and reciprocal-root assembly, followed by shared-product repairs | Original deficits 153 → 48; expanded inherited 111,912-pair corpus has 7,901 remaining loss pairs | Narrow component reviews; not a general `pow` speed or totality approval |
| `double` → `float` | 231,984 inputs, zero wrong results or losses against correct Qfplib | Component GO |
| `float` → `double` | 132,959 inputs, zero wrong results or losses against correct Qfplib | Component GO |
| Shared exp/pow product | 91 → 77 executed instructions; original 168-byte private RAM slot retained | Component GO, subject to the private R12 contract |
| Directed `exp` enclosure | All sixteen original `exp` deficits strictly resolved; 1,896 losses on its expanded 467,366-input corpus | Component GO and saved root receipt |
| Latest near-one `exp` | On those same 467,366 inputs, 1,896 → 196 losses, 1,700 fixed; full 490,031-input corpus has 214 remaining losses | Private component TECH_GO and root receipt received and verified |

The final `exp` expansion adds eighteen measured, preexisting loss inputs.
Its 214-input count must not be subtracted from a count on a different
corpus. Every remaining loss is bound to its parent. There are zero own
wrong answers and zero new losses against numerically correct Qfplib.
Incorrect Qfplib outputs and their instruction costs remain in the saved
records; there is no nominal-domain filter.

The latest near-one `exp` has 1,203,570 qualified fresh ARM calls and
490,029 actual directed MPFR validations plus two sNaN policy shortcuts.
The separate 2,688 logarithmic preimage generations are not validations.
Inherited parent/reference calls and rejected probes are not added to
fresh totals. The change adds 1,136 code bytes, introduces no new table
or global RAM, and raises observed full-call stack from 744 to 808 bytes.
Its public static frame shrinks from 96 to 88 bytes. The saved records
retain all 5,712 state cases that increase their parent instruction cost.

The shared product returns an additional retained fraction in R12 for
one private caller. Ordinary scalar C ABI conformance does not establish
this contract. The latest builder checks actual disassembly: the two
instructions after the call and the 88-instruction consumer live range.
Seventeen negative guard controls are saved. The guard must be adapted,
installed and rerun against any changed integrated release object.

Generic M0 and M4 compile controls remain equal within the documented
component scope. This is not a complete M4 firmware rebuild. Counts are
executed Thumb instructions, not physical device cycles. No device or
Flash was accessed to create this checkpoint.

The author-observed union of the original 507 historical inputs is
423 resolved (417 faster, six equal), with 84 remaining: `pow` 48,
`sin` 22 and `cos` 14. The separately recorded reviewed union remains
422 by the root coordinator's explicit accounting rule. Neither is a
single integrated executable, nor a universal speed guarantee. Expanded
corpora overlap and are not added to this historical count.

General `pow` totality, the remaining speed paths, FMA review, combined
integration, physical cycle measurements and release acceptance remain
open. The overall goal is not complete.

## Preserved material

`components/` contains the successive completed candidates, including
the eight `ln`/quotient stages, both `pow` stages, both conversions and
seven `exp`/shared-product stages. `reviews/` and `root-receipts/` contain
the available independent receipts without changing their original
wording. A historical HANDOFF that says review pending is superseded
only within the scope of its later saved receipt.

The near-one receipt arrived during checkpoint preparation. Its reviewer
ran 1,587 actual ARM calls, 176 directed MPFR validations plus two sNaN
shortcuts, 138 additional enclosure checks, five byte-exact rebuilds and
the fresh R12 guard with seventeen negative controls. These are separate
reviewer counts. All 51 direct root pins were reverified here. The saved
clarification makes the middle-product error interval exactly **(-3, 0]**;
zero is included. Frozen author reports retain their original pending
wording. The component receipt does not promote the reviewed whole-507
union or authorize integration or hardware access.

`work-in-progress/pow-exp-table-product/` contains an unchanged source
copy and its scope record. It is **not built or qualified** and has no
new performance result. `rejected/` preserves the separate tighter tiny
curvature trial's rejection record; its calls are excluded from qualified
totals. Intermediate trial binaries, firmware/ROM images and device
backups are omitted. Large JSON uses deterministic lossless gzip.

`provenance.json` maps every saved file to its original path and byte
hash. Original frozen manifests retain hashes of omitted binary files.
Producer scripts keep their historical paths; do not execute them inside
this archive. `status/` is a point-in-time ledger containing historical
entries as well as the latest explicitly named component results.

## Verification

```sh
python3 research/m0-math-checkpoint-20261025/verify.py
python3 research/m0-math-checkpoint-20261025/verify.py --check-local
python3 research/m0-math-checkpoint-20261025/verify.py \
  --build-output .build/m0-math-checkpoint-r5-replay \
  --toolchain /path/to/arm-none-eabi/bin
```

The verifier checks the preceding checkpoint chain, saved hashes and
lossless encodings, source/result bindings, review pins and every saved
public qualification row. It recounts losses, parent cost increases and
incorrect Qfplib answers. This recount is not a new ARM or MPFR campaign.
Optional rebuilding materializes only archived sources in a fresh private
directory and checks allocated bytes, symbols and semantic relocations
against frozen originals. Debug path differences are excluded from that
rebuild comparison; complete historical ELF hashes remain pinned. No
canonical file, original frozen packet or device is modified.
